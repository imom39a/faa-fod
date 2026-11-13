"""Score the pipeline against ground truth on every scene in app/data/testset.json.

    uv run python -m fodgate.evaluate [--limit N] [--dry-run] [--out DIR]

Reports recall (overall and in Critical zones), false alarms per clean Angle, severity agreement, INCOMPLETE
correctness, equipment-staging hits, cost and latency per Inspection, with mirrored / cropped Angles reported
separately, and compares against targets NF-1..NF-3. `--dry-run` runs the local stages only (no API calls)
and scores the Candidates instead of Findings. Writes results.json and summary.md to app/var/eval/.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from . import config, pipeline
from .detect.geometry import CAND_RADIUS, MATCH_RADIUS, centre_dist, iou, scale_for
from .llm import LLM, process_spend
from .scenes import Scene, SceneNotFound, load_scene, load_testset

TARGETS = {"NF-1 cost per Inspection (USD)": ("cost_per_inspection_mean", "<=", 0.05),
           "NF-2 seconds per Inspection": ("latency_s_mean", "<=", 20.0),
           "NF-3 recall overall": ("recall_overall", ">=", 0.90),
           "NF-3 recall in Critical zones": ("recall_critical", ">=", 0.95),
           "NF-3 false alarms per clean Angle": ("false_alarms_per_clean_angle", "<=", 0.5)}


def match(truth: list[dict], found: list[dict], radius: float) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Greedy one-to-one matching by centre distance (within `radius`, or IoU > 0.1).
    Returns (pairs of (truth index, found index), unmatched truth indices, unmatched found indices)."""
    pairs = sorted((centre_dist(t["bbox"], f["bbox"]), ti, fi) for ti, t in enumerate(truth) for fi, f in enumerate(found))
    mt, mf, out = set(), set(), []
    for d, ti, fi in pairs:
        if ti in mt or fi in mf:
            continue
        if d <= radius or iou(truth[ti]["bbox"], found[fi]["bbox"]) > 0.1:
            mt.add(ti)
            mf.add(fi)
            out.append((ti, fi))
    return out, [i for i in range(len(truth)) if i not in mt], [i for i in range(len(found)) if i not in mf]


def expected_verdict(scene: Scene) -> str:
    usable = [a for a in scene.angles.values() if a.declared_usable]
    if any(a.ground_truth for a in usable):
        return "FINDINGS"
    return "INCOMPLETE" if len(usable) < len(scene.angles) else "ALL_CLEAR"


def score_scene(scene: Scene, report: dict, candidates: dict[str, list[dict]] | None) -> dict:
    """Per-Angle rows for one Inspection. With `candidates` (dry run) Candidates are scored in place of Findings."""
    rows = []
    for name, spec in scene.angles.items():
        entry = next((a for a in report["angles"] if a["angle"] == name), None)
        got_unusable = entry is None or entry["status"] != "usable"
        scale = scale_for((entry or {}).get("width") or 3840)
        if candidates is not None:
            found = [{"bbox": c["box"], "severity": None, "finding_type": "fod"} for c in candidates.get(name, [])]
            radius = max(12.0, CAND_RADIUS * scale)
        else:
            found = [f for f in report["findings"] if f["angle"] == name and not f.get("carried_from_inspection_id")]
            radius = MATCH_RADIUS * scale
        truth = spec.ground_truth if spec.declared_usable else []
        pairs, missed, extra = match(truth, found, radius)
        rows.append({
            "scene_id": scene.scene_id, "angle": name, "derived": spec.derived or "native", "light": scene.light,
            "truth_unusable": not spec.declared_usable, "got_unusable": got_unusable,
            "unusable_reason": (entry or {}).get("unusable_reason"),
            "n_truth": len(truth), "n_found": len(found), "tp": len(pairs),
            "matches": [{"label": truth[ti].get("label"), "zone_tier": truth[ti].get("zone_tier"),
                         "finding_type": truth[ti].get("finding_type", "fod"),
                         "got_finding_type": found[fi].get("finding_type"),
                         "expected_severity": truth[ti].get("expected_severity"), "severity": found[fi].get("severity")}
                        for ti, fi in pairs],
            "missed": [{"label": truth[i].get("label"), "zone_tier": truth[i].get("zone_tier"),
                        "finding_type": truth[i].get("finding_type", "fod"), "bbox": truth[i]["bbox"]} for i in missed],
            "false_alarms": [{"bbox": found[i]["bbox"], "description": found[i].get("description"),
                              "severity": found[i].get("severity")} for i in extra],
        })
    return {"rows": rows}


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def aggregate(rows: list[dict], inspections: list[dict], dry_run: bool) -> dict:
    def recall(rs, pred=lambda item: True):
        hit = sum(1 for r in rs for m in r["matches"] if pred(m))
        miss = sum(1 for r in rs for m in r["missed"] if pred(m))
        return _ratio(hit, hit + miss), hit, hit + miss

    def block(rs):
        clean = [r for r in rs if r["n_truth"] == 0 and not r["truth_unusable"] and not r["got_unusable"]]
        seeded = [r for r in rs if r["n_truth"] > 0]
        rec, hit, total = recall(rs)
        crit, chit, ctotal = recall(rs, lambda m: m["zone_tier"] == "critical")
        return {"angles": len(rs), "objects": total, "found": hit, "recall_overall": rec,
                "critical_objects": ctotal, "critical_found": chit, "recall_critical": crit,
                "clean_angles": len(clean),
                "false_alarms_on_clean_angles": sum(len(r["false_alarms"]) for r in clean),
                "false_alarms_per_clean_angle": _ratio(sum(len(r["false_alarms"]) for r in clean), len(clean)),
                "extra_findings_on_seeded_angles": sum(len(r["false_alarms"]) for r in seeded)}

    out = block(rows)
    out["by_derivation"] = {
        "native": block([r for r in rows if r["derived"] == "native"]),
        "mirrored_or_cropped": block([r for r in rows if r["derived"] != "native"]),
    }
    sev = [m for r in rows for m in r["matches"] if m["expected_severity"] and m["severity"]]
    out["severity_agreement"] = _ratio(sum(1 for m in sev if m["expected_severity"] == m["severity"]), len(sev))
    out["severity_compared"] = len(sev)
    _, eq_hit, eq_total = recall(rows, lambda m: m["finding_type"] == "equipment_staging")
    typed = sum(1 for r in rows for m in r["matches"]
                if m["finding_type"] == "equipment_staging" and m.get("got_finding_type") == "equipment_staging")
    out["equipment_staging"] = {"expected": eq_total, "located": eq_hit, "reported_as_equipment_staging": typed}
    unusable_truth = [r for r in rows if r["truth_unusable"]]
    out["unusable_angles"] = {
        "expected": len(unusable_truth), "detected": sum(1 for r in unusable_truth if r["got_unusable"]),
        "usable_angles_wrongly_unusable": sum(1 for r in rows if not r["truth_unusable"] and r["got_unusable"])}
    out["inspections"] = len(inspections)
    out["incomplete_correct"] = _ratio(sum(1 for i in inspections if i["missing_angles_correct"]), len(inspections))
    lat = [i["latency_s"] for i in inspections]
    out["latency_s_mean"] = round(statistics.mean(lat), 2) if lat else None
    out["latency_s_median"] = round(statistics.median(lat), 2) if lat else None
    out["latency_s_max"] = round(max(lat), 2) if lat else None
    if not dry_run:
        out["verdict_correct"] = _ratio(sum(1 for i in inspections if i["verdict"] == i["expected_verdict"]), len(inspections))
        cost = [i["est_cost_usd"] for i in inspections]
        out["cost_per_inspection_mean"] = round(statistics.mean(cost), 5) if cost else None
        out["cost_per_inspection_max"] = round(max(cost), 5) if cost else None
        out["spent_usd_this_run"] = round(sum(i["spent_usd"] for i in inspections), 5)
    return out


def targets(summary: dict, dry_run: bool) -> list[dict]:
    out = []
    for name, (key, op, bound) in TARGETS.items():
        value = summary.get(key)
        if value is None or (dry_run and key != "latency_s_mean"):
            out.append({"target": name, "bound": f"{op} {bound}", "value": None, "met": None})
        else:
            out.append({"target": name, "bound": f"{op} {bound}", "value": value,
                        "met": value <= bound if op == "<=" else value >= bound})
    return out


def markdown(result: dict) -> str:
    s, dry = result["summary"], result["dry_run"]
    what = "Candidates (local stages only, no API)" if dry else "Findings"

    def pct(v):
        return "n/a" if v is None else f"{100 * v:.1f}%"

    def row(name, b):
        return (f"| {name} | {b['angles']} | {b['found']}/{b['objects']} ({pct(b['recall_overall'])}) | "
                f"{b['critical_found']}/{b['critical_objects']} ({pct(b['recall_critical'])}) | "
                f"{b['false_alarms_on_clean_angles']} on {b['clean_angles']} "
                f"({'n/a' if b['false_alarms_per_clean_angle'] is None else b['false_alarms_per_clean_angle']}) |")

    lines = [f"# Evaluation summary ({'dry run' if dry else 'full pipeline'})", "",
             f"Run at {result['run_at']} on {s['inspections']} Inspection(s) from `{result['data_dir']}`. "
             f"Scored: {what}.", ""]
    if dry:
        lines += ["A dry run measures the local proposer only: recall here is Candidate recall, and "
                  "\"false alarms\" are Candidates on clean Angles, which the decision step would still filter.", ""]
    lines += ["## Targets", "", "| Target | Bound | Measured | Met |", "|---|---|---|---|"]
    for t in result["targets"]:
        met = "not measured" if t["met"] is None else ("yes" if t["met"] else "NO")
        lines.append(f"| {t['target']} | {t['bound']} | {'n/a' if t['value'] is None else t['value']} | {met} |")
    lines += ["", "## Detection", "", f"| Angles | n | Recall ({what.split()[0]}) | Recall, Critical zones | False alarms on clean Angles (per Angle) |",
              "|---|---|---|---|---|", row("All", s), row("Native", s["by_derivation"]["native"]),
              row("Mirrored or cropped", s["by_derivation"]["mirrored_or_cropped"]), ""]
    u, e = s["unusable_angles"], s["equipment_staging"]
    lines += ["## Other measures", "",
              f"- Severity agreement on matched Findings: {pct(s['severity_agreement'])} of {s['severity_compared']}.",
              f"- Unusable Angles detected: {u['detected']}/{u['expected']}; usable Angles wrongly marked unusable: "
              f"{u['usable_angles_wrongly_unusable']}.",
              f"- Inspections whose list of missing Angles is exactly right (INCOMPLETE correctness): {pct(s['incomplete_correct'])}.",
              f"- Equipment staging (FOD-R9): {e['located']}/{e['expected']} located, {e['reported_as_equipment_staging']} "
              "reported as equipment staging.",
              f"- Latency per Inspection: mean {s['latency_s_mean']} s, median {s['latency_s_median']} s, max {s['latency_s_max']} s."]
    if not dry:
        lines += [f"- Verdict correct: {pct(s['verdict_correct'])}.",
                  f"- Cost per Inspection: mean ${s['cost_per_inspection_mean']}, max ${s['cost_per_inspection_max']} "
                  f"(uncached price). Actually spent in this run: ${s['spent_usd_this_run']} (cache hits are free)."]
    missed = [(r["scene_id"], r["angle"], m["label"], m["zone_tier"]) for r in result["rows"] for m in r["missed"]]
    lines += ["", "## Missed objects", ""] + ([f"- {a} {b}: {c} ({d})" for a, b, c, d in missed] or ["None."])
    fas = [(r["scene_id"], r["angle"], f.get("description") or "Candidate", f["bbox"]) for r in result["rows"]
           if r["n_truth"] == 0 for f in r["false_alarms"]]
    if not dry:
        lines += ["", "## False alarms on clean Angles", ""] + ([f"- {a} {b}: {c} at {d}" for a, b, c, d in fas] or ["None."])
    if result["skipped"]:
        lines += ["", "## Skipped scenes", ""] + [f"- {k}: {v}" for k, v in result["skipped"].items()]
    lines += ["", "## Limits to state with these results", "",
              "- Debris is composited, and reference frames are simulated with nothing moving between frames.",
              "- No Concourse T imagery: the photos are stand-ins.",
              "- Detector thresholds were fixed on the 22-frame spike set and not re-tuned here.", ""]
    return "\n".join(lines)


def run(limit: int | None = None, dry_run: bool = False, out_dir: Path | None = None, llm: LLM | None = None) -> dict:
    scene_ids = load_testset()
    if limit:
        scene_ids = scene_ids[:limit]
    if not dry_run and llm is None:
        llm = LLM()
        ok, why = llm.available()
        if not ok:
            raise SystemExit(f"Cannot run the full pipeline: {why}. Use --dry-run for the local stages only.")
    rows, inspections, skipped = [], [], {}
    for sid in scene_ids:
        try:
            scene = load_scene(sid)
        except SceneNotFound:
            skipped[sid] = "scene.json not found"
            continue
        t0 = time.time()
        report, details = pipeline.run_inspection(scene, gate="EVAL", turn_id=f"eval-{sid}", llm=None if dry_run else llm,
                                                  return_details=True)
        latency = round(time.time() - t0, 2)
        cands = {a: r.candidates for a, r in details.items()} if dry_run else None
        scored = score_scene(scene, report, cands)
        rows += scored["rows"]
        want_missing = sorted(a for a, s in scene.angles.items() if not s.declared_usable)
        meta = report["run_metadata"]
        inspections.append({
            "scene_id": sid, "kind": scene.kind, "light": scene.light, "inspection_id": report["inspection_id"],
            "verdict": report["verdict"], "expected_verdict": expected_verdict(scene),
            "missing_angles": report["missing_angles"], "expected_missing_angles": want_missing,
            "missing_angles_correct": sorted(report["missing_angles"]) == want_missing,
            "latency_s": latency, "timings_ms": meta["timings_ms"], "est_cost_usd": meta["est_cost_usd"],
            "spent_usd": meta["spent_usd"], "llm_calls": len(meta["llm_calls"]), "notes": meta["notes"]})
        print(f"{sid}: verdict={report['verdict']} findings={len(report['findings'])} missing={report['missing_angles']} "
              f"{latency}s ${meta['est_cost_usd']:.4f}", flush=True)
        stopped = process_spend()["stopped"]
        if stopped and not dry_run:
            skipped["(remaining scenes)"] = f"API calls stopped: {stopped}"
            break
    summary = aggregate(rows, inspections, dry_run)
    result = {"run_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "data_dir": str(config.data_dir()), "dry_run": dry_run,
              "limit": limit, "summary": summary, "targets": targets(summary, dry_run), "inspections": inspections,
              "rows": rows, "skipped": skipped}
    out_dir = out_dir or config.var_dir() / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    (out_dir / "summary.md").write_text(markdown(result))
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fodgate.evaluate", description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="only the first N scenes of the test set")
    ap.add_argument("--dry-run", action="store_true", help="local stages only; no API calls")
    ap.add_argument("--out", type=Path, default=None, help="output directory (default app/var/eval)")
    a = ap.parse_args(argv)
    result = run(limit=a.limit, dry_run=a.dry_run, out_dir=a.out)
    out_dir = a.out or config.var_dir() / "eval"
    print(markdown(result))
    print(f"wrote {out_dir / 'results.json'} and {out_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
