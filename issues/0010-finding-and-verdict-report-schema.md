---
id: 10
title: "What does an Inspection report contain (Finding and Verdict schema)?"
labels: [wayfinder:grilling]
parent: 1
blocked_by: [6, 7]
assignee: claude
status: closed
---

## Question

Decide the structured report the agent returns per Inspection: Verdict, per-Finding fields (angle/image, location in the committed highlight form, category, severity, rule cited, confidence, description), how "uncertain / image unusable" is expressed, and what the human Confirmation adds.

## Resolution

Schema: [spec/inspection-report-schema.md](../spec/inspection-report-schema.md).
- **Verdict precedence:** FINDINGS > INCOMPLETE > ALL CLEAR. `missing_angles` is always listed, and a non-empty list blocks clearance.
- **Findings carry:** bbox in original pixels, verbal location, zone tier, category, object class, size, severity, rule ID, high/medium/low confidence, `detected_by` and `decided_by`.
- **Angle status:** usable or unusable, with a reason (missing, glare, blur, blocked, low_light). Assessed by a local check first, or by Claude.
- **Kept outside the Verdict:** `dismissed_candidates` (with a reason) and `observations` for non-FOD hazards (FOD-R7).
- **Confirmation:** each Finding records an outcome (removed, false_alarm with a reason, or not_found_on_walk), who and when, an optional after-photo and an optional possible source. The Inspection gets a sign-off.
- **Re-inspections:** an on-demand Inspection links to its parent, and each Angle records which Inspection it came from.
- **Traceability:** schema and rule-set versions, local model versions, and run metadata (tokens, cost, stage timings) on every report.

## Amendment (2026-11-13)

- `kind` becomes `pre_arrival | pre_departure | on_demand`.
- Findings gain `responsible_party: airline | airport` and `finding_type: fod | equipment_staging`. `zone_tier` gains `outside_boundary`.
