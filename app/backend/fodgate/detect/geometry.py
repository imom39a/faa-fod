"""Box helpers shared by the proposers, the pipeline and scoring."""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

FULL_W = 3840          # thresholds in pixels are quoted at 4K width and scaled for smaller frames
CAND_RADIUS = 60       # a Candidate "covers" an object if its centre is this close (4K px)
MATCH_RADIUS = 150     # a Finding matches an object / an earlier Finding within this distance (4K px)
CROP = 320


def imread(path: Path | str) -> np.ndarray | None:
    """BGR uint8, or None when the file is missing or unreadable."""
    p = Path(path)
    if not p.is_file():
        return None
    return cv2.imread(str(p), cv2.IMREAD_COLOR)


def scale_for(width: int) -> float:
    return width / FULL_W


def iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def centre(b) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def centre_dist(a, b) -> float:
    (ax, ay), (bx, by) = centre(a), centre(b)
    return math.hypot(ax - bx, ay - by)


def same_object(a, b, radius: float) -> bool:
    return centre_dist(a, b) <= radius or iou(a, b) > 0.1


def nms_boxes(items: list[dict], iou_thr: float = 0.3, dist: float = 30) -> list[dict]:
    """Keep the highest-scoring box of each overlapping / near-duplicate group."""
    kept: list[dict] = []
    for f in sorted(items, key=lambda d: -d["score"]):
        if any(iou(f["box"], k["box"]) > iou_thr or centre_dist(f["box"], k["box"]) < dist for k in kept):
            continue
        kept.append(f)
    return kept


def merge_near(cands: list[dict], gap: float = 24, max_side: float = 240) -> list[dict]:
    """Merge Candidates whose boxes are within `gap` px (an object split into fragments, e.g. an object and
    its contact shadow). Keeps the max score; never grows a box past a plausible debris size."""
    items = [dict(f) for f in cands]
    changed = True
    while changed:
        changed = False
        out: list[dict] = []
        for f in items:
            for g in out:
                b, c = f["box"], g["box"]
                if b[0] - gap <= c[2] and c[0] - gap <= b[2] and b[1] - gap <= c[3] and c[1] - gap <= b[3]:
                    nb = [min(b[0], c[0]), min(b[1], c[1]), max(b[2], c[2]), max(b[3], c[3])]
                    if max(nb[2] - nb[0], nb[3] - nb[1]) <= max_side:
                        g["box"] = nb
                        g["score"] = max(f["score"], g["score"])
                        changed = True
                        break
            else:
                out.append(f)
        items = out
    return items


def crop_candidate(bgr: np.ndarray, box, size: int = CROP, mark: bool = True) -> tuple[np.ndarray, tuple[int, int, int]]:
    """Square native-resolution crop centred on the box (downscaled only when the box is larger than ~80% of
    the crop). A thin red rectangle marks the Candidate. Returns (BGR crop, (x0, y0, side))."""
    H, W = bgr.shape[:2]
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    side = int(max(size, 1.25 * max(box[2] - box[0], box[3] - box[1])))
    side = min(side, W, H)
    x0 = int(min(max(0, cx - side / 2), W - side))
    y0 = int(min(max(0, cy - side / 2), H - side))
    im = bgr[y0:y0 + side, x0:x0 + side].copy()
    if mark:
        p = 8
        cv2.rectangle(im, (int(box[0] - x0 - p), int(box[1] - y0 - p)), (int(box[2] - x0 + p), int(box[3] - y0 + p)),
                      (0, 0, 255), 2)
    if side != size:
        im = cv2.resize(im, (size, size), interpolation=cv2.INTER_AREA if side > size else cv2.INTER_LINEAR)
    return im, (x0, y0, side)


def clamp_box(box, width: int, height: int) -> list[int]:
    x1, x2 = sorted((box[0], box[2]))
    y1, y2 = sorted((box[1], box[3]))
    x1 = int(max(0, min(width - 1, round(x1))))
    y1 = int(max(0, min(height - 1, round(y1))))
    x2 = int(max(x1 + 1, min(width, round(x2))))
    y2 = int(max(y1 + 1, min(height, round(y2))))
    return [x1, y1, x2, y2]
