"""Review aids for the manual passes (choosing crops, placing polygons and debris, checking results).

Usage:
  preview.py grid <downloads_dir> <out_dir> <source_key> [...]      source photo, 1800 px wide, 500 px source grid
  preview.py stand <downloads_dir> <out_dir> <stand> [...]          the 6 Angle crops of a stand in one sheet, 10% grid; WIDE regions drawn
  preview.py scene <data_dir> <out_dir> <scene_id> [...]            the 6 current frames of a built scene with ground-truth boxes
  preview.py zoom <data_dir> <out_dir> <scene_id> <ANGLE>           native-resolution crops around each ground-truth box
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import frames  # noqa: E402
import build_scenes  # noqa: E402

Image.MAX_IMAGE_PIXELS = 80_000_000
ANGLES = ["NOSE", "ENG-L", "ENG-R", "CARGO", "AFT", "WIDE"]
MAN = HERE / "manifest"


def grid_fraction(im, label):
    d = ImageDraw.Draw(im)
    W, H = im.size
    for i in range(1, 10):
        d.line((W * i // 10, 0, W * i // 10, H), fill=(255, 255, 0), width=1)
        d.line((0, H * i // 10, W, H * i // 10), fill=(255, 255, 0), width=1)
        d.text((W * i // 10 + 2, 2), f".{i}", fill=(255, 255, 0))
        d.text((2, H * i // 10 + 2), f".{i}", fill=(255, 255, 0))
    d.rectangle((0, H - 14, 8 * len(label) + 6, H), fill=(0, 0, 0))
    d.text((3, H - 13), label, fill=(255, 255, 255))
    return im


def main():
    mode, a, out, keys = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:]
    out.mkdir(parents=True, exist_ok=True)
    if mode == "grid":
        lock = json.loads((MAN / "sources.lock.json").read_text())
        for k in keys:
            im = Image.open(a / lock[k]["file"]).convert("RGB")
            s = 1800 / im.width
            sm = im.resize((1800, round(im.height * s)))
            d = ImageDraw.Draw(sm)
            for x in range(500, im.width, 500):
                d.line((x * s, 0, x * s, sm.height), fill=(255, 255, 0), width=1)
                d.text((x * s + 2, 2), str(x), fill=(255, 255, 0))
            for y in range(500, im.height, 500):
                d.line((0, y * s, sm.width, y * s), fill=(255, 255, 0), width=1)
                d.text((2, y * s + 2), str(y), fill=(255, 255, 0))
            sm.save(out / f"grid_{k}.jpg", quality=80)
            print(k, im.size)
    elif mode == "stand":
        lock = json.loads((MAN / "sources.lock.json").read_text())
        stands = json.loads((MAN / "stands.json").read_text())
        for k in keys:
            st = stands[k]
            tw, th = 900, 506
            sheet = Image.new("RGB", (tw * 2, th * 3))
            for i, ang in enumerate(ANGLES):
                an = st["angles"][ang]
                im = frames.cut_angle(Image.open(a / lock[an["src"]]["file"]).convert("RGB"), an["box"], an.get("mirror", False))
                full = im.size
                im = im.resize((tw, th))
                if ang == "WIDE":
                    d = ImageDraw.Draw(im)
                    for name, col in (("envelope", (0, 255, 0)), ("erl", (255, 0, 255))):
                        pts = [(x * tw, y * th) for x, y in build_scenes.stand_regions(st)[name]]
                        d.line(pts + pts[:1], fill=col, width=2)
                grid_fraction(im, f"{k} {ang} {full[0]}x{full[1]}{' mirror' if an.get('mirror') else ''}")
                sheet.paste(im, ((i % 2) * tw, (i // 2) * th))
            sheet.save(out / f"stand_{k}.jpg", quality=80)
    elif mode == "scene":
        for k in keys:
            sc = json.loads((a / "scenes" / k / "scene.json").read_text())
            tw, th = 900, 506
            sheet = Image.new("RGB", (tw * 2, th * 3), (40, 40, 40))
            for i, ang in enumerate(ANGLES):
                an = sc["angles"][ang]
                if not an["image"]:
                    continue
                im = Image.open(a / "scenes" / k / an["image"]).convert("RGB")
                s = tw / im.width
                im = im.resize((tw, th))
                d = ImageDraw.Draw(im)
                if an["regions"]:
                    for name, col in (("envelope", (0, 255, 0)), ("erl", (255, 0, 255))):
                        pts = [(x * s, y * s) for x, y in an["regions"][name]]
                        d.line(pts + pts[:1], fill=col, width=2)
                for g in an["ground_truth"]:
                    b = [v * s for v in g["bbox"]]
                    d.rectangle((b[0] - 6, b[1] - 6, b[2] + 6, b[3] + 6), outline=(255, 0, 0), width=2)
                    d.text((b[0] - 6, b[1] - 18), f"{g['label']} {g['expected_severity']}", fill=(255, 255, 0))
                d.rectangle((0, th - 14, 330, th), fill=(0, 0, 0))
                d.text((3, th - 13), f"{k} {ang} {an['width']}x{an['height']} {an['derived']} {an['unusable_reason'] or ''}", fill=(255, 255, 255))
                sheet.paste(im, ((i % 2) * tw, (i // 2) * th))
            sheet.save(out / f"scene_{k}.jpg", quality=80)
    elif mode == "zoom":
        sid, angs = keys[0], keys[1:] or ANGLES
        sc = json.loads((a / "scenes" / sid / "scene.json").read_text())
        tiles = []
        for ang in angs:
            an = sc["angles"][ang]
            if not an["image"]:
                continue
            im = Image.open(a / "scenes" / sid / an["image"]).convert("RGB")
            for g in an["ground_truth"]:
                b = g["bbox"]
                cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
                r = max(200, int(max(b[2] - b[0], b[3] - b[1]) * 1.2))
                x0, y0 = min(max(0, cx - r), im.width - 2 * r), min(max(0, cy - r), im.height - 2 * r)
                t = im.crop((x0, y0, x0 + 2 * r, y0 + 2 * r)).resize((400, 400))
                ImageDraw.Draw(t).text((4, 4), f"{sid} {ang} {g['label']} {max(b[2]-b[0], b[3]-b[1])}px", fill=(255, 255, 0))
                tiles.append(t)
        if tiles:
            sheet = Image.new("RGB", (400 * min(4, len(tiles)), 400 * ((len(tiles) + 3) // 4)))
            for i, t in enumerate(tiles):
                sheet.paste(t, ((i % 4) * 400, (i // 4) * 400))
            sheet.save(out / f"zoom_{sid}.jpg", quality=85)


if __name__ == "__main__":
    main()
