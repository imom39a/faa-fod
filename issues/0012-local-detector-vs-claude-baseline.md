---
id: 12
title: "Which local detector proposes Candidates well enough to replace Claude-only detection?"
labels: [wayfinder:prototype]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

On the same 22-frame spike set (prototypes/spike/data/images, ground_truth.json), compare local image models, informed by the user's drone-lab experiments (/Users/vinothshanmugam/code/jev-playground/drone-lab), as the **Candidate proposer** in the local-first pipeline. Measure:
- Candidate recall (the target is to match the Claude-only baseline of 93%)
- Candidates per clean frame
- latency on the local machine

Then run the full hybrid: local Candidates → Haiku decisions (Sonnet for escalations) → plus the Critical-Angle Haiku safety net. Compare its recall, false alarms and cost against the Claude-only baseline. Decide which local model(s) and settings (tiling, thresholds) to use, and whether the hybrid meets the bar.

## Resolution

Evidence: [prototypes/local-detect/RESULTS.md](../prototypes/local-detect/RESULTS.md).
- **Proposer:** change detection against the Gate's reference frame (blobs scoring 20 or more, merged within 24 px, at most 30 per Angle), with DINOv2 patch comparison (0.6 or more) added on night or low-contrast Angles. OWLv2 and the Qwen3-VL local verifier are dropped.
- **Decision step:** Haiku 5.5 only by default, given the Candidate crop, the reference crop and a downscaled frame. Sonnet escalation is off by default. Severity is computed in code.
- **Hybrid vs Claude-only baseline on the spike set:** recall 96–100% vs 93%; false alarms 0.10 vs 0.70 per clean frame; $0.03–0.04 vs $0.19 per Inspection; 12–17 s vs 6–9 s.
- **Caveat:** the reference frames are simulated from the same photos with nothing moving, so the numbers flatter change detection.
