# fodgate: backend of the gate FOD inspection PoC

Python 3.12, uv project. Runs the Inspection pipeline, keeps the records, enforces the Confirmation rules and
serves the API the dashboard uses. Contract: `app/CONTRACT.md` section 2. Specs: `spec/`. Terms: `GLOSSARY.md`.

## Run

```bash
cd app/backend
uv sync                                         # add --group dino for the optional DINOv2 step (installs torch)
uv run uvicorn fodgate.api:app --port 8000      # API on /api, scene images on /images, dashboard on / if built
uv run pytest                                   # 187 tests, no API calls (Claude is mocked)
uv run python -m fodgate.agent                  # the same server with the always-on agent and a live log (spec/dispatch.md)
```

The API key is read from `<repo>/.env` (`ANTHROPIC_API_KEY=...`) into the server process only. It is never
printed or logged. Without a key the server still starts: Angles that need the reasoning step come back
unusable with reason `analysis_failed`, so nothing reads as clear.

To run against the small fixture scenes instead of `app/data/` (needs `prototypes/spike/data/images`):

```bash
uv run python tests/fixtures/build_fixtures.py
FOD_DATA_DIR=tests/fixtures/data uv run uvicorn fodgate.api:app --port 8000
```

## Settings (environment)

| Variable | Default | Meaning |
|---|---|---|
| `FOD_DECISION_MODEL` | `claude-haiku-5-5` | Model for Candidate decisions. Only `claude-haiku-5-5` or `claude-sonnet-5-5` are accepted; Opus is rejected. |
| `FOD_ESCALATION` | `off` | `sonnet` sends Critical-Angle Candidates Haiku was not highly confident about to Sonnet 5.5, whose decision replaces Haiku's. About $0.012 per escalated Angle. |
| `FOD_DINO_WEIGHTS` | unset | Path to `dinov2_vits14_pretrain.pth`. Enables the DINOv2 patch-anomaly proposer on night / low-contrast Angles. Needs `uv sync --group dino` and a `dinov2-*` source checkout next to the weights (or `FOD_DINO_SRC`). When unset or missing, the step is skipped and `run_metadata.notes` says so. |
| `FOD_LLM_CACHE` | `on` | Cache Claude results by content hash in `app/var/cache/`, so demo replays cost nothing. `off` disables it. |
| `FOD_DATA_DIR` | `app/data` | Scenes, test set, demo timeline and rule set. Missing optional files are tolerated (no timeline means five idle Gates). |
| `FOD_VAR_DIR` | `app/var` | SQLite database (`fod.sqlite`), LLM cache (`cache/`), Finding crops (`crops/`), evaluation output (`eval/`). |
| `FOD_MAX_SPEND_USD` | unset | Optional cap on real (uncached) API spend per process. Once reached, no more calls are made: pipeline, assistant and agent alike. |
| `FOD_AGENT` | `off` | The always-on agent. `code`: the dispatcher routes work by fixed rules and never calls the model. `on`: it also wakes `claude-haiku-5-5` for free text and routing choices. `python -m fodgate.agent` defaults to `on`. |
| `FOD_TIMELINE` | `timeline.json` | Which schedule to play: a file name in `<data>/demo/` or a path. `python -m fodgate.agent` defaults to `timeline-agent.json`. |
| `FOD_ENV_FILE` | `<repo>/.env` | Where the API key is read from. `/dev/null` runs keyless. |

A billing, credit or authentication error from the API stops all further calls for the life of the process.
`GET /api/health` shows whether Claude is available, the models in use and what the process has spent.

## Evaluate

```bash
uv run python -m fodgate.evaluate --dry-run          # local stages only, no API calls: Candidate recall
uv run python -m fodgate.evaluate --limit 2          # first 2 scenes of app/data/testset.json, full pipeline
uv run python -m fodgate.evaluate                    # every scene (about $0.01 to $0.02 per Inspection, uncached)
```

It writes `app/var/eval/results.json` and `app/var/eval/summary.md` (`--out DIR` to change): recall overall and
in Critical zones, false alarms per clean Angle, severity agreement, INCOMPLETE correctness, equipment-staging
hits, cost and latency per Inspection, with mirrored or cropped Angles reported separately, each compared with
targets NF-1 to NF-3. Detector thresholds are the ones fixed on the 22-frame spike set and are not tuned here.

## Layout

| Module | What it does |
|---|---|
| `rules.py` | Loads `fod-rules.json`. Zone tier (Angle, plus the WIDE envelope polygon), object class, severity matrix, rule ID, FOD-R9 equipment staging. Severity is always computed here, never taken from the model. |
| `detect/` | `usability.py` (missing, near-blank, blur, glare, low light), `change.py` (reference-frame change detection), `dino.py` (optional DINOv2), `geometry.py`. |
| `llm.py` | Claude calls with structured output: Candidate decisions, tiled pass, equipment scan. Cache, token and cost accounting, billing stop. |
| `pipeline.py` | One Inspection end to end, and on-demand re-inspection that inherits the other Angles. |
| `report.py` | Open Findings, highest open severity, Verdict precedence (FINDINGS > INCOMPLETE > ALL_CLEAR). |
| `store.py` | SQLite: Turns, Inspections (report JSON), Findings, Confirmations, events. |
| `workflow.py` | Confirmation rules and error codes, Inspection lifecycle, Gate status, "Needs a human" queue. |
| `demo.py` | Scripted timeline player: play, pause, reset, speed. |
| `assistant.py` | Haiku tool-use agent with five read-only tools. |
| `dispatch/` | The always-on agent: `dispatcher.py` (event loop, code-only routing, HOLD alert, timers, Escalation), `agent.py` (Haiku tool loop and its tool list), `commands.py` (slash commands; the only caller of the Confirmation methods), `tasks.py`, `timers.py`, `roster.py`, `models.py`. |
| `agent.py` | `python -m fodgate.agent`: server, dispatcher and the display-only console in one process. |
| `rehearse.py` | `python -m fodgate.rehearse`: plays the agent demo over HTTP as two people and prints a Markdown record. |
| `api.py` | FastAPI app. |
| `evaluate.py` | Scoring CLI. |

## How it behaves (where the contract left room)

- **A re-inspection never drops a Finding.** Only a Confirmation closes one. A Finding seen again in the new
  frame is replaced by the fresh one; a Finding not seen again is carried forward, still open. So a Ramp Agent
  cannot clear a HOLD by pressing re-inspect.
- **HOLD recorded as removed.** `POST .../confirm` with `removed` on an acknowledged HOLD always returns the new
  on-demand report. If the new frame no longer shows the object, the Confirmation is written to the original
  Finding and to the copy the new report carries (with `after_photo_ref`), and the new report's Verdict is
  computed after it. Otherwise the Finding is still open in the new report.
- **Verdict.** The Verdict is the result of the analysis and is not rewritten by later Confirmations; `status`
  and `highest_open_severity` are. Findings already closed when they are carried into an on-demand Inspection
  do not count toward its Verdict. An unusable Angle keeps the Verdict INCOMPLETE even after "checked by eye".
- **Reasoning step failed.** An Angle whose Candidates could not be decided (API error, spend cap, no key) is
  marked unusable with `unusable_reason: "analysis_failed"`, which is not in the schema's list of reasons.
- **Equipment staging (FOD-R9).** At pre-arrival, one extra Haiku call lists GSE, chocks and cones in WIDE; code
  checks each box against the ERL polygon. It is recorded in `llm_calls` with purpose `equipment_scan`.
- **Departure.** At scheduled pushback a Turn is shown as departed only once its latest Inspection is signed
  off. Until then the Gate stays in the queue with 0 minutes to pushback. Block-in is not held back.
- **While inspecting**, a report has `verdict: null` and empty `angles` and `findings`.
- **Extra report fields** beyond the schema and contract: `scene_id`; `findings[].acknowledged` (`{by, at}`),
  `findings[].carried_from_finding_id`, `findings[].rule.also` (FOD-R5 for unidentified objects);
  `run_metadata.est_cost_usd`, `spent_usd`, `notes`, `candidates`, `usability_checks` (which check decided each
  Angle), `analysis_kind`, `reasoning`; `llm_calls[].ms` and `cached`. `est_cost_usd` is the uncached price, so a
  replay from cache still shows what the Inspection costs.
- **Crops** are served under `/images/_crops/<inspection_id>/...` so the dashboard's `/images` proxy covers them.
- **Extra error codes:** `not_found` (404), `invalid_request` (422), `already_confirmed`, `already_signed_off`,
  `angle_usable`, `inspection_in_progress` (409), `assistant_unavailable` (503).
