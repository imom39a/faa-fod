# Gate FOD Inspection dashboard

The dashboard for the airline gate FOD inspection proof of concept: Vite + React + TypeScript, plain CSS, no UI framework. It implements section 3 of `../CONTRACT.md` and follows `../../spec/dashboard-ux.md`. Terms are used as in `../../GLOSSARY.md`.

## Run

```sh
npm install
npm run dev              # real mode: proxies /api and /images to http://localhost:8000
VITE_MOCK=1 npm run dev  # mock mode: fixture data, no backend (also: npm run dev:mock)
npm run build            # type-check, then write dist/ (the backend serves it at /)
npm test                 # vitest unit tests
```

Open http://localhost:5173. In real mode, start the backend first (`uv run uvicorn fodgate.api:app --port 8000` in `app/backend/`); if it is down the dashboard says so and keeps retrying.

## Mock mode

`VITE_MOCK=1` swaps the HTTP client for an in-browser mock of the backend (`src/mock/`). It implements the same API and rules: role checks, HOLD acknowledge → removed → re-inspection, confirm-all, checked-by-eye, sign-off preconditions, the queue order and the demo clock. No model is called; the cost and timing figures are illustrative. The mock and its photos are left out of a normal `npm run build`.

The scripted demo (6 minutes at 1x) covers every Gate status. Press Play, or jump with `?t=<seconds>`, for example `http://localhost:5173/?t=110`:

| Demo time | What to see |
|---|---|
| 0:00 | T1 awaiting pre-arrival, T4 idle, T2/T5/T8 aircraft on stand |
| 0:20 | T1 confirmed clear (pre-arrival signed off), T5 FINDINGS with an outside-boundary Finding (FOD-R10) |
| 1:01 | T4 inspecting; T1 FINDINGS with two HOLDs; T2 INCOMPLETE (ENG-R blocked, CARGO glare) |
| 1:10 | T4 pre-arrival: GSE inside the equipment restraint line (REMOVE, FOD-R9), a spill observation, dismissed Candidates |
| 1:50 | T8 confirmed clear; 2:20 departed; 2:50 idle |
| 4:04 | T4 pre-departure: a nut in the right engine intake zone (HOLD) |

Flows worth trying at T1 (`?t=60`): as Ramp Agent, a HOLD action is refused. As Ramp Lead, acknowledge the ENG-L bolt, then "Removed": the re-inspection comes back clean and the HOLD clears. The NOSE box cutter is still there after its re-inspection, so that HOLD stays open (a false alarm with a reason closes it). At T2, re-inspecting ENG-R fixes it; CARGO stays in glare, so a Ramp Lead records "checked by eye" before sign-off is allowed.

Mock-only behaviour: one demo second stands for 6 seconds of gate time (so the 6-minute demo spans about 36 minutes of timestamps and pushback countdowns); two scripted sign-offs are made by "T. Alvarez (scripted)"; a scheduled pushback waits until the pre-departure Inspection is signed off; Reset returns to the `?t=` start time.

Fixture photos (`src/mock/img/`) are copied from `prototypes/dashboard/assets/img`, with boxes from its `scenes.json` ground truth. They are crops of Wikimedia Commons photographs by Bahnfrend (CC0 1.0 and CC BY-SA 4.0) and Andy Mabbett (CC BY-SA 3.0), some with debris composited from FOD-A (FOD-UNOmaha, MIT) or a synthetic glare overlay. Full per-file sources: `prototypes/dashboard/assets/ATTRIBUTION.md`. The UI shows the credit under every image from `angles[].attribution`.

## Layout

```
src/
  api/types.ts        contract types (State, Report, Finding, ...)
  api/client.ts       Api interface + HTTP client, ApiError
  api/errors.ts       user-facing message for every contract error code
  api/index.ts        picks the HTTP client or the mock
  store/stateStore.ts polls GET /api/state every second
  store/identity.ts   role + name, remembered in localStorage
  lib/boxes.ts        Finding box scaling (original pixels → displayed size, minimum on-screen size)
  lib/gates.ts        Gate tile and "Needs a human" queue models
  lib/report.ts       open Findings, sign-off blockers, superseded Inspections, timeline, HOLD outcome
  components/         Overview, TurnView, Timeline, AngleFrame, FindingCard, SignoffDialog, DetailsPanel, AssistantPanel
  mock/               in-memory backend (backend.ts), fixtures, photos
```

Views: `#/` is the overview (5 Gate tiles, queue, demo controls, role switch); `#/turn/<turn_id>[/<inspection_id>]` is the Turn view. Without an Inspection id it follows the latest Inspection of the Turn.

## Decisions where the contract is silent

- `GET /turns/{id}`: only `inspections` and `events` are fixed. The client also reads optional `gate`, `flight` and `aircraft_type`, and falls back to `/api/state` for them.
- An Inspection is shown as superseded when a later Inspection names it as `parent_inspection_id`. Actions are offered only on the latest Inspection of a Turn while it is `awaiting_confirmation`.
- After any action the UI shows the Report the API returns. For "Removed" on a HOLD it decides "cleared" or "still there" from that Report: the same `finding_id` confirmed means cleared; an unconfirmed Finding on the same Angle overlapping the old box means still there.
- A Report with status `inspecting` is polled (the Turn is re-fetched every 1.5 s) until its Verdict arrives.
- Outside-boundary Findings are confirmed with outcome `removed` plus optional `possible_source`, and displayed as "Reported to Ramp 1 control / Airport Operations". An `acknowledged` one is treated as closed.
- HOLD buttons stay enabled for a Ramp Agent so the API's `role_not_allowed` refusal is shown (demo moment 4). "Removed" on a HOLD is disabled until it is acknowledged.
- The sign-off button in the dialog is disabled while the client can see blockers; `open_findings` and `unusable_angles` from the API are still handled.
- The contract does not restrict who may sign off, so both roles can.
- "Confirm all removed" also covers open REMOVE/ADVISORY Findings outside the boundary (the API marks them all), so the UI asks for one extra confirmation in that case.
- Category labels come from `GET /api/rules`.
