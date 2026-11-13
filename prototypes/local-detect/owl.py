"""PROTOTYPE (ticket 0012) - proposer 3: OWLv2 (open-vocabulary) with SAHI-style tiling at native 4K.

Model: google/owlv2-base-patch16-ensemble (safetensors, downloaded to models/; treated as untrusted data,
loaded with use_safetensors and no remote code). 15 overlapping 960x960 tiles per frame (no resize, the
model's native input size), boxes offset back to the full frame, class-agnostic NMS.

usage: .venv/bin/python -I owl.py   -> results/cand__owl.json   (all boxes with score >= 0.02)
"""
import sys
import time
from pathlib import Path

import cv2
import torch
from PIL import Image
from transformers import Owlv2ForObjectDetection, Owlv2Processor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

MODEL_DIR = C.HERE / "models/owlv2-base-patch16-ensemble"
QUERIES = ["a bolt", "a nut", "a metal washer", "a wrench", "a hammer", "pliers", "a hand tool", "debris",
           "a piece of plastic", "a plastic bag", "a luggage tag", "a bag tag", "a soda can", "a rock",
           "a piece of wire", "a small object lying on the ground", "litter"]
TS = 960
XS = [0, 720, 1440, 2160, 2880]
YS = [0, 600, 1200]
DEV = "mps"


def load():
    proc = Owlv2Processor.from_pretrained(MODEL_DIR)
    model = Owlv2ForObjectDetection.from_pretrained(MODEL_DIR, use_safetensors=True).to(DEV).eval()
    return proc, model


@torch.inference_mode()
def propose(proc, model, bgr, text_inputs, thr=0.02, batch=3):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    tiles = [(x, y, Image.fromarray(rgb[y:y + TS, x:x + TS])) for y in YS for x in XS]
    found = []
    for i in range(0, len(tiles), batch):
        chunk = tiles[i:i + batch]
        px = proc.image_processor(images=[t[2] for t in chunk], return_tensors="pt")["pixel_values"].to(DEV)
        n = len(chunk)
        out = model(input_ids=text_inputs["input_ids"].to(DEV).repeat(n, 1),
                    attention_mask=text_inputs["attention_mask"].to(DEV).repeat(n, 1), pixel_values=px)
        logits = out.logits.sigmoid()  # (n, patches, Q)
        boxes = out.pred_boxes  # cx, cy, w, h normalised to the (square) tile
        scores, labels = logits.max(-1)
        for j, (x0, y0, _) in enumerate(chunk):
            keep = scores[j] >= thr
            for s, l, b in zip(scores[j][keep].tolist(), labels[j][keep].tolist(), boxes[j][keep].tolist()):
                cx, cy, w, h = (v * TS for v in b)
                if w * h > 0.25 * TS * TS:  # whole-tile boxes are never debris
                    continue
                found.append({"box": [round(x0 + cx - w / 2), round(y0 + cy - h / 2), round(x0 + cx + w / 2), round(y0 + cy + h / 2)],
                              "score": round(s, 4), "label": QUERIES[l]})
    if DEV == "mps":
        torch.mps.synchronize()
    return C.nms_boxes(found, iou_thr=0.3, dist=15)


def main():
    proc, model = load()
    text = proc.tokenizer(QUERIES, padding="max_length", max_length=16, return_tensors="pt")
    q0 = C.load(C.query_frames()[0])
    propose(proc, model, q0, text)  # warm-up
    out = {}
    for name in C.query_frames():
        q = C.load(name)
        t0 = time.time()
        cands = propose(proc, model, q, text)
        dt = time.time() - t0
        out[name] = {"findings": cands, "latency_s": round(dt, 3)}
        print(f"{name}: {len(cands)} boxes {dt:.2f}s")
    C.save("cand__owl.json", out)


if __name__ == "__main__":
    main()
