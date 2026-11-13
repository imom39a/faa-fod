"""PROTOTYPE (ticket 0012) - hybrid end-to-end: local Candidates -> Haiku decisions -> Sonnet escalation
-> Critical-Angle Haiku whole-frame safety net. Throwaway; scores against the spike ground truth.

Per Angle (frame), all API work for that Angle runs in parallel with the other Angles:
  1. decide   claude-haiku-5-5: context frame (1280x720, numbered boxes) + per Candidate a 320 px native
              crop of the current frame AND of the clean reference + spec/fod-rules.md -> structured JSON decision per Candidate.
  2. escalate claude-sonnet-5-5: Critical Angles only (ENG-L, ENG-R, NOSE), Candidates Haiku was not
              'high' confidence about (either way). Sonnet's decision replaces Haiku's.
  3. net      claude-haiku-5-5 whole-frame FOD pass (spike prompt, 2560x1440) on Critical Angles, run in
              parallel with 1. Net findings with no Candidate within 60 px become new Candidates and go
              through 1 (+2).
Findings = decisions with is_fod true. Scored with the spike's 150 px matcher (same as the baseline).

usage:
  set -a; source ../../.env; set +a      # key only enters this process' environment
  .venv/bin/python -I hybrid.py results/cand__union_20_0.6.json [--vlm] [--no-net] [--tag name] [--limit N]
Stops all API work on a billing/credit error, or when spend passes --budget (default $1.5).
"""
import argparse
import base64
import io
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import run_spike as S  # noqa: E402

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
RULES = (C.ROOT / "spec/fod-rules.md").read_text()
MAX_CANDS = 30
CTX_W, CTX_H = 1280, 720

SPEC_CATEGORIES = ["fasteners_hardware", "aircraft_parts", "tools", "luggage_parts", "catering_flightline",
                   "cargo_packaging", "pavement_construction", "natural", "unidentified", "not_fod"]

DECIDE_SYSTEM = f"""You are the reasoning step of an airline FOD (Foreign Object Debris) inspection system for aircraft gates.
A local image model has proposed Candidates: regions of a fixed-camera frame that changed or look unusual. Most Candidates are NOT FOD: lighting changes, shadows, stains, markings, pavement texture, reflections, noise, people, vehicles and equipment.
For each Candidate decide whether it is FOD on the ground, using the airline rule set below. For each Candidate you get the CURRENT native-resolution crop (the red rectangle marks the Candidate; judge only what is inside it) and a REFERENCE crop of the same pixels from a recent clean frame of the same fixed camera (taken at a different time, so lighting, noise and shadows may differ slightly). Use the context frame for where it is.

Decide FOD when the current crop shows a distinct physical object lying on the ground inside the rectangle that is not in the reference. There is no minimum size: a small, compact object that is new relative to the reference is FOD even if you cannot identify it (FOD-R5, category unidentified). Decide not_fod when the rectangle shows the same thing in both crops, or only pavement, texture, a stain, a brightness/shadow change, markings, the aircraft, people, vehicles or equipment in normal positions.
Severity follows the rule set's zone tier x object class matrix; cite the rule that applies (FOD-R1/R2 Critical, R3 Service, R4 General, R5 unidentified, R8 misplaced equipment). For not_fod use severity NONE and rule NONE. Confidence never lowers severity.

<rule_set>
{RULES}
</rule_set>"""

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "candidate_id": {"type": "integer"},
                "what_is_visible": {"type": "string"},
                "is_fod": {"type": "boolean"},
                "category": {"type": "string", "enum": SPEC_CATEGORIES},
                "object_class": {"type": "string", "enum": ["hard", "light", "natural", "unidentified", "none"]},
                "severity": {"type": "string", "enum": ["HOLD", "REMOVE", "ADVISORY", "NONE"]},
                "rule": {"type": "string", "enum": [f"FOD-R{i}" for i in range(1, 9)] + ["NONE"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["candidate_id", "what_is_visible", "is_fod", "category", "object_class", "severity", "rule", "confidence"],
            "additionalProperties": False}},
    },
    "required": ["decisions"],
    "additionalProperties": False,
}

MATRIX = {"Critical": {"hard": "HOLD", "light": "HOLD", "unidentified": "HOLD", "natural": "HOLD"},
          "Service": {"hard": "REMOVE", "light": "REMOVE", "unidentified": "REMOVE", "natural": "REMOVE"},
          "General": {"hard": "REMOVE", "light": "ADVISORY", "unidentified": "REMOVE", "natural": "ADVISORY"}}


class StopAPI(Exception):
    pass


REFS = {}
STATE = {"spent": 0.0, "stopped": None, "calls": 0}
LOCK = threading.Lock()


def b64(rgb, q=90):
    buf = io.BytesIO(); Image.fromarray(rgb).save(buf, "JPEG", quality=q)
    return base64.standard_b64encode(buf.getvalue()).decode()


def context_image(bgr, cands):
    im = cv2.resize(bgr, (CTX_W, CTX_H), interpolation=cv2.INTER_AREA)
    s = CTX_W / bgr.shape[1]
    for f in cands:
        x1, y1, x2, y2 = (int(v * s) for v in f["box"])
        cv2.rectangle(im, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (0, 0, 255), 2)
        cv2.putText(im, str(f["cid"]), (x1 - 4, max(12, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


def guard(fn):
    """Run one API call; convert billing/credit errors into StopAPI; enforce the budget."""
    import anthropic
    with LOCK:
        if STATE["stopped"]:
            raise StopAPI(STATE["stopped"])
        if STATE["spent"] > ARGS.budget:
            STATE["stopped"] = f"budget ${ARGS.budget} reached"
            raise StopAPI(STATE["stopped"])
    try:
        return fn()
    except anthropic.APIStatusError as e:
        msg = str(getattr(e, "message", e))
        if e.status_code == 402 or getattr(e, "type", "") == "billing_error" or "credit" in msg.lower() or "billing" in msg.lower():
            with LOCK:
                STATE["stopped"] = f"billing/credit error HTTP {e.status_code}"
            raise StopAPI(STATE["stopped"])
        raise


def account(model, usage):
    pin, pout = S.PRICES[model]
    c = (usage.input_tokens * pin + usage.output_tokens * pout) / 1e6
    with LOCK:
        STATE["spent"] += c; STATE["calls"] += 1
    return c


def decide(client, model, name, bgr, cands, angle, tier, ref=None):
    content = [{"type": "text", "text": f"Context frame ({CTX_W}x{CTX_H}, downscaled from 3840x2160; Candidates numbered in red):"},
               {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64(context_image(bgr, cands), 85)}}]
    for f in cands:
        rgb, _ = C.crop_candidate(bgr, f["box"])
        content += [{"type": "text", "text": f"Candidate {f['cid']} CURRENT (native-resolution crop):"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64(rgb)}}]
        if ref is not None:
            rr, _ = C.crop_candidate(ref, f["box"])
            content += [{"type": "text", "text": f"Candidate {f['cid']} REFERENCE (same pixels, recent clean frame):"},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64(rr)}}]
    content.append({"type": "text", "text": (
        f"Angle: {angle}. Zone tier: {tier}. Decide every Candidate ({len(cands)} in total, ids "
        f"{[f['cid'] for f in cands]}). Return one decision per Candidate.")})

    def call():
        t0 = time.time()
        with client.messages.stream(model=model, max_tokens=16000, system=DECIDE_SYSTEM, thinking={"type": "adaptive"},
                                    output_config={"effort": "medium", "format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
                                    messages=[{"role": "user", "content": content}]) as st:
            msg = st.get_final_message()
        return msg, time.time() - t0
    msg, dt = guard(call)
    cost = account(model, msg.usage)
    text = next((b.text for b in msg.content if b.type == "text"), "")
    try:
        dec = json.loads(text)["decisions"] if msg.stop_reason == "end_turn" else []
    except (json.JSONDecodeError, KeyError):
        dec = []
    return {d["candidate_id"]: dict(d, model=model) for d in dec}, {"model": model, "s": round(dt, 2), "cost": cost,
                                                                     "in": msg.usage.input_tokens, "out": msg.usage.output_tokens,
                                                                     "stop": msg.stop_reason, "n": len(cands)}


def safety_net(client, name):
    def call():
        return S.call_claude(client, HAIKU, "whole", C.IMAGES / name, "medium")
    r = guard(call)
    with LOCK:
        STATE["spent"] += r["est_cost_usd"]; STATE["calls"] += 1
    return r


def run_angle(client, name, cands):
    angle = C.ANGLE_OF[C.GT[name]["frame"]]; tier = C.TIER_OF[angle]
    bgr = C.load(name)
    ref = REFS.setdefault(C.GT[name]["frame"], C.make_reference(C.GT[name]["frame"]))
    calls, t0 = [], time.time()
    cands = [dict(f, cid=i + 1, origin="local") for i, f in enumerate(cands[:MAX_CANDS])]
    with ThreadPoolExecutor(2) as ex:
        net_fut = ex.submit(safety_net, client, name) if (tier == "Critical" and not ARGS.no_net) else None
        decisions = {}
        if cands:
            decisions, info = decide(client, HAIKU, name, bgr, cands, angle, tier, ref); calls.append(info)
        net = net_fut.result() if net_fut else None
    t_first = time.time() - t0
    extra = []
    if net:
        calls.append({"model": HAIKU, "s": net["latency_s"], "cost": net["est_cost_usd"], "kind": "net", "n": len(net["findings"])})
        for f in net["findings"]:
            if not any(S.centre_dist(f["box"], c["box"]) < C.CAND_RADIUS for c in cands + extra):
                extra.append({"box": f["box"], "score": 0, "src": "net", "cid": len(cands) + len(extra) + 1, "origin": "net",
                              "net_desc": f.get("description"), "net_conf": f.get("confidence")})
        if extra:
            d2, info = decide(client, HAIKU, name, bgr, extra, angle, tier, ref); info["kind"] = "net-verify"; calls.append(info)
            decisions.update(d2)
    allc = cands + extra
    esc = [c for c in allc if tier == "Critical" and decisions.get(c["cid"], {}).get("confidence") != "high"]
    if esc:
        ts = time.time()
        d3, info = decide(client, SONNET, name, bgr, esc, angle, tier, ref); info["kind"] = "escalate"; calls.append(info)
        for k, v in d3.items():
            v["haiku"] = decisions.get(k); decisions[k] = v
    rows = []
    for c in allc:
        d = decisions.get(c["cid"])
        rows.append({**{k: v for k, v in c.items()}, "decision": d})
    findings = [{"box": r["box"], "description": r["decision"]["what_is_visible"], "confidence": r["decision"]["confidence"],
                 "severity": r["decision"]["severity"], "rule": r["decision"]["rule"], "category": r["decision"]["category"],
                 "object_class": r["decision"]["object_class"], "decided_by": r["decision"]["model"], "origin": r["origin"]}
                for r in rows if r["decision"] and r["decision"]["is_fod"]]
    for f in findings:
        f["matrix_severity"] = MATRIX[tier].get(f["object_class"])
    return {"angle": angle, "tier": tier, "candidates": rows, "findings": findings, "calls": calls,
            "api_wall_s": round(time.time() - t0, 2), "api_first_stage_s": round(t_first, 2),
            "cost": sum(c["cost"] for c in calls), "undecided": sum(1 for r in rows if not r["decision"])}


def main():
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("cands"); ap.add_argument("--vlm", action="store_true", help="input is a vlm__ file; drop VLM 'no'")
    ap.add_argument("--no-net", action="store_true"); ap.add_argument("--tag", default="")
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--only", nargs="*")
    ap.add_argument("--budget", type=float, default=1.5); ap.add_argument("--workers", type=int, default=6)
    ARGS = ap.parse_args()
    import anthropic
    client = anthropic.Anthropic(max_retries=3)
    data = json.loads(Path(ARGS.cands).read_text())
    names = ARGS.only or sorted(data)
    if ARGS.limit:
        names = names[:ARGS.limit]
    out_path = C.RESULTS / f"hybrid__{Path(ARGS.cands).stem}{'__' + ARGS.tag if ARGS.tag else ''}.json"
    results = json.loads(out_path.read_text())["results"] if out_path.exists() else {}

    def work(n):
        if n in results:
            return
        f = data[n]["findings"]
        if ARGS.vlm:
            f = [x for x in f if x.get("vlm_yes")]
        try:
            r = run_angle(client, n, f)
        except StopAPI as e:
            print(f"{n}: STOPPED ({e})", flush=True); return
        r["local_s"] = data[n].get("latency_s")
        if ARGS.vlm:
            r["vlm_s"] = round(sum(x.get("vlm_s", 0) for x in data[n]["findings"]), 2)
        with LOCK:
            results[n] = r
            out_path.write_text(json.dumps({"source": ARGS.cands, "vlm": ARGS.vlm, "net": not ARGS.no_net, "results": results}, indent=1, default=float))
        print(f"{n} [{r['angle']}]: {len(f)} cands -> {len(r['findings'])} findings; calls={[(c['model'][7:12], c.get('kind', 'decide'), c['n']) for c in r['calls']]} "
              f"{r['api_wall_s']}s ${r['cost']:.4f} (total ${STATE['spent']:.3f})", flush=True)

    with ThreadPoolExecutor(ARGS.workers) as ex:
        list(ex.map(work, names))
    print("spent", round(STATE["spent"], 4), "calls", STATE["calls"], "stopped:", STATE["stopped"])
    print("wrote", out_path)


if __name__ == "__main__":
    main()
