"""Fetch every source the build needs into the download cache and write the lock file.

Usage: .venv/bin/python -I fetch_sources.py <downloads_dir>

Reads manifest/sources.json ({key: {"title": "<Commons file title>"}}) and manifest/objects.json
(debris cut-outs; those with "commons" need a photo too). For each Commons file: one metadata
request (batched, 50 titles per request), a licence check (CC0 / PD / CC BY / CC BY-SA only), then
the original is downloaded once to <downloads_dir>/orig/. Also fetches the FOD-A example images
(MIT) from GitHub to <downloads_dir>/foda/. A source with "thumb": <width> is fetched as Commons' rendition of that
width instead of the original (used for the small debris-object photos; boxes and polygons for those are in rendition pixels). Full-size originals are rate limited hard for
anonymous clients (about 10 per 10 minutes), so a cold run of ~45 originals takes about an hour. Writes manifest/sources.lock.json with title, page URL,
author, licence, size and sha256 of every file: that lock file, not a search, is the reproducible
record. Requests are serial, paced for the anonymous tier, and use a generic User-Agent.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import commons  # noqa: E402

FODA_BASE = "https://raw.githubusercontent.com/FOD-UNOmaha/FOD-data/master/Examples/"
FODA_FILES = ["manyEx.png", "Picture1.png", "Picture3.png", "Picture4.png", "Picture5.png", "Picture8.png"]
FODA_LICENCE = "https://raw.githubusercontent.com/FOD-UNOmaha/FOD-data/master/LICENSE"


def main():
    dl = Path(sys.argv[1])
    man = HERE / "manifest"
    sources = json.loads((man / "sources.json").read_text())
    lock_p = man / "sources.lock.json"
    lock = json.loads(lock_p.read_text()) if lock_p.exists() else {}
    need = [k for k, v in sources.items() if k not in lock or lock[k]["title"] != v["title"]]
    widths = sorted({int(sources[k].get("thumb") or 3840) for k in need})
    for wdt in widths:   # one metadata request per rendition width (50 titles per request)
        ks = [k for k in need if int(sources[k].get("thumb") or 3840) == wdt]
        meta = commons.info([sources[k]["title"] for k in ks], thumb_width=wdt)
        for k in ks:
            t = sources[k]["title"]
            if t not in meta:
                sys.exit(f"not found on Commons: {t}")
            r = meta[t]
            if not commons.licence_ok(r["licence"]):
                sys.exit(f"licence not allowed for {t}: {r['licence']!r}")
            lock[k] = {kk: r[kk] for kk in ("title", "url", "author", "licence", "licence_url", "width", "height", "download_url", "thumb_url", "date")}
            lock[k]["file"] = ("thumb/" if sources[k].get("thumb") else "orig/") + commons.safe_name(r["title"])
            if sources[k].get("thumb"):
                lock[k]["rendition_width"] = wdt
    for k in sorted(sources, key=lambda k: not sources[k].get("thumb")):   # quick renditions first
        p = dl / lock[k]["file"]
        had = p.exists()
        via_thumb = bool(sources[k].get("thumb"))   # small sources (debris objects): the 3840 px rendition is enough
        _, sha = commons.fetch(lock[k]["thumb_url"] if via_thumb else lock[k]["download_url"], p, "thumb" if via_thumb else "file")
        if lock[k].get("sha256") and lock[k]["sha256"] != sha:
            sys.exit(f"sha256 changed for {k}: the Commons file was replaced; review it and delete the lock entry")
        lock[k]["sha256"] = sha
        lock_p.write_text(json.dumps(lock, indent=1, sort_keys=True))
        if not had:
            print("fetched", k, p.name, flush=True)
    for k in [k for k in lock if k not in sources]:
        del lock[k]
    lock_p.write_text(json.dumps(lock, indent=1, sort_keys=True))
    foda = {}
    for f in FODA_FILES + ["LICENSE"]:
        p, sha = commons.fetch(FODA_LICENCE if f == "LICENSE" else FODA_BASE + f, dl / "foda" / f, "thumb")
        foda[f] = sha
    (man / "foda.lock.json").write_text(json.dumps(foda, indent=1, sort_keys=True))
    print("sources:", len(sources), "| FOD-A files:", len(foda))


if __name__ == "__main__":
    main()
