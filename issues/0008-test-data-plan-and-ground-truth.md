---
id: 8
title: "What test data set and ground-truth labelling will the PoC use?"
labels: [wayfinder:grilling]
parent: 1
blocked_by: [4, 5, 13]
assignee: claude
status: closed
---

## Question

Decide the PoC test set: mix of public / synthetic / staged images, how many Inspections per Gate, ratio of clean to FOD, which debris types, and the ground-truth label format (per image: clean, or list of items with category + location) so detection can be scored.

## Resolution

Plan: [spec/test-data-plan.md](../spec/test-data-plan.md).
- 30 Inspections (180 Angle images) of real Wikimedia Commons photos: 10 pre-arrival (5 clean, 3 debris, 2 GSE staging) and 20 pre-departure (8 clean, 10 debris, 2 with an unusable Angle). At least 20% night or wet.
- Debris is FOD-A cut-outs composited at known positions, 1 to 4 per Inspection, half in Critical zones, a quarter under 30 px.
- ENG-L and AFT gaps are filled by labelled crops and mirrored ENG-R photos, scored separately.
- Ground truth uses the spike's format. Thresholds stay fixed from the spike set; the 30 Inspections are for scoring only.
