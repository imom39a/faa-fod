"""PROTOTYPE (ticket 0012) - score hybrid runs vs the Claude-only baseline (spike Sonnet tiles).

Final Findings use the spike's matcher (150 px / IoU>0.1) so numbers are comparable with the baseline.
Inspection = the frames sharing a variant (clean, fod1, fod2: 6 Angles; noop: 4 Angles).
  cost / Inspection     = sum over its Angles (6-Angle Inspections only)
  API latency           = max over Angles (Angles run in parallel)
  local latency (seq)   = sum of per-frame proposer time (one Mac, frames one after another)
usage: .venv/bin/python -I score_hybrid.py results/hybrid__*.json
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import run_spike as S  # noqa: E402

ADJ = json.loads((C.SPIKE / "adjudication.json").read_text())["pre_existing"]
BASE = C.SPIKE / "results/pred__claude-sonnet-5-5__tiles__medium.json"


def metrics(preds, per_frame_cost, api_s, local_s):
    S.IGNORE.clear()
    per = S.score(C.IMAGES, {"results": preds})
    a = S.aggregate(per)
    S.IGNORE.update(ADJ)
    adj = S.aggregate(S.score(C.IMAGES, {"results": preds}))
    S.IGNORE.clear()
    groups = {}
    for n in preds:
        groups.setdefault(n.split("__")[1].removesuffix(".jpg"), []).append(n)
    six = [g for g in groups.values() if len(g) == 6]
    insp_cost = statistics.mean(sum(per_frame_cost[n] for n in g) for g in six)
    insp_api = [max(api_s[n] for n in g) for g in six]
    insp_local = [sum(local_s[n] for n in g) for g in six] if local_s else None
    clean = [p for p in per if p["kind"] == "clean"]; noop = [p for p in per if p["kind"] == "noop"]
    return {
        "recall": f"{a['tp']}/{a['objects']} ({a['recall']:.0%})",
        "fa_clean": sum(len(p["false_alarms"]) for p in clean) / len(clean),
        "fa_noop": sum(len(p["false_alarms"]) for p in noop) / len(noop),
        "fa_control": a["fa_per_control_image"], "fa_control_adj": adj["fa_per_control_image"],
        "fa_all": a["fa_per_image"], "fa_all_adj": adj["fa_per_image"],
        "controls_zero_fa": f"{a['control_images_clean']}/{a['control_images']}",
        "cost_per_insp": insp_cost, "api_s_insp": statistics.median(insp_api),
        "local_s_insp": statistics.median(insp_local) if insp_local else 0.0,
        "per": per,
    }


def hybrid(path):
    d = json.loads(Path(path).read_text())["results"]
    preds = {n: {"findings": r["findings"], "latency_s": r["api_wall_s"]} for n, r in d.items()}
    cost = {n: r["cost"] for n, r in d.items()}
    api = {n: r["api_wall_s"] for n, r in d.items()}
    local = {n: (r.get("local_s") or 0) + (r.get("vlm_s") or 0) for n, r in d.items()}
    m = metrics(preds, cost, api, local)
    m["undecided"] = sum(r["undecided"] for r in d.values())
    m["calls"] = sum(len(r["calls"]) for r in d.values())
    m["escalated_cands"] = sum(c["n"] for r in d.values() for c in r["calls"] if c.get("kind") == "escalate")
    m["total_cost"] = sum(cost.values())
    m["severity_mismatch"] = sum(1 for r in d.values() for f in r["findings"] if f["severity"] != f.get("matrix_severity"))
    m["n_findings"] = sum(len(r["findings"]) for r in d.values())
    m["net_found"] = [(n, f["description"][:50]) for n, r in d.items() for f in r["findings"] if f["origin"] == "net"]
    return m


def baseline():
    d = json.loads(BASE.read_text())["results"]
    return metrics(d, {n: r["est_cost_usd"] for n, r in d.items()}, {n: r["latency_s"] for n, r in d.items()}, None)


def main():
    rows = [("Claude-only Sonnet 5.5 tiles (spike baseline)", baseline())] + [(Path(p).stem, hybrid(p)) for p in sys.argv[1:]]
    print("| run | recall | FA/clean | FA/noop | FA/control (adj.) | controls w/ 0 FA | $/6-Angle Inspection | API s / Inspection (parallel) | local s / Inspection (sequential) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for lab, m in rows:
        print(f"| {lab} | {m['recall']} | {m['fa_clean']:.2f} | {m['fa_noop']:.2f} | {m['fa_control']:.2f} ({m['fa_control_adj']:.2f}) "
              f"| {m['controls_zero_fa']} | {m['cost_per_insp']:.3f} | {m['api_s_insp']:.1f} | {m['local_s_insp']:.1f} |")
    for lab, m in rows:
        print(f"\n== {lab}")
        for k in ("undecided", "calls", "escalated_cands", "total_cost", "severity_mismatch", "n_findings", "net_found"):
            if k in m:
                print(f"  {k}: {m[k]}")
        for p in m["per"]:
            if p["missed"] or p["false_alarms"]:
                print(f"  {p['image']}: missed={p['missed']} FA={[(f['box'], (f['desc'] or '')[:70], f['conf']) for f in p['false_alarms']]}")


if __name__ == "__main__":
    main()
