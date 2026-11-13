"""Build small fixture scenes in the contract's scene.json format from the spike images.

    uv run python tests/fixtures/build_fixtures.py            # writes tests/fixtures/data/
    FOD_DATA_DIR=tests/fixtures/data uv run uvicorn fodgate.api:app --port 8000

Source: prototypes/spike/data/images (clean / fod pairs + ground_truth.json). Each Gate's reference frame is
its clean frame re-captured with simulated mild camera and lighting drift, as in prototypes/local-detect
(common.make_reference). Nothing here is used by the unit tests, which build tiny synthetic scenes instead.

Scenes
  fx-pd-fod    pre-departure, day. Debris on NOSE, ENG-L (Critical), CARGO (Service) and WIDE; one WIDE item
               lies outside the gate safety envelope (FOD-R10). `after` frames are clean.
  fx-pa-mixed  pre-arrival. ENG-L has no reference (tiled fallback), ENG-R is washed out by glare (its `after`
               frame is usable), AFT is missing, WIDE carries envelope and ERL regions (FOD-R9 scan runs).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1]))
from fodgate.rules import load_rules  # noqa: E402

SRC = REPO / "prototypes" / "spike" / "data" / "images"
OUT = HERE / "data"
ANGLE_OF = {"NOSE": "pelita_pwf", "ENG-L": "pelita_pwl", "ENG-R": "brussels", "CARGO": "spring", "AFT": "wingo",
            "WIDE": "tansonnhat"}
ENVELOPE = [[150, 1150], [3690, 1150], [3840, 2160], [0, 2160]]
ERL = [[900, 1300], [2940, 1300], [3200, 2100], [640, 2100]]
LABELS = {"hammer": ("tools", "hard"), "wrench": ("tools", "hard"), "pliers": ("tools", "hard"),
          "cutter": ("tools", "hard"), "bolt": ("fasteners_hardware", "hard"), "wire": ("fasteners_hardware", "hard"),
          "bag_tag": ("luggage_parts", "light"), "luggage_tag": ("luggage_parts", "light"),
          "soda_can": ("catering_flightline", "hard"), "plastic": ("cargo_packaging", "light"),
          "rock": ("pavement_construction", "hard")}
SOURCE = {"title": "spike test frame (prototypes/spike)", "url": None, "author": None, "licence": "see prototypes/spike"}


def make_reference(clean: np.ndarray, seed: int = 0) -> np.ndarray:
    """Mild drift: 1.6/-1.1 px shift, 0.03 deg rotation, gain 1.04, gamma 1.05, +-6% gradient, noise, JPEG q85."""
    rng = np.random.default_rng(seed)
    im = clean.astype(np.float32)
    h, w = im.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 0.03, 1.0)
    M[0, 2] += 1.6
    M[1, 2] += -1.1
    im = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    grad = np.linspace(0.94, 1.06, w, dtype=np.float32)[None, :, None]
    im = 255.0 * ((im / 255.0) ** 1.05) * 1.04 * grad
    im += rng.normal(0, 2.5, im.shape).astype(np.float32)
    ok, buf = cv2.imencode(".jpg", np.clip(im, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def glare(im: np.ndarray) -> np.ndarray:
    """Sun glare: a large blown-out bloom over most of the frame."""
    h, w = im.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bloom = np.exp(-(((xx - w * 0.55) / (w * 0.55)) ** 2 + ((yy - h * 0.5) / (h * 0.6)) ** 2))
    out = im.astype(np.float32) * (1 - 0.6 * bloom[..., None]) + 330.0 * bloom[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def truth(angle: str, objects: list[dict], rules) -> list[dict]:
    out = []
    for o in objects:
        category, hint = next((v for k, v in LABELS.items() if o["label"].startswith(k)), ("unidentified", None))
        c = rules.classify(angle=angle, bbox=o["box"], category=category, hint=hint,
                           envelope=ENVELOPE if angle == "WIDE" else None)
        out.append({"bbox": o["box"], "finding_type": "fod", "category": category, "object_class": c["object_class"],
                    "zone_tier": c["zone_tier"], "expected_severity": c["severity"], "label": o["label"]})
    return out


def build() -> bool:
    if not (SRC / "ground_truth.json").is_file():
        print(f"spike images not found at {SRC}; nothing built")
        return False
    gt = json.loads((SRC / "ground_truth.json").read_text())["images"]
    rules = load_rules(REPO / "app" / "data" / "rules" / "fod-rules.json")
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "rules").mkdir(parents=True)
    shutil.copy(REPO / "app" / "data" / "rules" / "fod-rules.json", OUT / "rules" / "fod-rules.json")
    refs = {}

    def reference(frame: str) -> np.ndarray:
        if frame not in refs:
            refs[frame] = make_reference(cv2.imread(str(SRC / f"{frame}__clean.jpg")))
        return refs[frame]

    def scene(scene_id: str, kind: str, description: str, variants: dict[str, str | None], *, no_ref=(), glare_on=(),
              after_clean=()) -> None:
        d = OUT / "scenes" / scene_id
        (d / "ref").mkdir(parents=True)
        (d / "after").mkdir()
        angles = {}
        for angle, frame in ANGLE_OF.items():
            variant = variants.get(angle)
            regions = {"envelope": ENVELOPE, "erl": ERL} if angle == "WIDE" else None
            if variant is None:
                angles[angle] = {"image": None, "reference": None, "after": None, "width": None, "height": None,
                                 "derived": "native", "source": SOURCE, "usable": False, "unusable_reason": "missing",
                                 "regions": regions, "ground_truth": [], "observations_truth": []}
                continue
            name = f"{frame}__{variant}.jpg"
            im = cv2.imread(str(SRC / name))
            usable, reason, objects = True, None, gt[name]["objects"]
            if angle in glare_on:
                im, usable, reason, objects = glare(im), False, "glare", []
            cv2.imwrite(str(d / f"{angle}.jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
            has_ref = angle not in no_ref
            if has_ref:
                cv2.imwrite(str(d / "ref" / f"{angle}.jpg"), reference(frame), [cv2.IMWRITE_JPEG_QUALITY, 92])
            has_after = angle in after_clean
            if has_after:
                shutil.copy(SRC / f"{frame}__clean.jpg", d / "after" / f"{angle}.jpg")
            angles[angle] = {"image": f"{angle}.jpg", "reference": f"ref/{angle}.jpg" if has_ref else None,
                             "after": f"after/{angle}.jpg" if has_after else None,
                             "width": im.shape[1], "height": im.shape[0], "derived": "native", "source": SOURCE,
                             "usable": usable, "unusable_reason": reason, "regions": regions,
                             "ground_truth": truth(angle, objects, rules), "observations_truth": []}
        (d / "scene.json").write_text(json.dumps({"scene_id": scene_id, "kind": kind, "light": "day",
                                                  "description": description, "angles": angles}, indent=1))

    scene("fx-pd-fod", "pre_departure", "Fixture: debris on NOSE, ENG-L, CARGO and WIDE (one item outside the envelope)",
          {"NOSE": "fod1", "ENG-L": "fod1", "ENG-R": "clean", "CARGO": "fod1", "AFT": "clean", "WIDE": "fod1"},
          after_clean=("NOSE", "ENG-L", "CARGO", "WIDE"))
    scene("fx-pa-mixed", "pre_arrival", "Fixture: no reference on ENG-L, glare on ENG-R, AFT missing",
          {"NOSE": "noop", "ENG-L": "clean", "ENG-R": "clean", "CARGO": "noop", "AFT": None, "WIDE": "clean"},
          no_ref=("ENG-L",), glare_on=("ENG-R",), after_clean=("ENG-R",))
    (OUT / "testset.json").write_text(json.dumps({"scenes": ["fx-pd-fod", "fx-pa-mixed"]}, indent=1))
    (OUT / "demo").mkdir()
    (OUT / "demo" / "timeline.json").write_text(json.dumps({
        "gates": ["T1", "T2", "T4", "T5", "T8"],
        "turns": [
            {"turn_id": "T1-DL1432", "gate": "T1", "flight": "DL1432", "aircraft_type": "A321", "events": [
                {"t": 0, "type": "stand_prep"},
                {"t": 2, "type": "inspection", "kind": "pre_arrival", "scene_id": "fx-pa-mixed"},
                {"t": 20, "type": "block_in"},
                {"t": 30, "type": "inspection", "kind": "pre_departure", "scene_id": "fx-pd-fod"},
                {"t": 90, "type": "scheduled_pushback"}]},
            {"turn_id": "T4-DL0880", "gate": "T4", "flight": "DL0880", "aircraft_type": "737-900ER", "events": [
                {"t": 5, "type": "stand_prep"},
                {"t": 40, "type": "inspection", "kind": "pre_departure", "scene_id": "fx-pd-fod"},
                {"t": 120, "type": "scheduled_pushback"}]},
        ]}, indent=1))
    print(f"built fixture data in {OUT}")
    return True


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
