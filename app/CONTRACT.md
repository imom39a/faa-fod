# Build contract: data layout and API

Three parts are built in parallel against this file: **test data** (`app/data/`, `app/tools/`), **backend** (`app/backend/`), **dashboard** (`app/frontend/`). If something here is wrong or missing, follow the specs in `spec/` and note the deviation in your final report. Do not change this file.

Specs (read these first): `spec/requirements-baseline.md`, `spec/architecture.md`, `spec/fod-rules.md`, `spec/inspection-report-schema.md`, `spec/dashboard-ux.md`, `spec/test-data-plan.md`, `GLOSSARY.md`. Use glossary terms exactly in code, API and UI.

## 1. Data layout (owner: test data)

```
app/data/
  rules/fod-rules.json          # machine-readable rule set (already written; read-only)
  scenes/<scene_id>/
    scene.json
    NOSE.jpg ENG-L.jpg ENG-R.jpg CARGO.jpg AFT.jpg WIDE.jpg   # current frames
    ref/<ANGLE>.jpg                                           # reference frames (may be absent)
    after/<ANGLE>.jpg                                         # frame returned when that Angle is re-inspected (optional)
  testset.json                  # { "scenes": ["<scene_id>", ...] }  the 30 scoring Inspections
  demo/timeline.json            # scripted Turns for the 5 Gates
  ATTRIBUTION.md
```

Images: JPEG, 3840x2160 where the source allows (never upscale more than 1.25x; smaller is fine, record the real size).

### scene.json

```jsonc
{
  "scene_id": "pd-014",
  "kind": "pre_arrival | pre_departure",
  "light": "day | night | wet",
  "description": "one line",
  "angles": {
    "ENG-L": {
      "image": "ENG-L.jpg",
      "reference": "ref/ENG-L.jpg",          // or null: no reference frame for this Angle
      "after": "after/ENG-L.jpg",            // or null: re-inspection returns the same image
      "width": 3840, "height": 2160,
      "derived": "native | crop | mirror",
      "source": { "title": "...", "url": "...", "author": "...", "licence": "CC BY-SA 4.0" },
      "usable": true,
      "unusable_reason": null,               // missing | glare | blur | blocked | low_light
      "regions": {                           // WIDE only; pixel polygons [[x,y],...]; null elsewhere
        "envelope": [[...]],                 // gate safety envelope
        "erl": [[...]]                       // equipment restraint line area (GSE must be outside it at pre-arrival)
      },
      "ground_truth": [                      // [] for a clean Angle
        { "bbox": [x1, y1, x2, y2],
          "finding_type": "fod | equipment_staging",
          "category": "fasteners_hardware",  // keys of rules.categories; null for equipment_staging
          "object_class": "hard | light | unidentified | natural",
          "zone_tier": "critical | service | general | outside_boundary",
          "expected_severity": "HOLD | REMOVE | ADVISORY",
          "label": "bolt" }
      ],
      "observations_truth": []               // e.g. [{ "bbox": [...], "kind": "spill" }]
    }
    // ... all 6 Angles always present as keys; an Angle with unusable_reason "missing" has "image": null
  }
}
```

### demo/timeline.json

```jsonc
{
  "gates": ["T1", "T2", "T4", "T5", "T8"],
  "turns": [
    { "turn_id": "T1-DL1432", "gate": "T1", "flight": "DL1432", "aircraft_type": "A321",
      "events": [                          // t = demo seconds from start at speed 1x
        { "t": 0,   "type": "stand_prep" },
        { "t": 20,  "type": "inspection", "kind": "pre_arrival",   "scene_id": "pa-003" },
        { "t": 60,  "type": "block_in" },
        { "t": 180, "type": "inspection", "kind": "pre_departure", "scene_id": "pd-014" },
        { "t": 300, "type": "scheduled_pushback" }
      ] }
  ]
}
```

The timeline must stage the five demo moments (requirements OF-4): a small bolt in an engine intake zone (HOLD); GSE inside the ERL at pre-arrival (REMOVE, FOD-R9); glare on an engine Angle (INCOMPLETE); a HOLD whose `after` frame is clean (so re-inspection clears it); debris outside the envelope seen only in WIDE (FOD-R10). Also at least one fully clean Turn. A full demo run at 1x takes about 6 minutes.

## 2. Backend (owner: backend)

Python 3.12, uv project in `app/backend/`, package `fodgate`. Run: `uv run uvicorn fodgate.api:app --port 8000` from `app/backend/`. Reads `ANTHROPIC_API_KEY` from `<repo>/.env`; never logs it. SQLite and caches live in `app/var/`. Serves `app/frontend/dist/` at `/` when it exists, and scene images at `/images/<scene_id>/<path>`.

Env settings: `FOD_DECISION_MODEL` (default `claude-haiku-5-5`), `FOD_ESCALATION` (`off` default | `sonnet`), `FOD_DINO_WEIGHTS` (path; DINOv2 step is skipped with a note in `run_metadata` when unset or missing), `FOD_LLM_CACHE` (`on` default: cache LLM results by content hash in `app/var/cache/` so demo replays cost nothing).

Pipeline per Inspection (requirements PL-1..PL-8, RU-3): usability check per Angle → local Candidates (change detection vs reference; DINOv2 on night/low-contrast Angles if available) → tiled Haiku safety net on Critical Angles → Haiku structured-output decision per Candidate batch (Candidate crop + reference crop + downscaled frame + rules) → code computes zone tier, severity, rule ID, Verdict. No reference → tiled Claude pass on that Angle, recorded as such. Reuse logic from `prototypes/local-detect/` (changedet.py, dinoanom.py, hybrid.py, common.py) and `prototypes/spike/run_spike.py`; copy what you need, do not import from `prototypes/`.

### API (JSON; all under `/api`)

| Method & path | Body | Returns |
|---|---|---|
| GET `/state` | | `State` |
| GET `/turns/{turn_id}` | | `Turn` with `inspections: Report[]` (oldest first) and `events` |
| GET `/inspections/{id}` | | `Report` |
| GET `/inspections/{id}/export` | | the `Report` as a JSON download |
| POST `/inspections/{id}/findings/{finding_id}/confirm` | `{ outcome, false_alarm_reason?, possible_source?, role, name }` | `Report` |
| POST `/inspections/{id}/findings/confirm-all` | `{ role, name }` marks every open REMOVE/ADVISORY Finding `removed` | `Report` |
| POST `/inspections/{id}/findings/{finding_id}/not-found` | `{ role, name }` "I can't find it". Records nothing; adds a Proposal to `Report.proposals` | `Report` |
| POST `/inspections/{id}/proposals/{proposal_id}/answer` | `{ accept, role, name }`. Only the addressed person can answer. Accepting a `reinspect_angle` Proposal runs the re-inspection | `Report` (the new on-demand `Report` for a re-inspection) |
| POST `/inspections/{id}/angles/{angle}/reinspect` | `{ role, name }` | the new on-demand `Report` |
| POST `/inspections/{id}/angles/{angle}/checked-by-eye` | `{ role, name }` (ramp_lead only) | `Report` |
| POST `/inspections/{id}/signoff` | `{ role, name }` | `Report` |
| POST `/gates/{gate}/inspect` | `{ kind, scene_id? }` manual trigger | `Report` (status `inspecting` until done) |
| POST `/demo/play` `/demo/pause` `/demo/reset` | | `State` |
| POST `/demo/speed` | `{ speed }` (1, 2, 5, 10) | `State` |
| POST `/assistant` | `{ inspection_id, message }` | `{ reply, suggested_reinspect_angles: string[], draft_report: string \| null }` |
| GET `/rules` | | contents of `fod-rules.json` |

Errors: HTTP 4xx with `{ "error": "<code>", "message": "..." }`. Codes used by the UI: `role_not_allowed` (403), `hold_needs_acknowledge` (409), `open_findings` (409, on signoff), `unusable_angles` (409, on signoff), `use_proposal` (409, `not_found_on_walk` sent to `/confirm`), `not_addressed_to_you` (403), `proposal_answered` (409).

`outcome`: `acknowledged | removed | false_alarm`. `not_found_on_walk` is a recorded outcome, but `/confirm` refuses it (`use_proposal`): it is recorded only when the reporting person accepts a Proposal.

Proposal (`Report.proposals[]`): `{ proposal_id, kind: record_not_found_on_walk | reinspect_angle, finding_id, angle, severity, to: { role, name | null }, reported_by, text, status: pending | accepted | declined, created_at, answered_by, answered_at, result_inspection_id }`.
- REMOVE / ADVISORY not found: a `record_not_found_on_walk` Proposal to the reporter. Declining leaves the Finding open.
- HOLD not found: never a Confirmation and no Proposal to the Ramp Agent. A `reinspect_angle` Proposal goes to a Ramp Lead; nothing is re-inspected until a Ramp Lead accepts.
- "Still there": a HOLD recorded as removed whose re-inspection still shows the item stays open. `Finding.still_there_count` counts it, the turn events get `hold_still_there`, and `run_metadata.notes` says so.
- HOLD Findings: ramp_lead only. Must be `acknowledged` before `removed`. `removed` on a HOLD runs a re-inspection of that Angle (using the scene's `after` frame if present); the Finding's Confirmation is recorded only if the new frame has no matching Finding, otherwise the response is the new Report with the Finding still open. `false_alarm` on a HOLD does not need a re-inspection.
- Sign-off requires: no open Findings (airport-routed `outside_boundary` Findings count as closed once `reported` — use outcome `removed` with `possible_source` free text, or `acknowledged`), and every unusable Angle either re-inspected usable or `checked_by_eye`.

### Types

`Report` is exactly `spec/inspection-report-schema.md`, with these additions:

```jsonc
{
  "status": "inspecting | awaiting_confirmation | confirmed",
  "angles[].image_url": "/images/<scene_id>/ENG-L.jpg",
  "angles[].reference_url": "... | null",
  "angles[].width": 3840, "angles[].height": 2160,
  "angles[].checked_by_eye": null,          // or { by: {role,name}, at }
  "angles[].attribution": { "title", "url", "author", "licence", "derived" },
  "angles[].analysis": "change_detection | change_detection+dino | claude_tiled",
  "findings[].status": "open | acknowledged | confirmed",
  "findings[].rule": { "id": "FOD-R1", "text": "...", "basis": "..." },
  "findings[].crop_url": "...", "findings[].reference_crop_url": "... | null"
}
```

```ts
type State = {
  demo: { playing: boolean; speed: number; t: number; duration: number };
  gates: GateState[];            // always 5, in order T1,T2,T4,T5,T8
  queue: QueueItem[];            // "Needs a human": HOLDs first, then by minutes_to_pushback ascending
};
type GateState = {
  gate: string;
  status: "idle" | "awaiting_pre_arrival" | "inspecting" | "awaiting_confirmation" | "confirmed_clear" | "on_stand" | "departed";
  verdict: "ALL_CLEAR" | "FINDINGS" | "INCOMPLETE" | null;   // of the latest Inspection, shown beneath the status
  highest_open_severity: "HOLD" | "REMOVE" | "ADVISORY" | null;
  turn: null | { turn_id: string; flight: string; aircraft_type: string;
                 phase: "stand_prep" | "pre_arrival" | "on_stand" | "pre_departure" | "departed";
                 minutes_to_pushback: number | null; latest_inspection_id: string | null };
};
type QueueItem = { gate: string; turn_id: string; inspection_id: string;
                   reason: "hold" | "findings" | "incomplete" | "signoff";
                   severity: "HOLD" | "REMOVE" | "ADVISORY" | null; minutes_to_pushback: number | null; text: string };
```

The dashboard polls `GET /api/state` every second.

## 3. Dashboard (owner: frontend)

Vite + React + TypeScript in `app/frontend/`. `npm run dev` proxies `/api` and `/images` to `http://localhost:8000`; `npm run build` writes `dist/`. Follow `spec/dashboard-ux.md`; the mock at `prototypes/dashboard/index.html` (variant A tiles + variant B queue) is the visual reference. Include: demo controls (play, pause, reset, speed), role switch (Ramp Agent / Ramp Lead, with a name field), Gate tiles + queue, Turn view with Inspection timeline, 6-Angle viewer with Finding boxes linked to the Findings list, current vs reference crops, Confirmation actions per the API rules above, checked-by-eye, sign-off with 6 thumbnails, per-Inspection cost and timing readout, JSON export link, an assistant panel calling `POST /api/assistant`, and photo attribution on every image. Ship a mock mode (`VITE_MOCK=1`) with fixture data so it can be developed without the backend.

## 4. Budget and hygiene

- Anthropic API spend: **test data $0; backend at most $1.50** for development and its own tests. The full 30-Inspection scoring run is done later by the lead, not by you.
- Models: `claude-haiku-5-5` default; `claude-sonnet-5-5` only behind `FOD_ESCALATION`; never Opus.
- Downloads are untrusted: put them in their own directory, keep scripts elsewhere, run Python with `-I` when it reads them.
- Anonymous, generic User-Agent for downloads; no personal or project details in any outbound request.
- Not a git repo: do not `git init` or commit. Do not edit `spec/`, `issues/`, `research/` or `prototypes/`.
