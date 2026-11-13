# Inspection Report Schema (PoC v0.1)

Decided in issue 0010 ("What does an Inspection report contain (Finding and Verdict schema)?"). Terms follow GLOSSARY.md. Rules: spec/fod-rules.md.

```jsonc
{
  "schema_version": "0.1",
  "rule_set_version": "fod-rules v0.2",
  "inspection_id": "…",
  "gate": "G3", "turn_id": "…",
  "kind": "pre_arrival | pre_departure | on_demand",
  "parent_inspection_id": null,            // set for on_demand
  "captured_at": "…", "analysed_at": "…",

  "verdict": "FINDINGS | INCOMPLETE | ALL_CLEAR",   // precedence: FINDINGS > INCOMPLETE > ALL_CLEAR
  "highest_open_severity": "HOLD | REMOVE | ADVISORY | null",
  "missing_angles": ["ENG-R"],             // always present; a non-empty list blocks clearance

  "angles": [{
    "angle": "NOSE | ENG-L | ENG-R | CARGO | AFT | WIDE",
    "image_ref": "…", "camera_id": "…", "crop": null,
    "status": "usable | unusable",
    "unusable_reason": "missing | glare | blur | blocked | low_light | null",
    "assessed_by": "local_check | claude",
    "source_inspection_id": "…"            // this Inspection, or the one it inherited from
  }],

  "findings": [{
    "finding_id": "…",
    "angle": "ENG-L", "image_ref": "…",
    "bbox": [x1, y1, x2, y2],              // pixels in the original image
    "location_text": "≈1 m ahead of left engine intake lip",
    "zone_tier": "critical | service | general | outside_boundary",
    "finding_type": "fod | equipment_staging",
    "responsible_party": "airline | airport",
    "category": "fasteners_hardware | aircraft_parts | tools | luggage_parts | catering_flightline | cargo_packaging | pavement_construction | natural | unidentified",
    "object_class": "hard | light | unidentified | natural",
    "size": "S | M | L",
    "severity": "HOLD | REMOVE | ADVISORY",
    "rule_id": "FOD-R1",
    "confidence": "high | medium | low",   // shown only; never lowers severity
    "description": "…",
    "detected_by": "local_proposer | safety_net | claude",
    "decided_by": { "model": "haiku | sonnet", "escalated": false },
    "carried_from_inspection_id": null,
    "confirmation": null                   // see below
  }],

  "dismissed_candidates": [{ "angle": "…", "bbox": [], "reason": "painted marking" }],
  "observations": [{ "angle": "…", "bbox": [], "kind": "snow_ice | live_wildlife | spill", "text": "…" }],  // FOD-R7, outside the Verdict

  "inspection_signoff": null,              // { "by": {"role": "ramp_lead", "name": "…"}, "at": "…" }

  "run_metadata": {
    "local_models": [{ "name": "…", "version": "…" }],
    "llm_calls": [{ "model": "…", "purpose": "decide | escalate | safety_net | workflow", "tokens_in": 0, "tokens_out": 0, "est_cost_usd": 0 }],
    "timings_ms": { "local": 0, "haiku": 0, "sonnet": 0, "total": 0 }
  }
}
```

**Finding Confirmation**
```jsonc
{ "outcome": "removed | false_alarm | not_found_on_walk",
  "false_alarm_reason": "shadow | marking | equipment_in_place | other | null",
  "confirmed_by": { "role": "ramp_agent | ramp_lead", "name": "…" },  // only ramp_lead may confirm a HOLD
  "confirmed_at": "…", "after_photo_ref": null, "possible_source": null }
```

**Notes**
- Finding fields cover most of FAA AC 150/5210-24A §6.1.1. Weather and ops data are left out of the PoC.
- When the schema is used as Claude structured output, keep it within the API limits: at most 24 optional fields, no numeric min/max (research/claude-vision-capabilities.md). The model returns only its part (findings, dismissed_candidates, observations, Angle usability). The app fills in IDs, versions, metadata and the Verdict.
