---
id: 4
title: "What FOD image data can we use or generate for testing?"
labels: [wayfinder:research]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

Survey public FOD / airport apron image datasets (e.g. academic FOD datasets): content, viewpoint (close-up runway vs gate/apron), size, labels, and licence (is commercial PoC use allowed?). Also survey practical ways to produce synthetic test images (image editing / generation to insert debris into clean apron scenes) and their realism caveats. Output: shortlist with recommended mix.

## Resolution

Findings: [research/fod-test-data-sources.md](../research/fod-test-data-sources.md).
- No public dataset matches the gate/apron view with an aircraft. All public FOD data is close-up runway pavement.
- **FOD-A** (MIT licence, commercial use OK, 31 classes based on FAA categories, more than 30k boxes) is the only usable set. Limits: 400 px images, no clean images, near-duplicate video frames. Use it only to check object recognition.
- Ruled out: AIT Apron (non-commercial, no FOD class), the withdrawn runway set, and others whose release status or licence is unclear.
- A test-object kit exists in AC 150/5220-24 (metal cylinder, golf ball, wrench, socket, lug nut, fuel cap, etc.), so staged shoots can be repeated.
- Synthetic options: copy-paste gives exact labels but looks unrealistic. AI inpainting looks realistic but has caveats: boxes need relabelling, Gemini adds SynthID, FLUX Fill is non-commercial. Claude can't generate images.
- Recommended mix: ~40% staged at the airline's gate cameras, ~25% clean real frames (to measure false alarms), ~25% synthetic insertions plus a no-op-edit control, ~10% FOD-A. Report real and synthetic results separately.
