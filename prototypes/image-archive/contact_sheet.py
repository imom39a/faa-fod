"""Tile manifest images into numbered contact sheets for a quick manual Angle-tagging pass.

Usage: .venv/bin/python -I contact_sheet.py [--per-sheet 6] [--out sheets/]
Reads manifest.jsonl, writes sheets/sheet_NN.jpg (2 columns x 3 rows of 800 px tiles) and
sheets/index.csv mapping sheet/slot -> manifest id and file.
"""

import argparse
import csv
import json
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
Image.MAX_IMAGE_PIXELS = 40_000_000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-sheet", type=int, default=6)
    ap.add_argument("--out", default="sheets")
    a = ap.parse_args()
    out = HERE / a.out
    out.mkdir(exist_ok=True)
    recs = [json.loads(l) for l in (HERE / "manifest.jsonl").read_text().splitlines()]
    recs = [r for r in recs if r.get("file")]
    tw, th, cols = 800, 450, 2
    rows = -(-a.per_sheet // cols)
    with (out / "index.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sheet", "slot", "n", "id", "file", "title"])
        for s in range(0, len(recs), a.per_sheet):
            sheet = Image.new("RGB", (tw * cols, th * rows), "black")
            d = ImageDraw.Draw(sheet)
            for i, r in enumerate(recs[s : s + a.per_sheet]):
                with Image.open(HERE / r["file"]) as im:
                    im = im.convert("RGB")
                    im.thumbnail((tw - 4, th - 4))
                    x, y = (i % cols) * tw, (i // cols) * th
                    sheet.paste(im, (x + 2, y + 2))
                n = s + i + 1
                d.rectangle([x + 2, y + 2, x + 60, y + 34], fill="yellow")
                d.text((x + 8, y + 6), f"#{n}", fill="black", font_size=24)
                w.writerow([s // a.per_sheet + 1, i + 1, n, r["id"], r["file"], r["title"]])
            sheet.save(out / f"sheet_{s // a.per_sheet + 1:02d}.jpg", quality=85)


if __name__ == "__main__":
    main()
