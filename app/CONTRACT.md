# Build contract: data layout and API

Three parts are built in parallel against this file: **test data** (`app/data/`, `app/tools/`), **backend** (`app/backend/`), **dashboard** (`app/frontend/`). If something here is wrong or missing, follow the specs in `spec/` and note the deviation in your final report. The parallel build this file was frozen for is finished: change it together with the code it describes (`AGENTS.md`).

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
  demo/timeline-agent.json      # short schedule for the always-on agent demo (same format; pick with FOD_TIMELINE)
  roster/roster.json            # demo Roster: { "people": [{ person_id, name, role, gates[], pin, shift }] }
  roster/escalation.json        # Escalation ladder thresholds, in demo seconds
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

Env settings: `FOD_DECISION_MODEL` (default `claude-haiku-5-5`), `FOD_ESCALATION` (`off` default | `sonnet`), `FOD_DINO_WEIGHTS` (path; DINOv2 step is skipped with a note in `run_metadata` when unset or missing), `FOD_LLM_CACHE` (`on` default: cache LLM results by content hash in `app/var/cache/` so demo replays cost nothing), `FOD_AGENT` (`off` default | `code` | `on`: the always-on agent, section 5), `FOD_TIMELINE` (a file name in `app/data/demo/` or a path; default `timeline.json`), `FOD_MAX_SPEND_USD` (cap on real API spend per process; applies to the pipeline, the assistant and the agent).

Pipeline per Inspection (requirements PL-1..PL-8, RU-3): usability check per Angle → local Candidates (change detection vs reference; DINOv2 on night/low-contrast Angles if available) → tiled Haiku safety net on Critical Angles → Haiku structured-output decision per Candidate batch (Candidate crop + reference crop + downscaled frame + rules) → code computes zone tier, severity, rule ID, Verdict. No reference → tiled Claude pass on that Angle, recorded as such. Reuse logic from `prototypes/local-detect/` (changedet.py, dinoanom.py, hybrid.py, common.py) and `prototypes/spike/run_spike.py`; copy what you need, do not import from `prototypes/`.

### API (JSON; all under `/api`)

| Method & path | Body | Returns |
|---|---|---|
| GET `/state` | | `State` |
| GET `/turns/{turn_id}` | | `Turn` with `inspections: Report[]` (oldest first) and `events` |
| GET `/turns/{turn_id}/record` | | `TurnRecord` (see "Turn record" below). Read-only; 404 `not_found` for an unknown Turn |
| GET `/inspections/{id}` | | `Report` |
| GET `/inspections/{id}/export` | | the `Report` as a JSON download |
| POST `/inspections/{id}/findings/{finding_id}/confirm` | `{ outcome, false_alarm_reason?, possible_source?, role, name }` | `Report` |
| POST `/inspections/{id}/findings/confirm-all` | `{ role, name }` marks every open REMOVE/ADVISORY Finding `removed` | `Report` |
| POST `/inspections/{id}/angles/{angle}/reinspect` | `{ role, name }` | the new on-demand `Report` |
| POST `/inspections/{id}/angles/{angle}/checked-by-eye` | `{ role, name }` (ramp_lead only) | `Report` |
| POST `/inspections/{id}/signoff` | `{ role, name }` | `Report` |
| POST `/gates/{gate}/inspect` | `{ kind, scene_id? }` manual trigger | `Report` (status `inspecting` until done) |
| POST `/demo/play` `/demo/pause` `/demo/reset` | | `State` |
| POST `/demo/speed` | `{ speed }` (1, 2, 5, 10) | `State` |
| POST `/assistant` | `{ inspection_id, message }` | `{ reply, suggested_reinspect_angles: string[], draft_report: string \| null }` |
| GET `/rules` | | contents of `fod-rules.json` |

Errors: HTTP 4xx with `{ "error": "<code>", "message": "..." }`. Codes used by the UI: `role_not_allowed` (403), `hold_needs_acknowledge` (409), `open_findings` (409, on signoff), `unusable_angles` (409, on signoff).

`outcome`: `acknowledged | removed | false_alarm | not_found_on_walk`.
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

### Turn record

`GET /api/turns/{turn_id}/record` lists every Inspection, Task, Report and Confirmation of one Turn in time order, with who did each and the cost of the Turn. The dashboard shows it on the Turn's page and offers it as a JSON download. It only reads the store: it never writes and never calls a model. No session is needed. Unknown Turn: 404 `{ "error": "not_found", "message" }`.

A Report is what a person said about a Task (accepted, done, not found, blocked, a note). A Confirmation is what was recorded. They are always separate entries, of kind `report` and `confirmation`.

```ts
type TurnRecord = {
  turn_id: string; gate: string; flight: string | null;
  generated_at: string;                          // ISO time the record was built
  cost: { inspections_usd: number;               // sum of run_metadata.est_cost_usd of the Turn's Inspections
          agent_usd: number;                     // agent wakes logged against this Turn (routing wakes)
          total_usd: number;                     // inspections_usd + agent_usd
          note: string | null };                 // set when some agent wakes belong to no Turn and are not counted
  entries: RecordEntry[];
};
type RecordEntry = {
  seq: number;                                   // 0..n-1 in the returned order
  at: string;                                    // ISO time; sorted by at, ties broken by a stable source order
  t: number | null;                              // demo seconds when known
  kind: "inspection" | "task" | "report" | "confirmation";   // clients must also accept kinds not listed here
  event: string;                                 // see below; clients must also accept events not listed here
  person: { person_id: string | null; name: string | null; role: string | null } | null;
  text: string;                                  // one plain line
  refs: { inspection_id: string | null; task_id: string | null;
          finding_id: string | null;             // the Inspection's Finding ID (data.finding_label has the short label, "F1")
          angle: string | null };
  data: object;                                  // details, by kind (below)
};
```

| kind | event | person | data |
|---|---|---|---|
| `inspection` | `started`, `reinspected` (an on-demand Inspection), `completed` | `reinspected`: who asked, when known; else null | `inspection_kind`; on `started` / `reinspected`: `scene_id`, `angles`, `reason` (`requested` \| `hold_removed` \| null), `parent_inspection_id`; on `completed`: `verdict`, `highest_open_severity`, `missing_angles` (as they were when it finished), `new_findings`, `est_cost_usd`, `spent_usd` |
| `task` | `assigned`, `reassigned`, `escalated`, `reopened`, `closed`, `cancelled`; any other Task event in the activity log (`handover`, or a `task_*` event a later ticket adds) appears by its log name without `task_`, with the log row's text | the Task's assignee at that point (an event the record does not know changes it only when its data names a `to`) | `task_type` (any string: types added later appear by name), `finding_label`, `severity`; `by` (`code` \| `agent` \| `timer` \| person_id) on every event except `closed` / `cancelled`; `assigned`: `instruction`; `reassigned`: `from`, `to`, `reason`; `escalated`: `level`, `reason`, `notified[]`; `closed` / `cancelled`: `reason`, `confirmation_id`; any other event: `log_event`, and `from`, `to`, `reason`, `level` when the log row has them |
| `report` | named as in the commands: `accept`, `done`, `cant`, `not_found`, `note` | who reported | `report_id`, `report_kind` (as stored: `accepted`, `done`, `not_found`, `blocked`, `note`), `raw_text` (the note typed after a command, or the free text), `via` (`command` \| `free_text`), `finding_label` |
| `confirmation` | the action: `acknowledged`, `removed`, `false_alarm`, `not_found_on_walk`, `checked_by_eye`, `signoff` | who recorded it, with role from the confirmations table and `person_id` from the chat session or the Roster | `confirmation_id`, `via` (`command` \| `accepted_proposal` \| `dashboard` for the section 2 endpoints), `raw_text`, `proposal_id`, `finding_label`, `severity`, `outcome_details` (`false_alarm_reason`, `possible_source`, `after_photo_ref` when set) |

Order: store times have one-second resolution, so ties are common. They are broken by the activity log (section 5), the one ordered sequence of what happened; a Confirmation always comes before the Task close it caused. Entries with no activity-log row (for example with `FOD_AGENT=off`) follow, Inspections first, each in its table's order.

## 3. Dashboard (owner: frontend)

Vite + React + TypeScript in `app/frontend/`. `npm run dev` proxies `/api` and `/images` to `http://localhost:8000`; `npm run build` writes `dist/`. Follow `spec/dashboard-ux.md`; the mock at `prototypes/dashboard/index.html` (variant A tiles + variant B queue) is the visual reference. Include: demo controls (play, pause, reset, speed), role switch (Ramp Agent / Ramp Lead, with a name field), Gate tiles + queue, Turn view with Inspection timeline, 6-Angle viewer with Finding boxes linked to the Findings list, current vs reference crops, Confirmation actions per the API rules above, checked-by-eye, sign-off with 6 thumbnails, per-Inspection cost and timing readout, JSON export link, an assistant panel calling `POST /api/assistant`, and photo attribution on every image. The always-on agent adds the chat page (`#/chat`), the activity log (`#/activity`), the read-only Crew and Tasks page (`#/crew`, from `GET /api/agent/board`) and, on the Turn view, the read-only Turn record (`GET /api/turns/{turn_id}/record`). Ship a mock mode (`VITE_MOCK=1`) with fixture data so it can be developed without the backend.

## 4. Budget and hygiene

- Anthropic API spend: **test data $0; backend at most $1.50** for development and its own tests. The full 30-Inspection scoring run is done later by the lead, not by you.
- Models: `claude-haiku-5-5` default; `claude-sonnet-5-5` only behind `FOD_ESCALATION`; never Opus.
- Downloads are untrusted: put them in their own directory, keep scripts elsewhere, run Python with `-I` when it reads them.
- Anonymous, generic User-Agent for downloads; no personal or project details in any outbound request.
- Not a git repo: do not `git init` or commit. Do not edit `spec/`, `issues/`, `research/` or `prototypes/`.

## 5. Always-on agent API (owner: backend; client: the dashboard's chat page)

Specification: `spec/dispatch.md`. All paths are under `/api/agent`. JSON in and out. The endpoints are always mounted; the dispatcher runs when `FOD_AGENT` is `code` or `on` (`./run-agent.sh` sets `on`).

**Session.** `POST /join` returns a token. Send it on every call marked *session* as `Authorization: Bearer <token>`. Role, Shift and Gates are read from the Roster row behind the token on every call. `role`, `name` or `person_id` fields in any other request body are ignored. (Sections 2 and 3 are unchanged: those endpoints still take `role` and `name` from the body.)

| Method & path | Auth | Body or query | Returns |
|---|---|---|---|
| GET `/roster` | none | | `{ people: Person[] }` for the sign-in picker. Never contains a PIN |
| POST `/join` | none | `{ person_id, pin }` (`person_id` may also be the Roster name, any case) | `{ token, person: Person }` |
| GET `/inbox` | session | `?after=<message_id>` (default 0) | `Inbox` |
| POST `/say` | session | `{ text }` free text, 1 to 500 characters | `{ ok: true, routed: "agent", message_id }`. If the text is a command (starts with `/`, or is `y` / `n`), it is run as one and the result is `CommandResult` plus `routed: "command"` |
| POST `/command` | session | `{ text: "/ack F1" }` or `{ command: "ack", args: ["F1"] }` | `CommandResult` |
| POST `/proposals/{proposal_id}/answer` | session | `{ accept: boolean }` | `CommandResult` |
| GET `/activity` | none | `?after=<id>&gate=<gate>&turn_id=<turn_id>&limit=<n>` (all optional; limit default 500, max 1000) | `Activity` |
| GET `/board` | none | | `Board` |

```ts
type Person = { person_id: string; name: string; role: "ramp_agent" | "ramp_lead" | "supervisor";
                gates: string[]; shift: "on" | "break" | "off";
                signed_in: boolean };          // polled the inbox or the API in the last 15 s

type Inbox = {
  person: Person;
  epoch: number;                 // changes on demo Reset: drop what you hold and poll again with after=0
  clock_t: number;               // demo seconds
  cursor: number;                // pass as ?after= on the next poll
  messages: Message[];           // every message to or from this person with message_id > after, oldest first
  tasks: Task[];                 // this person's open Tasks plus their last 10 closed ones (supervisor: everyone's)
  pending_proposals: Proposal[]; // questions waiting for this person's yes or no, oldest first
};
type Message = { message_id: number;
                 from: string;   // person_id | "agent" (model-written) | "code" (fixed wording)
                 to: string;     // person_id | "agent" (free text) | "code" (a command)
                 kind: "agent" | "code" | "timer" | "person" | "command";
                 text: string;   // may contain "\n"
                 task_id: string | null;
                 proposal_id: string | null;   // set on the message that asks a proposal: show accept / decline here
                 at: string; t: number };      // ISO time, demo seconds
type Task = { task_id: string;                 // "K-3"
              type: "ack_hold" | "remove" | "walk_and_report" | "check_by_eye" | "report_outside_boundary" | "sign_off";
              gate: string; turn_id: string; inspection_id: string;   // always the Turn's latest Inspection
              finding_id: string | null;       // short label, "F1"; stable across re-inspections
              inspection_finding_id: string | null;  // the same Finding's ID in inspection_id: a link opens it there
              angle: string | null;
              severity: "HOLD" | "REMOVE" | "ADVISORY" | null;   // copied from the Finding by code
              required_role: "ramp_lead" | "any";
              assignee_id: string | null; instruction: string;
              status: "assigned" | "accepted" | "reported" | "closed" | "cancelled";
              created_by: string;              // "code" | "agent" | person_id
              escalation_level: number;        // 0 to 2
              created_at: string; closed_at: string | null; close_reason: string | null;
              closed_by_confirmation_id: number | null };
type Proposal = { proposal_id: string;         // "P-2"
                  kind: "confirm" | "reinspect" | "handover";
                  question: string;            // "record F2 as removed"
                  action: object;              // confirm: { label, outcome, false_alarm_reason, turn_id }
                                               // reinspect: { gate, angle, turn_id }; handover: { from_id }
                  created_by: string;          // "agent" | "code" | person_id
                  created_at: string; status: "pending";
                  expires_t: number; expires_in_s: number };     // demo seconds

type CommandResult = { ok: true; lines: string[] };   // the same lines also arrive in the inbox as one message

type Activity = { epoch: number; cursor: number; entries: Entry[]; cost: Cost };   // entries oldest first
type Entry = { id: number; at: string; t: number;
               kind: "code" | "agent" | "wake" | "timer" | "cost" | "idle" | "person" | "message";   // display class
               event: string;                  // see the list below
               gate: string | null; turn_id: string | null;
               actor: string;                  // "code" | "agent" | "timer" | person_id | a person's name (confirmation)
               text: string;                   // one human-readable line, may contain "\n"
               data: object };                 // event-specific details
type Cost = { agent_session_usd: number; wakes: number; model_requests: number; tokens_in: number; tokens_out: number;
              process_usd: number; cap_usd: number | null };

type Board = { mode: "off" | "code" | "on"; model: string; model_available: boolean; model_note: string;
               clock_t: number;
               tasks: (Task & { reports: { by_person_id, at, kind, raw_text, via: "command" | "free_text" }[] })[];  // last 100
               roster: (Person & { open_tasks: number })[];
               timers: { task_id: string; kind: string; fire_t: number }[];
               activity: Entry[];              // the last 60 entries
               cost: Cost };
```

**Polling.** The chat page polls `GET /inbox?after=<cursor>` about once a second (this also keeps `signed_in` true) and `GET /activity?after=<cursor>` for the log page. The Crew and Tasks page polls `GET /board` about once a second, one request at a time. None of these calls reaches a model. `gate` and `turn_id` filter the log to entries tied to that Gate or Turn; entries that belong to no Gate (sign-ins, most messages) are left out when a filter is given.

**Activity events.** `inspection_completed` (data: `inspection_id, kind, verdict, highest_open_severity, open_findings[]`), `task_assigned` (data: the `Task`), `hold_alert`, `task_reassigned`, `task_accepted`, `task_reported` (data: `task_id, kind, via, raw_text`), `task_reopened`, `task_escalated` (data: `task_id, level, reason, notified[]`), `task_closed` / `task_cancelled` (data: `task_ids[], reason, confirmation_id`), `timer_fired`, `message` (data: `message_id, from, to, kind, task_id, proposal_id`), `proposal_created`, `proposal_answered` (data: `proposal_id, status: accepted | declined | void, action`), `confirmation` (data: `action: acknowledged | removed | false_alarm | not_found_on_walk | checked_by_eye | signoff, finding_id, angle, by: { role, name }, inspection_id`; `at` is when), `command_refused` (data: `command, error`), `handover`, `signed_in`, `agent_wake_started`, `agent_tool` (data: `tool, args, ok, result`), `agent_note`, `agent_wake` (data: `trigger, model, outcome, tokens_in, tokens_out, est_cost_usd, seconds, tool_calls[]`), `agent_wake_failed`, `model_unavailable`, `free_text_not_interpreted`, `unroutable`, `departed`, `idle`, `dispatcher_started`, `demo_reset`.

**Commands** (the `text` form; the structured form is the same word without the slash, with `args` in the same order). Finding IDs are the short labels (`F1`), Task IDs are `K-n`, Gates are `T5`.

| Command | Who | Effect |
|---|---|---|
| `/tasks` | anyone | list open Tasks (supervisor: everyone's) |
| `/accept K-3` `/done K-3 [note]` `/cant K-3 <reason>` | the assignee | a Report on the Task. Never a Confirmation. `/done` on a REMOVE or ADVISORY Task creates a proposal for that person |
| `/ack F1` | Ramp Lead (HOLD) | Confirmation `acknowledged` |
| `/removed F1 [possible source]` | by severity | Confirmation `removed`. On a HOLD: takes a new photo first; recorded only if clean |
| `/false-alarm F2 <shadow\|marking\|equipment_in_place\|other>` `/not-found F2` | by severity | Confirmation |
| `/reported F3` | by severity | records an outside-envelope Finding as reported |
| `/all-removed T5` | Ramp Agent or Ramp Lead | every open REMOVE and ADVISORY Finding at the Gate; never a HOLD |
| `/reinspect T5 ENG-R` | Ramp Agent or Ramp Lead | new photo of one Angle; closes nothing |
| `/eye T5 ENG-R` | Ramp Lead | checked by eye |
| `/signoff T5` | Ramp Agent or Ramp Lead | sign off the Gate's latest Inspection |
| `/send <person> F1 [instruction]` `/reassign K-3 <person>` | Ramp Lead, supervisor | create or move a Task |
| `/handover <person>` `/break` `/back` | Ramp Agent or Ramp Lead | Handover (the other person accepts with `y`), Shift |
| `/shift <person> on\|break\|off` `/msg <person> <text>` | supervisor | |
| `y` `n` (optionally `y P-2`) | the person asked | answer a proposal; same as `POST /proposals/{id}/answer` |
| `/who` `/help` | anyone | Roster; command list for the caller's role |

**Errors.** HTTP 4xx with `{ error, message }`, as in section 2. A refused command also appears in the person's thread and in the activity log. Codes: `bad_credentials` (401), `not_signed_in` (401), `role_not_allowed` (403), `not_your_task` (403), `not_found` (404), `invalid_command` (422), `invalid_request` (422), and 409 for `refused` (a routing check failed; the message says why), `nothing_to_answer`, `proposal_void`, `open_hold`, `task_closed`, `nothing_to_hand_over`, plus the section 2 codes `hold_needs_acknowledge`, `open_findings`, `unusable_angles`, `already_confirmed`, `already_signed_off`, `inspection_in_progress`, `angle_usable`.

**Audit.** A Confirmation made through these endpoints carries, in the `confirmations` table's data, `via` (`command` or `accepted_proposal`), `raw_text`, `person_id` and, for a proposal, `proposal_id`.
