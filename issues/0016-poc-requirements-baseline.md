---
id: 16
title: "What is the approved requirements baseline for the Delta ATL Concourse T PoC?"
labels: [wayfinder:grilling]
parent: 1
blocked_by: [14, 15, 17]
assignee: claude
status: closed
---

## Question

Consolidate every decision so far (rules, schema, Angles, pipeline, dashboard) together with the researched turnaround workflow (0014) and the ATL Concourse T example site (0015) into one numbered requirements baseline: functional, workflow/FAA-compliance, data and records, AI pipeline, UI, and non-functional (cost, latency, local-first). Each requirement must be traceable to its source decision or regulation. The user reviews and approves it before any further prototyping.

## Resolution

The approved baseline is [spec/requirements-baseline.md](../spec/requirements-baseline.md) v1.0: about 60 numbered requirements, each traced to a decision or source. Decided in this ticket:
- **Gates:** T1, T2, T4, T5, T8 at ATL Concourse T, presented as an example modelled on public facts.
- **Turn:** starts at stand preparation and ends at pushback. No separate post-departure Inspection.
- **Stand markings:** the gate safety envelope and equipment restraint line are mapped per Gate in the WIDE image.
- **Pipeline:** change detection against a reference frame, plus DINOv2 on night or low-contrast Angles. Haiku 5.5 decides; Sonnet is available but off. The Critical-Angle safety net is a tiled Haiku pass. With no reference frame, the Inspection falls back to a tiled Claude pass and says so.
- **Targets:** at most $0.05 and 20 s per Inspection; recall at least 90% overall and 95% in Critical zones; at most 0.5 false alarms per clean Angle.
- **Records:** every Inspection is recorded, with a 2-year production target. Spills are a non-FOD observation.
- **Test set:** about 30 Inspections (180 Angle images), a third pre-arrival, at least 20% night or wet. ENG-L and AFT gaps are filled by crops and mirrored ENG-R photos, labelled. Downloads stay anonymous.
