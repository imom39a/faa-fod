"""One Inspection end to end: images in, report out (spec/inspection-report-schema.md + contract additions).

Per Angle (PL-1..PL-8):
  1. usability check (local, plus what scene.json declares);
  2. local Candidates: change detection against the reference frame, DINOv2 added on night / low-contrast
     Angles when available;
  3. tiled Haiku safety net on Critical Angles; its hits become Candidates;
  4. Haiku structured-output decision per Candidate batch (current crop + reference crop + context frame + rules);
  5. code computes zone tier, object class, severity, rule ID and the Verdict.
With no reference frame, steps 2-3 are replaced by a tiled Claude pass on that Angle and the report says so.
"""
from __future__ import annotations

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import config, report as R
from .detect import change, dino, usability
from .detect.geometry import CAND_RADIUS, MATCH_RADIUS, centre_dist, crop_candidate, imread, same_object, scale_for
from .llm import LLM, CallRecord, LLMError, short_model
from .rules import RuleSet, box_centre, is_equipment_staging, load_rules, size_class
from .scenes import AngleSpec, Scene

ANALYSIS_FAILED = "analysis_failed"   # contract deviation: extra unusable_reason when the reasoning step failed


def new_inspection_id() -> str:
    return "insp-" + uuid.uuid4().hex[:10]


@dataclass
class AngleResult:
    entry: dict
    findings: list[dict] = field(default_factory=list)
    dismissed: list[dict] = field(default_factory=list)
    observations: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    calls: list[CallRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    usability: dict = field(default_factory=dict)
    local_models: list[dict] = field(default_factory=list)
    local_ms: int = 0
    bgr: np.ndarray | None = None
    ref: np.ndarray | None = None


# ---------------------------------------------------------------------- one Angle
def analyse_angle(*, scene: Scene, spec: AngleSpec, image_rel: str | None, kind: str, gate: str, inspection_id: str,
                  llm: LLM | None, rules: RuleSet, pool: ThreadPoolExecutor) -> AngleResult:
    angle = spec.angle
    t0 = time.time()
    img_path = scene.path(image_rel)
    bgr = imread(img_path) if img_path else None
    local = usability.check(bgr)
    honour_declared = image_rel == spec.image           # an `after` frame is a new capture
    usable, reason, decided_by = usability.combine(local, spec.declared_usable if honour_declared else True,
                                                   spec.declared_reason if honour_declared else None)
    ref_path = scene.path(spec.reference)
    entry = {
        "angle": angle,
        "image_ref": scene.ref(image_rel) if img_path else None,
        "camera_id": f"{gate}-CAM-{angle}",
        "crop": None,
        "status": "usable" if usable else "unusable",
        "unusable_reason": reason,
        "assessed_by": "local_check",
        "source_inspection_id": inspection_id,
        "image_url": scene.url(image_rel) if img_path else None,
        "reference_url": scene.url(spec.reference) if ref_path else None,
        "width": int(bgr.shape[1]) if bgr is not None else None,
        "height": int(bgr.shape[0]) if bgr is not None else None,
        "checked_by_eye": None,
        "attribution": {"title": spec.source.get("title"), "url": spec.source.get("url"),
                        "author": spec.source.get("author"), "licence": spec.source.get("licence"),
                        "derived": spec.derived},
        "analysis": None,
    }
    res = AngleResult(entry=entry, usability={
        "angle": angle, "usable": usable, "reason": reason, "decided_by": decided_by,
        "local": {"usable": local.usable, "reason": local.reason, "metrics": local.metrics},
        "declared": {"usable": spec.declared_usable, "reason": spec.declared_reason} if honour_declared else None})
    res.local_models.append({"name": "usability_check", "version": "1"})
    if not usable:
        res.local_ms = int((time.time() - t0) * 1000)
        return res

    h, w = bgr.shape[:2]
    scale = scale_for(w)
    ref = imread(ref_path) if ref_path else None
    if ref is not None and ref.shape[:2] != (h, w):
        ref = cv2.resize(ref, (w, h), interpolation=cv2.INTER_AREA)
    res.bgr, res.ref = bgr, ref
    tier = rules.angle_zone_tier[angle]
    envelope = (spec.regions or {}).get("envelope")
    erl = (spec.regions or {}).get("erl")
    no_reference = ref is None

    # Remote first passes start now and run while the local stage works.
    net_future = equip_future = None
    if llm is not None:
        if no_reference or tier == "critical":
            net_future = pool.submit(_safe, llm.tiled_scan, bgr=bgr, angle=angle, purpose="safety_net")
        if kind == "pre_arrival" and angle == "WIDE" and erl:
            equip_future = pool.submit(_safe, llm.equipment_scan, bgr=bgr)
    if kind == "pre_arrival" and angle == "WIDE" and not erl:
        res.notes.append("WIDE has no equipment restraint line region: the FOD-R9 staging check was skipped")

    # ---- local Candidates
    cands: list[dict] = []
    if no_reference:
        entry["analysis"] = "claude_tiled"
        res.notes.append(f"{angle}: no reference frame, analysed with a tiled Claude pass (PL-8)")
    else:
        entry["analysis"] = "change_detection"
        cands, info = change.propose(ref, bgr)
        res.local_models.append({"name": "change_detection", "version": change.VERSION})
        if info["truncated"]:
            res.notes.append(f"{angle}: {info['truncated']} lower-scoring Candidates dropped by the cap of "
                             f"{change.MAX_CANDIDATES} per Angle")
        if scene.light == "night" or local.low_contrast:
            ok, note = dino.availability()
            if ok:
                try:
                    extra = dino.propose(ref, bgr, ref_key=str(ref_path))
                    radius = max(12.0, CAND_RADIUS * scale)
                    for d in sorted(extra, key=lambda c: -c["score"]):
                        if len(cands) >= change.MAX_CANDIDATES:
                            break
                        if not any(centre_dist(d["box"], c["box"]) < radius for c in cands):
                            cands.append(d)
                    entry["analysis"] = "change_detection+dino"
                    res.local_models.append({"name": "dinov2_patch_anomaly", "version": dino.VERSION})
                except RuntimeError as e:
                    res.notes.append(f"{angle}: DINOv2 step skipped ({e})")
            else:
                res.notes.append(f"{angle}: DINOv2 step skipped ({note})")
    for i, c in enumerate(cands):
        c["cid"] = i + 1
    res.local_ms = int((time.time() - t0) * 1000)

    if llm is None:                                      # dry run: local stages only
        res.candidates = cands
        res.notes.append(f"{angle}: reasoning step skipped (dry run); Candidates are not Findings")
        return res

    # ---- decisions
    failed: list[str] = []
    decisions: dict[int, dict] = {}
    common = dict(rules_json=json.dumps(rules.data, ensure_ascii=False), angle=angle, kind=kind, light=scene.light,
                  bgr=bgr, ref=ref)

    def decide(batch: list[dict], model: str, purpose: str) -> dict[int, dict]:
        out: dict[int, dict] = {}
        todo = batch
        for attempt in range(2):                         # one retry for Candidates the model left out
            if not todo:
                break
            try:
                got, recs = llm.decide(model=model, purpose=purpose, cands=todo, fresh=attempt > 0, **common)
            except LLMError as e:
                failed.append(f"decision step failed: {e}")
                break
            res.calls.extend(recs)
            out.update(got)
            todo = [c for c in todo if c["cid"] not in out]
        return out

    decisions.update(decide(cands, llm.decision_model, "decide"))

    # ---- tiled pass hits join the Candidates and go through the same decision step
    if net_future is not None:
        hits, rec, err = net_future.result()
        if rec:
            res.calls.append(rec)
        if hits is None:
            msg = f"tiled pass failed ({err or 'no result'})"
            if no_reference:
                failed.append(msg)                       # it was the only analysis of this Angle
            else:
                res.notes.append(f"{angle}: safety net {msg}; local Candidates were still decided")
        else:
            radius = max(12.0, CAND_RADIUS * scale)
            extra = []
            for f in hits:
                if any(centre_dist(f["box"], c["box"]) < radius for c in cands + extra):
                    continue
                extra.append({"box": f["box"], "score": 0.0, "origin": "claude" if no_reference else "safety_net",
                              "hint": f["description"], "cid": len(cands) + len(extra) + 1})
            decisions.update(decide(extra, llm.decision_model, "decide"))
            cands = cands + extra

    # ---- optional Sonnet escalation: Critical Angles, Candidates Haiku was not sure about
    if llm.escalation == "sonnet" and tier == "critical" and llm.decision_model != config.SONNET:
        unsure = [c for c in cands if decisions.get(c["cid"], {}).get("confidence") != "high"]
        if unsure:
            for cid, d in decide(unsure, config.SONNET, "escalate").items():
                decisions[cid] = dict(d, escalated=True)

    # ---- equipment staging (FOD-R9)
    staging_boxes: list[list[int]] = []
    if equip_future is not None:
        items, rec, err = equip_future.result()
        if rec:
            res.calls.append(rec)
        if items is None:
            failed.append(f"equipment scan failed ({err or 'no result'})")
        else:
            for it in items:
                if is_equipment_staging(kind, angle, it["box"], erl):
                    staging_boxes.append(it["box"])
                    res.findings.append(_finding(
                        rules.classify_equipment_staging(angle=angle, bbox=it["box"], envelope=envelope),
                        angle=angle, entry=entry, box=it["box"], detected_by="claude", model=config.HAIKU,
                        escalated=False, confidence=it["confidence"],
                        description=f"{it['label']} inside the equipment restraint line before arrival",
                        location_text="inside the equipment restraint line"))

    # ---- turn decisions into Findings, dismissed Candidates and observations
    for c in cands:
        d = decisions.get(c["cid"])
        if d is None:
            continue
        box = [int(v) for v in c["box"]]
        verdict = d["verdict"]
        inside_staged = any(b[0] <= box_centre(box)[0] <= b[2] and b[1] <= box_centre(box)[1] <= b[3]
                            for b in staging_boxes)
        if verdict == "fod":
            category = d["category"] if d["category"] in rules.categories else "unidentified"
            res.findings.append(_finding(
                rules.classify(angle=angle, bbox=box, category=category, hint=d.get("material"), envelope=envelope),
                angle=angle, entry=entry, box=box, detected_by=_detected_by(c), model=d["model"],
                escalated=bool(d.get("escalated")), confidence=d["confidence"],
                description=d["what_is_visible"], location_text=d["location_text"]))
        elif verdict == "equipment" and inside_staged:
            res.dismissed.append({"angle": angle, "bbox": box, "reason": "part of GSE reported as equipment staging"})
        elif verdict == "equipment" and is_equipment_staging(kind, angle, box, erl):
            staging_boxes.append(box)
            res.findings.append(_finding(
                rules.classify_equipment_staging(angle=angle, bbox=box, envelope=envelope),
                angle=angle, entry=entry, box=box, detected_by=_detected_by(c), model=d["model"],
                escalated=bool(d.get("escalated")), confidence=d["confidence"],
                description=d["what_is_visible"], location_text=d["location_text"]))
        elif verdict == "equipment":
            res.dismissed.append({"angle": angle, "bbox": box,
                                  "reason": _one_line("equipment in its normal position: " + d["reason"])})
        elif verdict == "observation" and d.get("observation_kind") not in (None, "none"):
            res.observations.append({"angle": angle, "bbox": box, "kind": d["observation_kind"],
                                     "text": d["what_is_visible"]})
        else:
            res.dismissed.append({"angle": angle, "bbox": box, "reason": _one_line(d["reason"] or d["what_is_visible"])})

    undecided = [c for c in cands if c["cid"] not in decisions]
    if undecided:
        failed.append(f"{len(undecided)} Candidate(s) were not decided")
    if failed:
        # Fail safe: an Angle the reasoning step could not finish is not shown as clear.
        entry["status"], entry["unusable_reason"] = "unusable", ANALYSIS_FAILED
        res.usability.update(usable=False, reason=ANALYSIS_FAILED, decided_by="pipeline")
        res.notes.append(f"{angle}: " + "; ".join(dict.fromkeys(failed)))
    res.candidates = cands
    return res


def _safe(fn, **kw):
    """Run a first-pass call in the pool; never raise. Returns (result | None, record | None, error | None)."""
    try:
        out, rec = fn(**kw)
        return out, rec, None if out is not None else f"model stopped with {rec.stop_reason or 'no output'}"
    except LLMError as e:
        return None, None, str(e)


def _detected_by(c: dict) -> str:
    return {"change": "local_proposer", "dino": "local_proposer", "safety_net": "safety_net"}.get(c["origin"], "claude")


def _one_line(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _finding(cls: dict, *, angle: str, entry: dict, box, detected_by: str, model: str, escalated: bool,
             confidence: str, description: str, location_text: str) -> dict:
    box = [int(v) for v in box]
    return {
        "finding_id": None,
        "angle": angle, "image_ref": entry["image_ref"],
        "bbox": box,
        "location_text": location_text,
        "zone_tier": cls["zone_tier"],
        "finding_type": cls["finding_type"],
        "responsible_party": cls["responsible_party"],
        "category": cls["category"],
        "object_class": cls["object_class"],
        "size": size_class(box),
        "severity": cls["severity"],
        "rule_id": cls["rule_id"],
        "confidence": confidence if confidence in ("high", "medium", "low") else "low",
        "description": description,
        "detected_by": detected_by,
        "decided_by": {"model": short_model(model), "escalated": escalated},
        "carried_from_inspection_id": None,
        "confirmation": None,
        "status": "open",
        "acknowledged": None,
        "rule": cls["rule"],
        "crop_url": None, "reference_crop_url": None,
    }


# ---------------------------------------------------------------------- one Inspection
def run_inspection(scene: Scene, *, gate: str, turn_id: str | None, kind: str | None = None, llm: LLM | None,
                   inspection_id: str | None = None, parent: dict | None = None,
                   angles: list[str] | None = None, rules: RuleSet | None = None,
                   return_details: bool = False):
    """Run one Inspection and return its report.

    A first Inspection analyses all 6 Angles. With `parent` (an earlier report) and `angles`, this is an
    on-demand re-inspection: only those Angles are re-captured (using the scene's `after` frame when there is
    one) and every other Angle inherits its result, Findings and Confirmations from the parent (WF-R4).
    """
    rules = rules or load_rules()
    inspection_id = inspection_id or new_inspection_id()
    captured_at = R.now_iso()
    t0 = time.time()
    if parent is not None:
        kind = "on_demand"
        recapture = [a for a in config.ANGLES if a in set(angles or config.ANGLES)]
    else:
        kind = kind or scene.kind
        recapture = list(config.ANGLES)
    analysis_kind = _analysis_kind(parent, kind, scene)

    def image_for(angle: str) -> str | None:
        spec = scene.angles[angle]
        if parent is None:
            return spec.image
        if spec.after and scene.path(spec.after):
            return spec.after                              # the frame captured for the re-inspection
        prev = next((a for a in parent["angles"] if a["angle"] == angle), None)
        ref = (prev or {}).get("image_ref")
        return ref.split("/", 1)[1] if ref and "/" in ref else spec.image

    with ThreadPoolExecutor(max_workers=6) as angle_pool, ThreadPoolExecutor(max_workers=8) as call_pool:
        futures = {a: angle_pool.submit(analyse_angle, scene=scene, spec=scene.angles[a], image_rel=image_for(a),
                                        kind=analysis_kind, gate=gate, inspection_id=inspection_id, llm=llm,
                                        rules=rules, pool=call_pool) for a in recapture}
        results = {a: f.result() for a, f in futures.items()}

    angle_entries, findings, dismissed, observations = [], [], [], []
    carry_notes: list[str] = []
    for a in config.ANGLES:
        prev_findings = [f for f in parent["findings"] if f["angle"] == a] if parent else []
        if a in results:
            r = results[a]
            angle_entries.append(r.entry)
            fresh = list(r.findings)
            radius = MATCH_RADIUS * scale_for(r.entry.get("width") or 3840)
            # A re-inspection never drops a Finding: only a Confirmation closes one. An open Finding seen again
            # is replaced by the fresh one; anything else from the parent is carried as it stands.
            for pf in prev_findings:
                match = next((f for f in fresh if same_object(f["bbox"], pf["bbox"], radius)), None) \
                    if R.is_open(pf) and r.entry["status"] == "usable" else None
                if match is not None:
                    if pf.get("status") == "acknowledged":
                        match["status"], match["acknowledged"] = "acknowledged", pf.get("acknowledged")
                    match["seen_again_from_finding_id"] = pf["finding_id"]
                    if pf.get("still_there_count"):
                        match["still_there_count"] = pf["still_there_count"]
                    continue
                findings.append(_carry(pf, parent))
                if R.is_open(pf):
                    carry_notes.append(f"{a}: Finding {pf['finding_id']} was not seen in the new frame; it stays "
                                       "open until a Confirmation closes it")
            findings += fresh
            dismissed += r.dismissed
            observations += r.observations
        elif parent is not None:
            prev = next((x for x in parent["angles"] if x["angle"] == a), None)
            if prev:
                angle_entries.append(json.loads(json.dumps(prev)))
            findings += [_carry(f, parent) for f in prev_findings]
            dismissed += [d for d in parent.get("dismissed_candidates", []) if d["angle"] == a]
            observations += [o for o in parent.get("observations", []) if o["angle"] == a]

    crop_dir = config.crops_dir() / inspection_id
    for n, f in enumerate(findings, 1):
        f["finding_id"] = f"{inspection_id}-F{n}"
        r = results.get(f["angle"])
        if r is not None and f["crop_url"] is None and r.bgr is not None:
            crop_dir.mkdir(parents=True, exist_ok=True)
            crop, _ = crop_candidate(r.bgr, f["bbox"], mark=False)
            cv2.imwrite(str(crop_dir / f"F{n}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            f["crop_url"] = f"/images/_crops/{inspection_id}/F{n}.jpg"
            if r.ref is not None:
                rcrop, _ = crop_candidate(r.ref, f["bbox"], mark=False)
                cv2.imwrite(str(crop_dir / f"F{n}_ref.jpg"), rcrop, [cv2.IMWRITE_JPEG_QUALITY, 90])
                f["reference_crop_url"] = f"/images/_crops/{inspection_id}/F{n}_ref.jpg"

    calls = [c for a in recapture for c in results[a].calls]
    notes = [n for a in recapture for n in results[a].notes] + carry_notes
    local_models = list({json.dumps(m, sort_keys=True): m for a in recapture for m in results[a].local_models}.values())
    total_ms = int((time.time() - t0) * 1000)

    def span(family: str) -> int:
        cs = [c for c in calls if short_model(c.model) == family]
        return int((max(c.ended for c in cs) - min(c.started for c in cs)) * 1000) if cs else 0

    report = {
        "schema_version": config.SCHEMA_VERSION,
        "rule_set_version": rules.version,
        "inspection_id": inspection_id,
        "gate": gate, "turn_id": turn_id,
        "kind": kind,
        "parent_inspection_id": parent["inspection_id"] if parent else None,
        "captured_at": captured_at, "analysed_at": R.now_iso(),
        "verdict": R.compute_verdict(findings, angle_entries),
        "highest_open_severity": None,
        "missing_angles": [a["angle"] for a in angle_entries if a["status"] != "usable"],
        "angles": angle_entries,
        "findings": findings,
        "dismissed_candidates": dismissed,
        "observations": observations,
        "inspection_signoff": None,
        "run_metadata": {
            "local_models": local_models,
            "llm_calls": [c.public() for c in calls],
            "timings_ms": {"local": max((results[a].local_ms for a in recapture), default=0),
                           "haiku": span("haiku"), "sonnet": span("sonnet"), "total": total_ms},
            "est_cost_usd": round(sum(c.est_cost_usd for c in calls), 6),
            "spent_usd": round(sum(c.est_cost_usd for c in calls if not c.cached), 6),
            "analysis_kind": analysis_kind,
            "analysed_angles": recapture,
            "candidates": {a: len(results[a].candidates) for a in recapture},
            "usability_checks": [results[a].usability for a in recapture],
            "reasoning": "skipped (dry run)" if llm is None else
                         {"decision_model": llm.decision_model, "escalation": llm.escalation},
            "notes": notes,
        },
        "status": "awaiting_confirmation",
        "scene_id": scene.scene_id,
    }
    R.refresh(report)
    if llm is None:
        report["verdict"] = None                 # dry run: Candidates were proposed but nothing was decided
    if return_details:
        return report, results
    for r in results.values():
        r.bgr = r.ref = None
    return report


def _carry(finding: dict, parent: dict) -> dict:
    g = json.loads(json.dumps(finding))
    g["carried_from_inspection_id"] = finding.get("carried_from_inspection_id") or parent["inspection_id"]
    g["carried_from_finding_id"] = finding["finding_id"]
    g["finding_id"] = None
    return g


def _analysis_kind(parent: dict | None, kind: str, scene: Scene) -> str:
    """The kind that drives the analysis (FOD-R9 applies at pre-arrival). An on-demand Inspection keeps the
    kind of the Inspection chain it belongs to."""
    if parent is None:
        return kind if kind in ("pre_arrival", "pre_departure") else scene.kind
    return parent.get("run_metadata", {}).get("analysis_kind") or (
        parent["kind"] if parent["kind"] in ("pre_arrival", "pre_departure") else scene.kind)


def carried_copy(report: dict, finding: dict) -> dict | None:
    """The copy of `finding` (from the parent Inspection) that `report` carried forward, if any. After a
    re-inspection of the Finding's Angle, a carried copy means the new frame did not show the object again."""
    return next((f for f in report["findings"] if f.get("carried_from_finding_id") == finding["finding_id"]), None)


def seen_again(report: dict, finding: dict) -> dict | None:
    """The fresh Finding in `report` that replaced `finding` because the re-inspection frame showed the same
    object again ("still there"), if any."""
    return next((f for f in report["findings"] if f.get("seen_again_from_finding_id") == finding["finding_id"]), None)
