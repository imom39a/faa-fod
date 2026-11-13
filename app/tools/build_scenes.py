"""Build app/data/scenes/, testset.json and ATTRIBUTION.md from the manifests.

Usage: .venv/bin/python -I build_scenes.py <downloads_dir> <data_dir> [--only <scene_id> ...] [--clean]

Inputs (all under tools/manifest/):
  sources.lock.json  photos (written by fetch_sources.py)
  stands.json        stand -> light, 6 Angle crops (source key, 16:9 box in source px, mirror),
                     WIDE regions (envelope, erl) as fractions of the WIDE frame
  objects.json       debris cut-outs (FOD-A cells/pictures, Commons plain-background photos) and
                     GSE cut-outs (polygon in a Commons photo), with category, object class, label
  scenes.json        every scene: stand, description, debris placements, controls, unusable Angles,
                     GSE staging, reference mode, whether it is in the scoring set
Positions in scenes.json are fractions of the frame (x, y in 0..1); debris size (long_px) is in
output pixels. Everything is deterministic: seeds derive from scene_id and Angle.
"""
import hashlib
import json
import shutil
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageStat

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import debris  # noqa: E402
import frames  # noqa: E402

Image.MAX_IMAGE_PIXELS = 80_000_000
MIN_CONTRAST = 10.0   # a pasted object must change its pixels by at least this many grey levels on average
ANGLES = ["NOSE", "ENG-L", "ENG-R", "CARGO", "AFT", "WIDE"]
MAN = HERE / "manifest"


def seed_of(*parts):
    return zlib.crc32("/".join(map(str, parts)).encode())


class Sources:
    def __init__(self, dl: Path):
        self.dl, self.lock, self._cache = dl, json.loads((MAN / "sources.lock.json").read_text()), {}

    def image(self, key):
        if key not in self._cache:
            if len(self._cache) >= 3:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = Image.open(self.dl / self.lock[key]["file"]).convert("RGB")
        return self._cache[key]

    def credit(self, key):
        r = self.lock[key]
        return {"title": r["title"], "url": r["url"], "author": r["author"], "licence": r["licence"]}


class Objects:
    def __init__(self, dl: Path, sources: Sources):
        self.dl, self.src, self.spec, self._cache = dl, sources, json.loads((MAN / "objects.json").read_text()), {}

    def cutout(self, key):
        if key in self._cache:
            return self._cache[key]
        o = self.spec["debris"][key]
        if "foda_cell" in o:
            r = debris.cut_foda(Image.open(self.dl / "foda/manyEx.png"), *o["foda_cell"], thr=o.get("thr", 60), sub=o.get("sub"), chroma=o.get("chroma"), open_px=o.get("open", 3))
        elif "foda_picture" in o:
            r = debris.cut_picture(Image.open(self.dl / "foda" / o["foda_picture"]), thr=o.get("thr", 70), box=o.get("box"))
        elif "polygon" in o:   # object on a busy background: hand-drawn polygon (pixels of the fetched file)
            cut, m = self._poly(self.src.image(o["commons"]), o["polygon"])
            if max(cut.size) > 400:
                k = 400 / max(cut.size)
                cut, m = (im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS) for im in (cut, m))
            r = (cut, m.filter(ImageFilter.GaussianBlur(1.0)), None)
        else:
            r = debris.cut_plain(self.src.image(o["commons"]), box=o.get("box"), thr=o.get("thr", 45))
        if o.get("bg"):   # stated luminance reference: the pavement brightness this object's exposure corresponds to
            r = (r[0], r[1], tuple(o["bg"]))
        self._cache[key] = r
        return r

    def gse(self, key):
        """GSE cut-out: polygon (source px) in a Commons photo -> RGBA-style (image, mask)."""
        g = self.spec["gse"][key]
        return self._poly(self.src.image(g["commons"]), g["polygon"])

    @staticmethod
    def _poly(im, polygon):
        xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
        box = (min(xs), min(ys), max(xs), max(ys))
        cut = im.crop(box)
        m = Image.new("L", cut.size, 0)
        ImageDraw.Draw(m).polygon([(x - box[0], y - box[1]) for x, y in polygon], fill=255)
        return cut, m


def px(poly, W, H):
    return [[round(x * W), round(y * H)] for x, y in poly]


def stand_regions(st):
    """WIDE regions of a stand as fractions of the WIDE frame. stands.json gives them either as
    fractions ("regions") or in source pixels of the WIDE photo ("regions_src"), which is how they
    were drawn; source pixels are mapped through the WIDE crop box (and its mirror flag)."""
    if st.get("regions"):
        return st["regions"]
    a = st["angles"]["WIDE"]
    x0, y0, x1, y1 = a["box"]
    out = {}
    for name, poly in st["regions_src"].items():
        pts = [[min(1.0, max(0.0, (x - x0) / (x1 - x0))), min(1.0, max(0.0, (y - y0) / (y1 - y0)))] for x, y in poly]
        out[name] = [[1 - x, y] for x, y in pts] if a.get("mirror") else pts
    return out


def inside(poly, x, y):
    n, c = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def place(d, a, W, H):
    """Centre of a placement in frame px. Given as fractions of the frame (x, y) or as source-photo
    pixels (sx, sy), which are mapped through the Angle's crop box and mirror flag."""
    if "sx" in d:
        x0, y0, x1, y1 = a["box"]
        fx, fy = (d["sx"] - x0) / (x1 - x0), (d["sy"] - y0) / (y1 - y0)
        assert 0.01 < fx < 0.99 and 0.01 < fy < 0.99, f"placement {d} is outside crop {a['box']}"
        if a.get("mirror"):
            fx = 1 - fx
    else:
        fx, fy = d["x"], d["y"]
    return round(fx * W), round(fy * H)


def paste_gse(frame, cut, mask, g):
    """Paste a GSE cut-out with its bottom-centre at (x, y) (fractions) and width w (fraction)."""
    W, H = frame.size
    if g.get("mirror"):
        cut, mask = cut.transpose(Image.FLIP_LEFT_RIGHT), mask.transpose(Image.FLIP_LEFT_RIGHT)
    nw = round(g["w"] * W)
    nh = round(cut.height * nw / cut.width)
    cut = cut.resize((nw, nh), Image.LANCZOS)
    mask = mask.resize((nw, nh), Image.LANCZOS).filter(ImageFilter.GaussianBlur(max(1.0, nw / 400)))
    if g.get("gain"):
        cut = ImageEnhance.Brightness(cut).enhance(g["gain"])
    x0, y0 = round(g["x"] * W - nw / 2), round(g["y"] * H - nh)
    sh = Image.new("L", (W, H), 0)   # soft ground shadow under the vehicle
    ImageDraw.Draw(sh).ellipse((x0 - nw * 0.03, y0 + nh * 0.80, x0 + nw * 1.03, y0 + nh * 1.04), fill=int(255 * g.get("shadow", 0.45)))
    frame.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), sh.filter(ImageFilter.GaussianBlur(nw / 25)))
    frame.paste(cut, (x0, y0), mask)
    bb = mask.point(lambda v: 255 if v > 60 else 0).getbbox()
    return [max(0, x0 + bb[0]), max(0, y0 + bb[1]), min(W, x0 + bb[2]), min(H, y0 + bb[3])]


def save(im, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=frames.JPEG_Q, optimize=True)


def derived_of(a, src_size):
    if a.get("mirror"):
        return "mirror"
    x0, y0, x1, y1 = a["box"]
    return "native" if (x1 - x0) * (y1 - y0) >= 0.80 * src_size[0] * src_size[1] else "crop"


def build_scene(sc, stands, src: Sources, objs: Objects, rules, out: Path):
    st = stands[sc["stand"]]
    sdir = out / "scenes" / sc["scene_id"]
    if sdir.exists():
        shutil.rmtree(sdir)
    sdir.mkdir(parents=True)
    scene = {"scene_id": sc["scene_id"], "kind": sc["kind"], "light": st["light"], "description": sc["description"], "angles": {}}
    prov = {"scene_id": sc["scene_id"], "stand": sc["stand"], "scoring": bool(sc.get("scoring")), "control": sc.get("control"),
            "reference_mode": sc.get("ref_mode", "mild"), "angles": {}}
    for ang in ANGLES:
        a = dict(st["angles"][ang])
        a.update((sc.get("angle_override") or {}).get(ang, {}))
        simg = src.image(a["src"])
        base = frames.cut_angle(simg, a["box"], a.get("mirror", False))
        W, H = base.size
        cur = base.copy()
        tier = rules["angle_zone_tier"][ang]
        regions = None
        if ang == "WIDE":
            rg = sc.get("regions") or stand_regions(st)
            regions = {"envelope": px(rg["envelope"], W, H), "erl": px(rg["erl"], W, H)}
        gt, used, p = [], [], {"source_key": a["src"], "crop_box_source_px": a["box"], "mirrored": bool(a.get("mirror")), "edits": []}
        noop = (sc.get("noop") or {}).get(ang)
        if noop:
            cur = frames.noop_edit(cur, [[round(s[0] * W), round(s[1] * H), round(s[2] * W), round(s[3] * H), int(s[4])] for s in noop],
                                   seed_of(sc["scene_id"], ang, "noop"))
            p["edits"].append("no-op compositing control (tone jitter + pavement patch pasted on pavement)")
        for d in (sc.get("debris") or {}).get(ang, []):
            o = objs.spec["debris"][d["obj"]]
            obj, mask, bg = objs.cutout(d["obj"])
            cx, cy = place(d, a, W, H)
            box, contrast = debris.paste(cur, obj, mask, cx, cy, d["long_px"], d.get("rot", 0), bg, d.get("min_gain", 0.35))
            if contrast < MIN_CONTRAST:
                raise SystemExit(f"{sc['scene_id']}/{ang}: {d['obj']} is nearly invisible where it was placed "
                                 f"(mean change {contrast:.1f} grey levels < {MIN_CONTRAST}); move it or raise min_gain")
            zt = tier
            if ang == "WIDE":
                zt = "general" if inside(regions["envelope"], cx, cy) else "outside_boundary"
            cls = d.get("object_class", o["object_class"])
            gt.append({"bbox": box, "finding_type": "fod", "category": o["category"], "object_class": cls, "zone_tier": zt,
                       "expected_severity": rules["severity_matrix"][cls][zt], "label": o["label"]})
            used.append(d["obj"])
            p["edits"].append(f"debris composited: {d['obj']} ({o['label']}) at {box}, long edge {max(box[2]-box[0], box[3]-box[1])} px, contrast {contrast:.0f}")
        g = (sc.get("gse") or {}).get(ang)
        if g and g.get("cutout"):
            box = paste_gse(cur, *objs.gse(g["cutout"]), g)
            gt.append({"bbox": box, "finding_type": "equipment_staging", "category": None, "object_class": None, "zone_tier": "general",
                       "expected_severity": "REMOVE", "label": objs.spec["gse"][g["cutout"]]["label"]})
            used.append(g["cutout"])
            p["edits"].append(f"GSE composited: {g['cutout']} at {box}")
        elif g:  # GSE really present in the photograph: annotate only
            b = g["bbox"]
            gt.append({"bbox": [round(b[0] * W), round(b[1] * H), round(b[2] * W), round(b[3] * H)], "finding_type": "equipment_staging",
                       "category": None, "object_class": None, "zone_tier": "general", "expected_severity": "REMOVE", "label": g["label"]})
        obs = [{"bbox": [round(b["bbox"][0] * W), round(b["bbox"][1] * H), round(b["bbox"][2] * W), round(b["bbox"][3] * H)], "kind": b["kind"]}
               for b in (sc.get("observations") or {}).get(ang, [])]
        un = (sc.get("unusable") or {}).get(ang)
        image = f"{ang}.jpg"
        if un:
            assert not gt, "an unusable Angle carries no ground truth"
            s = seed_of(sc["scene_id"], ang, "unusable")
            if un["reason"] == "missing":
                image = None
            elif un["reason"] == "glare":
                cur = frames.glare(cur, *un.get("at", [0.25, 0.07]), seed=s)
            elif un["reason"] == "blur":
                cur = frames.blur(cur, s)
            elif un["reason"] == "low_light":
                cur = frames.low_light(cur, s)
            else:
                raise ValueError(un["reason"])
            p["edits"].append(f"unusable: synthetic {un['reason']}")
        if image:
            save(cur, sdir / image)
        no_ref = ang in (sc.get("no_reference") or [])
        if not no_ref:
            (sdir / "ref").mkdir(exist_ok=True)
            (sdir / "ref" / f"{ang}.jpg").write_bytes(frames.make_reference(base, seed_of(sc["scene_id"], ang, "ref"), sc.get("ref_mode", "mild")))
        after = None
        if (gt or un) and sc.get("after", True) and not (g and not g.get("cutout")):
            after = f"after/{ang}.jpg"
            save(frames.recapture(base, seed_of(sc["scene_id"], ang, "after")), sdir / after)
        scene["angles"][ang] = {
            "image": image, "reference": None if no_ref else f"ref/{ang}.jpg", "after": after,
            "width": W, "height": H, "derived": derived_of(a, simg.size), "source": src.credit(a["src"]),
            "usable": not un, "unusable_reason": un["reason"] if un else None,
            "regions": regions, "ground_truth": gt, "observations_truth": obs,
        }
        p["objects"] = used
        prov["angles"][ang] = p
    (sdir / "scene.json").write_text(json.dumps(scene, indent=1, ensure_ascii=False) + "\n")
    (sdir / "build.json").write_text(json.dumps(prov, indent=1, ensure_ascii=False) + "\n")
    return scene, prov


def main():
    dl, out = Path(sys.argv[1]), Path(sys.argv[2])
    only = set()
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1:])
    stands = json.loads((MAN / "stands.json").read_text())
    scenes = json.loads((MAN / "scenes.json").read_text())["scenes"]
    rules = json.loads((out / "rules/fod-rules.json").read_text())
    src = Sources(dl)
    objs = Objects(dl, src)
    ids = [s["scene_id"] for s in scenes]
    assert len(ids) == len(set(ids)), "duplicate scene_id"
    if not only and (out / "scenes").exists():  # full build: drop scenes no longer in the manifest
        for d in (out / "scenes").iterdir():
            if d.is_dir() and d.name not in ids:
                shutil.rmtree(d)
    for sc in sorted(scenes, key=lambda s: s["stand"]):
        if only and sc["scene_id"] not in only:
            continue
        build_scene(sc, stands, src, objs, rules, out)
        print("built", sc["scene_id"], flush=True)
    if only:   # partial rebuild: leave testset.json, the timeline and ATTRIBUTION.md alone
        return
    (out / "testset.json").write_text(json.dumps({"scenes": [s["scene_id"] for s in scenes if s.get("scoring")]}, indent=1) + "\n")
    tl = json.loads((MAN / "timeline.json").read_text())
    for t in tl["turns"]:
        for e in t["events"]:
            assert e["type"] != "inspection" or e["scene_id"] in ids, f"timeline uses unknown scene {e.get('scene_id')}"
    (out / "demo").mkdir(exist_ok=True)
    for t in tl["turns"]:
        t.pop("note", None)   # notes are for the manifest reader; the contract has no such key
    (out / "demo/timeline.json").write_text(json.dumps(tl, indent=1) + "\n")
    import attribution  # noqa: E402
    attribution.write(out, MAN)


if __name__ == "__main__":
    main()
