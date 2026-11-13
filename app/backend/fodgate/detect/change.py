"""Candidate proposer 1: reference-frame change detection at full resolution (PL-1, PL-2).

Current frame vs the Gate's reference frame from the same fixed camera:
  1. align: ECC (Euclidean) on 1/4-scale greyscale, warp the reference onto the current frame
  2. illumination: local affine colour match (low-frequency mean/std, 1/8 scale)
  3. diff: colour distance with a +-1 px neighbourhood minimum (robust to residual misalignment / JPEG)
  4. blobs: robust threshold max(abs, median + k*MAD), close/open, connected components, min area
Settings are the ones chosen in prototypes/local-detect/RESULTS.md and are not re-tuned here (TD-4).
"""
from __future__ import annotations

import cv2
import numpy as np

from .geometry import merge_near, nms_boxes

ABS_THR = 18.0      # colour distance (0..441) floor
K_MAD = 6.0
MIN_AREA = 25       # px (~5x5 at 4K)
PAD = 6
BORDER = 12
MIN_SCORE = 20.0    # keep Candidates scoring >= 20 ...
MERGE_GAP = 24      # ... after merging fragments within 24 px ...
MAX_CANDIDATES = 30  # ... capped at the 30 highest per Angle
VERSION = "changedet-0012"


def align(ref: np.ndarray, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    s = 0.25
    rg = cv2.cvtColor(cv2.resize(ref, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
    qg = cv2.cvtColor(cv2.resize(q, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
    rg = cv2.GaussianBlur(rg, (0, 0), 1.0)
    qg = cv2.GaussianBlur(qg, (0, 0), 1.0)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(qg, rg, warp, cv2.MOTION_EUCLIDEAN,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), None, 5)
    except cv2.error:
        warp = np.eye(2, 3, dtype=np.float32)   # no convergence: compare unaligned
    warp[:, 2] /= s
    h, w = q.shape[:2]
    aligned = cv2.warpAffine(ref, warp, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                             borderMode=cv2.BORDER_REFLECT)
    return aligned, warp


def normalise(ref: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Local affine colour match: per-channel low-frequency mean/std of the current frame mapped onto the
    reference's. Handles global gain, gradients, soft cloud shadows and (locally) gamma changes."""
    s = 1 / 8

    def stats(im):
        small = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA).astype(np.float32)
        mu = cv2.GaussianBlur(small, (0, 0), 6)
        sd = np.sqrt(np.maximum(cv2.GaussianBlur(small * small, (0, 0), 6) - mu * mu, 1.0))
        return mu, sd

    mr, sr = stats(ref)
    mq, sq = stats(q)
    gain = np.clip(sr / sq, 0.5, 2.0)

    def up(a):
        return cv2.resize(a, (q.shape[1], q.shape[0]), interpolation=cv2.INTER_LINEAR)

    return (q.astype(np.float32) - up(mq)) * up(gain) + up(mr)


def diff_map(ref: np.ndarray, qn: np.ndarray) -> np.ndarray:
    r = cv2.GaussianBlur(ref.astype(np.float32), (3, 3), 0)
    qq = cv2.GaussianBlur(qn, (3, 3), 0)
    best = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            sh = np.roll(r, (dy, dx), axis=(0, 1))
            d = np.sqrt(((qq - sh) ** 2).sum(axis=2))
            best = d if best is None else np.minimum(best, d)
    return best


def blobs(d: np.ndarray, abs_thr: float = ABS_THR, k: float = K_MAD, min_area: int = MIN_AREA) -> tuple[list[dict], float]:
    med = float(np.median(d[::4, ::4]))
    mad = float(np.median(np.abs(d[::4, ::4] - med))) + 1e-6
    thr = max(abs_thr, med + k * 1.4826 * mad)
    m = (d > thr).astype(np.uint8)
    m[:BORDER] = 0
    m[-BORDER:] = 0
    m[:, :BORDER] = 0
    m[:, -BORDER:] = 0                       # warp / reflect artefacts
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    H, W = d.shape
    out = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in stats[i])
        if a < min_area:
            continue
        reg = d[y:y + h, x:x + w][lab[y:y + h, x:x + w] == i]
        excess = float(reg.mean() - thr)
        out.append({"box": [max(0, x - PAD), max(0, y - PAD), min(W, x + w + PAD), min(H, y + h + PAD)],
                    "area": a,
                    # contrast x size, size capped at 20x20 px so big diffuse illumination blobs don't dominate
                    "score": round(excess * float(np.sqrt(min(a, 400))), 1)})
    return out, thr


def propose(ref: np.ndarray, q: np.ndarray, *, min_score: float = MIN_SCORE, merge_gap: float = MERGE_GAP,
            max_candidates: int = MAX_CANDIDATES) -> tuple[list[dict], dict]:
    """Candidates for the current frame `q` against reference `ref` (both BGR uint8).
    Returns ([{"box": [x1,y1,x2,y2], "score": s, "origin": "change"}], info)."""
    if ref.shape[:2] != q.shape[:2]:
        ref = cv2.resize(ref, (q.shape[1], q.shape[0]), interpolation=cv2.INTER_AREA)
    ref_al, warp = align(ref, q)
    d = diff_map(ref_al, normalise(ref_al, q))
    raw, thr = blobs(d)
    raw = nms_boxes(raw, iou_thr=0.3, dist=20)
    kept = merge_near([c for c in raw if c["score"] >= min_score], gap=merge_gap)
    kept = sorted(kept, key=lambda c: -c["score"])
    info = {"threshold": round(thr, 2), "blobs": len(raw), "kept": len(kept),
            "truncated": max(0, len(kept) - max_candidates)}
    out = [{"box": [int(v) for v in c["box"]], "score": float(c["score"]), "origin": "change"}
           for c in kept[:max_candidates]]
    return out, info
