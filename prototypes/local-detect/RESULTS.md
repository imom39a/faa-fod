# Ticket 0012: local Candidate proposer vs Claude-only baseline (PROTOTYPE, throwaway)

Evidence for [issue 0012](../../issues/0012-local-detector-vs-claude-baseline.md). The human makes the call; this file gives the evidence and a recommendation. Run on 2026-11-13 on an M1 Pro (16 GB), with PyTorch 2.14 on MPS, OpenCV on CPU and mlx-vlm 0.7.1, against the real Claude API. Total API spend was **about $0.68** over 6 hybrid runs and 224 calls. No billing errors occurred.

## TL;DR

- **Reference-frame change detection is the proposer to use.** It runs on CPU in 0.9 s per 4K frame and proposes 27 of 28 seeded objects (96%) at about 1.5 Candidates per clean frame. Under heavy simulated camera and lighting drift it still reaches 96%, but at about 12 Candidates per clean frame.
- **The DINOv2 patch anomaly is a useful second channel but not a primary.** Combined with change detection (change ≥20 OR DINO ≥0.6), Candidate recall is 28/28 at 2.7 per clean frame, at a cost of 1.7 s/frame more on MPS. Its boxes are coarse (14 px grid).
- **OWLv2 tiled open-vocabulary detection is the wrong tool.** It is slow (7.3 s/frame) and noisy (86% recall at 72 Candidates per clean frame). Gated by change detection, it adds nothing that change detection alone doesn't already do.
- **The hybrid clears the recall and false-alarm bar at about 1/5 of the cost:** recall 96–100% vs 93%, false alarms 0.10 per control frame vs 0.70, and **$0.03–0.04 vs $0.19 per 6-Angle Inspection.** It is **slower**: about 11 s of API time plus up to 5 s of local time per Inspection, vs about 6–9 s.
- **The local VLM verifier (Qwen3-VL-4B) is not worth it.** It removes almost every false Candidate, but it also drops 3 of 28 real objects (2 tiny bolts and a 22 px can), which costs 7 points of end-to-end recall. It saves about $0.01 per Inspection and adds 0.8 s per crop.
- **Biggest caveat: composited debris is unusually easy for change detection.** The objects are pasted onto the exact background pixels, and the "recent clean reference" is simulated. Thresholds were also chosen on this same 28-object set. Re-measure on the staged captures (0011) before trusting the headline numbers.

## Setup

- **Data:** the spike set (`../spike/data/images`, `ground_truth.json`): 22 frames at 3840×2160, 28 seeded objects of 16–80 px, 6 clean frames and 4 no-op frames. Scoring reuses `run_spike.score`.
- **Reference frame:** the spike's clean frame is the exact background the debris was pasted onto, so diffing against it directly would be trivially perfect. Each camera's "recent clean reference" is instead the clean frame re-captured with simulated drift (`common.make_reference`):
  - **mild:** 1.6/−1.1 px shift, 0.03° rotation, gain 1.04, gamma 1.05, ±6% left-to-right illumination gradient, sensor noise σ 2.5, JPEG q85.
  - **hard:** 4.3/−3.2 px shift, 0.12°, gain 1.10, gamma 1.15, ±15% gradient, a soft 25%-dark cloud-shadow ellipse, noise σ 4.5, JPEG q75.
  - All 22 frames, clean ones included, are compared against that reference. Neither mode moves GSE or people, adds rain, or moves shadows with the sun.
- **Candidate recall** uses a *tighter* match than the spike: the Candidate's centre must be within 60 px of the object (or IoU > 0.1), so the 320 px crop sent to Claude certainly contains it. **Hybrid Findings** use the spike's 150 px matcher, so they compare like-for-like with the baseline.
- **Angles (an assumption, needed for zones):** pelita_pwf = NOSE, pelita_pwl = ENG-L and brussels = ENG-R are Critical; spring = CARGO and wingo = AFT are Service; tansonnhat = WIDE is General. An Inspection is the 6 frames of one variant (clean, fod1, fod2). The no-op variant has only 4 Angles, so it counts toward false alarms but not toward cost per Inspection.

## 1. Proposer comparison (mild reference unless noted)

Latency is per 4K frame on this Mac, after warm-up and excluding JPEG decode (about 0.06 s). The DINO reference features are computed once per camera and cached.

| proposer | setting | Candidate recall | Candidates / clean | Candidates / no-op | extra Candidates / seeded | latency / frame |
|---|---|---|---|---|---|---|
| **1. Change detection** (CPU) | all blobs | 27/28 (96%) | 19.3 | 27.0 | 20.2 | 0.90 s |
|  | **score ≥ 20, merged** | **27/28 (96%)** | **1.5** | 4.0 | 1.5 | 0.90 s |
|  | score ≥ 50 | 26/28 (93%) | 0.2 | 1.8 | 0.2 | 0.90 s |
|  | score ≥ 200 | 26/28 (93%) | 0.0 | 1.2 | 0.0 | 0.90 s |
|  | *hard drift*, ≥ 20 merged | 27/28 (96%) | 11.8 | 15.2 | 11.8 | 0.90 s |
|  | *hard drift*, ≥ 200 merged | 26/28 (93%) | 0.5 | 2.0 | 0.5 | 0.90 s |
| **2. DINOv2 ViT-S/14 patch anomaly** (MPS) | ≥ 0.5 | 28/28 (100%) | 5.8 | 7.0 | 6.2 | 1.74 s |
|  | ≥ 0.55 | 26/28 (93%) | 2.0 | 4.2 | 2.3 | 1.74 s |
|  | ≥ 0.6 | 24/28 (86%) | 1.2 | 1.5 | 1.2 | 1.74 s |
|  | *hard drift*, ≥ 0.55 | 26/28 (93%) | 10.3 | 9.0 | 10.5 | 2.28 s |
| **3. OWLv2 base-ens., 15 × 960 px tiles** (MPS) | ≥ 0.05 | 28/28 (100%) | 267 | 343 | 270 | 7.28 s |
|  | ≥ 0.10 | 24/28 (86%) | 72 | 93 | 73 | 7.28 s |
|  | top-20 per frame | 21/28 (75%) | 20 | 20 | 18 | 7.28 s |
| **1 + 2 combined** | **change ≥ 20 OR DINO ≥ 0.6** | **28/28 (100%)** | **2.7** | 4.8 | 2.7 | 2.6 s |
|  | change ≥ 200 OR DINO ≥ 0.6 | 28/28 (100%) | 1.2 | 2.0 | 1.2 | 2.6 s |
|  | change AND DINO ≥ 0.4 | 27/28 (96%) | 0.0 | 1.2 | 0.3 | 2.6 s |
|  | *hard drift*, change ≥ 20 OR DINO ≥ 0.6 | 28/28 (100%) | 22.2 | 24.0 | 22.3 | 2.6 s |
| **1 + 3 combined** | OWL ≥ 0.05 AND change | 27/28 (96%) | 2.3 | 3.2 | 2.2 | 8.2 s |
| **4. + Qwen3-VL-4B verifier** (MLX) | on (1 + 2), pre-merge | 25/28 (89%) | 0.0 | 0.2 | 0.3 | +0.81 s / crop |
|  | *hard drift* | 26/28 (93%) | 0.0 | 0.2 | 0.2 | +0.81 s / crop |

**Notes:**
- **Misses.** Change detection misses only the 20 px night bolt in `wingo__fod2`; DINO catches it. Change detection at ≥ 50 also loses the 22 px bolt on the red-hatched surface in `pelita_pwf__fod1`. Those are the same two tiny bolts every Claude-only configuration missed.
- **No-op frames always keep about 1.2 Candidates even at high thresholds.** These are the pasted pavement patches, which are real pixel changes. One of them copied part of a jet-bridge leg onto open pavement (see Examples).
- **Box quality.** Change-detection boxes have a median centre error of 1.6 px (median IoU 0.51, held down by 6 px padding on tiny objects). DINO boxes sit on the 14 px patch grid (median IoU 0.20). OWL boxes are tight (IoU 0.89) when it finds the object.
- **SAM 2.1 Tiny was not used.** Change blobs are already pixel-accurate, and in the combined proposer DINO-only Candidates are rare. Downstream they are 320 px crops anyway, so tighter boxes would not change any decision.
- **Robustness steps that mattered, all principled rather than tuned per object:**
  - a local mean/std colour match for illumination (a plain gain map left gamma residue);
  - a ±1 px neighbourhood-minimum diff;
  - a 12 px border mask for warp artefacts;
  - capping the size term at 20×20 px, so large diffuse lighting blobs don't outrank compact objects;
  - merging fragments within 24 px.

## 2. Hybrid end-to-end vs Claude-only

**Pipeline** (`hybrid.py`), with the Angles of an Inspection running in parallel:
1. Candidates from the local proposer.
2. **Haiku 5.5** decides each Candidate. It gets one request per Angle with the rule set from `spec/fod-rules.md`, a 1280×720 context frame with numbered boxes, and for each Candidate a **320 px native crop of both the current frame and the reference**. It returns structured JSON: is_fod, category, object class, severity, rule and confidence.
3. **Sonnet 5.5** re-decides every Candidate on a Critical Angle that Haiku was not `high` confidence about.
4. **Safety net:** in parallel with step 2, a Haiku whole-frame pass (the spike prompt) runs on the Critical Angles. Its findings that are more than 60 px from any Candidate become new Candidates and go through steps 2 and 3.

All calls use effort `medium`, adaptive thinking and streaming. All 224 calls returned `end_turn`, and every Candidate got a decision.

| run | recall | FA / clean | FA / no-op | FA / control (adjudicated) | controls with 0 FA | $ / 6-Angle Inspection | API s / Inspection | local s / Inspection |
|---|---|---|---|---|---|---|---|---|
| **Claude-only Sonnet 5.5 tiles (spike baseline)** | 26/28 (93%) | 0.67 | 0.75 | 0.70 (0.20) | 4/10 | 0.187 | 6.4 (max 9) | 0 |
| **Hybrid, change ≥ 20** | 27/28 (96%) | 0.00 | 0.25 | 0.10 (0.10) | 9/10 | **0.031** | 11.4 | 5.4 |
| Hybrid, change ≥ 20 OR DINO ≥ 0.6 | **28/28 (100%)** | 0.00 | 0.25 | 0.10 (0.10) | 9/10 | 0.037 | 11.5 | 15.9 |
| Hybrid, change ≥ 20, *hard drift* | 27/28 (96%) | 0.00 | 0.25 | 0.10 (0.10) | 9/10 | 0.041 | 16.7 | 5.4 |
| Hybrid, combined before fragment merge | 27/28 (96%) | 0.00 | 0.25 | 0.10 (0.10) | 9/10 | 0.041 | 13.1 | 15.9 |
| Hybrid, same + Qwen3-VL verifier | 25/28 (89%) | 0.00 | 0.25 | 0.10 (0.10) | 9/10 | 0.029 | 11.4 | 40.2 |

- **"local s / Inspection" is the sum of 6 frames processed one after another on the Mac.** Overlapping it with the API calls (each Angle goes to Claude as soon as its Candidates are ready) brings the end-to-end time to roughly 12–17 s for change-only.
- **The single remaining false alarm is the same one in every hybrid run:** the no-op patch in `pelita_pwf__noop` that copied a piece of jet-bridge leg onto open pavement. In the image it is a real new object-like thing, and Sonnet called it FOD at `medium`. Read strictly, every hybrid run has 0 false alarms on clean frames. The baseline's false alarms were pre-existing loose items, a stain and bags on a dolly. Change detection never proposes those, because they are in the reference too (see caveats).
- **Fragment duplicates.** Before merging, the hybrid produced 4 extra Findings on seeded frames (one object split into 2–3 blobs). Merging within 24 px removed them.
- **Cost breakdown:** Haiku decisions cost about $0.0013 per Angle. **Sonnet escalation is about 70–75% of the hybrid's cost**, about $0.023 of the $0.031 per Inspection.
- **The Haiku-only counterfactual** comes from the stored Haiku decisions, with no new calls: the same recall in every run, at 0.10–0.20 FA per control frame and about **$0.008 per Inspection**. On this set, Sonnet changed only 1–2 decisions per run. All were Haiku `low`/`medium` "FOD" calls on unseeded Candidates that Sonnet rejected. Sonnet never rescued a real object Haiku had rejected. The one tiny bolt Haiku was unsure of (`low`), Sonnet kept as FOD.
- **The safety net found nothing new in any run,** because the proposer had already covered every seeded object on the Critical Angles. On its own it is weak. From the spike's stored runs, Haiku **whole**-frame finds only 7/14 objects on the Critical frames. Haiku **tiled** finds 12/14, but has 1.6 raw false alarms per control frame, which the decision step would then filter.
- **Severity and rule.** All Findings were HOLD on Critical, REMOVE on Service, and REMOVE or ADVISORY on General, citing FOD-R1/R2/R3/R4/R5. One Finding disagreed with the severity matrix: an unidentified WIDE object rated ADVISORY, where the matrix says REMOVE. Compute severity in code from tier × object class rather than trusting the model's value.
- **Latency.** The Critical Angles are the slow path: Haiku decide plus net (about 5 s), then Sonnet (about 3.5 s), for a median of 8.7 s per Angle and up to 13 s. Service and General Angles take 3–4 s.

## Examples (`results/examples.jpg`, CURRENT | REFERENCE)

- **Found, where every Claude-only run missed it:** `brussels__fod1` grey plastic, 70 px, in dusk shadow beside a truck. It stands out against the reference. Haiku `medium` FOD, Sonnet confirmed.
- **Found, where every Claude-only run missed it:** `pelita_pwf__fod1` 22 px bolt on the hatched surface. Haiku said FOD `low`, Sonnet escalation kept it as FOD `medium`. On the first smoke test, *without* the reference crop, both models called it "a pavement speck". **Sending the reference crop is what made the decision work.**
- **Found once, missed in other runs:** `wingo__fod2` 20 px night bolt, proposed only by DINO. Haiku rejected it at `low` in the pre-merge run and accepted it at `low` in the merged run. That is run-to-run noise, and AFT is not escalated.
- **False alarm:** the `pelita_pwf__noop` pasted patch that carries a jet-bridge-leg fragment.
- **Correct rejections:** for example, lights on a tug at night, "same in both crops", `high`. Haiku rejected the large majority of Candidates at `high` confidence by comparing the current and reference crops.

## Recommendation

1. **Proposer:** use **reference-frame change detection** (`changedet.py`) as the primary proposer on every Angle at full resolution, with these settings:
   - ECC Euclidean alignment at 1/4 scale;
   - local mean/std colour normalisation at 1/8 scale;
   - ±1 px neighbourhood-minimum colour diff;
   - threshold max(18, median + 6·MAD);
   - minimum blob area 25 px;
   - merge fragments within 24 px;
   - **keep Candidates with score ≥ 20, capped at the 30 highest per Angle.**

   **Threshold for recall, not for Candidate count.** A Candidate costs about $0.0002 in a Haiku decision, so 10 extra Candidates cost about the same as one missed bolt is worth zero. Under hard drift, ≥ 20 still gives 96% recall at 12 Candidates per frame, and the hybrid still had no false alarm on a clean frame. Do **not** raise the threshold to ≥ 50 or more: that loses the 22 px bolt.
2. **Add DINOv2 (≥ 0.6, OR-ed with change detection) on night or low-contrast Angles only.** It is what found the 20 px night bolt, at 1.7 s/frame on MPS. Skip it on day Angles if local latency matters.
3. **Drop OWLv2.** At these sizes open-vocabulary detection is slower and worse than change detection, and it adds nothing as a re-ranker.
4. **Drop the local VLM verifier.** It trades 7–11 points of recall for about $0.01 per Inspection. Haiku with a reference crop is a better and nearly free filter.
5. **Decision step:** always send **current + reference crops** together with the context frame, and compute severity in code from tier × object class.
6. **Escalation:** keep the Sonnet escalation rule for Critical Angles. It is cheap insurance against Haiku false alarms, but on this set it never recovered a miss. If cost matters more than about 0.1 false alarms per frame, a Haiku-only decision step costs about $0.008 per Inspection.
7. **Safety net:** make it Haiku **tiled** rather than whole-frame on Critical Angles, and feed its Findings into the decision step rather than straight into the Verdict. The whole-frame net is too weak (7/14 on Critical frames) to catch what a proposer would miss.
8. **Does the hybrid meet the bar?** **Yes on recall, false alarms and cost; no on latency.**
   - Recall: 96–100% vs 93%.
   - False alarms: 0.10 vs 0.70 per control frame.
   - Cost: $0.03–0.04 vs $0.19 per Inspection.
   - Latency: about 12–17 s vs 6–9 s per Inspection. That is still seconds, but if it matters, run Haiku-only on non-Critical Angles and fire Sonnet escalation per Angle as soon as Haiku returns.

   The verdict is provisional until it is re-measured on staged captures (0011).

## Caveats

- **Composited debris favours change detection.** Each object is pasted onto the *exact* pixels of the clean background, with crisp edges and a contact shadow, so the diff is unusually clean. Real debris arrives with real lighting and scale. Real gates also produce changes that aren't debris: GSE, people, hoses and chocks move, puddles form and dry, shadows sweep across the apron. None of that is simulated, so the real-world Candidate rate will be much higher than 1.5 per frame. The Haiku decision step's false-alarm rate on those Candidates is unmeasured.
- **The reference is simulated** from the same clean photo. "Hard drift" is a stress test, not a measurement.
- **Change detection assumes fixed cameras and a recent clean reference.**
  - A camera bumped by more than a few pixels, or zoomed, needs re-referencing.
  - **Debris already present in the reference is invisible to change detection.** The baseline's pre-existing loose items (the Wingo mat, the pelita_pwl scrap) were never proposed. The reference must therefore come from a Confirmed-clean Inspection, and the Critical-Angle safety net is the only guard against a dirty reference.
- **Small set, one run each, thresholds chosen on the test set.** There are 28 objects, so one object is 3.6 points. The thresholds and robustness steps were picked while looking at these same frames. Haiku's decision on the 20 px night bolt flipped between runs.
- **Assumed Angle mapping.** Real Inspections need per-camera ground masks and Zones, which would also remove sky and terminal Candidates for free.
- **Latency was measured with this single Mac doing all local work.** Change detection runs on CPU, DINO and OWL on MPS, and the VLM on MLX. Model load times (a few seconds each) are excluded.

## Files and reproduce

- **Scripts:**
  - `common.py`: data, the simulated reference, scoring (wraps `../spike/run_spike.py`), crops and merging.
  - The proposers: `changedet.py`, `dinoanom.py`, `owl.py`.
  - `combos.py`: combines proposer outputs.
  - `vlm_verify.py` and `vlm_summary.py`: the local VLM verifier.
  - `evaluate.py`: threshold sweeps.
  - `hybrid.py`: the end-to-end pipeline.
  - `score_hybrid.py` and `escalation.py`: scoring and the escalation counterfactual.
  - `examples.py`: builds the examples image.
- **Outputs (`results/`):**
  - `cand__*.json`: Candidates per proposer and setting; the `__hard` suffix is hard drift.
  - `vlm__*.json`: verifier answers per Candidate.
  - `hybrid__*.json`: every decision with its model, confidence, cost and latency.
  - `examples.jpg`.
- **Weights:**
  - **Read-only from drone-lab:** DINOv2 ViT-S/14 (`models/follow`) and Qwen3-VL-4B-Instruct-4bit (`.models-vision`).
  - **New download:** `models/owlv2-base-patch16-ensemble`, 605 MB, safetensors only.

```sh
cd prototypes/local-detect
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python torch==2.14.0 torchvision==0.29.0 \
  opencv-python-headless numpy pillow scipy transformers==5.17.0 anthropic mlx-vlm==0.7.1 mlx==0.32.2 huggingface-hub
.venv/bin/python -I changedet.py && .venv/bin/python -I dinoanom.py && .venv/bin/python -I owl.py   # add FOD_REF=hard for drift
.venv/bin/python -I combos.py            # writes cand__change_20.json, cand__union_20_0.6.json, ...
.venv/bin/python -I evaluate.py results/cand__changedet.json --thr 20 50 200 --missed
.venv/bin/python -I vlm_verify.py results/cand__union_20_0.6.json
set -a; source ../../.env; set +a        # ANTHROPIC_API_KEY, process env only
.venv/bin/python -I hybrid.py results/cand__change_20.json --budget 0.5
.venv/bin/python -I score_hybrid.py results/hybrid__*.json && .venv/bin/python -I escalation.py results/hybrid__*.json
```
