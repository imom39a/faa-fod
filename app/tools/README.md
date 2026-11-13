# Test-data tools

Builds `app/data/` (scenes, `testset.json`, `demo/timeline.json`, `ATTRIBUTION.md`) from the manifests in `manifest/`. No Anthropic API calls. Contract: `app/CONTRACT.md` section 1; plan: `spec/test-data-plan.md`.

## Rebuild

```
cd app/tools
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python pillow numpy opencv-python-headless
.venv/bin/python -I fetch_sources.py ../var/downloads          # Commons originals + FOD-A examples -> app/var/downloads/ (cached)
.venv/bin/python -I build_scenes.py ../var/downloads ../data    # scenes, testset.json, demo/timeline.json, ATTRIBUTION.md
.venv/bin/python -I validate_data.py ../data                    # contract + plan checks, summary table, exit 1 on error
```

`-I` because the scripts read downloaded (untrusted) files; downloads live only under `app/var/downloads/` and are only decoded with Pillow. The build is deterministic: seeds derive from the scene id and Angle, and `manifest/sources.lock.json` pins every photo by URL and sha256.

A cold `fetch_sources.py` run is slow. Wikimedia serves full-size originals to a generic User-Agent at about 10 files per 10 minutes (HTTP 429 with `Retry-After: 600` beyond that), so the script paces originals 65 s apart and honours `Retry-After`. Decision for the user (see `research/gate-image-archives.md` section 2): a User-Agent with a team contact would lift this, but the brief says anonymous.

## Files

| File | What it does |
|---|---|
| `commons.py` | Commons API client: search, metadata, cached downloads, licence allowlist (CC0, PD, CC BY, CC BY-SA), pacing |
| `fetch_sources.py` | Downloads everything in `manifest/sources.json`, writes `manifest/sources.lock.json` and `foda.lock.json` |
| `frames.py` | Angle crop, reference drift (`make_reference`, mild and hard), `recapture` for after frames, glare / blur / low-light, no-op control |
| `debris.py` | Debris cut-outs (FOD-A cells and pictures, plain-background Commons photos) and compositing |
| `build_scenes.py` | Builds every scene in `manifest/scenes.json`; writes `scene.json` (contract) and `build.json` (provenance) |
| `attribution.py` | Writes `ATTRIBUTION.md` from the built scenes |
| `validate_data.py` | Validator |
| `find_candidates.py`, `preview.py` | Aids for the manual passes: contact sheets of search results; gridded previews for choosing crops, polygons and debris positions; scene sheets with ground-truth boxes |

## Manifests

- `sources.json`: key → Commons file title. `"thumb": 960` fetches the 960 px rendition instead of the original (small debris-object photos).
- `stands.json`: one entry per stand (a set of photos of one aircraft at one stand, or one empty stand): `light`, the six Angle crops (`src`, 16:9 `box` in source pixels, `mirror`), and the WIDE polygons `envelope` and `erl` in source pixels (`regions_src`), drawn by eye from painted markings where visible.
- `objects.json`: debris cut-outs with category, object class and label; GSE cut-outs (polygon in a photo).
- `scenes.json`: every scene. `scoring: true` puts it in `testset.json`. Debris placements are source pixels (`sx`, `sy`) or frame fractions (`x`, `y`); `long_px` is in output pixels. WIDE zone tier (general or outside boundary) is computed from the envelope polygon.
- `timeline.json`: the demo script, copied to `app/data/demo/timeline.json`.

## Rules the build follows

- Output is 16:9, 3840×2160 when the crop is at least 3072 source pixels wide, otherwise the crop size × 1.25 at most (never upscaled further). The real size is in `scene.json`.
- `derived`: `mirror` if flipped left-to-right, `native` if the crop keeps at least 80% of the photo, else `crop`.
- Reference = the clean crop with simulated drift (mild by default; `ref_mode: hard` on a few scenes). After frame = a clean re-capture, written for every Angle that has ground truth or is unusable.
- Debris is composited per Angle. An item placed in one Angle is not drawn into the other Angles that overlap it (a known limit of the composited set).
