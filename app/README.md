# Gate FOD Inspection PoC

Example deployment: Delta at ATL Concourse T, Gates T1, T2, T4, T5, T8. Specs are in `../spec/`; terms in `../GLOSSARY.md`.

## Run the demo

```bash
# once
cd app/frontend && npm install && npm run build
cd ../backend && uv sync            # add --group dino for the optional DINOv2 step

# each time
cd app/backend && uv run uvicorn fodgate.api:app --port 8000
# open http://localhost:8000 and press Play
```

The Anthropic API key is read from `../.env` (`ANTHROPIC_API_KEY=...`). Claude results are cached in `app/var/cache/`, so replaying the demo costs nothing once each scene has run. Reset clears the records and keeps the cache. Set `FOD_MAX_SPEND_USD` to cap spend per run.

## Parts

| Folder | What it is |
|---|---|
| `backend/` | Pipeline, Confirmation rules, demo player, assistant, scoring (`python -m fodgate.evaluate`). See its README. |
| `frontend/` | React dashboard. `VITE_MOCK=1 npm run dev` runs it without the backend. |
| `data/` | 30 scoring Inspections, 5 demo scenes, the demo timeline, the rule set, photo attribution. |
| `tools/` | Scripts that rebuild `data/` from Wikimedia Commons. |
| `CONTRACT.md` | Data layout and API shared by the three parts. |
| `EVAL-RESULTS.md` | Latest scoring run against the targets. |

## Tests

```bash
cd app/backend && uv run pytest        # 142 tests, Claude mocked
cd app/frontend && npm test            # 39 tests
```

## Limits to state when showing this

- Debris is pasted into real photos, and reference frames are simulated with nothing moving between frames.
- The photos are stand-ins: none is of ATL Concourse T. Within a demo Turn the pre-arrival and pre-departure photos are different airports.
- Most Angles are crops of wider photos; left-engine views are mirrored right-engine photos.
- The system takes snapshots at two points in a Turn. It does not watch continuously.
