# FOD test data sources: public datasets and synthetic generation

Answers [issue 0004](../issues/0004-fod-test-data-sources.md): which FOD and apron image data the gate-camera PoC can use or generate to measure Claude's accuracy, and on what terms.

Researched 2026-11-13. Each claim links to the source it came from. "Unverified" marks anything I could not confirm at the primary source.

## Bottom line

- **No public dataset matches the PoC's viewpoint.** That viewpoint is fixed gate/apron cameras, several angles around a parked aircraft, with GSE, people and markings in frame. Public FOD data is close-up pavement shots taken with handheld cameras or low-flying drones on runways and taxiways, with no aircraft in frame. The one real apron dataset (AIT Apron Dataset) is licensed for non-commercial use only and contains no FOD.
- **FOD-A is the only usable public FOD set.** It is MIT-licensed, so commercial PoC use is allowed. It has 31 FAA-derived classes and over 30k boxes. Use it for an object-recognition sanity check, not to estimate gate-camera accuracy.
- **The headline accuracy number must come from the airline's own gate cameras.** The core set should be physically seeded FOD photographed at a real or out-of-service gate, plus clean captures from the same cameras. AI-edited images can fill out the matrix of angles, sizes, lighting and object types, but they have known realism problems and must be reported as a separate number.

## 1. Public datasets

| Dataset | Content | Viewpoint | Size and labels | Licence / availability | Fit for the PoC |
|---|---|---|---|---|---|
| **FOD-A** (Munyer et al., IEEE ICMLA 2021) | 31 FOD classes: Bolt, Nut, Washer, Wrench, Pliers, Hammer, Screwdriver, Wire, Hose, FuelCap, LuggageTag, LuggagePart, PlasticPart, MetalSheet, PaintChip, Rock, SodaCan, Battery, Tape, Wood and others | Video frames from handheld and UAV cameras; "runway or taxiway background"; mostly one object on bare pavement, zoomed out but still near-field | Over 30,000 boxes (Pascal VOC); per-instance light (bright 17,012 / dim 12,464 / dark 4,387) and weather (dry 26,647 / wet 7,216) tags; v2.1 at 400×400 (8.3 GB) or 300×300 VOC with train/val split (412 MB) | **MIT** (LICENSE file, © 2020 FOD-UNOmaha). Google Drive download | **Partial.** Commercial use is fine and the class list is aligned with the FAA. However: there are no aircraft, GSE or gate context; the images are downscaled to 400 px; there are no FOD-free negatives; and frames from the same video are near-duplicates, so sample across videos |
| **FODAnomalyData** (Munyer et al., CSCI'22) | Clean runway and taxiway pavement for training; FOD scattered at random for testing | UAS at 30 ft (0.1 in/px), cut into 448×448 patches | 81,185 clean patches and 447 annotated FOD patches | Repo is MIT, but the README says **"The data is no longer available"** | **None.** Not obtainable |
| **Apron Dataset** (AIT, ACCV-W 2022) | Real apron scenes: 43 classes of GSE, container trolleys, aircraft, people and signs. No FOD class | Cameras mounted on apron transport vehicles, so ground level and moving | 10,098 images; boxes plus atmosphere, lighting, time-of-day and occlusion tags | **Non-commercial only.** Bars use "with a purpose to procure a commercial gain" and bars redistribution. Available on request | **Not usable** for an airline PoC without a separate licence from AIT. Its value is as a reference for what apron imagery looks like |
| **Xu et al. 2018** (EURASIP JIVP), Shanghai Hongqiao | Material classification: metal / concrete / plastic | Zoomed-in close-ups, per the FOD-A paper's comparison | 3,470 images, about 3,000 instances | Paper is CC BY 4.0. Dataset release and licence are **unverified** (no repo found; the publisher page was blocked) | **Low.** Classification only, not detection, and close-ups |
| **AARFOD** (2024, arXiv 2403.08499) | FOD-A merged with RailFOD23 (railway) | Runway plus rail track | 48,409 images, 35 classes, 74,334 boxes | No download link or dataset licence on arXiv | **Low.** Its airport portion is just FOD-A |
| **Roboflow Universe projects** (e.g. "FOD detection using yolov5", 4 classes) | Community uploads, often re-cuts of FOD-A | Varies | Small | Licence set per project (that one says CC BY 4.0) | **Low.** Unknown provenance; check each project's images and licence before use |
| **Private sets** (e.g. Sensors 2025, 12,000 images from Luoyang Beijiao and Xuzhou Guanyin airports, apron included) | — | — | — | Public release **unverified** | Ask the authors only if it becomes necessary |

FOD-A's own authors make the same point about field data: "It is likely that images collected during applied FOD detection tasks will not be zoomed into objects" ([FOD-A paper §III-A](https://arxiv.org/pdf/2110.03072)). Their later paper goes further and argues that supervised detection "appears to be impractical" because "any object that is improperly located … can be considered as FOD" ([2210.16901 §II-B](https://arxiv.org/pdf/2210.16901)). This supports scoring "is there something that shouldn't be here" first and object category second.

## 2. Seeded physical FOD: the recommended core

The most realistic labelled data is real objects placed in front of the PoC's real cameras.

- **Standard object kit.** FAA AC 150/5220-24 (*Airport FOD Detection Equipment*) defines the test targets that FOD detection systems must find. They are an unpainted metal cylinder 1.2 in high × 1.5 in diameter; a white, grey or black 1.7 in sphere (golf ball); and a group of objects each no larger than 4 in unless stated: a chunk of asphalt or concrete, part of a runway light fixture, an adjustable wrench up to 8 in, a deep socket at least 2 in, a piece of tyre rubber, a distorted metal strip up to 8 in, a fuel cap, a lug nut, a hydraulic line up to 8 in, and a 2 in white PVC pipe. The AC's definitions cover runways, taxiways and aprons ([AC 150/5220-24 ¶ on Detection Performance](https://www.faa.gov/documentLibrary/media/Advisory_Circular/150_5220_24.pdf)). This gives the PoC an FAA-anchored, reproducible test kit. Add apron-typical items from the FAA list quoted in FOD-A: catering and pallet plastic, luggage parts, bag tags, safety wire, cans.
- **Protocol.**
  1. Capture each camera angle clean.
  2. Place objects at known positions, logging object ID, position and distance from camera.
  3. Re-capture from every angle.
  4. Remove the objects and capture clean again. This gives paired clean/FOD frames with free ground truth, and the clean-again frames measure false alarms.
  5. Vary time of day and wet/dry conditions to mirror FOD-A's light and weather tags.
- **Caveats.** This needs airside access and a safety sign-off, and every object must be recovered afterwards (count in = count out). Ground-truth design is the subject of issue 0008.

## 3. Synthetic insertion into clean apron frames

Use this to multiply the seeded set across more angles, object types and conditions. Claude analyses images but does not generate them, so a separate tool is needed.

| Approach | How | Licence / commercial use | Realism caveats |
|---|---|---|---|
| **Copy-paste compositing** (cut objects out of FOD-A or your own photos and paste them onto clean gate frames) | SRIA ([arXiv 2309.13264](https://arxiv.org/abs/2309.13264)) pasted segmented FOD-A objects onto 29 runway backgrounds to make 2,227 images, and out-of-distribution accuracy rose from 41% to 92% for a trained detector | FOD-A source objects are MIT; backgrounds are your own | Pixel-exact ground truth. But scale and perspective often mismatch, there are no cast or contact shadows, edges show halos, and FOD-A cut-outs are only 400 px. Airport-FOD3S (Sensors 2025, [MDPI 25/15/4565](https://www.mdpi.com/1424-8220/25/15/4565)) names exactly these problems ("did not match the actual scene", wrong size) and adds stages for size, blending and style transfer; its full text was not reviewed here |
| **Mask-based inpainting with a hosted model** (OpenAI GPT Image edits; Google Gemini "Nano Banana" image models) | Supply a clean frame, a mask and a prompt such as "a steel wrench lying on the concrete" | Commercial API terms. Gemini: "All generated images include a SynthID watermark" ([Gemini image docs](https://aistudio.google.com/docs/image-generation)) | OpenAI: "Masking with GPT Image is entirely prompt-based", meaning the model "may not follow the mask's exact shape precisely" ([OpenAI image guide](https://developers.openai.com/api/docs/guides/image-generation)). So the box must be re-derived after the edit, the output must be diffed against the clean frame for unintended changes elsewhere, and the edit may come out at the wrong scale |
| **Open-weight inpainting** (SDXL Inpainting 0.1; FLUX.1 Fill [dev]) | Run locally with a mask | SDXL inpainting: CreativeML **OpenRAIL++** ([model card](https://huggingface.co/diffusers/stable-diffusion-xl-1.0-inpainting-0.1)). FLUX.1 Fill [dev]: **FLUX.1 [dev] Non-Commercial License** on the weights, although the card says outputs may be used commercially ([model card](https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev)). Have legal read the licence before relying on it | Same issues: plausible-looking but wrong-scale objects, texture "melt" at the mask edge, and changes to the surrounding pavement |

**Caveats that apply to all synthetic images:**

1. **Shortcut risk.** A model, Claude included, may pick up on editing artifacts (seams, re-encoding noise, watermark residue) rather than the debris. To control for this, run the same edit pipeline on clean frames with a null edit or a harmless change, and include those as negatives.
2. **Scale.** The objects that matter, such as nuts, safety wire and paint chips, may be only a few pixels wide from a gate camera. Generators tend to draw them too large. Check object size against a seeded real reference at the same distance.
3. **Reporting.** Report accuracy on real seeded images and on synthetic images as separate numbers, and never pool them. Sim2Real gaps are well documented, and FOD-S2R ([arXiv 2512.01315](https://arxiv.org/html/2512.01315)) exists specifically to measure one, albeit in a fuel-tank setting.
4. **Labelling.** Tag every synthetic image as synthetic in its metadata so it cannot leak into "real" evaluation sets or demos.

## 4. Recommended mix

For a first accuracy run, sized for a PoC:

| Share | Source | Purpose |
|---|---|---|
| ~40% | **Real gate-camera captures, physically seeded** with the AC 150/5220-24 kit plus apron items, in clean → seeded → cleared triplets, all angles, day/night and wet/dry | Headline accuracy and false-alarm rate. The only set that answers the actual question |
| ~25% | **Real clean gate captures** (including normal clutter such as chocks, cones, GSE, people, hoses and markings) | False-positive rate on scenes that are busy but legitimate. This is critical, because "not FOD" objects dominate an apron |
| ~25% | **Synthetic insertions** into those same clean frames (hosted inpainting for realism, copy-paste for exact boxes), plus null-edit negatives | Wider coverage of object types, sizes and positions; reported separately |
| ~10% | **FOD-A sample** (stratified by class and by light/weather tag, a few frames per source video) | Object-recognition sanity check against FAA categories and a cross-check with published results. Not a viewpoint proxy |

Excluded: the Apron Dataset (non-commercial licence), FODAnomalyData (withdrawn), and Roboflow or private sets (unclear provenance or not released).

## Sources

- FOD-A repo and MIT LICENSE: https://github.com/FOD-UNOmaha/FOD-data (LICENSE: https://raw.githubusercontent.com/FOD-UNOmaha/FOD-data/master/LICENSE; class histogram `Examples/AnnotationInstancesV2.1.png`)
- FOD-A paper: https://arxiv.org/abs/2110.03072 (PDF https://arxiv.org/pdf/2110.03072)
- FODAnomalyData repo ("no longer available"): https://github.com/FOD-UNOmaha/FODAnomalyData; paper: https://arxiv.org/abs/2210.16901
- Apron Dataset repo and LICENCE: https://github.com/apronai/apron-dataset; paper: https://openaccess.thecvf.com/content/ACCV2022W/MLCSA/papers/Steininger_Towards_Scene_Understanding_for_Autonomous_Operations_on_Airport_Aprons_ACCVW_2022_paper.pdf
- Xu et al. 2018: https://doi.org/10.1186/s13640-018-0261-2
- AARFOD: https://arxiv.org/abs/2403.08499
- Roboflow example: https://universe.roboflow.com/yolo-lmxxo/fod-detection-using-yolov5
- Sensors 2025 private airport set: https://doi.org/10.3390/s25165116
- FAA AC 150/5220-24: https://www.faa.gov/documentLibrary/media/Advisory_Circular/150_5220_24.pdf
- SRIA domain randomisation: https://arxiv.org/abs/2309.13264
- Airport-FOD3S: https://www.mdpi.com/1424-8220/25/15/4565
- FOD-S2R: https://arxiv.org/html/2512.01315
- OpenAI image generation guide: https://developers.openai.com/api/docs/guides/image-generation
- Gemini image generation docs: https://aistudio.google.com/docs/image-generation
- SDXL Inpainting model card: https://huggingface.co/diffusers/stable-diffusion-xl-1.0-inpainting-0.1
- FLUX.1 Fill [dev] model card: https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev
