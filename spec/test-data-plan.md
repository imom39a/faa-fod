# Test Data Plan (PoC v1.0)

Decided in issues 0008 and 0016. Sources: `research/gate-image-archives.md`, `research/fod-test-data-sources.md`.

- **Images:** real photographs from Wikimedia Commons, fetched with `prototypes/image-archive/build_manifest.py` using an anonymous client. Attribution is stored in the manifest. Photos already used in the 22-frame spike set are excluded.
- **Size:** 30 Inspections, 180 Angle images.
  - 10 pre-arrival (empty stand): 5 clean, 3 with debris, 2 with GSE inside the equipment restraint line.
  - 20 pre-departure (aircraft on stand): 8 clean, 10 with debris, 2 with an unusable Angle.
  - At least 20% of Inspections are night or wet.
- **Angles:** ENG-L and AFT are thin in public photos. They are filled by cropping those zones from wide frames and by mirroring ENG-R photos, each labelled as a crop or mirror.
- **Debris:** FOD-A cut-outs (MIT licence) composited at known positions. 1 to 4 items per debris Inspection, covering all 8 named categories, half in Critical zones, at least a quarter under 30 px.
- **Controls:** clean frames with normal clutter, and clean frames passed through the compositing step with nothing added.
- **Reference frames:** each Gate's reference is its clean frame with simulated camera and lighting drift, as in `prototypes/local-detect`.
- **Ground truth:** per image, either clean or a list of items with box (pixels), category, object class, zone tier and expected severity, in the spike's `ground_truth.json` format. Unusable Angles carry their reason.
- **Scoring:** detector thresholds stay at the values chosen on the 22-frame spike set. The 30 Inspections are used only for scoring, against the targets in the baseline (NF-1 to NF-3). Results on mirrored or cropped Angles are reported separately.
- **Known limits to state with results:** composited debris, simulated references with nothing moving, and no Concourse T imagery.
