"""Candidate proposer 2 (optional): DINOv2 ViT-S/14 patch-embedding anomaly vs the reference frame.

Used only on night / low-contrast Angles (PL-2), OR-ed with change detection at anomaly >= 0.6.
torch is an optional dependency (`uv sync --group dino`). Weights come from FOD_DINO_WEIGHTS; the DINOv2
model code is loaded from a `dinov2-*` source checkout next to the weights file, or from FOD_DINO_SRC.
When anything is missing the step is skipped and `availability()` says why (reported in run_metadata).
"""
from __future__ import annotations

import os
import sys
import threading
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np

from .. import config

P, T = 14, 518             # patch size, tile size (37x37 patches)
THRESHOLD = 0.6
VERSION = "dinov2_vits14"

_lock = threading.Lock()         # guards model loading
_infer_lock = threading.Lock()   # one inference at a time (MPS / memory)
_model = None
_device = None
_unavailable: str | None = None
_ref_cache: "OrderedDict[str, object]" = OrderedDict()


def _source_dir(weights: Path) -> Path | None:
    env = os.environ.get("FOD_DINO_SRC")
    if env:
        return Path(env)
    hits = sorted(p for p in weights.parent.glob("dinov2-*") if p.is_dir())
    return hits[0] if hits else None


def availability() -> tuple[bool, str]:
    """(available, note). Cheap after the first call."""
    global _unavailable
    if _model is not None:
        return True, "loaded"
    if _unavailable:
        return False, _unavailable
    w = config.dino_weights()
    if w is None:
        return False, "FOD_DINO_WEIGHTS is not set"
    if not w.is_file():
        return False, "FOD_DINO_WEIGHTS file not found"
    try:
        import torch  # noqa: F401
    except ImportError:
        return False, "torch is not installed (uv sync --group dino)"
    if _source_dir(w) is None:
        return False, "DINOv2 source checkout (dinov2-*) not found next to the weights; set FOD_DINO_SRC"
    return True, "ready"


def _load():
    global _model, _device, _unavailable
    with _lock:
        if _model is not None:
            return _model
        ok, note = availability()
        if not ok:
            raise RuntimeError(note)
        try:
            import torch
            w = config.dino_weights()
            src = str(_source_dir(w))
            if src not in sys.path:
                sys.path.insert(0, src)
            from dinov2.hub.backbones import dinov2_vits14  # type: ignore
            m = dinov2_vits14(pretrained=False)
            m.load_state_dict(torch.load(w, map_location="cpu", weights_only=True), strict=True)
            _device = "mps" if torch.backends.mps.is_available() else "cpu"
            _model = m.to(_device).eval()
        except Exception as e:  # any load failure disables the step for this process
            _unavailable = f"DINOv2 failed to load: {type(e).__name__}"
            raise RuntimeError(_unavailable) from e
        return _model


def _features(bgr: np.ndarray):
    import torch
    import torch.nn.functional as F
    model = _load()
    h, w = bgr.shape[:2]
    gh, gw = -(-h // T), -(-w // T)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    canvas = np.zeros((gh * T, gw * T, 3), np.uint8)
    canvas[:h, :w] = rgb
    mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
    with torch.inference_mode():
        x = (torch.from_numpy(canvas).permute(2, 0, 1).float().div(255).unsqueeze(0) - mean) / std
        tiles = x.unfold(2, T, T).unfold(3, T, T).permute(0, 2, 3, 1, 4, 5).reshape(-1, 3, T, T)
        outs = []
        for i in range(0, tiles.shape[0], 8):
            f = model.forward_features(tiles[i:i + 8].to(_device))["x_norm_patchtokens"]
            outs.append(F.normalize(f, dim=-1))
        n = T // P
        return torch.cat(outs).view(gh, gw, n, n, -1).permute(0, 2, 1, 3, 4).reshape(gh * n, gw * n, -1)


def _anomaly(fq, fr, h: int, w: int) -> np.ndarray:
    """Per patch: 1 - max cosine similarity over the reference's 3x3 patch neighbourhood (tolerates drift)."""
    import torch
    import torch.nn.functional as F
    with torch.inference_mode():
        H, W, _ = fr.shape
        pad = F.pad(fr.permute(2, 0, 1).unsqueeze(0), (1, 1, 1, 1), mode="replicate")[0].permute(1, 2, 0)
        best = None
        for dy in range(3):
            for dx in range(3):
                sim = (fq * pad[dy:dy + H, dx:dx + W]).sum(-1)
                best = sim if best is None else torch.maximum(best, sim)
        a = (1 - best).cpu().numpy()
    return a[: h // P + 1, : w // P + 1]


def propose(ref: np.ndarray, q: np.ndarray, *, ref_key: str | None = None, threshold: float = THRESHOLD) -> list[dict]:
    """Candidates [{"box", "score", "origin": "dino"}] where patch anomaly >= threshold. Raises RuntimeError
    when DINOv2 is unavailable."""
    if ref.shape[:2] != q.shape[:2]:
        ref = cv2.resize(ref, (q.shape[1], q.shape[0]), interpolation=cv2.INTER_AREA)
    h, w = q.shape[:2]
    _load()
    with _infer_lock:
        fr = _ref_cache.get(ref_key) if ref_key else None
        if fr is None:
            fr = _features(ref)
            if ref_key:
                _ref_cache[ref_key] = fr
                while len(_ref_cache) > 6:
                    _ref_cache.popitem(last=False)
        a = _anomaly(_features(q), fr, h, w)
    m = (a > threshold).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, bw, bh, _area = (int(v) for v in stats[i])
        peak = float(a[y:y + bh, x:x + bw][lab[y:y + bh, x:x + bw] == i].max())
        out.append({"box": [x * P, y * P, min(w, (x + bw) * P), min(h, (y + bh) * P)],
                    "score": round(peak, 4), "origin": "dino"})
    return out

