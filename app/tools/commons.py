"""Wikimedia Commons client for the test-data build: search, metadata, cached downloads.

Anonymous, generic User-Agent (no personal or project details). Requests are made in series and
paced for the anonymous tier (10 requests/min on the API); HTTP 429 honours Retry-After.
Downloads are untrusted data: they are written only under app/var/downloads/ and are only ever
decoded with Pillow by scripts run with `python -I`.
"""
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "gate-image-fetch/0.1 (python-urllib)"
API = "https://commons.wikimedia.org/w/api.php"
API_GAP_S = 6.5      # anonymous tier: 10 req/min
FILE_GAP_S = 65.0    # full-size originals from upload.wikimedia.org: measured about 10 files per 10 minutes for a
                     # generic User-Agent before HTTP 429 with Retry-After: 600. Thumbnails tolerate a faster pace.
THUMB_GAP_S = 1.5
ALLOWED = re.compile(r"^(cc0|public domain|pd|cc[- ]by(-sa)?[- ][0-9.]+)", re.I)
_last = {"api": 0.0, "file": 0.0, "thumb": 0.0}


def _get(url, kind, timeout=300):
    gap = {"api": API_GAP_S, "file": FILE_GAP_S, "thumb": THUMB_GAP_S}[kind]
    err = None
    for attempt in range(8):
        wait = _last[kind] + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[kind] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            err = e
            if e.code in (429, 503):
                ra = e.headers.get("Retry-After")
                wait_s = min(1200.0, float(ra)) + 5 if ra and ra.isdigit() else 30 + 30 * attempt
                print(f"  HTTP {e.code}, waiting {wait_s:.0f}s (Retry-After honoured)", flush=True)
                time.sleep(wait_s)
                _last[kind] = time.time()
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            err = e
            time.sleep(10 + 10 * attempt)
    raise err


def api(**params):
    params.update(format="json", formatversion="2", maxlag="5")
    return json.loads(_get(API + "?" + urllib.parse.urlencode(params), "api"))


def _strip(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()


def _record(pg, thumb_width=None):
    ii = (pg.get("imageinfo") or [{}])[0]
    em = ii.get("extmetadata") or {}
    v = lambda k: (em.get(k) or {}).get("value", "")
    title = pg["title"][5:] if pg["title"].startswith("File:") else pg["title"]
    return {
        "title": title,
        "url": "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(title.replace(" ", "_"), safe="()_-.,'"),
        "author": _strip(v("Artist")) or _strip(v("Credit")) or "unknown",
        "licence": _strip(v("LicenseShortName")),
        "licence_url": v("LicenseUrl"),
        "width": ii.get("width"), "height": ii.get("height"), "mime": ii.get("mime"),
        "download_url": ii.get("url"), "thumb_url": ii.get("thumburl"),
        "sha1": ii.get("sha1"), "date": _strip(v("DateTimeOriginal")),
    }


IIPROP = "url|size|mime|sha1|extmetadata"


def search(query, limit=50, thumb_width=330, offset=0):
    """Full-text search in the File namespace. One API request."""
    d = api(action="query", generator="search", gsrsearch=f"filetype:bitmap {query}", gsrnamespace="6",
            gsrlimit=str(limit), gsroffset=str(offset), prop="imageinfo", iiprop=IIPROP,
            iiurlwidth=str(thumb_width), iiextmetadatafilter="Artist|Credit|LicenseShortName|LicenseUrl|DateTimeOriginal")
    pages = sorted((d.get("query") or {}).get("pages", []), key=lambda p: p.get("index", 0))
    return [_record(p) for p in pages if p.get("imageinfo")]


def category(cat, limit=200, thumb_width=330):
    d = api(action="query", generator="categorymembers", gcmtitle="Category:" + cat, gcmtype="file",
            gcmlimit=str(limit), prop="imageinfo", iiprop=IIPROP, iiurlwidth=str(thumb_width),
            iiextmetadatafilter="Artist|Credit|LicenseShortName|LicenseUrl|DateTimeOriginal")
    return [_record(p) for p in (d.get("query") or {}).get("pages", []) if p.get("imageinfo")]


def info(titles, thumb_width=3840):
    """Metadata for exact file titles (without 'File:'), up to 50 per request."""
    out = {}
    for i in range(0, len(titles), 50):
        d = api(action="query", titles="|".join("File:" + t for t in titles[i:i + 50]), prop="imageinfo",
                iiprop=IIPROP, iiurlwidth=str(thumb_width),
                iiextmetadatafilter="Artist|Credit|LicenseShortName|LicenseUrl|DateTimeOriginal")
        norm = {n["to"]: n["from"] for n in (d["query"].get("normalized") or [])}
        for p in d["query"]["pages"]:
            if p.get("imageinfo"):
                r = _record(p)
                asked = norm.get(p["title"], p["title"])[5:]
                out[asked] = r
    return out


def licence_ok(lic):
    return bool(ALLOWED.match(lic or "")) and "nc" not in (lic or "").lower().split("-") and "nd" not in (lic or "").lower().split("-")


def safe_name(title):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title)


def fetch(url, dest: Path, kind="file"):
    """Download once into the cache; returns (path, sha256). kind: "file" (original) or "thumb"."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or dest.stat().st_size == 0:
        data = _get(url, kind)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.rename(dest)
    return dest, hashlib.sha256(dest.read_bytes()).hexdigest()
