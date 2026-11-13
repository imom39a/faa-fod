"""Search Commons and build numbered contact sheets of candidate photos for the manual selection pass.

Usage: .venv/bin/python -I find_candidates.py <downloads_dir> <name> "<query>" ["<query>" ...]
       (a query starting with "cat:" lists a category; "title:<file title>" looks up exact files;
        a first argument "width:1280" fetches larger thumbnails)
Writes <downloads_dir>/thumbs/<name>.json (records) and <name>_NN.jpg sheets (4x3 thumbnails).
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import commons  # noqa: E402


MINW = 1000


def main():
    dl, name, queries = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
    tdir = dl / "thumbs"
    recs, seen = [], set()
    width = 330
    if queries and queries[0].startswith("width:"):   # larger thumbnails for a closer look, e.g. width:1280
        width, queries = int(queries[0][6:]), queries[1:]
    titles = [q[6:] for q in queries if q.startswith("title:")]
    batches = [list(commons.info(titles, thumb_width=width).values())] if titles else []
    for q in queries:
        if q.startswith("title:"):
            rs = batches.pop() if batches else []
        else:
            rs = commons.category(q[4:], thumb_width=width) if q.startswith("cat:") else commons.search(q, thumb_width=width)
        for r in rs:
            if r["title"] in seen or not commons.licence_ok(r["licence"]) or r["mime"] != "image/jpeg" or (r["width"] or 0) < MINW:
                continue
            seen.add(r["title"]); r["query"] = q; recs.append(r)
    for i, r in enumerate(recs):
        p = tdir / name / (f"{i:03d}_" + commons.safe_name(r["title"])[:80] + ".jpg")
        try:
            commons.fetch(r["thumb_url"], p, "thumb"); r["thumb"] = str(p)
        except Exception as e:  # noqa: BLE001
            print("thumb failed", r["title"], e)
    (tdir / f"{name}.json").write_text(json.dumps(recs, indent=1))
    cw, ch, cols, rows = 330, 250, 5, 4
    for s in range(0, len(recs), cols * rows):
        sheet = Image.new("RGB", (cw * cols, ch * rows), (30, 30, 30))
        d = ImageDraw.Draw(sheet)
        for j, r in enumerate(recs[s:s + cols * rows]):
            x, y = (j % cols) * cw, (j // cols) * ch
            if r.get("thumb"):
                try:
                    im = Image.open(r["thumb"]).convert("RGB"); im.thumbnail((cw - 4, ch - 24))
                    sheet.paste(im, (x + 2, y + 22))
                except Exception:  # noqa: BLE001
                    pass
            d.text((x + 4, y + 4), f"{s + j} {r['width']}x{r['height']} {r['licence']} {r['title'][:28]}", fill=(255, 255, 0))
        sheet.save(tdir / f"{name}_{s // (cols * rows):02d}.jpg", quality=80)
    print(len(recs), "candidates")
    for i, r in enumerate(recs):
        print(i, r["width"], r["licence"], "|", r["title"])


if __name__ == "__main__":
    main()
