"""PROTOTYPE (ticket 0012) - proposer 1: reference-frame change detection at full 4K resolution.

query frame vs simulated recent clean reference of the same fixed camera:
  1. align: ECC (Euclidean) on 1/4-scale greyscale, warp the reference onto the query
  2. illumination: local affine colour match (low-frequency mean/std of query -> reference, 1/8 scale)
  3. diff: colour distance with a +-1 px neighbourhood minimum (robust to residual misalignment / JPEG)
  4. blobs: robust threshold (max(abs, median + k*MAD)), close/open, connected components, min area
Every blob is a Candidate scored by its mean excess diff x sqrt(area); thresholds are swept afterwards.

usage: .venv/bin/python -I changedet.py            -> results/cand__changedet.json
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir
import common as C  # noqa: E402

ABS_THR = 18.0      # colour distance (0..441) floor
K_MAD = 6.0
MIN_AREA = 25       # px at 4K (~5x5)
PAD = 6
BORDER = 12


def align(ref, q):
    s = 0.25
    rg = cv2.cvtColor(cv2.resize(ref, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
    qg = cv2.cvtColor(cv2.resize(q, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
    rg = cv2.GaussianBlur(rg, (0, 0), 1.0); qg = cv2.GaussianBlur(qg, (0, 0), 1.0)
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        _, warp = cv2.findTransformECC(qg, rg, warp, cv2.MOTION_EUCLIDEAN,
                                       (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5), None, 5)
    except cv2.error:
        pass
    warp[:, 2] /= s
    h, w = q.shape[:2]
    return cv2.warpAffine(ref, warp, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT), warp


def normalise(ref, q):
    """Local affine colour match: per-channel low-frequency mean/std of the query mapped onto the reference's.
    Handles global gain, gradients, soft cloud shadows and (locally) gamma changes."""
    s = 1 / 8
    def stats(im):
        small = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA).astype(np.float32)
        mu = cv2.GaussianBlur(small, (0, 0), 6)
        sd = np.sqrt(np.maximum(cv2.GaussianBlur(small * small, (0, 0), 6) - mu * mu, 1.0))
        return mu, sd
    mr, sr = stats(ref); mq, sq = stats(q)
    gain = np.clip(sr / sq, 0.5, 2.0)
    up = lambda a: cv2.resize(a, (q.shape[1], q.shape[0]), interpolation=cv2.INTER_LINEAR)
    return (q.astype(np.float32) - up(mq)) * up(gain) + up(mr)


def diff_map(ref, qn):
    r = cv2.GaussianBlur(ref.astype(np.float32), (3, 3), 0)
    qq = cv2.GaussianBlur(qn, (3, 3), 0)
    best = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            sh = np.roll(r, (dy, dx), axis=(0, 1))
            d = np.sqrt(((qq - sh) ** 2).sum(axis=2))
            best = d if best is None else np.minimum(best, d)
    return best


def blobs(d, abs_thr=ABS_THR, k=K_MAD, min_area=MIN_AREA):
    med = float(np.median(d[::4, ::4])); mad = float(np.median(np.abs(d[::4, ::4] - med))) + 1e-6
    thr = max(abs_thr, med + k * 1.4826 * mad)
    m = (d > thr).astype(np.uint8)
    m[:BORDER] = 0; m[-BORDER:] = 0; m[:, :BORDER] = 0; m[:, -BORDER:] = 0  # warp/reflect artefacts
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    H, W = d.shape
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < min_area:
            continue
        reg = d[y:y + h, x:x + w][lab[y:y + h, x:x + w] == i]
        excess = float(reg.mean() - thr)
        out.append({"box": [max(0, x - PAD), max(0, y - PAD), min(W, x + w + PAD), min(H, y + h + PAD)],
                    "area": int(a), "mean_diff": float(reg.mean()), "peak": float(reg.max()),
                    # contrast x size, size capped at 20x20 px so big diffuse illumination blobs don't dominate
                    "score": round(excess * np.sqrt(min(a, 400)), 1)})
    return out, thr


def propose(ref, q):
    ref_al, warp = align(ref, q)
    qn = normalise(ref_al, q)
    d = diff_map(ref_al, qn)
    cands, thr = blobs(d)
    return C.nms_boxes(cands, iou_thr=0.3, dist=20), {"thr": thr, "warp": warp.tolist()}, d


def main():
    refs = {s: C.make_reference(s) for s in C.SCENES}
    out = {}
    for name in C.query_frames():
        t0 = time.time()
        q = C.load(name)
        t1 = time.time()
        cands, info, _ = propose(refs[C.GT[name]["frame"]], q)
        t2 = time.time()
        out[name] = {"findings": cands, "latency_s": round(t2 - t1, 3), "decode_s": round(t1 - t0, 3), **info}
        print(f"{name}: {len(cands)} blobs thr={info['thr']:.1f} {t2 - t1:.2f}s")
    C.save(f"cand__changedet{C.SUFFIX}.json", out)


if __name__ == "__main__":
    main()
