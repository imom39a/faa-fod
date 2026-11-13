"""PROTOTYPE (dashboard 0009) - throwaway. Builds the real-photo Angle images for the dashboard.

Usage (from prototypes/dashboard; paths are arguments, always run with -I):
  ../spike/.venv/bin/python -I tools/fetch_sources.py assets/raw/orig          # re-download originals (~60 MB, not kept)
  ../spike/.venv/bin/python -I tools/build_assets.py assets/raw/orig ../spike/data/raw/foda assets [--clean-only]

- Crops each Angle out of openly licensed Wikimedia Commons photos (see assets/ATTRIBUTION.md).
  An Angle is defined by its ground Zone, and issue 0005 allows "an Angle may be a crop of a
  larger frame", so one high-res stand photo can supply several Angles.
- Resizes every Angle frame to 1600x900 (16:9).
- Pastes real photographed debris (FOD-A crops, MIT) at fixed positions with the spike's
  feathered-mask + contact-shadow + brightness-matched compositing (prototypes/spike/make_dataset.py).
- Makes INCOMPLETE frames: a genuinely blocked capture (Thai stand, 2nd photo, belt-loader truck
  parked in the ENG-R view) and a synthetic low-sun glare over a real frame.
- Writes assets/scenes.json (ground truth: boxes in 1600x900 image px) and assets/scenes.js
  (same data as window.FOD_ASSETS, so index.html works from file:// without fetch).
"""
import json
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageStat

OW, OH = 1600, 900
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "spike"))
import make_dataset as md  # noqa: E402  (our own spike code: cut_foda, paste)

# ---------------------------------------------------------------- sources
PHOTOS = {
    "pel1": "Pelita_Air_Airbus_A320_PK-PWL_Jakarta_2025_01_.jpg",
    "pel2": "Pelita_Air_Airbus_A320_PK-PWL_Jakarta_2025_02_.jpg",
    "pel3": "Pelita_Air_Airbus_A320_PK-PWL_Jakarta_2025_03_.jpg",
    "tha1": "Thai_Airbus_A320_HS-TXS_Denpasar_2025_01_.jpg",
    "tha2": "Thai_Airbus_A320_HS-TXS_Denpasar_2025_02_.jpg",
    "tha3": "Thai_Airbus_A320_HS-TXS_Denpasar_2025_03_.jpg",
    "gar1": "Garuda_Boeing_737_PK-GFV_Jakarta_2023_01_.jpg",
    "ryr": "Engine_of_Boeing_737-800_EI-DLY.JPG",
}

CREDIT = {
    "pel1": "Photo: Bahnfrend / Wikimedia Commons, CC0", "pel2": "Photo: Bahnfrend / Wikimedia Commons, CC0",
    "pel3": "Photo: Bahnfrend / Wikimedia Commons, CC0",
    "tha1": "Photo: Bahnfrend / Wikimedia Commons, CC BY-SA 4.0", "tha2": "Photo: Bahnfrend / Wikimedia Commons, CC BY-SA 4.0",
    "tha3": "Photo: Bahnfrend / Wikimedia Commons, CC BY-SA 4.0",
    "gar1": "Photo: Bahnfrend / Wikimedia Commons, CC BY-SA 4.0",
    "ryr": "Photo: Andy Mabbett / Wikimedia Commons, CC BY-SA 3.0",
}

# set -> angle -> (photo, crop box x0,y0,x1,y1 in source px; all 16:9)
SETS = {
    "PEL": {
        "NOSE": ("pel3", (1200, 2000, 4400, 3800)),
        "ENG-L": ("pel2", (3200, 1750, 5600, 3100)),
        "ENG-R": ("pel1", (1100, 1800, 3500, 3150)),
        "CARGO": ("pel1", (1000, 2170, 4200, 3970)),
        "AFT": ("pel1", (600, 1050, 3800, 2850)),
        "WIDE": ("pel2", (0, 433, 5826, 3710)),
    },
    "THA": {
        "NOSE": ("tha3", (3000, 1680, 5800, 3255)),
        "ENG-L": ("tha3", (3994, 1950, 5794, 2962)),
        "ENG-R": ("tha1", (2300, 1050, 4700, 2400)),
        "CARGO": ("tha3", (900, 1400, 4100, 3200)),
        "AFT": ("tha1", (0, 300, 3200, 2100)),
        "WIDE": ("tha1", (0, 1, 5765, 3244)),
    },
    "GAR": {
        "NOSE": ("gar1", (3616, 2000, 6016, 3350)),
        "ENG-L": ("ryr", (0, 308, 3008, 2000)),
        "ENG-R": ("gar1", (1900, 1750, 4300, 3100)),
        "CARGO": ("gar1", (1200, 1750, 4400, 3550)),
        "AFT": ("gar1", (0, 700, 3200, 2500)),
        "WIDE": ("gar1", (0, 632, 6016, 4016)),
    },
}


def load(raw: Path, key: str, _cache={}):
    if key not in _cache:
        _cache[key] = Image.open(raw / PHOTOS[key]).convert("RGB")
    return _cache[key]


def crop(im: Image.Image, box):
    return im.crop(box).resize((OW, OH), Image.LANCZOS)


def register(ref: Image.Image, mov: Image.Image):
    """Find (scale, dx, dy) so that mov(x*s+dx, y*s+dy) ~ ref(x, y). Brute force at low res."""
    w = 480
    f = ref.width / w
    r = ref.convert("L").resize((w, round(ref.height / f)))
    best = None
    for s in [0.97 + 0.005 * i for i in range(13)]:
        fm = f * s  # mov px per small-ref px
        m = mov.convert("L").resize((round(mov.width / fm), round(mov.height / fm)))
        for dx in range(-40, 41):
            for dy in range(-20, 21):
                # compare central region
                bx = (60, 60, w - 60, r.height - 60)
                a = r.crop(bx)
                b = m.crop((bx[0] + dx, bx[1] + dy, bx[2] + dx, bx[3] + dy))
                d = ImageStat.Stat(ImageChops.difference(a, b)).mean[0]
                if best is None or d < best[0]:
                    best = (d, s, dx * fm, dy * fm)
    _, s, dx, dy = best
    return s, dx, dy


def map_box(box, s, dx, dy):
    x0, y0, x1, y1 = box
    return tuple(round(v) for v in (x0 * s + dx, y0 * s + dy, x1 * s + dx, y1 * s + dy))


def glare(im: Image.Image, cx: float, cy: float, seed: int = 3):
    """Low-sun veiling glare + bloom + flare ghosts, as from the sun just outside the frame."""
    rnd = random.Random(seed)
    W, H = im.size
    out = im.copy()
    # veiling glare: big radial wash, strongest near the sun position
    veil = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(veil)
    for r in range(int(W * 1.1), 0, -12):
        a = int(255 * (1 - r / (W * 1.1)) ** 1.6)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=a)
    veil = veil.filter(ImageFilter.GaussianBlur(30))
    white = Image.new("RGB", (W, H), (255, 248, 228))
    out = Image.composite(white, out, veil.point(lambda v: min(255, int(v * 1.25))))
    # lower contrast overall (washed-out lens)
    out = ImageEnhance.Contrast(out).enhance(0.38)
    out = ImageEnhance.Brightness(out).enhance(1.18)
    # flare ghosts along the line from sun through centre
    ghosts = Image.new("RGB", (W, H), (0, 0, 0))
    gm = Image.new("L", (W, H), 0)
    gd, gmd = ImageDraw.Draw(ghosts), ImageDraw.Draw(gm)
    for t, rad, col in [(0.55, 60, (120, 255, 170)), (0.8, 28, (255, 200, 120)), (1.15, 90, (150, 170, 255)), (1.45, 40, (255, 150, 220))]:
        gx, gy = cx + (W / 2 - cx) * t * 2, cy + (H / 2 - cy) * t * 2
        gd.ellipse((gx - rad, gy - rad, gx + rad, gy + rad), fill=col)
        gmd.ellipse((gx - rad, gy - rad, gx + rad, gy + rad), fill=70 + rnd.randint(0, 30))
    gm = gm.filter(ImageFilter.GaussianBlur(6))
    out = Image.composite(ImageChops.screen(out, ghosts), out, gm)
    # streak
    st = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(st)
    ang = math.atan2(H / 2 - cy, W / 2 - cx)
    L = W * 1.5
    sd.line((cx - L * math.cos(ang), cy - L * math.sin(ang), cx + L * math.cos(ang), cy + L * math.sin(ang)), fill=120, width=10)
    st = st.filter(ImageFilter.GaussianBlur(14))
    out = Image.composite(Image.new("RGB", (W, H), (255, 250, 235)), out, st)
    return out


# ---------------------------------------------------------------- debris
# FOD-A objects. manyEx cells reuse the spike's cut_foda(); Picture*.png are 420x420 single
# examples with a red annotation box drawn by FOD-A, so we cut strictly inside that box.
PICTURES = {"nut": "Picture5.png", "strap": "Picture8.png"}


def red_box(im: Image.Image):
    """Bounding box of FOD-A's drawn red annotation rectangle, inset so the red line is excluded."""
    px = im.load()
    pts = [(x, y) for x in range(im.width) for y in range(im.height)
           if px[x, y][0] > 180 and px[x, y][1] < 80 and px[x, y][2] < 80]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs) + 5, min(ys) + 5, max(xs) - 4, max(ys) - 4)


def cut_picture(foda: Path, key: str):
    full = Image.open(foda / PICTURES[key]).convert("RGB")
    cell = full.crop(red_box(full))
    cw, ch = cell.size
    ring = [cell.getpixel((x, y)) for x in range(cw) for y in range(ch) if x < 8 or y < 8 or x >= cw - 8 or y >= ch - 8]
    bg = tuple(sorted(p[i] for p in ring)[len(ring) // 2] for i in range(3))
    mask = Image.new("L", cell.size, 0)
    mp = mask.load()
    for x in range(cw):
        for y in range(ch):
            p = cell.getpixel((x, y))
            mp[x, y] = 255 if sum(abs(p[i] - bg[i]) for i in range(3)) > 70 and not (p[0] > 170 and p[1] < 90 and p[2] < 90) else 0
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
    bb = mask.getbbox()
    return cell.crop(bb), mask.crop(bb).filter(ImageFilter.GaussianBlur(0.8)), bg


def get_obj(foda: Path, sheet: Image.Image, key: str):
    if key in PICTURES:
        return cut_picture(foda, key)
    return md.cut_foda(sheet, key)


md.FODA_CELLS.setdefault("debris_crumpled", (2, 6))  # manyEx row 3, "Rock" column: crumpled dry debris


def main():
    raw, foda, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    clean_only = "--clean-only" in sys.argv
    spec = json.loads((HERE / "composites.json").read_text()) if not clean_only else {"composites": []}
    (out / "img").mkdir(parents=True, exist_ok=True)
    data = {"image_size": [OW, OH], "sets": {}, "frames": {}}
    base, base_src = {}, {}
    for sname, angles in SETS.items():
        data["sets"][sname] = {}
        for ang, (photo, box) in angles.items():
            im = crop(load(raw, photo), box)
            base[(sname, ang)] = im
            base_src[(sname, ang)] = photo
            fn = f"img/{sname.lower()}_{ang.lower()}_clean.jpg"
            im.save(out / fn, quality=84, optimize=True, progressive=True)
            data["sets"][sname][ang] = fn
            data["frames"][fn] = {"set": sname, "angle": ang, "kind": "clean", "source": PHOTOS[photo],
                                  "crop_src_px": list(box), "objects": [], "credit": CREDIT[photo]}
    # Thai stand, second capture from the same camera (tha2): register to tha1 and cut the same Angles
    s, dx, dy = register(load(raw, "tha1"), load(raw, "tha2"))
    print(f"tha2 -> tha1 registration: scale {s:.3f}, dx {dx:.0f}, dy {dy:.0f}")
    for ang in ("ENG-R", "AFT", "WIDE"):
        box = map_box(SETS["THA"][ang][1], s, dx, dy)
        im2 = load(raw, "tha2")
        box = (max(0, box[0]), max(0, box[1]), min(im2.width, box[2]), min(im2.height, box[3]))
        im = crop(im2, box)
        base[("THA2", ang)] = im
        base_src[("THA2", ang)] = "tha2"
        kind = "blocked" if ang == "ENG-R" else "clean"
        fn = f"img/tha_{ang.lower()}_{'blocked' if kind == 'blocked' else 'capture2'}.jpg"
        im.save(out / fn, quality=84, optimize=True, progressive=True)
        data["frames"][fn] = {"set": "THA", "angle": ang, "kind": kind, "source": PHOTOS["tha2"], "crop_src_px": list(box), "credit": CREDIT["tha2"],
                              "objects": [], **({"note": "Belt-loader truck (JAS) parked between camera and the ENG-R ground zone in this real capture."} if kind == "blocked" else {})}
    data["thaCapture2"] = {a: f"img/tha_{a.lower()}_{'blocked' if a == 'ENG-R' else 'capture2'}.jpg" for a in ("ENG-R", "AFT", "WIDE")}
    if clean_only:
        write(out, data)
        return
    sheet = Image.open(foda / "manyEx.png")
    for c in spec["composites"]:
        if c.get("annotate_only"):  # real marks on an existing frame, nothing pasted
            data["frames"][f"img/{c['name']}.jpg"]["objects"] += [
                {"id": o["id"], "box": o["box"], "composited": False, "what": o["what"]} for o in c["real"]]
            continue
        src = c.get("base", [c["set"], c["angle"]])
        im = base[tuple(src)].copy()
        objs = []
        for o in c.get("objects", []):
            obj, mask, bg = get_obj(foda, sheet, o["fod"])
            before = im.copy()
            md.paste(im, obj, mask, o["cx"], o["cy"], o["long_px"], o.get("rot", 0), bg)
            # tight box = pixels that visibly changed (excludes the faint contact shadow / mask fringe)
            diff = ImageChops.difference(before, im).convert("L").point(lambda v: 255 if v > 16 else 0)
            b = diff.filter(ImageFilter.MinFilter(3)).getbbox() or diff.getbbox()  # drop 1-px speckle
            box = [max(0, b[0] - 5), max(0, b[1] - 5), min(OW, b[2] + 5), min(OH, b[3] + 5)]
            objs.append({"id": o["id"], "fod_a": o["fod"], "box": box, "composited": True})
        merged = {}  # one Finding box per id (union of its pasted pieces)
        for o in objs:
            m = merged.setdefault(o["id"], {**o, "pieces": 0})
            m["box"] = [min(m["box"][0], o["box"][0]), min(m["box"][1], o["box"][1]), max(m["box"][2], o["box"][2]), max(m["box"][3], o["box"][3])]
            m["pieces"] += 1
        objs = list(merged.values())
        if c.get("glare"):
            im = glare(im, *c["glare"])
        fn = f"img/{c['name']}.jpg"
        im.save(out / fn, quality=84, optimize=True, progressive=True)
        data["frames"][fn] = {"set": c["set"], "angle": c["angle"], "kind": c.get("kind", "seeded"), "base": "/".join(src),
                              "credit": CREDIT[base_src[tuple(src)]] + " · debris: FOD-A (MIT), composited" * bool(objs),
                              "objects": objs, **({"note": c["note"]} if c.get("note") else {})}
    write(out, data)


def write(out: Path, data):
    (out / "scenes.json").write_text(json.dumps(data, indent=1))
    (out / "scenes.js").write_text("// generated by tools/build_assets.py - ground truth for the dashboard\nwindow.FOD_ASSETS = "
                                   + json.dumps(data) + ";\n")
    print("frames:", len(data["frames"]))


if __name__ == "__main__":
    main()
