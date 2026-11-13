# Spike 0007: Claude FOD detection feasibility (PROTOTYPE, throwaway)

Evidence for [issue 0007](../../issues/0007-claude-detection-feasibility-spike.md). The human makes the final call; this file gives the evidence and a recommendation. Run on 2026-11-13 against the real Claude API.

## TL;DR

- **Detection works on clearly visible debris and fails on tiny debris.** With 2×2 tiling, Sonnet 5.5 found 26 of 28 seeded objects (93%). Opus 5.5 and Haiku 5.5 each found 25 (89%). Every object 26–45 px wide (at 3840×2160) was found by all tiled runs. Objects of 25 px or less were found 4 times in 6.
- **Pixel boxes are accurate enough to commit to.** When an object was found, the median box-centre error was 1–3 px at 4K, the true centre fell inside the predicted box 87–100% of the time, and IoU was at least 0.5 in 70–92% of matches.
- **Tiling clearly helps recall but adds false alarms.** Tiling roughly doubles cost. Every false alarm except one was tagged `low` confidence.
- **Recommendation:** use a pixel bounding box, a single tiled pass (no downscaling), and **Sonnet 5.5** for the PoC. Before adding a second pass, re-measure on real staged captures (0011).
- **Caveat:** 22 images, 28 objects, one run per configuration. A difference of 1–2 objects (4–7 points) between models is within noise.

## Dataset (`data/images/`, built by `make_dataset.py`)

There are 22 frames, all 3840×2160 to simulate a 4K fixed camera, built from 6 background scenes:

| Kind | Count | What |
|---|---|---|
| seeded | 12 | 2 variants per scene, 2–3 debris objects each, **28 objects** in total |
| clean | 6 | unedited background |
| no-op edit | 4 | Re-encoded, ±4% brightness, and 1–2 pavement patches pasted onto pavement with the same feathered compositing used for debris. This tests whether paste artefacts alone trigger findings. |

**Backgrounds.** Wikimedia Commons photos of narrowbody aircraft at gates or aprons. The originals are in `data/raw/commons/`, with metadata in `data/raw/commons_meta.json`:

| Scene | Source | Author | Licence |
|---|---|---|---|
| `pelita_pwf` (nose-on, jet bridge, tug, day) | [Pelita Air Airbus A320 PK-PWF Jakarta 2025 (01).jpg](https://commons.wikimedia.org/wiki/File:Pelita_Air_Airbus_A320_PK-PWF_Jakarta_2025_(01).jpg) | Bahnfrend | CC0 |
| `pelita_pwl` (raised 3/4 view, ramp crew, day) | [Pelita Air Airbus A320 PK-PWL Jakarta 2025 (01).jpg](https://commons.wikimedia.org/wiki/File:Pelita_Air_Airbus_A320_PK-PWL_Jakarta_2025_(01).jpg) | Bahnfrend | CC0 |
| `spring` (side view, belt loader, carts, day) | [Spring Airlines Airbus A320 B-6708 at Shanghai Pudong June 2025.jpg](https://commons.wikimedia.org/wiki/File:Spring_Airlines_Airbus_A320_B-6708_at_Shanghai_Pudong_June_2025.jpg) | 4300streetcar | CC BY 4.0 |
| `brussels` (737 at jet bridge, low sun, dark foreground) | [Airport Brussels 1.jpg](https://commons.wikimedia.org/wiki/File:Airport_Brussels_1.jpg) | Karelj | Public domain |
| `tansonnhat` (high WIDE-style view, hazy) | [Tansonnhat9.jpg](https://commons.wikimedia.org/wiki/File:Tansonnhat9.jpg) | Genghiskhan | Public domain |
| `wingo` (737 at gate, **night**) | [Wingo Boeing 737-700 sitting at the gate at Cali Airport.jpg](https://commons.wikimedia.org/wiki/File:Wingo_Boeing_737-700_sitting_at_the_gate_at_Cali_Airport.jpg) | Simply Aviation | CC BY 2.0 |

Each image was cropped to 16:9, keeping the ground, and resized to 3840×2160. Two were upscaled to reach that size (Brussels by 1.6×, Tansonnhat by 1.18×), so they are softer than a real 4K camera.

**Debris** came from two sources:
- 11 objects cut from the **FOD-A** example sheet `Examples/manyEx.png` ([FOD-UNOmaha/FOD-data](https://github.com/FOD-UNOmaha/FOD-data), MIT, © 2020 FOD-UNOmaha). They are hammer, cutter, pliers, wire, plastic parts, rock, bolt and luggage tag. The licence is saved in `data/raw/foda/LICENSE`.
- 4 simple drawn objects: soda can, bag tag, wrench and plastic bag.

Objects were pasted with a feathered mask, a soft contact shadow and brightness matched to the local pavement. Sizes range from 16 to 80 px on the long edge (6 small at 25 px or less, 16 medium at 26–45 px, 6 large above 45 px), chosen to be roughly plausible for 5–30 cm objects at those distances. Placements are in `placements.json` and ground truth is in `data/images/ground_truth.json`.

**Pre-existing objects.** The real photos already contain some loose items, such as a dark mat at the Wingo stand, a white scrap at `pelita_pwl` and a blurred white object at Tansonnhat. These were not labelled. I report two sets of numbers:
- **Strict:** any finding that doesn't match a seeded object counts as a false alarm.
- **Adjudicated:** findings inside 5 regions that I checked by eye and confirmed as real loose objects in the source photos are excluded (`adjudication.json`). This was done after the runs, so treat it as a reading aid, not the headline.

## Method (`run_spike.py`)

- **Prompt:** one system prompt with a FOD definition, an explicit NOT-FOD list (aircraft, GSE, people, cones and chocks, markings, stains, shadows, background) and a pixel-coordinate instruction. The exact text is `SYSTEM_PROMPT` in the script.
- **Output:** structured outputs (`output_config.format`, JSON schema). Each Finding has `image_index`, `x1, y1, x2, y2` (int px), a `category` enum, `description`, a verbal `location`, and `confidence` (low, medium or high). All 132 calls returned `end_turn` with valid JSON, and none were refused.
- **Two modes, one request per frame:**
  - **whole:** the frame is pre-resized to 2560×1440, at or under the 2576 px high-res-tier limit, so Claude sees exactly the pixels sent. Boxes are scaled ×1.5 back to 4K.
  - **tiles:** four overlapping 2048×1152 tiles at native resolution go in **one** request. Boxes are offset back to the full frame and duplicates from the overlap are removed.
- **Models:** `claude-opus-5-5`, `claude-sonnet-5-5` and `claude-haiku-5-5`, all at `effort: medium` with adaptive thinking and streaming. `served_model` matched the requested model on every call.
- **No server-side `fallbacks`, on purpose.** A silent model swap would contaminate a per-model comparison. A production build should add them.
- **Scoring:**
  - A seeded object counts as found when a Finding's centre is within 150 px (at 4K) of the object's centre, or IoU exceeds 0.1. Matching is greedy and one-to-one.
  - Unmatched Findings are false alarms (FA).
  - Localisation is measured as IoU, centre error, whether the true centre falls inside the predicted box, and whether the prediction lands in the same cell of a 4×4 grid (each cell is 960×540 px at 4K).
- **Cost** is estimated from `usage` at list prices: Opus $4/$20, Sonnet $2/$10, Haiku $0.10/$0.50 per MTok. **Latency** is wall clock per request, with 4 requests running in parallel.

## Results

### Strict

| run | recall | seeded imgs with ≥1 hit | FA / img (all) | FA / control img | clean controls with 0 FA | median IoU | IoU≥0.5 | GT centre inside box | median centre err (px @4K) | 4×4 grid hit | median / max latency s | mean in / out tokens | $ / frame |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 whole | 23/28 (82%) | 11/12 | 0.18 | 0.20 | 8/10 | 0.69 | 16/23 | 20/23 | 2.7 | 23/23 | 5.8 / 8.4 | 6148 / 311 | 0.031 |
| Opus 5.5 tiles | 25/28 (89%) | 12/12 | 0.55 | 0.70 | 5/10 | 0.80 | 22/25 | 23/25 | 1.4 | 24/25 | 5.3 / 8.4 | 13941 / 290 | 0.062 |
| Sonnet 5.5 whole | 22/28 (79%) | 12/12 | 0.18 | 0.30 | 7/10 | 0.72 | 19/22 | 20/22 | 2.5 | 20/22 | 4.3 / 8.9 | 6148 / 261 | 0.015 |
| **Sonnet 5.5 tiles** | **26/28 (93%)** | 12/12 | 0.45 | 0.70 | 4/10 | **0.85** | 24/26 | 24/26 | 1.1 | 25/26 | 4.6 / 7.5 | 13941 / 307 | 0.031 |
| Haiku 5.5 whole | 17/28 (61%) | 10/12 | 0.45 | 0.50 | 5/10 | 0.72 | 13/17 | 17/17 | 2.0 | 16/17 | 4.0 / 5.4 | 6148 / 397 | 0.0008 |
| Haiku 5.5 tiles | 25/28 (89%) | 12/12 | 0.73 | 1.30 | 4/10 | 0.78 | 21/25 | 23/25 | 1.6 | 25/25 | 5.4 / 7.2 | 13941 / 604 | 0.0017 |

### Adjudicated (pre-existing real objects excluded; recall and localisation unchanged)

| run | FA / img (all) | FA / control img | clean controls with 0 FA |
|---|---|---|---|
| Opus 5.5 whole | 0.05 | 0.00 | 10/10 |
| Opus 5.5 tiles | 0.14 | 0.20 | 8/10 |
| Sonnet 5.5 whole | 0.14 | 0.20 | 8/10 |
| Sonnet 5.5 tiles | 0.09 | 0.20 | 8/10 |
| Haiku 5.5 whole | 0.32 | 0.40 | 6/10 |
| Haiku 5.5 tiles | 0.55 | 1.10 | 4/10 |

### Recall by object size (long edge at 3840×2160)

| run | small ≤25 px (n=6) | medium 26–45 px (n=16) | large >45 px (n=6) |
|---|---|---|---|
| Opus whole | 4 | 15 | 4 |
| Opus tiles | 4 | 16 | 5 |
| Sonnet whole | 4 | 13 | 5 |
| Sonnet tiles | 4 | 16 | 6 |
| Haiku whole | 2 | 11 | 4 |
| Haiku tiles | 4 | 16 | 5 |

### Other observations

- **No-op edits caused no findings.** None of the no-op-edited controls had a finding at a pasted-patch location. Findings on no-op frames sit at the same spots as on the matching clean frame, so paste artefacts are not what the models react to.
- **Pre-existing objects were found consistently.** The real loose items in the backgrounds (the Wingo mat, the `pelita_pwl` scrap, the Tansonnhat white object) were reported by most configurations on every frame of that scene.
- **Cost per 6-Angle Inspection, extrapolated from per-frame cost:**

  | | whole | tiles |
  |---|---|---|
  | Sonnet | $0.09 | $0.19 |
  | Opus | $0.18 | $0.37 |
  | Haiku | <$0.01 | $0.01 |

  These match the estimates in `research/claude-vision-capabilities.md`.
- **Latency per Inspection:** each frame takes 4–6 s (median), at most 9 s. Six Angles sent as parallel requests should take about 6–9 s of wall clock. Sent one after another, they would take about 30 s.
- **Thinking was very short at medium effort:** about 260–600 output tokens per call, including the JSON. Higher effort was not tested.
- **Total API spend:** about **$3.10** across 132 calls.

## Example misses and false alarms

See `results/examples_misses_and_false_alarms.jpg`. Per-image detail is in `results/*.scored.json`, and the raw responses are in `results/pred__*.json`.

**Misses:**
- **Tiny bolts (20–22 px).** Missed by **all 6 configurations** in `pelita_pwf__fod1` (on a red-hatched, stained surface) and `wingo__fod2` (at night). This is the practical floor: a 5 cm bolt at that size is about 2.5 cm/px, beyond what any configuration resolves.
- **Grey plastic part, 70 px, in deep shadow beside a truck** (`brussels__fod1`, dusk). Missed by all configurations. Shadows and dark scenes are a real weakness.
- **Red hammer, 80 px, standing out clearly.** Opus whole missed it. Sonnet whole found it but described it as a "possibly cone fragment, low confidence". Objects that look like equipment can be rationalised away.
- **Haiku whole missed 11 of 28.** It missed a whole image's worth of 18–60 px objects in `pelita_pwl__fod2` and in `spring__fod2`.

**False alarms:**
- **Paint or spill stain under the jet bridge** (`spring`). Reported in 4 of 6 configurations, always `low`.
- **Drain cover** (`tansonnhat`), from Opus tiles.
- **"Small cylindrical object, possibly a can"** at an empty spot (`spring__fod2`, Opus whole). This was the **only medium-confidence false alarm** in all 132 calls, and the only clear hallucination.
- **Bags on a dolly bed** (Sonnet tiles). These are on equipment, not the ground.
- **Haiku** reported specks and dark patches, and once listed a traffic cone while saying in the same Finding that it is not FOD.

## Recommendation (for the human decision on 0007)

### 1. Highlight form: commit to a **pixel bounding box**, stored in full-frame coordinates

Coarser forms throw away precision the model already gives us:
- A found box puts its centre a median of 1–3 px from the object at 4K.
- 87–100% of boxes contain the object's centre.
- A 4×4 grid cell (960×540 px) is right 91–100% of the time, but a cell is far too large for a ramp agent to find a 3 cm bolt.

In the UI:
- Draw the box padded to a minimum display size, since small boxes are hard to see.
- Show the model's verbal `location` ("left of nose gear, near the cone") as secondary text.
- Derive the grid cell or Zone in code if the dashboard needs it. Don't ask the model for it.

Caveat: pasted objects have crisp, high-contrast edges, so these localisation numbers are probably optimistic. Re-check IoU on real seeded captures (0011).

### 2. Use a **single tiled pass at native resolution**; a crop re-check pass is optional, decided by real-data false alarms

- **Tiling** (no downscale, 4 tiles in one request) raised recall for every model: Sonnet from 79% to 93%, Opus from 82% to 89%, Haiku from 61% to 89%. It costs about 2.3× the input tokens and adds no meaningful latency (requests are parallel, and the 4 tiles go in one request).
- **The price is more low-confidence false alarms:** strict false alarms on controls went from 0.2–0.3 to 0.7 per image for Sonnet and Opus.
- **Proposal:**
  - Treat `low`-confidence Findings as "check" items rather than full FINDINGS. All false alarms except one were `low`.
  - Add a second pass (crop each low-confidence candidate at native resolution and re-ask) only if the false-alarm rate on real gate captures is unacceptable. That two-pass flow was **not tested** here.
- A single whole-frame pass is not enough for small debris: Haiku whole found only 61%, and Sonnet whole missed 3 of 16 medium objects.

### 3. Model tier: **Sonnet 5.5** (tiled, effort medium) for the PoC

- It had the best recall (93%) and the best localisation (median IoU 0.85).
- It costs about $0.19 per 6-Angle Inspection and has a median latency of 4.6 s per frame.
- **Opus 5.5** (also at medium) was no better on this sample and costs twice as much. Keep it as a drop-in to re-test at higher effort if real-data recall falls short.
- **Haiku 5.5** tiled matches on recall but has about 2–5× the false alarms on clean frames. It is about 1/20 of Sonnet's cost, which makes it worth trying as a cheap first-pass candidate finder whose Findings Sonnet re-checks. Not tested.

### Caveats

- **Small sample, one run each.** There are 28 objects, so one object is 3.6 points of recall. Run-to-run variance was not measured. Treat Opus vs Sonnet as a tie.
- **Composites are not gate cameras.**
  - Pasted and drawn objects lack true scale and perspective.
  - The backgrounds are public photos from varied viewpoints, two of them upscaled.
  - The real-world false-alarm rate on busy aprons (hoses, chocks, straps, wet patches) is unmeasured.
  - The headline accuracy must come from 0011 staged captures.
- **The adjudication was done after the runs** by me, from the model outputs. The strict table is the conservative one.
- **Only medium effort was tested.** No crop tool and no two-pass flow were tested. Night and dusk are covered by just 2 scenes, and that is where the misses cluster.
- **Not run: the multi-Angle Inspection test.** That test sends all 6 Angles in one request and is implemented as `run_spike.py inspect`. The account's API credit balance ran out (HTTP 400 "credit balance is too low") on its first call, after the 6 main runs completed. The code is therefore **untested against the API**.
- **The schema was edited after the runs.** `image_index` was widened from enum 0–3 to 0–23 to support `inspect`. The 6 scored runs used 0–3.
- **The proxy evaluation was dropped.** The original plan had Claude Code view the images itself as a proxy. Real API results made it redundant.

## Reproduce

```sh
cd prototypes/spike
uv venv .venv && uv pip install --python .venv/bin/python pillow anthropic
.venv/bin/python -I make_dataset.py data/raw data/images placements.json     # rebuild the set
set -a; source ../../.env; set +a                                           # ANTHROPIC_API_KEY
.venv/bin/python -I run_spike.py run data/images results --model claude-sonnet-5-5 --mode tiles --budget 1.0
.venv/bin/python -I run_spike.py inspect data/images results --model claude-sonnet-5-5 --mode whole   # untested
.venv/bin/python -I run_spike.py table data/images results/pred__*medium.json [--ignore adjudication.json]
.venv/bin/python -I run_spike.py prepare data/images /tmp/views --mode tiles   # exact images Claude sees
```

To point the harness at real gate captures (0011), drop 3840×2160 JPEGs into a directory with a `ground_truth.json` in the same format. Other frame sizes need `FULL_W`, `FULL_H` and the tile constants adjusted.
