"""Reproducible gate/apron image manifest builder (PROTOTYPE, issue 0013).

query -> licence filter -> attribution record (manifest.jsonl) -> optional sample download (raw/).

Sources:
  commons   Wikimedia Commons Action API (no key). generator=search in the File namespace.
  openverse Openverse API (no key, anonymous tier). license_type=commercial,modification.

Safety: downloads are untrusted. This script lives outside raw/, writes only into raw/,
verifies each file with Pillow, caps pixel count, and never executes downloaded content.
Run with:  .venv/bin/python -I build_manifest.py --help

Politeness: Wikimedia gives ~10 req/min to clients without contact info in the User-Agent
(https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits), so requests to Wikimedia hosts
are spaced >= 6.5 s and run strictly in series; Retry-After on 429/503 is honoured.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
MANIFEST = HERE / "manifest.jsonl"

# Generic UA, no personal info. Wikimedia's UA policy asks for contact info; without it we
# stay in the lowest (10 req/min) tier, which is fine for a sample. See research note.
UA = "FOD-PoC-ImageArchive/0.1 (internal research prototype; python-urllib)"
MAX_WIDTH = 1600
MAX_PIXELS = 40_000_000  # decompression-bomb guard
MIN_WIDTH = 1000

# Query plan: each query is aimed at one or more Angles (hint only; humans tag the real Angle).
COMMONS_QUERIES = [
    ("jet bridge A320 gate", "NOSE,WIDE"),
    ("Boeing 737 at gate jet bridge", "NOSE,WIDE"),
    ("A320 pushback tug", "NOSE"),
    ("belt loader aircraft baggage", "CARGO"),
    ("A320 cargo door loading baggage", "CARGO"),
    ("737 engine ramp ground crew", "ENG-L,ENG-R"),
    ("A320 apron stand ground handling", "WIDE,CARGO"),
    ("aircraft gate night apron 737", "NIGHT"),
    ("A320 apron night", "NIGHT"),
    ("airport apron rain aircraft", "WET"),
    ("incategory:\"Jet bridges\"", "NOSE,WIDE"),
    ("incategory:\"Aircraft at night\"", "NIGHT"),
]
OPENVERSE_QUERIES = [
    ("a320 gate", "NOSE,WIDE"),
    ("737 gate", "NOSE,WIDE"),
    ("belt loader", "CARGO"),
    ("airport apron night", "NIGHT"),
    ("ramp baggage aircraft", "CARGO"),
]

# Licence allowlist: free for commercial use and modification. NC / ND / fair use are rejected.
_OK = [
    (re.compile(r"^cc0"), "CC0"),
    (re.compile(r"^(public domain|pd\b|pd-|pdm)"), "PD"),
    (re.compile(r"^cc[ -]by[ -]sa[ -]?(\d(\.\d)?)?"), "CC BY-SA"),
    (re.compile(r"^cc[ -]by[ -]?(\d(\.\d)?)?$"), "CC BY"),
    (re.compile(r"^cc[ -]by[ -]\d(\.\d)?"), "CC BY"),
]
_BAD = re.compile(r"\b(nc|nd)\b|fair use|non-?commercial|no derivatives", re.I)
# Titles that are almost never ground-level gate/apron scenes.
_SKIP_TITLE = re.compile(r"(cockpit|cabin|interior|seat|in flight|landing|take-?off|takeoff|"
                         r"departing|arriving|approach|climb|model|diagram|map|logo|svg)", re.I)

_last_call: dict[str, float] = {}


def _wait(host: str) -> None:
    gap = 6.5 if "wikimedia" in host or "wikipedia" in host else 2.0
    dt = time.monotonic() - _last_call.get(host, 0.0)
    if dt < gap:
        time.sleep(gap - dt)
    _last_call[host] = time.monotonic()


def fetch(url: str, *, max_bytes: int = 25_000_000, tries: int = 4) -> bytes:
    host = urllib.parse.urlsplit(url).hostname or ""
    for attempt in range(tries):
        _wait(host)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ValueError(f"response too large: {url}")
                return data
        except urllib.error.HTTPError as e:
            if e.code in (429, 503, 502, 504) and attempt < tries - 1:
                wait = int(e.headers.get("Retry-After") or 0) or 10 * (attempt + 1)
                print(f"  {e.code} from {host}, sleeping {wait}s", file=sys.stderr)
                time.sleep(min(wait, 120))
                continue
            raise
    raise RuntimeError("unreachable")


def strip_html(s: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def normalise_licence(short: str) -> str | None:
    s = (short or "").strip().lower()
    if not s or _BAD.search(s):
        return None
    for rx, name in _OK:
        if rx.search(s):
            return name
    return None


# ---------------------------------------------------------------- Commons
_II = {
    "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata|sha1",
        "iiurlwidth": str(MAX_WIDTH),
        "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|ObjectName|ImageDescription|"
                               "DateTimeOriginal|AttributionRequired|Restrictions|UsageTerms",
}
_API = "https://commons.wikimedia.org/w/api.php?"
_BASE = {"action": "query", "format": "json", "formatversion": "2", "maxlag": "5"}


def commons_search(query: str, hint: str, limit: int) -> list[dict]:
    params = {**_BASE, **_II, "generator": "search", "gsrnamespace": "6", "gsrlimit": str(limit),
              "gsrsearch": f"{query} filetype:bitmap"}
    return _commons_records(json.loads(fetch(_API + urllib.parse.urlencode(params))), query, hint)


def commons_category(cat: str, hint: str, limit: int, depth: int = 2) -> list[dict]:
    """All bitmap files in a category tree (breadth-first, `depth` levels of subcats)."""
    out, todo, done = [], [(cat.removeprefix("Category:"), 0)], set()
    while todo and len(out) < limit:
        c, lvl = todo.pop(0)
        if c in done:
            continue
        done.add(c)
        params = {**_BASE, **_II, "generator": "categorymembers", "gcmtitle": f"Category:{c}",
                  "gcmtype": "file|subcat", "gcmlimit": "200"}
        d = json.loads(fetch(_API + urllib.parse.urlencode(params)))
        for p in d.get("query", {}).get("pages", []):
            if p.get("ns") == 14 and lvl < depth:
                todo.append((p["title"].removeprefix("Category:"), lvl + 1))
        recs = _commons_records(d, f"category:{c}", hint)
        out += [r for r in recs if r["title"]]
    return out[:limit]


def _commons_records(d: dict, query: str, hint: str) -> list[dict]:
    out = []
    for p in sorted(d.get("query", {}).get("pages", []), key=lambda p: p.get("index", 0)):
        if p.get("ns") != 6:
            continue
        ii = (p.get("imageinfo") or [{}])[0]
        md = {k: v.get("value") for k, v in (ii.get("extmetadata") or {}).items()}
        out.append({
            "source": "commons",
            "id": f"commons:{p['pageid']}",
            "title": p["title"].removeprefix("File:"),
            "page_url": ii.get("descriptionurl"),
            "author": strip_html(md.get("Artist")),
            "licence_raw": md.get("LicenseShortName") or "",
            "licence_url": md.get("LicenseUrl") or "",
            "restrictions": md.get("Restrictions") or "",
            "date_taken": strip_html(md.get("DateTimeOriginal")),
            "description": strip_html(md.get("ImageDescription"))[:300],
            "width": ii.get("width"), "height": ii.get("height"), "mime": ii.get("mime"),
            "download_url": ii.get("thumburl") or ii.get("url"),
            "original_sha1": ii.get("sha1"),
            "query": query, "angle_hint": hint,
        })
    return out


# ---------------------------------------------------------------- Openverse
def openverse_search(query: str, hint: str, limit: int) -> list[dict]:
    params = {"q": query, "license_type": "commercial,modification", "category": "photograph",
              "page_size": str(min(limit, 20)), "filter_dead": "true", "mature": "false"}
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)
    d = json.loads(fetch(url))
    out = []
    for r in d.get("results", []):
        lic = f"cc {r.get('license', '')} {r.get('license_version') or ''}".strip()
        if r.get("license") in ("cc0", "pdm"):
            lic = r["license"]
        out.append({
            "source": f"openverse/{r.get('source')}",
            "id": f"openverse:{r['id']}",
            "title": r.get("title") or "",
            "page_url": r.get("foreign_landing_url"),
            "author": r.get("creator") or "",
            "licence_raw": lic.replace("cc by", "CC BY").upper() if lic.startswith("cc ") else lic,
            "licence_url": r.get("license_url") or "",
            "restrictions": "",
            "date_taken": "",
            "description": "",
            "width": r.get("width"), "height": r.get("height"), "mime": r.get("filetype"),
            "download_url": r.get("url"),  # original; resized locally to MAX_WIDTH
            "original_sha1": None,
            "openverse_attribution": r.get("attribution"),
            "query": query, "angle_hint": hint,
        })
    return out


# ---------------------------------------------------------------- pipeline
def accept(rec: dict) -> tuple[bool, str]:
    lic = normalise_licence(rec["licence_raw"])
    if not lic:
        return False, f"licence:{rec['licence_raw']!r}"
    rec["licence"] = lic
    rec["sharealike"] = lic == "CC BY-SA"
    rec["attribution_required"] = lic in ("CC BY", "CC BY-SA")
    if rec.get("mime") and not str(rec["mime"]).lower().endswith(("jpeg", "jpg", "png")):
        return False, f"mime:{rec['mime']}"
    if (rec.get("width") or 0) < MIN_WIDTH:
        return False, f"small:{rec.get('width')}"
    if _SKIP_TITLE.search(rec["title"]):
        return False, "title"
    if rec.get("restrictions"):
        rec["note"] = f"non-copyright restrictions: {rec['restrictions']}"
    return True, "ok"


def safe_name(rec: dict) -> str:
    h = hashlib.sha1(rec["id"].encode()).hexdigest()[:10]
    stem = re.sub(r"[^A-Za-z0-9]+", "_", rec["title"].rsplit(".", 1)[0])[:40].strip("_")
    return f"{rec['source'].split('/')[0]}_{h}_{stem}.jpg"


def download(rec: dict) -> None:
    data = fetch(rec["download_url"])
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    with Image.open(io.BytesIO(data)) as im:
        im.verify()
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in ("JPEG", "PNG"):
            raise ValueError(f"unexpected format {im.format}")
        im = im.convert("RGB")
        if im.width > MAX_WIDTH:
            im = im.resize((MAX_WIDTH, round(im.height * MAX_WIDTH / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)  # re-encode: drops embedded metadata/payloads
    RAW.mkdir(exist_ok=True)
    path = RAW / safe_name(rec)
    path.write_bytes(buf.getvalue())
    rec["file"] = f"raw/{path.name}"
    rec["file_sha256"] = hashlib.sha256(buf.getvalue()).hexdigest()
    rec["file_wh"] = [im.width, im.height]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", default="commons,openverse")
    ap.add_argument("--per-query", type=int, default=5, help="accepted images kept per query")
    ap.add_argument("--max", type=int, default=50, help="total images to download")
    ap.add_argument("--search-limit", type=int, default=40, help="results fetched per query")
    ap.add_argument("--dry-run", action="store_true", help="metadata only, no downloads")
    ap.add_argument("--query", action="append", default=[],
                    help="override the built-in query plan: 'text|ANGLE_HINT' (repeatable)")
    ap.add_argument("--category", action="append", default=[],
                    help="Commons category tree to walk: 'Name|ANGLE_HINT' (repeatable; commons only)")
    ap.add_argument("--depth", type=int, default=2, help="subcategory depth for --category")
    ap.add_argument("--shuffle-seed", type=int, default=None,
                    help="randomly sample within each query/category (reproducible) instead of rank order")
    ap.add_argument("--set", default="general", help="label stored in each record, e.g. 'atl'")
    a = ap.parse_args()

    seen: set[str] = set()
    if MANIFEST.exists():  # resumable: keep earlier records, skip their ids
        for line in MANIFEST.read_text().splitlines():
            seen.add(json.loads(line)["id"])
    stats: dict[str, int] = {}
    plan = []
    custom = [tuple((q.split("|", 1) + [""])[:2]) for q in a.query]
    cats = [tuple((c.split("|", 1) + [""])[:2]) for c in a.category]
    if cats:
        plan += [(lambda c, h, n: commons_category(c, h, n, a.depth), c, h) for c, h in cats]
    if "commons" in a.sources and (custom or not cats):
        if custom:
            COMMONS_QUERIES[:] = custom

        plan += [(commons_search, q, h) for q, h in COMMONS_QUERIES]
    if "openverse" in a.sources and (custom or not cats):
        if custom:
            OPENVERSE_QUERIES[:] = custom
        plan += [(openverse_search, q, h) for q, h in OPENVERSE_QUERIES]

    picked: list[dict] = []
    for fn, q, h in plan:
        try:
            recs = fn(q, h, a.search_limit)
        except Exception as e:  # noqa: BLE001 - keep going on a flaky source
            print(f"[{getattr(fn, '__name__', 'fn')}] {q!r}: FAILED {e}", file=sys.stderr)
            stats["query_failed"] = stats.get("query_failed", 0) + 1
            continue
        if a.shuffle_seed is not None:
            random.Random(f"{a.shuffle_seed}:{q}").shuffle(recs)
        kept = 0
        for r in recs:
            stats["seen"] = stats.get("seen", 0) + 1
            if r["id"] in seen:
                continue
            ok, why = accept(r)
            key = why if why.startswith("licence") else why.split(":")[0]  # keep rejected licence names
            stats[key] = stats.get(key, 0) + 1
            if ok and kept < a.per_query:
                seen.add(r["id"])
                picked.append(r)
                kept += 1
        print(f"[{getattr(fn, '__name__', 'fn')}] {q!r}: {len(recs)} results, kept {kept}", file=sys.stderr)

    picked = picked[: a.max]
    target = MANIFEST.with_suffix(".dryrun.jsonl") if a.dry_run else MANIFEST
    with target.open("a") as f:
        for r in picked:
            if not a.dry_run:
                try:
                    download(r)
                except Exception as e:  # noqa: BLE001
                    r["download_error"] = str(e)[:200]
            r["set"] = a.set
            r["retrieved"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {r.get('file') or r.get('download_error')}", file=sys.stderr)
    print(json.dumps({"picked": len(picked), **stats}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
