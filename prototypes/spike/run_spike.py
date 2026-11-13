"""PROTOTYPE (spike 0007) - throwaway harness. Not production code.

Sends labelled gate/apron frames to Claude, asks for FOD Findings as structured
JSON with pixel bounding boxes, and scores them against ground truth.

Commands
  run     call the API:   run_spike.py run <images_dir> <out_dir> --model claude-opus-5-5 --mode whole|tiles
  prepare write the exact images the API would see (for inspection / proxy runs):
                          run_spike.py prepare <images_dir> <out_dir> --mode whole|tiles
  score   score a predictions file:  run_spike.py score <images_dir> <predictions.json>
  table   summarise several runs:    run_spike.py table <images_dir> <pred1.json> [<pred2.json> ...]

Auth: a normal Anthropic() client (ANTHROPIC_API_KEY or `ant auth login` profile).
Run with:  set -a; source ../../.env; set +a; .venv/bin/python -I run_spike.py run ...

Modes
  whole  frame resized to 2560x1440 (<= 2576 px long edge, ~4.7k visual tokens) so
         Claude sees exactly the pixels we send; boxes are scaled x1.5 back to 3840x2160.
  tiles  frame cut into 2x2 overlapping 2048x1152 tiles (no downscale, ~3k tokens each),
         all 4 tiles sent in ONE request; boxes come back per tile and are offset back.
"""
import argparse
import base64
import io
import json
import math
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

FULL_W, FULL_H = 3840, 2160
WHOLE_SIZE = (2560, 1440)
TILE_W, TILE_H = 2048, 1152
TILE_ORIGINS = [(0, 0), (FULL_W - TILE_W, 0), (0, FULL_H - TILE_H), (FULL_W - TILE_W, FULL_H - TILE_H)]
TILE_NAMES = ["top-left", "top-right", "bottom-left", "bottom-right"]

# $ per million tokens (input, output). Source: claude-api skill model table, cached 2026-11-03.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}

CATEGORIES = ["tool_or_hardware", "fastener_or_small_metal", "plastic_or_wrapping", "paper_or_tag",
              "luggage_part", "can_or_bottle", "rock_or_pavement_debris", "rubber_or_hose_or_wire",
              "other_unknown"]

SYSTEM_PROMPT = """You are an airport ramp-safety inspector reviewing fixed-camera images of a narrowbody aircraft gate (apron/stand).

Task: find FOD (Foreign Object Debris) ON THE GROUND: any loose object lying on the apron surface that does not belong there and could be ingested by an engine, cut a tyre or injure someone. Typical FOD: tools (wrenches, pliers, hammers, screwdrivers, cutters), bolts, nuts, washers, safety wire, metal strips, rocks or pavement chunks, plastic bags, wrapping, bottle or can, bag tags, luggage parts, rags, rubber pieces, hose or wire pieces.

NOT FOD (do not report): the aircraft and its parts; jet bridge; ground support equipment (tugs, belt loaders, carts, dollies, stairs, fuel trucks, GPU, hoses connected to the aircraft); people; deliberately placed safety cones and wheel chocks; painted markings, stand numbers, lines; cracks, joints, stains, oil spots, puddles, tyre marks, shadows and reflections; grass and things far off the apron (buildings, roads, other stands in the background).

Look carefully across the whole ground surface, including small, dark or partly shadowed objects. Small objects may be only 10-30 pixels across. Report each distinct suspected object once. If you see nothing, return an empty findings list. Prefer reporting a genuinely suspicious small object with confidence "low" over silently ignoring it, but do not report normal equipment or markings.

Coordinates: give each finding a tight bounding box in ABSOLUTE PIXELS of the image it appears in, origin at the top-left, x to the right, y down, as x1,y1 (top-left corner) and x2,y2 (bottom-right corner)."""

USER_WHOLE = "Image: one {w}x{h} px camera frame of the gate. Return all FOD findings with pixel boxes in this image's coordinates. Use image_index 0 for every finding."
USER_TILES = ("The camera frame is split into 4 overlapping tiles, each {w}x{h} px, given in order as image_index 0=top-left, "
              "1=top-right, 2=bottom-left, 3=bottom-right. Objects in the overlap may appear in two tiles; report them in either. "
              "Return all FOD findings; for each, set image_index to the tile it appears in and give the pixel box in THAT TILE's coordinates.")

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "image_index": {"type": "integer", "enum": list(range(24))},
                    "x1": {"type": "integer"}, "y1": {"type": "integer"},
                    "x2": {"type": "integer"}, "y2": {"type": "integer"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "description": {"type": "string"},
                    "location": {"type": "string", "description": "short verbal location, e.g. 'left of nose gear, near the cone'"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                },
                "required": ["image_index", "x1", "y1", "x2", "y2", "category", "description", "location", "confidence"],
                "additionalProperties": False,
            },
        },
        "scene_notes": {"type": "string"},
    },
    "required": ["findings", "scene_notes"],
    "additionalProperties": False,
}


# ----------------------------------------------------------------- images
def views_for(path: Path, mode: str):
    """Return list of (PIL image, (offset_x, offset_y), scale) exactly as sent."""
    im = Image.open(path).convert("RGB")
    assert im.size == (FULL_W, FULL_H), im.size
    if mode == "whole":
        return [(im.resize(WHOLE_SIZE, Image.LANCZOS), (0, 0), FULL_W / WHOLE_SIZE[0])]
    return [(im.crop((ox, oy, ox + TILE_W, oy + TILE_H)), (ox, oy), 1.0) for ox, oy in TILE_ORIGINS]


def b64jpeg(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode()


def user_text(mode: str) -> str:
    return USER_WHOLE.format(w=WHOLE_SIZE[0], h=WHOLE_SIZE[1]) if mode == "whole" else USER_TILES.format(w=TILE_W, h=TILE_H)


def to_full_frame(findings, mode):
    """Map raw findings (per-view pixel coords) to 3840x2160 boxes, dedupe tile overlaps."""
    out = []
    for f in findings:
        i = f.get("image_index", 0) if mode == "tiles" else 0
        if mode == "whole":
            s, (ox, oy) = FULL_W / WHOLE_SIZE[0], (0, 0)
        else:
            s, (ox, oy) = 1.0, TILE_ORIGINS[i]
        x1, x2 = sorted((f["x1"], f["x2"])); y1, y2 = sorted((f["y1"], f["y2"]))
        box = [ox + x1 * s, oy + y1 * s, ox + x2 * s, oy + y2 * s]
        out.append({**f, "box": [round(v) for v in box]})
    # dedupe (tile overlap): drop a finding whose box overlaps / is near an earlier one
    kept = []
    for f in out:
        if any(iou(f["box"], k["box"]) > 0.2 or centre_dist(f["box"], k["box"]) < 40 for k in kept):
            continue
        kept.append(f)
    return kept


# ----------------------------------------------------------------- API
def build_content(paths, mode):
    """One frame -> USER_WHOLE/USER_TILES. Several frames (an Inspection) -> numbered images."""
    content, k = [], 0
    for fi, path in enumerate(paths):
        for ti, (im, _, _) in enumerate(views_for(path, mode)):
            if len(paths) > 1:
                lab = f"Angle {fi + 1}" + (f", {TILE_NAMES[ti]} tile" if mode == "tiles" else "")
                content.append({"type": "text", "text": f"image_index {k} ({lab}):"})
            elif mode == "tiles":
                content.append({"type": "text", "text": f"image_index {ti} ({TILE_NAMES[ti]} tile):"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64jpeg(im)}})
            k += 1
    if len(paths) == 1:
        content.append({"type": "text", "text": user_text(mode)})
    else:
        per = 1 if mode == "whole" else 4
        size = f"{WHOLE_SIZE[0]}x{WHOLE_SIZE[1]}" if mode == "whole" else f"{TILE_W}x{TILE_H} (2x2 overlapping tiles per Angle: top-left, top-right, bottom-left, bottom-right)"
        content.append({"type": "text", "text": (
            f"This Inspection has {len(paths)} camera Angles of the same kind of gate scene, {per} image(s) per Angle, each {size} px. "
            "Inspect every image. For each FOD finding set image_index to the image it appears in and give the pixel box in THAT image's coordinates.")})
    return content


def call_claude(client, model, mode, path, effort):
    paths = path if isinstance(path, list) else [path]
    content = build_content(paths, mode)
    t0 = time.time()
    # Streaming + get_final_message avoids HTTP timeouts with adaptive thinking.
    # NOTE: no server-side `fallbacks` on purpose - a silent model swap would contaminate the
    # per-model comparison. Refusals are recorded instead (stop_reason).
    with client.messages.stream(
        model=model,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": FINDINGS_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        msg = stream.get_final_message()
    dt = time.time() - t0
    text = next((b.text for b in msg.content if b.type == "text"), "")
    try:
        parsed = json.loads(text) if msg.stop_reason == "end_turn" else {"findings": [], "scene_notes": ""}
    except json.JSONDecodeError:
        parsed = {"findings": [], "scene_notes": "UNPARSEABLE"}
    u = msg.usage
    pin, pout = PRICES.get(model, (0, 0))
    cost = (u.input_tokens * pin + u.output_tokens * pout) / 1e6
    return {
        "image": ",".join(p.name for p in paths), "model": model, "served_model": msg.model, "mode": mode, "effort": effort,
        "stop_reason": msg.stop_reason, "latency_s": round(dt, 2),
        "usage": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens}, "est_cost_usd": round(cost, 5),
        "raw": parsed, "findings": to_full_frame(parsed.get("findings", []), mode) if len(paths) == 1 else None,
    }


def cmd_run(a):
    import anthropic
    client = anthropic.Anthropic()
    imgs = sorted(Path(a.images_dir).glob("*.jpg"))
    if a.limit:
        imgs = imgs[: a.limit]
    out_dir = Path(a.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"pred__{a.model}__{a.mode}__{a.effort}.json"
    prior = json.loads(out_path.read_text()) if out_path.exists() else {"results": {}}
    results = prior["results"]
    lock, spent = threading.Lock(), [sum(r.get("est_cost_usd", 0) for r in results.values())]

    def work(p):
        if p.name in results and results[p.name].get("stop_reason") == "end_turn":
            return
        with lock:
            if spent[0] > a.budget:
                print(f"budget {a.budget} reached, skipping {p.name}"); return
        try:
            r = call_claude(client, a.model, a.mode, p, a.effort)
        except anthropic.APIStatusError as e:
            print(f"{p.name}: API error {e.status_code}: {e.message}"); return
        except anthropic.APIConnectionError as e:
            print(f"{p.name}: connection error {e}"); return
        with lock:
            results[p.name] = r; spent[0] += r["est_cost_usd"]
            print(f"{p.name}: {len(r['findings'])} findings, {r['latency_s']}s, "
                  f"in={r['usage']['input_tokens']} out={r['usage']['output_tokens']} ${r['est_cost_usd']:.3f} (run total ${spent[0]:.2f})")
            out_path.write_text(json.dumps({"model": a.model, "mode": a.mode, "effort": a.effort, "results": results}, indent=1))

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(work, imgs))
    print(f"wrote {out_path}")
    print_summary(score(Path(a.images_dir), json.loads(out_path.read_text())), out_path.name)


def cmd_inspect(a):
    """Multi-Angle Inspection: all frames sharing a suffix (clean/noop/fod1/fod2) in ONE request."""
    import anthropic
    client = anthropic.Anthropic()
    groups = {}
    for p in sorted(Path(a.images_dir).glob("*.jpg")):
        groups.setdefault(p.stem.split("__")[1], []).append(p)
    out_path = Path(a.out_dir) / f"pred__{a.model}__inspection-{a.mode}__{a.effort}.json"
    results, per_view = {}, (1 if a.mode == "whole" else 4)
    for g, paths in groups.items():
        r = call_claude(client, a.model, a.mode, paths, a.effort)
        print(f"inspection {g}: {len(paths)} angles, {r['latency_s']}s, in={r['usage']['input_tokens']} out={r['usage']['output_tokens']} ${r['est_cost_usd']:.3f} stop={r['stop_reason']}")
        for fi, p in enumerate(paths):
            mine = [dict(f, image_index=f["image_index"] - fi * per_view) for f in r["raw"].get("findings", [])
                    if fi * per_view <= f["image_index"] < (fi + 1) * per_view]
            results[p.name] = {"image": p.name, "inspection": g, "latency_s": r["latency_s"], "stop_reason": r["stop_reason"],
                               "usage": {k: v / len(paths) for k, v in r["usage"].items()},
                               "est_cost_usd": r["est_cost_usd"] / len(paths), "findings": to_full_frame(mine, a.mode)}
        out_path.write_text(json.dumps({"model": a.model, "mode": "inspection-" + a.mode, "effort": a.effort, "results": results}, indent=1))
    print_summary(score(Path(a.images_dir), json.loads(out_path.read_text())), out_path.name)


def cmd_prepare(a):
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    for p in sorted(Path(a.images_dir).glob("*.jpg")):
        for i, (im, _, _) in enumerate(views_for(p, a.mode)):
            suffix = "" if a.mode == "whole" else f"__t{i}"
            im.save(out / f"{p.stem}{suffix}.jpg", quality=90)
    (out / "PROMPT.txt").write_text(SYSTEM_PROMPT + "\n\n---\n" + user_text(a.mode) + "\n\n---schema---\n" + json.dumps(FINDINGS_SCHEMA, indent=1))
    print(f"prepared {a.mode} views in {out}")


# ----------------------------------------------------------------- scoring
def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def centre(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def centre_dist(a, b):
    (ax, ay), (bx, by) = centre(a), centre(b)
    return math.hypot(ax - bx, ay - by)


def grid_cell(pt, n=4):
    return (min(n - 1, int(pt[0] / (FULL_W / n))), min(n - 1, int(pt[1] / (FULL_H / n))))


MATCH_RADIUS = 150  # px at 3840x2160: a finding "counts" if its centre is this close to the object (or IoU>0.1)


IGNORE = {}  # frame -> [[x1,y1,x2,y2,why], ...]  set via --ignore (adjudication.json)


def score(images_dir: Path, preds: dict):
    gt = json.loads((images_dir / "ground_truth.json").read_text())["images"]
    per = []
    for name, g in gt.items():
        r = preds["results"].get(name)
        if r is None:
            continue
        finds = list(r["findings"])
        ign = IGNORE.get(g["frame"], [])
        pre = [f for f in finds if any(z[0] <= centre(f["box"])[0] <= z[2] and z[1] <= centre(f["box"])[1] <= z[3] for z in ign)]
        finds = [f for f in finds if f not in pre]
        objs = g["objects"]
        # greedy match by centre distance
        pairs = sorted(((centre_dist(o["box"], f["box"]), oi, fi) for oi, o in enumerate(objs) for fi, f in enumerate(finds)))
        mo, mf, matches = set(), set(), []
        for d, oi, fi in pairs:
            if oi in mo or fi in mf:
                continue
            if d <= MATCH_RADIUS or iou(objs[oi]["box"], finds[fi]["box"]) > 0.1:
                mo.add(oi); mf.add(fi); matches.append((oi, fi, d))
        loc = []
        for oi, fi, d in matches:
            ob, fb = objs[oi]["box"], finds[fi]["box"]
            gw, gh = ob[2] - ob[0], ob[3] - ob[1]
            loc.append({
                "label": objs[oi]["label"], "iou": round(iou(ob, fb), 3), "centre_err_px": round(d, 1),
                "pred_box_area_ratio": round(((fb[2] - fb[0]) * (fb[3] - fb[1])) / max(1, gw * gh), 2),
                "grid4_hit": grid_cell(centre(fb)) == grid_cell(centre(ob)),
                "inside_pred_box": fb[0] <= centre(ob)[0] <= fb[2] and fb[1] <= centre(ob)[1] <= fb[3],
            })
        per.append({
            "image": name, "kind": g["kind"], "n_gt": len(objs), "tp": len(matches),
            "missed": [objs[i]["label"] + f"({objs[i]['long_px']}px)" for i in range(len(objs)) if i not in mo],
            "false_alarms": [{"box": finds[i]["box"], "desc": finds[i].get("description", ""), "conf": finds[i].get("confidence")}
                             for i in range(len(finds)) if i not in mf],
            "pre_existing_found": len(pre), "loc": loc, "latency_s": r.get("latency_s"), "cost": r.get("est_cost_usd", 0),
            "usage": r.get("usage", {}),
        })
    return per


def aggregate(per):
    n_gt = sum(p["n_gt"] for p in per); tp = sum(p["tp"] for p in per)
    seeded = [p for p in per if p["kind"] == "seeded"]; ctrl = [p for p in per if p["kind"] != "seeded"]
    loc = [l for p in per for l in p["loc"]]
    fa_all = sum(len(p["false_alarms"]) for p in per)
    fa_ctrl = sum(len(p["false_alarms"]) for p in ctrl)
    fa_hc = sum(1 for p in per for f in p["false_alarms"] if f["conf"] != "low")
    lat = sorted(p["latency_s"] for p in per if p["latency_s"] is not None)
    med = lambda xs: (sorted(xs)[len(xs) // 2] if xs else None)
    return {
        "images": len(per), "objects": n_gt, "recall": tp / n_gt if n_gt else None, "tp": tp,
        "seeded_images_any_hit": sum(1 for p in seeded if p["tp"] > 0), "seeded_images": len(seeded),
        "fa_per_image": fa_all / len(per) if per else None,
        "fa_per_control_image": fa_ctrl / len(ctrl) if ctrl else None,
        "control_images_clean": sum(1 for p in ctrl if not p["false_alarms"]), "control_images": len(ctrl),
        "fa_non_low_conf": fa_hc,
        "median_iou": med([l["iou"] for l in loc]), "iou_ge_0_5": sum(l["iou"] >= 0.5 for l in loc),
        "iou_ge_0_3": sum(l["iou"] >= 0.3 for l in loc),
        "median_centre_err_px": med([l["centre_err_px"] for l in loc]),
        "centre_le_50px": sum(l["centre_err_px"] <= 50 for l in loc),
        "inside_pred_box": sum(l["inside_pred_box"] for l in loc),
        "grid4_hit": sum(l["grid4_hit"] for l in loc), "n_loc": len(loc),
        "median_latency_s": med(lat), "max_latency_s": lat[-1] if lat else None,
        "total_cost": sum(p["cost"] or 0 for p in per),
        "mean_in_tokens": sum(p["usage"].get("input_tokens", 0) for p in per) / max(1, len(per)),
        "mean_out_tokens": sum(p["usage"].get("output_tokens", 0) for p in per) / max(1, len(per)),
    }


def print_summary(per, title):
    s = aggregate(per)
    print(f"\n== {title}")
    for k, v in s.items():
        print(f"  {k}: {round(v, 3) if isinstance(v, float) else v}")
    for p in per:
        if p["missed"] or p["false_alarms"]:
            print(f"  {p['image']}: missed={p['missed']} FA={[(f['box'], f['desc'][:60], f['conf']) for f in p['false_alarms']]}")


def load_ignore(a):
    if getattr(a, "ignore", None):
        IGNORE.update(json.loads(Path(a.ignore).read_text())["pre_existing"])


def cmd_score(a):
    load_ignore(a)
    preds = json.loads(Path(a.predictions).read_text())
    per = score(Path(a.images_dir), preds)
    print_summary(per, a.predictions)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps({"summary": aggregate(per), "per_image": per}, indent=1))


def cmd_table(a):
    load_ignore(a)
    print("| run | recall | img w/ any hit | FA/img (all) | FA/control img | clean controls | median IoU | IoU>=0.5 | IoU>=0.3 | median centre err (px@4K) | centre<=50px | GT centre inside box | 4x4 grid cell hit | median latency s | mean in/out tokens | est. cost $ |")
    print("|" + "---|" * 16)
    for pth in a.predictions:
        preds = json.loads(Path(pth).read_text())
        s = aggregate(score(Path(a.images_dir), preds))
        n = s["n_loc"] or 1
        print(f"| {Path(pth).stem.replace('pred__', '')} | {s['tp']}/{s['objects']} ({s['recall']:.0%}) | {s['seeded_images_any_hit']}/{s['seeded_images']} "
              f"| {s['fa_per_image']:.2f} | {s['fa_per_control_image']:.2f} | {s['control_images_clean']}/{s['control_images']} "
              f"| {s['median_iou']} | {s['iou_ge_0_5']}/{n} | {s['iou_ge_0_3']}/{n} | {s['median_centre_err_px']} | {s['centre_le_50px']}/{n} "
              f"| {s['inside_pred_box']}/{n} | {s['grid4_hit']}/{n} | {s['median_latency_s']} | {s['mean_in_tokens']:.0f}/{s['mean_out_tokens']:.0f} | {s['total_cost']:.2f} |")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("images_dir"); r.add_argument("out_dir")
    r.add_argument("--model", default="claude-opus-5-5"); r.add_argument("--mode", choices=["whole", "tiles"], default="whole")
    r.add_argument("--effort", default="medium"); r.add_argument("--workers", type=int, default=4)
    r.add_argument("--limit", type=int, default=0); r.add_argument("--budget", type=float, default=2.0)
    i = sub.add_parser("inspect"); i.add_argument("images_dir"); i.add_argument("out_dir")
    i.add_argument("--model", default="claude-opus-5-5"); i.add_argument("--mode", choices=["whole", "tiles"], default="whole")
    i.add_argument("--effort", default="medium")
    p = sub.add_parser("prepare"); p.add_argument("images_dir"); p.add_argument("out_dir"); p.add_argument("--mode", choices=["whole", "tiles"], default="whole")
    s = sub.add_parser("score"); s.add_argument("images_dir"); s.add_argument("predictions"); s.add_argument("--json-out"); s.add_argument("--ignore")
    t = sub.add_parser("table"); t.add_argument("images_dir"); t.add_argument("predictions", nargs="+"); t.add_argument("--ignore")
    a = ap.parse_args()
    {"run": cmd_run, "inspect": cmd_inspect, "prepare": cmd_prepare, "score": cmd_score, "table": cmd_table}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
