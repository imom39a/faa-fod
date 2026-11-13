"""Per-Angle usability check (FOD-R6 / AN-3): missing, near-blank, blur, glare, low light.

Runs locally on a downscaled greyscale copy; no image leaves the machine. Thresholds are deliberately
conservative: a usable night frame must not be thrown away, and a doubtful frame is still analysed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

CHECK_W = 960
BLANK_STD = 6.0           # near-uniform frame (lens covered, dead feed)
LOW_LIGHT_MEAN = 18.0     # mean luma below this, with no bright detail, cannot show small debris
LOW_LIGHT_P95 = 50.0
GLARE_FRACTION = 0.35     # share of blown-out pixels (luma >= 245)
BLUR_LAPLACIAN_VAR = 12.0  # variance of the Laplacian below this is defocus / motion blur / smeared lens
# "Night or low-contrast" Angles get the DINOv2 channel as well (PL-2).
LOW_CONTRAST_MEAN = 70.0
LOW_CONTRAST_STD = 25.0


@dataclass
class Usability:
    usable: bool
    reason: str | None                    # missing | glare | blur | blocked | low_light | None
    metrics: dict = field(default_factory=dict)

    @property
    def low_contrast(self) -> bool:
        m = self.metrics
        return bool(m) and (m["mean"] < LOW_CONTRAST_MEAN or m["std"] < LOW_CONTRAST_STD)


def measure(bgr: np.ndarray) -> dict:
    h, w = bgr.shape[:2]
    s = min(1.0, CHECK_W / w)
    small = cv2.resize(bgr, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA) if s < 1 else bgr
    g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gf = g.astype(np.float32)
    return {
        "mean": round(float(gf.mean()), 2),
        "std": round(float(gf.std()), 2),
        "p95": round(float(np.percentile(gf, 95)), 2),
        "blown_fraction": round(float((g >= 245).mean()), 4),
        "laplacian_var": round(float(cv2.Laplacian(g, cv2.CV_32F).var()), 2),
    }


def check(bgr: np.ndarray | None) -> Usability:
    if bgr is None or bgr.size == 0:
        return Usability(False, "missing")
    m = measure(bgr)
    if m["std"] < BLANK_STD:
        reason = "low_light" if m["mean"] < 40 else "glare" if m["mean"] > 215 else "blocked"
        return Usability(False, reason, m)
    if m["mean"] < LOW_LIGHT_MEAN and m["p95"] < LOW_LIGHT_P95:
        return Usability(False, "low_light", m)
    if m["blown_fraction"] > GLARE_FRACTION:
        return Usability(False, "glare", m)
    if m["laplacian_var"] < BLUR_LAPLACIAN_VAR:
        return Usability(False, "blur", m)
    return Usability(True, None, m)


def combine(local: Usability, declared_usable: bool, declared_reason: str | None) -> tuple[bool, str | None, str]:
    """Merge the local check with what scene.json declares. Either one can make the Angle unusable.
    Returns (usable, reason, decided_by) with decided_by in
    {"local_check", "scene_declared", "local_check+scene_declared"}."""
    if local.usable and declared_usable:
        return True, None, "local_check"
    if not local.usable and not declared_usable:
        return False, local.reason if local.reason == "missing" else (declared_reason or local.reason), \
            "local_check+scene_declared"
    if not local.usable:
        return False, local.reason, "local_check"
    return False, declared_reason or "blocked", "scene_declared"
