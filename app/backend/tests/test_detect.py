import cv2
import numpy as np

from fodgate.detect import change, dino, usability
from fodgate.detect.geometry import centre_dist, clamp_box, crop_candidate, merge_near, nms_boxes
from tests.conftest import background, noisy, paste


def test_usability_reasons():
    im = background(0)
    assert usability.check(im).usable
    assert usability.check(None).reason == "missing"
    assert usability.check(cv2.GaussianBlur(im, (0, 0), 12)).reason == "blur"
    assert usability.check((im * 0.04).astype(np.uint8)).reason == "low_light"
    assert usability.check(np.clip(im.astype(np.int16) + 200, 0, 255).astype(np.uint8)).reason == "glare"
    assert usability.check(np.full((540, 960, 3), 128, np.uint8)).reason == "blocked"      # near-blank
    assert usability.check(np.zeros((540, 960, 3), np.uint8)).reason == "low_light"


def test_usability_combine_records_who_decided():
    ok, bad = usability.Usability(True, None, {}), usability.Usability(False, "blur", {})
    assert usability.combine(ok, True, None) == (True, None, "local_check")
    assert usability.combine(ok, False, "glare") == (False, "glare", "scene_declared")
    assert usability.combine(bad, True, None) == (False, "blur", "local_check")
    assert usability.combine(bad, False, "glare") == (False, "glare", "local_check+scene_declared")


def test_change_detection_finds_pasted_object_and_ignores_noise():
    clean = background(3)
    box = [400, 250, 416, 266]
    cands, info = change.propose(noisy(clean, 3), paste(clean, box))
    assert len(cands) == 1 and centre_dist(cands[0]["box"], box) < 10 and cands[0]["score"] >= change.MIN_SCORE
    none, _ = change.propose(noisy(clean, 3), noisy(clean, 9))
    assert none == []


def test_change_detection_caps_candidates():
    clean = background(4)
    im = clean
    for i in range(40):
        x, y = 30 + (i % 10) * 90, 40 + (i // 10) * 110
        im = paste(im, [x, y, x + 14, y + 14])
    cands, info = change.propose(noisy(clean, 4), im)
    assert len(cands) == change.MAX_CANDIDATES == 30 and info["truncated"] >= 1
    assert cands == sorted(cands, key=lambda c: -c["score"])


def test_merge_within_24px_and_nms():
    merged = merge_near([{"box": [0, 0, 10, 10], "score": 5}, {"box": [30, 0, 40, 10], "score": 9},
                         {"box": [200, 0, 210, 10], "score": 1}])
    assert len(merged) == 2 and merged[0]["box"] == [0, 0, 40, 10] and merged[0]["score"] == 9
    assert len(merge_near([{"box": [0, 0, 10, 10], "score": 1}, {"box": [35, 0, 45, 10], "score": 1}])) == 2
    kept = nms_boxes([{"box": [0, 0, 10, 10], "score": 1}, {"box": [1, 1, 11, 11], "score": 2}])
    assert len(kept) == 1 and kept[0]["score"] == 2


def test_crop_and_clamp():
    im = background(1)
    crop, (x0, y0, side) = crop_candidate(im, [940, 520, 958, 538])
    assert crop.shape == (320, 320, 3) and x0 + side <= 960 and y0 + side <= 540
    assert clamp_box([-5, 10, 2000, 5], 960, 540) == [0, 5, 960, 10]


def test_dino_is_optional(monkeypatch):
    ok, note = dino.availability()
    assert not ok and "FOD_DINO_WEIGHTS" in note
    monkeypatch.setenv("FOD_DINO_WEIGHTS", "/nonexistent/weights.pth")
    assert dino.availability() == (False, "FOD_DINO_WEIGHTS file not found")
