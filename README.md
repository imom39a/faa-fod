# Gate FOD Inspection PoC

A proof of concept that checks an aircraft gate for **foreign object debris (FOD)** from camera images, before an aircraft arrives and before it pushes back. It flags each item with a photo crop, a severity and the rule behind it, and a person always confirms before a gate is shown as clear.

The example site is Delta at ATL Concourse T, Gates T1, T2, T4, T5 and T8. No real airport data is used: the images are openly licensed photographs with debris pasted in at known positions.

## Quick start

You need [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 20 or newer. uv installs Python 3.12 for you.

```bash
git clone https://github.com/imom39a/faa-fod.git
cd faa-fod
./setup.sh        # installs dependencies and builds the dashboard (a few minutes)
./run.sh          # starts the app
```

Open http://localhost:8000 and press **Play**.

**API key.** The scripted demo replays saved Claude results from `app/var/cache/`, so it normally runs without a key. If a saved result doesn't match on your machine, that Angle shows as unusable with reason `analysis_failed`; add a key to fix it. You need a key for anything new: the assistant panel, re-running the scoring, or inspecting new images. Put it in `.env` (created by `setup.sh`):

```
ANTHROPIC_API_KEY=sk-ant-...
```

`run.sh` caps API spend at $1.00 per run. Change it with `FOD_MAX_SPEND_USD=5 ./run.sh`. A full demo run with no saved results costs about $0.10.

## Using the demo

The app replays a scripted 6 minutes at five gates. The schedule and the photos are scripted. The analysis, the rules and the human workflow are real.

**Top bar**
- **Play / Pause / Reset:** run, stop or restart the scripted schedule. Reset wipes the records.
- **1x to 10x:** how fast the schedule's clock runs.
- **Ramp Agent / Ramp Lead:** who you are acting as. Only a Ramp Lead can clear a HOLD.

**Gate tiles** show each gate's flight, status and the system's result:
- **ALL CLEAR:** nothing found.
- **FINDINGS:** debris or misplaced equipment found. Severity is **HOLD** (aircraft must not move), **REMOVE** (clear before departure) or **ADVISORY** (log it).
- **INCOMPLETE:** a camera view was unusable, so the system will not call the stand clear.

**"Needs a human" queue** lists every gate waiting on a person: HOLDs first, then whichever gate is closest to pushback.

**A walkthrough**
1. Press Play at 2x.
2. When a HOLD appears in the queue, click it. You see six photos with a box on the object and the rule it breaks.
3. As Ramp Agent, try **Acknowledge**. You are refused.
4. Switch to Ramp Lead. Press **Acknowledge**, then **Removed**. The system re-photographs that view; the HOLD clears only if the new photo is clean.
5. Press **Sign off Inspection**. The tile turns to "Confirmed clear".

The demo stages five moments: a small bolt in an engine intake zone (HOLD), equipment parked inside the restraint line before arrival (REMOVE), glare on an engine view (INCOMPLETE), the Ramp Lead-only HOLD clearance, and debris beyond the stand routed to ramp control.

## How it works

1. **Local detection.** For each of six camera views (Angles), the current image is compared with a clean reference image of the same view. Anything that changed becomes a Candidate. This runs on the laptop and costs nothing.
2. **Decision.** Claude Haiku looks at each Candidate crop beside the reference crop and decides whether it is debris and what kind. A second Haiku pass covers the three most critical views as a backup.
3. **Rules in code.** Severity, the rule cited and the overall result are computed by ordinary code from `app/data/rules/fod-rules.json`, so the same images always give the same result.
4. **Human Confirmation.** Nothing clears without a person. Every action is recorded with who and when.

## Results

On the 30-Inspection test set (`app/EVAL-RESULTS.md`):

| Target | Bound | Measured |
|---|---|---|
| Cost per Inspection | at most $0.05 | $0.008 |
| Time per Inspection | at most 20 s | 8.7 s |
| Recall overall | at least 90% | 100% (42 of 42) |
| Recall in Critical zones | at least 95% | 100% (23 of 23) |
| False alarms per clean Angle | at most 0.5 | 0.10 |

**Limits to state when showing this**
- Debris is pasted into real photos, and reference images are simulated with nothing moving between frames. Expect lower numbers on real camera footage.
- The photos are stand-ins. None is of ATL Concourse T, and within one demo Turn the before-arrival and before-departure photos are different airports.
- Most views are crops of wider photos; left-engine views are mirrored right-engine photos.
- The system takes snapshots at two points in a Turn. It does not watch continuously.
- No FAA rule prescribes a gate FOD workflow. The rules cite FAA advisory text and IATA practice, and say which is which.

## Repository layout

| Path | What it is |
|---|---|
| `app/backend/` | FastAPI app: detection pipeline, Confirmation rules, demo player, assistant, scoring |
| `app/frontend/` | React dashboard |
| `app/data/` | Test set (30 Inspections), 5 demo scenes, demo schedule, rule set, photo attribution |
| `app/var/cache/` | Saved Claude results, so replays are free |
| `app/tools/` | Scripts that rebuild `app/data/` from Wikimedia Commons |
| `app/CONTRACT.md` | Data layout and API shared by backend, dashboard and data |
| `spec/` | Approved requirements, rules, report schema, dashboard UX, test data plan, architecture |
| `research/` | Sourced research: FAA guidance, turnaround workflow, ATL site, Delta and vendors, image sources |
| `issues/` | The decision record: one file per decision, indexed by `0001-map-...md` |
| `prototypes/` | Throwaway experiments that informed the decisions. Not part of the app. |
| `GLOSSARY.md` | The project's terms. Use them exactly. |

## Development

```bash
# Backend (API on :8000)
cd app/backend
uv run uvicorn fodgate.api:app --port 8000 --reload
uv run pytest                                  # 142 tests, Claude mocked, no API calls

# Dashboard with live reload (on :5173, proxies /api and /images to :8000)
cd app/frontend
npm run dev
VITE_MOCK=1 npm run dev                        # no backend needed: built-in mock
npm test                                       # 39 tests
npm run build                                  # what ./run.sh serves

# Scoring against the targets
cd app/backend
uv run python -m fodgate.evaluate --dry-run    # local detection only, no API calls
uv run python -m fodgate.evaluate              # full run, about $0.25 without saved results
```

Backend settings (environment variables) are listed in `app/backend/README.md`. Rebuilding the test images is described in `app/tools/README.md`; it takes about 30 minutes because Wikimedia limits anonymous downloads.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `./run.sh` says the dashboard is not built | Run `./setup.sh` |
| Dashboard shows "Not connected" | The backend is not running, or is on another port. Start `./run.sh` |
| Port 8000 is in use | `PORT=8010 ./run.sh` |
| An Angle shows unusable, reason `analysis_failed` | No saved result matched and no API key is set (or the spend cap or credit ran out). Add `ANTHROPIC_API_KEY` to `.env` and press Reset |
| Gates stay on "Pushback due" at the end | Expected. A Turn only departs after a person signs off its last Inspection |
| The assistant panel returns an error | It needs an API key; its answers are not saved |

## Image credits

Every photograph is openly licensed (mostly CC BY-SA, some CC BY, CC0 and public domain). Sources, authors and licences are in `app/data/ATTRIBUTION.md` and shown under each image in the dashboard. Debris cut-outs come from the FOD-A dataset (MIT licence). If you share images from this repository, the attribution must go with them.
