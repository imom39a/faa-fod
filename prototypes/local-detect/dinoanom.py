"""PROTOTYPE (ticket 0012) - proposer 2: DINOv2 ViT-S/14 patch-embedding anomaly vs the clean reference.

Weights + model code are reused READ-ONLY from drone-lab (models/follow/dinov2_vits14_pretrain.pth).
The frame is processed at native resolution as non-overlapping 518x518 tiles (37x37 patches of 14 px).
Anomaly per patch = min over the reference's 3x3 patch neighbourhood of (1 - cosine similarity), so a
1-patch camera drift is tolerated. Connected anomalous patches become a Candidate box (14 px grid).
Reference features are computed once per camera and cached; latency is the query only.

usage: .venv/bin/python -I dinoanom.py   -> results/cand__dino.json
"""
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

DINO_SRC = C.DRONE_LAB / "models/follow/dinov2-7764ea0f912e53c92e82eb78a2a1631e92725fc8"
DINO_W = C.DRONE_LAB / "models/follow/dinov2_vits14_pretrain.pth"
sys.path.insert(0, str(DINO_SRC))
from dinov2.hub.backbones import dinov2_vits14  # noqa: E402

P, T = 14, 518
GW, GH = 8, 5  # tiles -> 4144 x 2590 padded canvas
DEV = "mps"
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def load_model():
    m = dinov2_vits14(pretrained=False)
    m.load_state_dict(torch.load(DINO_W, map_location="cpu", weights_only=True), strict=True)
    return m.to(DEV).eval()


@torch.inference_mode()
def features(model, bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    canvas = np.zeros((GH * T, GW * T, 3), np.uint8)
    canvas[: rgb.shape[0], : rgb.shape[1]] = rgb
    x = torch.from_numpy(canvas).permute(2, 0, 1).float().div(255).unsqueeze(0)
    x = (x - MEAN) / STD
    tiles = x.unfold(2, T, T).unfold(3, T, T)  # 1,3,GH,GW,T,T
    tiles = tiles.permute(0, 2, 3, 1, 4, 5).reshape(-1, 3, T, T)
    outs = []
    for i in range(0, tiles.shape[0], 8):
        f = model.forward_features(tiles[i:i + 8].to(DEV))["x_norm_patchtokens"]  # b, 1369, 384
        outs.append(F.normalize(f, dim=-1))
    f = torch.cat(outs).view(GH, GW, 37, 37, -1).permute(0, 2, 1, 3, 4).reshape(GH * 37, GW * 37, -1)
    torch.mps.synchronize()
    return f  # (185, 296, 384) on DEV


@torch.inference_mode()
def anomaly(fq, fr):
    H, W, D = fr.shape
    pad = F.pad(fr.permute(2, 0, 1).unsqueeze(0), (1, 1, 1, 1), mode="replicate")[0].permute(1, 2, 0)
    best = None
    for dy in range(3):
        for dx in range(3):
            sim = (fq * pad[dy:dy + H, dx:dx + W]).sum(-1)
            best = sim if best is None else torch.maximum(best, sim)
    a = (1 - best).cpu().numpy()
    hh, ww = 2160 // P + 1, 3840 // P + 1
    return a[:hh, :ww]


def blobs(a, thr):
    m = (a > thr).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        peak = float(a[y:y + h, x:x + w][lab[y:y + h, x:x + w] == i].max())
        out.append({"box": [int(x * P), int(y * P), int(min(3840, (x + w) * P)), int(min(2160, (y + h) * P))],
                    "patches": int(area), "score": round(peak, 4)})
    return out


def main():
    model = load_model()
    refs = {}
    for s in C.SCENES:
        refs[s] = features(model, C.make_reference(s))
    features(model, C.load(C.query_frames()[0]))  # warm-up
    out = {}
    for name in C.query_frames():
        q = C.load(name)
        t0 = time.time()
        a = anomaly(features(model, q), refs[C.GT[name]["frame"]])
        cands = C.nms_boxes(blobs(a, 0.15), iou_thr=0.3, dist=20)
        dt = time.time() - t0
        out[name] = {"findings": cands, "latency_s": round(dt, 3),
                     "anom_p99": float(np.percentile(a, 99)), "anom_max": float(a.max())}
        print(f"{name}: {len(cands)} blobs p99={out[name]['anom_p99']:.3f} max={a.max():.3f} {dt:.2f}s")
    C.save(f"cand__dino{C.SUFFIX}.json", out)


if __name__ == "__main__":
    main()
