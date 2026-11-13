"""PROTOTYPE (spike 0007) - throwaway. Builds a small labelled FOD test set.

Usage:  .venv/bin/python -I make_dataset.py <raw_dir> <out_dir> [--frames-only]

- Crops 6 openly-licensed apron photos (Wikimedia Commons, see raw/commons_meta.json)
  to 16:9 and resizes to 3840x2160 ("4K camera frame").
- Cuts debris objects out of FOD-A example thumbnails (MIT) and draws a few
  simple synthetic objects, then pastes them at fixed, seeded positions on the
  apron surface. Writes images + ground_truth.json (pixel boxes in 3840x2160).
- Controls: clean frames, and "no-op edit" clean frames (re-encoded, slight
  tone jitter, and a pavement patch pasted onto pavement with the same feathered
  compositing as the debris, so paste artefacts alone are tested).
"""
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageStat

W, H = 3840, 2160

# source file -> (crop box in source px)  -- crop keeps the ground (bottom of frame)
FRAMES = {
    "brussels": ("commons/Airport_Brussels_1.jpg", (0, 175, 2400, 1525)),
    "pelita_pwf": ("commons/Pelita_Air_Airbus_A320_PK_PWF_Jakarta_20.jpg", (0, 374, 3840, 2534)),
    "pelita_pwl": ("commons/Pelita_Air_Airbus_A320_PK_PWL_Jakarta_20.jpg", (0, 387, 3840, 2547)),
    "spring": ("commons/Spring_Airlines_Airbus_A320_B_6708_at_Sh.jpg", (0, 398, 3840, 2558)),
    "tansonnhat": ("commons/Tansonnhat9.jpg", (0, 612, 3264, 2448)),
    "wingo": ("commons/Wingo_Boeing_737_700_sitting_at_the_gate.jpg", (4, 0, 3836, 2156)),
}

# FOD-A manyEx.png grid cells (x0,y0,x1,y1) and label
COLS = [(8, 115), (127, 234), (246, 354), (365, 472), (485, 593), (604, 711), (722, 830), (842, 949)]
ROWS = [(33, 140), (150, 257), (267, 375)]
FODA_CELLS = {
    "cutter_a": (0, 1), "hammer_a": (0, 2), "wire_a": (0, 3), "plastic_grey": (0, 4),
    "pliers_a": (0, 5), "luggage_tag": (0, 7), "cutter_b": (1, 1), "hammer_b": (1, 2),
    "plastic_yellow": (1, 4), "pliers_blue": (1, 5), "rock": (1, 6), "bolt_long": (2, 0),
    "wire_b": (2, 3), "plastic_orange": (2, 4), "pliers_red": (2, 5),
}


def prep_frames(raw: Path):
    out = {}
    for name, (rel, box) in FRAMES.items():
        im = Image.open(raw / rel).convert("RGB").crop(box).resize((W, H), Image.LANCZOS)
        out[name] = im
    return out


def cut_foda(sheet: Image.Image, key: str):
    r, c = FODA_CELLS[key]
    (x0, x1), (y0, y1) = COLS[c], ROWS[r]
    cell = sheet.crop((x0 + 3, y0 + 3, x1 - 2, y1 - 2)).convert("RGB")
    cw, ch = cell.size
    ring = [cell.getpixel((x, y)) for x in range(cw) for y in range(ch)
            if x < 6 or y < 6 or x >= cw - 6 or y >= ch - 6]
    bg = tuple(sorted(p[i] for p in ring)[len(ring) // 2] for i in range(3))
    mask = Image.new("L", cell.size, 0)
    mp = mask.load()
    for x in range(cw):
        for y in range(ch):
            p = cell.getpixel((x, y))
            d = sum(abs(p[i] - bg[i]) for i in range(3))
            mp[x, y] = 255 if d > 60 else 0
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
    bbox = mask.getbbox()
    cell, mask = cell.crop(bbox), mask.crop(bbox)
    return cell, mask.filter(ImageFilter.GaussianBlur(0.8)), bg


def drawn_object(kind: str):
    """Simple hand-drawn debris, rendered at 4x then shrunk for anti-aliasing."""
    s = 4
    if kind == "soda_can":
        im = Image.new("RGB", (60 * s, 26 * s)); m = Image.new("L", im.size, 0)
        d, dm = ImageDraw.Draw(im), ImageDraw.Draw(m)
        d.rounded_rectangle((0, 0, 60 * s - 1, 26 * s - 1), 10 * s, fill=(200, 20, 30))
        d.rectangle((40 * s, 0, 46 * s, 26 * s), fill=(220, 220, 225))
        d.rectangle((5 * s, 4 * s, 35 * s, 8 * s), fill=(240, 240, 240))
        dm.rounded_rectangle((0, 0, 60 * s - 1, 26 * s - 1), 10 * s, fill=255)
    elif kind == "bag_tag":
        im = Image.new("RGB", (70 * s, 22 * s)); m = Image.new("L", im.size, 0)
        d, dm = ImageDraw.Draw(im), ImageDraw.Draw(m)
        d.rectangle((0, 0, 52 * s, 22 * s), fill=(245, 245, 240))
        for i in range(8):
            d.rectangle(((6 + i * 5) * s, 5 * s, (8 + i * 5) * s, 17 * s), fill=(20, 20, 20))
        d.line((52 * s, 11 * s, 70 * s, 6 * s), fill=(30, 120, 220), width=2 * s)
        dm.rectangle((0, 0, 52 * s, 22 * s), fill=255)
        dm.line((52 * s, 11 * s, 70 * s, 6 * s), fill=255, width=2 * s)
    elif kind == "wrench":
        im = Image.new("RGB", (80 * s, 22 * s)); m = Image.new("L", im.size, 0)
        d, dm = ImageDraw.Draw(im), ImageDraw.Draw(m)
        for dd, col in ((d, (150, 155, 160)), (dm, 255)):
            dd.rectangle((14 * s, 7 * s, 68 * s, 15 * s), fill=col)
            dd.ellipse((0, 0, 22 * s, 22 * s), fill=col)
            dd.ellipse((62 * s, 2 * s, 80 * s, 20 * s), fill=col)
        d.ellipse((5 * s, 6 * s, 15 * s, 16 * s), fill=(0, 0, 0)); dm.ellipse((5 * s, 6 * s, 15 * s, 16 * s), fill=0)
        d.line((16 * s, 9 * s, 66 * s, 9 * s), fill=(210, 212, 215), width=2 * s)
    elif kind == "plastic_bag":
        im = Image.new("RGB", (50 * s, 40 * s)); m = Image.new("L", im.size, 0)
        poly = [(5, 10), (20, 0), (42, 6), (50, 22), (38, 38), (15, 40), (0, 28)]
        poly = [(x * s, y * s) for x, y in poly]
        ImageDraw.Draw(im).polygon(poly, fill=(235, 238, 240))
        ImageDraw.Draw(im).line([poly[1], poly[4]], fill=(200, 205, 210), width=2 * s)
        ImageDraw.Draw(m).polygon(poly, fill=230)
    else:
        raise ValueError(kind)
    w, h = im.size
    return im.resize((w // s, h // s), Image.LANCZOS), m.resize((w // s, h // s), Image.LANCZOS)


def paste(frame: Image.Image, obj: Image.Image, mask: Image.Image, cx: int, cy: int,
          long_px: int, angle: float, src_bg=None):
    """Paste obj centred at (cx,cy) with its long edge = long_px. Returns GT box."""
    obj = obj.rotate(angle, expand=True, resample=Image.BICUBIC)
    mask = mask.rotate(angle, expand=True, resample=Image.BICUBIC)
    bb = mask.point(lambda v: 255 if v > 40 else 0).getbbox()
    obj, mask = obj.crop(bb), mask.crop(bb)
    sc = long_px / max(obj.size)
    nw, nh = max(2, round(obj.width * sc)), max(2, round(obj.height * sc))
    obj = obj.resize((nw, nh), Image.LANCZOS)
    mask = mask.resize((nw, nh), Image.LANCZOS).filter(ImageFilter.GaussianBlur(max(0.6, long_px / 120)))
    x0, y0 = cx - nw // 2, cy - nh // 2
    # match brightness to local pavement
    local = frame.crop((x0 - nw, y0 - nh, x0 + 2 * nw, y0 + 2 * nh))
    lum_local = ImageStat.Stat(local.convert("L")).median[0]
    if src_bg is not None:
        lum_src = 0.299 * src_bg[0] + 0.587 * src_bg[1] + 0.114 * src_bg[2]
        obj = ImageEnhance.Brightness(obj).enhance(max(0.35, min(1.4, lum_local / max(lum_src, 1))))
    elif lum_local < 90:  # drawn objects: dim them on dark/night pavement
        obj = ImageEnhance.Brightness(obj).enhance(max(0.35, lum_local / 120))
    # soft contact shadow
    sh = Image.new("RGB", (nw, nh), (0, 0, 0))
    shm = mask.point(lambda v: int(v * 0.35)).filter(ImageFilter.GaussianBlur(max(1, long_px / 30)))
    frame.paste(sh, (x0 + max(1, nw // 25), y0 + max(1, nh // 12)), shm)
    frame.paste(obj, (x0, y0), mask)
    return [x0, y0, x0 + nw, y0 + nh]


# Seeded placements: (frame, variant, [(object, cx, cy, long_px, angle)]).
# Positions chosen on visible apron surface; sizes ~ perspective-plausible for
# 10-30 cm objects (bigger near the bottom). long_px is at 3840x2160.
PLACEMENTS = None  # filled from placements.json


def main():
    raw, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    frames = prep_frames(raw)
    if "--frames-only" in sys.argv:
        for k, im in frames.items():
            im.save(out / f"frame_{k}.jpg", quality=92)
        return
    placements = json.loads(Path(sys.argv[3]).read_text())
    sheet = Image.open(raw / "foda/manyEx.png")
    rng = random.Random(7)
    gt = {}
    for k, im in frames.items():  # clean controls
        name = f"{k}__clean.jpg"
        im.save(out / name, quality=92)
        gt[name] = {"frame": k, "kind": "clean", "objects": []}
    for k in placements["noop"]:  # no-op edited controls
        im = frames[k].copy()
        im = ImageEnhance.Brightness(im).enhance(1.0 + rng.uniform(-0.04, 0.04))
        for (sx, sy, dx, dy, sz) in placements["noop"][k]:
            patch = im.crop((sx, sy, sx + sz, sy + sz))
            m = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(m).ellipse((sz // 6, sz // 6, sz - sz // 6, sz - sz // 6), fill=255)
            im.paste(patch, (dx, dy), m.filter(ImageFilter.GaussianBlur(sz / 12)))
        name = f"{k}__noop.jpg"
        im.save(out / name, quality=88)
        gt[name] = {"frame": k, "kind": "noop", "objects": []}
    for entry in placements["seeded"]:
        k, var, objs = entry["frame"], entry["variant"], entry["objects"]
        im = frames[k].copy()
        boxes = []
        for (obj, cx, cy, long_px, ang) in objs:
            if obj in FODA_CELLS:
                o, m, bg = cut_foda(sheet, obj)
                src = "FOD-A"
            else:
                o, m = drawn_object(obj); bg = None
                src = "drawn"
            box = paste(im, o, m, cx, cy, long_px, ang, bg)
            boxes.append({"label": obj, "source": src, "box": box, "long_px": long_px})
        name = f"{k}__fod{var}.jpg"
        im.save(out / name, quality=92)
        gt[name] = {"frame": k, "kind": "seeded", "objects": boxes}
    (out / "ground_truth.json").write_text(json.dumps({"image_size": [W, H], "images": gt}, indent=1))
    print(f"wrote {len(gt)} images to {out}")


if __name__ == "__main__":
    main()
