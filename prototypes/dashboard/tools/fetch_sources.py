"""PROTOTYPE - re-downloads the original Commons photos used by build_assets.py.

Usage: ../spike/.venv/bin/python -I tools/fetch_sources.py assets/raw/orig
Downloads are untrusted data: they go into their own directory and are only ever read by
build_assets.py (run with -I, paths as arguments). Polite generic User-Agent, paced requests.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "fod-dashboard-prototype/0.1 (research prototype)"
TITLES = [
    "File:Pelita Air Airbus A320 PK-PWL Jakarta 2025 (01).jpg",
    "File:Pelita Air Airbus A320 PK-PWL Jakarta 2025 (02).jpg",
    "File:Pelita Air Airbus A320 PK-PWL Jakarta 2025 (03).jpg",
    "File:Thai Airbus A320 HS-TXS Denpasar 2025 (01).jpg",
    "File:Thai Airbus A320 HS-TXS Denpasar 2025 (02).jpg",
    "File:Thai Airbus A320 HS-TXS Denpasar 2025 (03).jpg",
    "File:Garuda Boeing 737 PK-GFV Jakarta 2023 (01).jpg",
    "File:Engine of Boeing 737-800 EI-DLY.JPG",
]


def get(url):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r:
                return r.read()
        except Exception as e:  # 429s are common on upload.wikimedia.org: back off
            err = e
            time.sleep(15 + 20 * i)
    raise err


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    q = urllib.parse.urlencode({"action": "query", "titles": "|".join(TITLES), "prop": "imageinfo",
                                "iiprop": "url", "format": "json", "formatversion": "2"})
    pages = json.loads(get("https://commons.wikimedia.org/w/api.php?" + q))["query"]["pages"]
    for pg in pages:
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", pg["title"][5:])
        if (out / name).exists():
            continue
        (out / name).write_bytes(get(pg["imageinfo"][0]["url"]))
        print("fetched", name)
        time.sleep(20)


if __name__ == "__main__":
    main()
