"""Frame operations for the test-data build: Angle crops, reference drift, degradations, controls.

make_reference() is a copy of prototypes/local-detect/common.py (simulated camera and lighting
drift for a fixed camera); glare() is a copy of prototypes/dashboard/tools/build_assets.py scaled
to the frame size. Copied, not imported, per app/CONTRACT.md.
"""
import math
import random

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

MAX_W, MAX_H = 3840, 2160
MAX_UPSCALE = 1.25
JPEG_Q = 88


def out_size(crop_w):
    """Output size for a 16:9 crop that is crop_w source px wide: 3840x2160 if the source allows,
    never upscaled more than 1.25x."""
    w = min(MAX_W, int(crop_w * MAX_UPSCALE))
    w -= w % 16
    return w, w * 9 // 16


def cut_angle(src: Image.Image, box, mirror=False):
    x0, y0, x1, y1 = box
    assert 0 <= x0 < x1 <= src.width and 0 <= y0 < y1 <= src.height, (box, src.size)
    assert abs((x1 - x0) / (y1 - y0) - 16 / 9) < 0.01, f"crop {box} is not 16:9"
    im = src.crop(box).resize(out_size(x1 - x0), Image.LANCZOS)
    return im.transpose(Image.FLIP_LEFT_RIGHT) if mirror else im


def pil_to_bgr(im):
    return cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2BGR)


def bgr_to_pil(a):
    return Image.fromarray(cv2.cvtColor(a, cv2.COLOR_BGR2RGB))


def make_reference(clean: Image.Image, seed=0, mode="mild"):
    """Simulated 'recent clean reference' for a fixed camera: the clean frame re-captured with
    camera/sensor drift. mild: 1.6/-1.1 px shift + 0.03 deg rotation, gain 1.04, gamma 1.05, a soft
    left-to-right illumination gradient (+-6%), sensor noise (sigma 2.5), JPEG q85.
    hard: 4.3/-3.2 px shift + 0.12 deg rotation, gain 1.10, gamma 1.15, +-15% gradient, a soft
    25%-dark cloud-shadow ellipse, noise sigma 4.5, JPEG q75. Shifts scale with frame width
    (values are for 3840 px). Nothing moves in the scene (no GSE, people, rain or sun shadows)."""
    hard = mode == "hard"
    rng = np.random.default_rng(seed)
    im = pil_to_bgr(clean).astype(np.float32)
    h, w = im.shape[:2]
    k = w / 3840
    rot, sx, sy, gain, gamma, g, noise, qual = ((0.12, 4.3, -3.2, 1.10, 1.15, 0.15, 4.5, 75) if hard
                                                else (0.03, 1.6, -1.1, 1.04, 1.05, 0.06, 2.5, 85))
    # per-seed variation so that no two references drift identically (sign and +-30% magnitude)
    j = rng.uniform(0.7, 1.3, 3) * rng.choice([-1, 1], 3)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), rot * j[0], 1.0)
    M[0, 2] += sx * k * j[1]; M[1, 2] += sy * k * j[2]
    im = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    grad = np.linspace(1 - g, 1 + g, w, dtype=np.float32)[None, :, None]
    if rng.random() < 0.5:
        grad = grad[:, ::-1, :]
    im = 255.0 * ((im / 255.0) ** gamma) * gain * grad
    if hard:
        sh = np.zeros((h, w), np.float32)
        cv2.ellipse(sh, (int(w * 0.6), int(h * 0.75)), (int(900 * k), int(350 * k)), 15, 0, 360, 1.0, -1)
        sh = cv2.GaussianBlur(sh, (0, 0), 120 * k)
        im *= (1 - 0.25 * sh)[..., None]
    im += rng.normal(0, noise, im.shape).astype(np.float32)
    im = np.clip(im, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, qual])
    return buf.tobytes()


def recapture(clean: Image.Image, seed):
    """A later capture of the same clean view (used for `after` frames): sub-pixel shift, a 1-2%
    exposure change and light sensor noise. Deliberately much closer to the current frame than the
    reference is, as two captures minutes apart would be."""
    rng = np.random.default_rng(seed)
    im = pil_to_bgr(clean).astype(np.float32)
    h, w = im.shape[:2]
    M = np.float32([[1, 0, rng.uniform(-0.6, 0.6)], [0, 1, rng.uniform(-0.6, 0.6)]])
    im = cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    im = im * rng.uniform(0.985, 1.02) + rng.normal(0, 1.2, im.shape).astype(np.float32)
    return bgr_to_pil(np.clip(im, 0, 255).astype(np.uint8))


def glare(im: Image.Image, fx: float, fy: float, seed: int = 3):
    """Low-sun veiling glare + bloom + flare ghosts, as from the sun just outside the frame.
    (fx, fy) = sun position as a fraction of the frame."""
    rnd = random.Random(seed)
    W, H = im.size
    k = W / 1600
    cx, cy = fx * W, fy * H
    small = (W // 4, H // 4)
    veil = Image.new("L", small, 0)
    d = ImageDraw.Draw(veil)
    R = small[0] * 1.1
    for r in range(int(R), 0, -3):
        a = int(255 * (1 - r / R) ** 1.6)
        d.ellipse((cx / 4 - r, cy / 4 - r, cx / 4 + r, cy / 4 + r), fill=a)
    veil = veil.filter(ImageFilter.GaussianBlur(8 * k)).resize((W, H), Image.BILINEAR)
    white = Image.new("RGB", (W, H), (255, 248, 228))
    out = Image.composite(white, im, veil.point(lambda v: min(255, int(v * 1.25))))
    out = ImageEnhance.Contrast(out).enhance(0.38)
    out = ImageEnhance.Brightness(out).enhance(1.18)
    ghosts = Image.new("RGB", (W, H), (0, 0, 0))
    gm = Image.new("L", (W, H), 0)
    gd, gmd = ImageDraw.Draw(ghosts), ImageDraw.Draw(gm)
    for t, rad, col in [(0.55, 60, (120, 255, 170)), (0.8, 28, (255, 200, 120)), (1.15, 90, (150, 170, 255)), (1.45, 40, (255, 150, 220))]:
        rad *= k
        gx, gy = cx + (W / 2 - cx) * t * 2, cy + (H / 2 - cy) * t * 2
        gd.ellipse((gx - rad, gy - rad, gx + rad, gy + rad), fill=col)
        gmd.ellipse((gx - rad, gy - rad, gx + rad, gy + rad), fill=70 + rnd.randint(0, 30))
    gm = gm.filter(ImageFilter.GaussianBlur(6 * k))
    out = Image.composite(ImageChops.screen(out, ghosts), out, gm)
    st = Image.new("L", (W, H), 0)
    ang = math.atan2(H / 2 - cy, W / 2 - cx)
    L = W * 1.5
    ImageDraw.Draw(st).line((cx - L * math.cos(ang), cy - L * math.sin(ang), cx + L * math.cos(ang), cy + L * math.sin(ang)),
                            fill=120, width=int(10 * k))
    st = st.filter(ImageFilter.GaussianBlur(14 * k))
    return Image.composite(Image.new("RGB", (W, H), (255, 250, 235)), out, st)


def blur(im: Image.Image, seed=0):
    """Heavy defocus + motion blur (a knocked or vibrating camera): unusable for small objects."""
    a = pil_to_bgr(im)
    k = max(1.0, a.shape[1] / 3840)
    a = cv2.GaussianBlur(a, (0, 0), 14 * k)
    n = int(61 * k) | 1
    kern = np.zeros((n, n), np.float32)
    cv2.line(kern, (0, n // 2 + n // 6), (n - 1, n // 2 - n // 6), 1.0, 1)
    a = cv2.filter2D(a, -1, kern / kern.sum())
    return bgr_to_pil(a)


def low_light(im: Image.Image, seed=0):
    """Under-exposed capture (failed floodlight): very dark and noisy."""
    rng = np.random.default_rng(seed)
    a = pil_to_bgr(im).astype(np.float32)
    a = 255.0 * (a / 255.0) ** 1.6 * 0.07 + rng.normal(0, 5, a.shape)
    return bgr_to_pil(np.clip(a, 0, 255).astype(np.uint8))


def noop_edit(im: Image.Image, patches, seed):
    """Control: pass a clean frame through the compositing step with nothing added. A slight tone
    jitter, then pavement patches pasted onto pavement with the same feathered mask as debris.
    patches: [[sx, sy, dx, dy, size_px], ...] in frame px. As in prototypes/spike/make_dataset.py."""
    rng = random.Random(seed)
    im = ImageEnhance.Brightness(im).enhance(1.0 + rng.uniform(-0.04, 0.04))
    for sx, sy, dx, dy, sz in patches:
        patch = im.crop((sx, sy, sx + sz, sy + sz))
        m = Image.new("L", (sz, sz), 0)
        ImageDraw.Draw(m).ellipse((sz // 6, sz // 6, sz - sz // 6, sz - sz // 6), fill=255)
        im.paste(patch, (dx, dy), m.filter(ImageFilter.GaussianBlur(sz / 12)))
    return im
