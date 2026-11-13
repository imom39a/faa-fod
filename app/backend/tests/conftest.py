"""Shared fixtures: a temporary data / var directory, tiny synthetic scenes and a fake LLM transport.

No test calls the Claude API. Synthetic frames are 960x540 textured backgrounds with small squares pasted in
as debris; the reference frame is the clean background with a little sensor noise.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from fodgate import config, llm as llm_mod
from fodgate.llm import LLM

W, H = 960, 540
ENVELOPE = [[100, 200], [860, 200], [960, 540], [0, 540]]
ERL = [[300, 300], [660, 300], [700, 520], [260, 520]]
TIER = {"NOSE": "critical", "ENG-L": "critical", "ENG-R": "critical", "CARGO": "service", "AFT": "service",
        "WIDE": "general"}
REPO_RULES = config.REPO_ROOT / "app" / "data" / "rules" / "fod-rules.json"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    data, var = tmp_path / "data", tmp_path / "var"
    (data / "rules").mkdir(parents=True)
    (data / "scenes").mkdir()
    shutil.copy(REPO_RULES, data / "rules" / "fod-rules.json")
    monkeypatch.setenv("FOD_DATA_DIR", str(data))
    monkeypatch.setenv("FOD_VAR_DIR", str(var))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    for k in ("FOD_DECISION_MODEL", "FOD_ESCALATION", "FOD_DINO_WEIGHTS", "FOD_LLM_CACHE", "FOD_MAX_SPEND_USD"):
        monkeypatch.delenv(k, raising=False)
    llm_mod.reset_process_state()
    yield
    llm_mod.reset_process_state()


@pytest.fixture
def data_dir() -> Path:
    return config.data_dir()


def background(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = cv2.GaussianBlur(rng.integers(90, 170, (H, W, 3), dtype=np.uint8), (0, 0), 3)
    fine = rng.integers(0, 40, (H, W, 3), dtype=np.uint8)
    im = cv2.addWeighted(base, 0.8, fine, 0.6, 0)
    cv2.line(im, (0, 400), (W, 380), (40, 200, 220), 3)           # a painted line gives the aligner structure
    cv2.rectangle(im, (700, 60), (900, 160), (200, 200, 200), -1)  # and a fixed "building"
    return im


def paste(im: np.ndarray, box, colour=(20, 20, 200)) -> np.ndarray:
    out = im.copy()
    cv2.rectangle(out, (box[0], box[1]), (box[2], box[3]), colour, -1)
    return out


def noisy(im: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed + 1000)
    return np.clip(im.astype(np.int16) + rng.integers(-2, 3, im.shape), 0, 255).astype(np.uint8)


def make_scene(scene_id: str, *, kind: str = "pre_departure", light: str = "day", objects: dict | None = None,
               no_ref=(), declared_unusable: dict | None = None, missing=(), degrade: dict | None = None,
               after_clean=(), after_same=(), with_regions: bool = True, truth_class: dict | None = None) -> Path:
    """Write a scene in the contract's scene.json format. `objects` maps Angle -> list of boxes."""
    objects, declared_unusable, degrade = objects or {}, declared_unusable or {}, degrade or {}
    d = config.data_dir() / "scenes" / scene_id
    (d / "ref").mkdir(parents=True, exist_ok=True)
    (d / "after").mkdir(exist_ok=True)
    angles = {}
    for i, angle in enumerate(config.ANGLES):
        regions = {"envelope": ENVELOPE, "erl": ERL} if (angle == "WIDE" and with_regions) else None
        if angle in missing:
            angles[angle] = {"image": None, "reference": None, "after": None, "usable": False,
                             "unusable_reason": "missing", "regions": regions, "ground_truth": []}
            continue
        clean = background(i)
        im = clean
        for box in objects.get(angle, []):
            im = paste(im, box)
        if degrade.get(angle) == "blur":
            im = cv2.GaussianBlur(im, (0, 0), 12)
        elif degrade.get(angle) == "dark":
            im = (im * 0.04).astype(np.uint8)
        elif degrade.get(angle) == "glare":
            im = np.clip(im.astype(np.int16) + 200, 0, 255).astype(np.uint8)
        cv2.imwrite(str(d / f"{angle}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
        has_ref = angle not in no_ref
        if has_ref:
            cv2.imwrite(str(d / "ref" / f"{angle}.jpg"), noisy(clean, i), [cv2.IMWRITE_JPEG_QUALITY, 95])
        after = None
        if angle in after_clean:
            cv2.imwrite(str(d / "after" / f"{angle}.jpg"), noisy(clean, i + 50), [cv2.IMWRITE_JPEG_QUALITY, 95])
            after = f"after/{angle}.jpg"
        elif angle in after_same:
            shutil.copy(d / f"{angle}.jpg", d / "after" / f"{angle}.jpg")
            after = f"after/{angle}.jpg"
        cls = (truth_class or {}).get(angle, ("tools", "hard", "HOLD"))
        angles[angle] = {
            "image": f"{angle}.jpg", "reference": f"ref/{angle}.jpg" if has_ref else None, "after": after,
            "width": W, "height": H, "derived": "mirror" if angle == "ENG-L" else "native",
            "source": {"title": f"synthetic {angle}", "url": "https://example.invalid/x", "author": "tests",
                       "licence": "CC0"},
            "usable": angle not in declared_unusable, "unusable_reason": declared_unusable.get(angle),
            "regions": regions,
            "ground_truth": [{"bbox": list(b), "finding_type": "fod", "category": cls[0], "object_class": cls[1],
                              "zone_tier": TIER[angle], "expected_severity": cls[2], "label": "square"}
                             for b in objects.get(angle, [])],
            "observations_truth": []}
    (d / "scene.json").write_text(json.dumps({"scene_id": scene_id, "kind": kind, "light": light,
                                              "description": "synthetic", "angles": angles}))
    return d


class Brain:
    """Scripted stand-in for Claude. Records every call."""

    def __init__(self):
        self.calls: list[dict] = []
        self.verdict = lambda cid, angle: "fod"            # per Candidate
        self.category = lambda cid, angle: ("tools", "hard")
        self.confidence = lambda cid, angle: "high"
        self.net_hits: dict[str, list[list[int]]] = {}       # Angle -> boxes found by the tiled pass
        self.equipment: list[list[int]] = []                 # boxes found by the equipment scan
        self.skip_ids: set[int] = set()                      # Candidates the model "forgets" to decide
        self.fail_purposes: set[str] = set()                 # schema kinds that return a non-finished response

    def __call__(self, *, model, system, content, schema, effort, max_tokens) -> dict:
        kind = next(iter(schema["properties"]))
        text = " ".join(b["text"] for b in content if b["type"] == "text")
        angle = (re.search(r"Angle: ([A-Z-]+)\.", text) or [None, "WIDE"])[1]
        self.calls.append({"model": model, "kind": kind, "angle": angle, "images": sum(b["type"] == "image" for b in content),
                           "text": text, "system": system})
        if kind in self.fail_purposes:
            return {"text": "", "stop_reason": "max_tokens", "tokens_in": 1000, "tokens_out": 10}
        if kind == "decisions":
            ids = json.loads(re.search(r"ids (\[[\d, ]*\])", text)[1])
            out = []
            for cid in ids:
                if cid in self.skip_ids:
                    continue
                cat, mat = self.category(cid, angle)
                v = self.verdict(cid, angle)
                out.append({"candidate_id": cid, "what_is_visible": f"object {cid}", "verdict": v,
                            "category": cat if v == "fod" else "none", "material": mat,
                            "observation_kind": "spill" if v == "observation" else "none",
                            "location_text": f"somewhere on {angle}", "confidence": self.confidence(cid, angle),
                            "reason": f"verdict {v}"})
            body = {"decisions": out}
        elif kind == "findings":
            body = {"findings": [{"image_index": 0, "x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3],
                                  "description": "net hit", "confidence": "low"} for b in self.net_hits.get(angle, [])]}
        else:
            body = {"equipment": [{"x1": b[0], "y1": b[1], "x2": b[2], "y2": b[3], "label": "baggage tug",
                                   "confidence": "high"} for b in self.equipment]}
        return {"text": json.dumps(body), "stop_reason": "end_turn", "tokens_in": 1000, "tokens_out": 200}

    def of(self, kind: str) -> list[dict]:
        return [c for c in self.calls if c["kind"] == kind]


@pytest.fixture
def brain() -> Brain:
    return Brain()


@pytest.fixture
def fake_llm(brain) -> LLM:
    return LLM(transport=brain)
