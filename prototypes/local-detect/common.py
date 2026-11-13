"""PROTOTYPE (ticket 0012) - throwaway. Shared helpers: data, reference frames, scoring.

Scoring reuses prototypes/spike/run_spike.py (same ground_truth.json format, same greedy matcher).
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPIKE = ROOT / "prototypes/spike"
IMAGES = SPIKE / "data/images"
RESULTS = HERE / "results"
DRONE_LAB = Path("/Users/vinothshanmugam/code/jev-playground/drone-lab")  # READ-ONLY

sys.path.insert(0, str(SPIKE))
import run_spike  # noqa: E402  (score, aggregate, iou, centre_dist, PRICES, SYSTEM_PROMPT ...)

GT = json.loads((IMAGES / "ground_truth.json").read_text())["images"]
SCENES = sorted({g["frame"] for g in GT.values()})

# Each spike scene stands in for one Angle of a 6-Angle Inspection (assumption, for zone/severity only).
ANGLE_OF = {"pelita_pwf": "NOSE", "pelita_pwl": "ENG-L", "brussels": "ENG-R",
            "spring": "CARGO", "wingo": "AFT", "tansonnhat": "WIDE"}
TIER_OF = {"NOSE": "Critical", "ENG-L": "Critical", "ENG-R": "Critical",
           "CARGO": "Service", "AFT": "Service", "WIDE": "General"}

# Candidate recall uses a TIGHTER match than the spike's 150 px: the Candidate's centre must be within
# 60 px of the object (or IoU > 0.1), so a 320 px crop around the Candidate certainly contains it.
CAND_RADIUS = 60


def load(name):
    return cv2.imread(str(IMAGES / name), cv2.IMREAD_COLOR)  # BGR uint8


REF_MODE = os.environ.get("FOD_REF", "mild")  # "mild" (default) or "hard" drift
SUFFIX = "" if REF_MODE == "mild" else "__" + REF_MODE


def make_reference(scene, seed=0, mode=None):
    """Simulated 'recent clean reference' for a fixed camera.

    The spike's clean frame IS the background the debris was pasted on, so diffing against it directly
    is trivially perfect on clean frames. Instead the reference is the clean frame re-captured with
    camera/sensor drift: a 1.6/-1.1 px shift + 0.03 deg rotation, a global gain and gamma change, a soft
    left-to-right illumination gradient (+-6%), sensor noise (sigma 2.5) and JPEG q85 re-encoding.
    It does NOT simulate moving GSE/people, rain, or shadows moving with the sun.
    mode="hard": 4.3/-3.2 px shift + 0.12 deg rotation, gain 1.10, gamma 1.15, +-15% gradient,
    a soft 25%-dark cloud-shadow ellipse, sensor noise sigma 4.5 and JPEG q75.
    """
    hard = (mode or REF_MODE) == "hard"
    rng = np.random.default_rng(seed)
    im = load(f"{scene}__clean.jpg").astype(np.float32)
    h, w = im.shape[:2]
    rot, sx, sy, gain, gamma, g, noise, qual = ((0.12, 4.3, -3.2, 1.10, 1.15, 0.15, 4.5, 75) if hard
                                                else (0.03, 1.6, -1.1, 1.04, 1.05, 0.06, 2.5, 85))
    M = cv2.getRotationMatrix2D((w / 2, h / 2), rot, 1.0)
    M[0, 2] += sx; M[1, 2] += sy
    im = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    grad = np.linspace(1 - g, 1 + g, w, dtype=np.float32)[None, :, None]
    im = 255.0 * ((im / 255.0) ** gamma) * gain * grad
    if hard:
        sh = np.zeros((h, w), np.float32)
        cv2.ellipse(sh, (int(w * 0.6), int(h * 0.75)), (900, 350), 15, 0, 360, 1.0, -1)
        sh = cv2.GaussianBlur(sh, (0, 0), 120)
        im *= (1 - 0.25 * sh)[..., None]
    im += rng.normal(0, noise, im.shape).astype(np.float32)
    im = np.clip(im, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, qual])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def query_frames():
    """All 22 frames; each is compared with the simulated reference of its scene."""
    return sorted(GT)


def score_candidates(cands_by_image, radius=CAND_RADIUS):
    """cands_by_image: {name: {"findings": [{"box": [x1,y1,x2,y2], "score": s}], "latency_s": t}}"""
    old = run_spike.MATCH_RADIUS
    run_spike.MATCH_RADIUS = radius
    try:
        per = run_spike.score(IMAGES, {"results": cands_by_image})
    finally:
        run_spike.MATCH_RADIUS = old
    return per


def summarise(per):
    n_gt = sum(p["n_gt"] for p in per); tp = sum(p["tp"] for p in per)
    clean = [p for p in per if p["kind"] == "clean"]; noop = [p for p in per if p["kind"] == "noop"]
    seeded = [p for p in per if p["kind"] == "seeded"]
    lat = sorted(p["latency_s"] for p in per if p["latency_s"] is not None)
    return {
        "recall": tp / n_gt, "tp": tp, "n_gt": n_gt,
        "cand_per_clean": sum(len(p["false_alarms"]) for p in clean) / max(1, len(clean)),
        "cand_per_noop": sum(len(p["false_alarms"]) for p in noop) / max(1, len(noop)),
        "fp_per_seeded": sum(len(p["false_alarms"]) for p in seeded) / max(1, len(seeded)),
        "median_latency_s": lat[len(lat) // 2] if lat else None,
        "missed": [f"{p['image']}:{m}" for p in per for m in p["missed"]],
    }


def nms_boxes(items, iou_thr=0.3, dist=30):
    """items sorted by score desc; drop overlapping/near duplicates."""
    kept = []
    for f in sorted(items, key=lambda d: -d["score"]):
        if any(run_spike.iou(f["box"], k["box"]) > iou_thr or run_spike.centre_dist(f["box"], k["box"]) < dist for k in kept):
            continue
        kept.append(f)
    return kept


def save(name, obj):
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / name).write_text(json.dumps(obj, indent=1, default=float))


CROP = 320


def crop_candidate(bgr, box, size=CROP, mark=True):
    """Square crop centred on the Candidate at native resolution (downscaled only if the box is bigger
    than ~80% of the crop). A thin red rectangle marks the Candidate. Returns RGB uint8 and the crop origin."""
    H, W = bgr.shape[:2]
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    side = int(max(size, 1.25 * max(box[2] - box[0], box[3] - box[1])))
    x0 = int(min(max(0, cx - side / 2), W - side)); y0 = int(min(max(0, cy - side / 2), H - side))
    im = bgr[y0:y0 + side, x0:x0 + side].copy()
    if mark:
        p = 8
        cv2.rectangle(im, (int(box[0] - x0 - p), int(box[1] - y0 - p)), (int(box[2] - x0 + p), int(box[3] - y0 + p)), (0, 0, 255), 2)
    if side != size:
        im = cv2.resize(im, (size, size), interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB), (x0, y0, side)


def label_candidates(name, cands, radius=CAND_RADIUS):
    """Mark each Candidate tp=True if it is the greedy match of a seeded object (same rule as scoring)."""
    objs = GT[name]["objects"]
    pairs = sorted((run_spike.centre_dist(o["box"], f["box"]), oi, fi) for oi, o in enumerate(objs) for fi, f in enumerate(cands))
    mo, mf = set(), {}
    for d, oi, fi in pairs:
        if oi in mo or fi in mf:
            continue
        if d <= radius or run_spike.iou(objs[oi]["box"], cands[fi]["box"]) > 0.1:
            mo.add(oi); mf[fi] = objs[oi]["label"]
    return [dict(f, tp=fi in mf, gt_label=mf.get(fi)) for fi, f in enumerate(cands)]


def merge_near(cands, gap=24):
    """Merge Candidates whose boxes are within `gap` px of each other (one object split into fragments,
    e.g. an object and its pasted contact shadow). Keeps the max score; repeats until stable."""
    items = [dict(f) for f in cands]
    changed = True
    while changed:
        changed = False
        out = []
        for f in items:
            for g in out:
                b, c = f["box"], g["box"]
                if b[0] - gap <= c[2] and c[0] - gap <= b[2] and b[1] - gap <= c[3] and c[1] - gap <= b[3]:
                    nb = [min(b[0], c[0]), min(b[1], c[1]), max(b[2], c[2]), max(b[3], c[3])]
                    if max(nb[2] - nb[0], nb[3] - nb[1]) <= 240:  # never grow past a plausible debris size
                        g["box"] = nb; g["score"] = max(f["score"], g["score"]); changed = True
                        break
            else:
                out.append(f)
        items = out
    return items
