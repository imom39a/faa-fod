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

`VITE_MOCK=1` swaps the HTTP client for an in-browser mock of the backend (`src/mock/`). It implements the same API and rules: role checks, HOLD acknowledge → removed → re-inspection, confirm-all, checked-by-eye, sign-off preconditions, the queue order and the demo clock. A re-inspection never drops an open Finding: one the new photo no longer shows is carried, still open, until a Confirmation closes it. No model is called; the cost and timing figures are illustrative. The mock and its photos are left out of a normal `npm run build`.

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

**Crew and Tasks in mock mode** (`http://localhost:5173/#/crew`). At load the demo has no Task yet, so the page shows a marked sample (`src/mock/crewSample.ts`): a Ramp Agent on a break ("Lee (sample)"), an escalated HOLD at level 2, an escalated REMOVE, a check-by-eye Task with a Report, a closed sign-off, a Task of a type the dashboard does not know (`handover_accept`), a short activity log and an illustrative cost. Each sample Task and activity entry has a "Sample" tag, and each sample Task opens a real mock Turn. The sample is only added to `GET /agent/board`; the chat page, the activity log and the Turn record never see it. When the demo creates its first Task (press Play, or open `?t=120#/crew`), the page shows the mock dispatcher's own Board. At `?t=120` a Task link opens its Turn with the Finding selected.

## Chat page (`#/chat`)

The chat page is where one person works with the always-on agent (`../CONTRACT.md` section 5). Every button sends one structured command to `POST /api/agent/command` as the signed-in person; the server decides and a refusal is shown in the thread and in a banner. Nothing on the page records a Confirmation except a button that person presses or a proposal they accept.

- **Sign-in.** Pick a name from the Roster and enter the PIN. The role comes from the Roster on the server. Sign-in is kept per browser tab, so two tabs can be two people.
- **Tasks and their buttons.** Each Task card groups its buttons: "Record on the Inspection" (a Confirmation, in your name), "Report to the agent" (not a Confirmation, dashed border), "New photo" (records nothing) and "Routing". The one or two next steps are repeated under the newest message about the Task.
- **Not found.** On a removal or walk Task, "Not found" is a Report (`cant-find`, with an optional note). For a REMOVE or ADVISORY Finding the same person is then asked whether to record it as not found on walk; only their Accept records it. For a HOLD nothing is proposed to them: the Ramp Lead holding the HOLD is told and is asked whether to take a new photo. "Record not found" (a Confirmation) is offered only on a HOLD Task held by a Ramp Lead and on an outside-envelope Task.
- **Reported to…** A Task for debris outside the gate safety envelope has two Confirmation buttons, "Reported to Ramp 1 control" and "Reported to Airport Ops" (`reported F3 ramp1` / `reported F3 airport-ops`). The one the Task's instruction names is the primary button. The Task's message carries a drafted report behind "Show draft report"; the system sends nothing.
- **Shift controls** ("Your Shift", not shown to a supervisor). "Go on a break" (`break`), "Back on shift" (`back`, shown on a break or off shift) and "Hand over…". A break is refused while you hold an open HOLD Task.
- **Handover.** "Hand over…" lists the Ramp Agents and Ramp Leads on shift and sends `handover <person>`. They get a question with the brief (every open Task, its Reports and running timers) and Accept / Decline. Nothing moves until they accept; then every open Task moves, timers keep running and your Shift ends. If they decline or do not answer before the question expires, your Tasks stay with you and you are told. A Handover confirms nothing.
- **Still there.** When "Removed" on a HOLD takes a new photo that still shows the object, the banner says so, the removal Task goes back to its holder, the HOLD goes up one Escalation level and the reply says who else on shift could be sent.

**Trying it in mock mode.** `npm run dev:mock`, then open `http://localhost:5173/?t=20#/chat` (the demo stays paused, so no question expires while you click; press Play to see timers fire). Mock PINs: Kim 1111, Okafor 2222, Patel 3333, Reyes 4444, Dana 9999. Open one tab per person: the tabs share one mock.

| To see | Do |
|---|---|
| Not found on a REMOVE Task | As Kim: "Not found" on the T5 bag tag, send, then Accept the question |
| Break refused with a HOLD | As Okafor: "Go on a break" |
| Break and back | As Kim: "Go on a break", then "Back on shift" |
| Handover refused | As Okafor: "Hand over…" to Kim (a Ramp Agent cannot take the HOLD) |
| Handover | As Okafor: "Hand over…" to Reyes. As Reyes: Accept or Decline. To see no answer, press Play at 10x and wait 2 demo minutes |
| Not found on a HOLD | Open the tabs with `?t=215`. As Reyes: Acknowledge the T1 NOSE HOLD, type `/send patel F1`. As Patel: "Not found". Reyes gets the new-photo question |
| Still there | Continue as Reyes: "Removed (takes a new photo)" on the T1 NOSE HOLD |
| Reported to… | With `?t=215`, as Kim: the T8 WIDE Task, "Show draft report", then "Reported to Ramp 1 control" |
| Unusable Angle near pushback | Press Play from 0:00 as Reyes: the T2 check-by-eye Tasks reach Escalation level 2 at 3:50 |

The new events show on `#/activity` under "Shift / Handover" (Handover asked, declined, expired, done; Shift changes; the only Ramp Lead trying to leave) and "Confirmation" (who an outside-envelope Finding was reported to).

**Turn record in mock mode.** On a Turn's page, press "Show Turn record". The mock builds it from the mock backend's Inspections and Confirmations and from the mock dispatcher's activity log (`src/mock/turnRecord.ts`). The Turns signed off before the demo starts (T2, T5, T8) also get a sample sign-off Task and two sample Reports, tagged "Sample".

Fixture photos (`src/mock/img/`) are copied from `prototypes/dashboard/assets/img`, with boxes from its `scenes.json` ground truth. They are crops of Wikimedia Commons photographs by Bahnfrend (CC0 1.0 and CC BY-SA 4.0) and Andy Mabbett (CC BY-SA 3.0), some with debris composited from FOD-A (FOD-UNOmaha, MIT) or a synthetic glare overlay. Full per-file sources: `prototypes/dashboard/assets/ATTRIBUTION.md`. The UI shows the credit under every image from `angles[].attribution`.

## Layout

```
src/
  api/types.ts        contract types (State, Report, Finding, ...)
  api/client.ts       Api interface + HTTP client, ApiError
  api/errors.ts       user-facing message for every contract error code
  api/index.ts        picks the HTTP client or the mock
  api/turnRecordTypes.ts  Turn record types (GET /api/turns/{turn_id}/record)
  store/stateStore.ts polls GET /api/state every second
  store/identity.ts   role + name, remembered in localStorage
  lib/boxes.ts        Finding box scaling (original pixels → displayed size, minimum on-screen size)
  lib/gates.ts        Gate tile and "Needs a human" queue models
  lib/report.ts       open Findings, sign-off blockers, superseded Inspections, timeline, HOLD outcome
  lib/crewTasks.ts    Crew and Tasks: Task order, unknown Task types, Roster groups, links
  lib/turnRecord.ts   Turn record: tolerant normaliser, time order, JSON download
  store/boardStore.ts polls GET /api/agent/board about once a second, never two requests at once
  components/         Overview, TurnView, Timeline, AngleFrame, FindingCard, SignoffDialog, DetailsPanel, AssistantPanel,
                      CrewTasksPage (#/crew), TurnRecord (on the Turn view)
  mock/               in-memory backend (backend.ts), fixtures, photos; crewSample.ts (sample Board), turnRecord.ts (mock Turn record)
```

Views: `#/` is the overview (5 Gate tiles, queue, demo controls, role switch); `#/turn/<turn_id>[/<inspection_id>][?finding=<finding_id>]` is the Turn view. Without an Inspection id it follows the latest Inspection of the Turn; `?finding=` selects that Finding once. `#/crew` is Crew and Tasks (read-only). `#/chat` and `#/activity` are the always-on agent's chat page and activity log.

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
- Crew and Tasks polls `GET /api/agent/board` every second, one request at a time. When a poll fails it waits longer each time (up to 8 s) and keeps the last Board on screen with a "Not connected" banner.
- The Turn record is fetched only after "Show Turn record" is pressed, then every 2 s while it is open. The client drops an entry with no `kind` or no valid `at`, fills other missing fields, and shows an unknown `kind` or `event` by name.
- A Task link uses `inspection_finding_id` for `?finding=`. A server that does not send that field gets a link to the Inspection only.
