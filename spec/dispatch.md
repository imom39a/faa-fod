# Dispatch: the always-on agent (PoC v1.1)

Design study: `research/always-on-agent-conversion.md` (option B). Rehearsal with measured cost: `research/always-on-agent-rehearsal.md`. API: `app/CONTRACT.md` section 5. Terms: `GLOSSARY.md` (Roster, Shift, Task, Report, Escalation, Handover). This section adds to the approved behaviour; where it differs from `spec/dashboard-ux.md` ("Roles: a switch stands in for sign-in") it applies only to the agent's own endpoints.

## What it is

- An always-on agent runs inside the backend process. It is started from a terminal (`./run-agent.sh`), which shows a live, display-only log. People reach it through a chat page in the browser; nobody types into the terminal.
- It manages a Roster of people, hands out Tasks that come from Inspection results, takes people's Reports back, and looks at the record again after every change.
- It is driven by the same scripted schedule and scenes as the dashboard. The dashboard is unchanged and shows the same Turns, Inspections and Confirmations.

## The rules that do not move

1. **Severity, rule ID and Verdict are computed in code**, as before. A Task copies its severity from the Finding. No agent tool takes a severity, a rule ID, a Verdict or a Finding status as input.
2. **Nothing clears without a person.** The agent has no tool that records a Confirmation, a check by eye or a sign-off. A Confirmation is recorded in exactly two ways: a slash command typed (or sent by a button) by a signed-in person and parsed by code, or a proposal that the same person accepts. The record keeps which of the two it was, the raw text and the person.
3. **Only a Ramp Lead records anything on a HOLD**, in two steps. The agent cannot propose a HOLD Confirmation to a Ramp Agent, and cannot propose "removed" for a HOLD that is not yet acknowledged. "Removed" on a HOLD still takes a new photo first and counts only if it is clean.
4. **A Report is not a Confirmation.** "Done" on a Task changes the Task and tells whoever must act. The Finding stays open.
5. **An unusable Angle stays INCOMPLETE.** Checking it by eye is a Ramp Lead's Task and only that lead's command records it.
6. **The agent never says a Gate, Angle or Finding is clear and never says an aircraft may move.** Code refuses such wording in its messages. Escalation only tells people; the system does not hold or release a pushback.
7. **Model:** `claude-haiku-5-5` only. There is no setting to raise it.

## Who is acting

- People sign in with a Roster name and PIN and get a session token. **Role, Shift and Gates come from the Roster row behind the token.** A role or name sent in a request body is ignored by the agent's endpoints.
- The PIN is a demo stand-in for sign-in. Production needs the airline's identity system and device binding.
- **Known gap:** the older dashboard endpoints (`/api/inspections/...`) still trust the `role` and `name` in the request body, so that the dashboard keeps working unchanged. Anyone who can reach the server can act as a Ramp Lead through them. The agent's activity log, board and roster listing are also readable without a session, like every other read endpoint of the PoC.
- The agent cannot add people, change roles, Shifts, PINs, Escalation thresholds, the model or the spend cap. The supervisor sets a person's Shift with a command.

## Code first

Every change in the store is an event. The dispatcher sleeps until one arrives; a pending timer is a row checked by code. **Idle time makes no model calls.**

Handled by code alone, with fixed wording:

- **HOLD alert.** When an Inspection has an open HOLD inside the gate safety envelope, code creates the "acknowledge HOLD" Task for a Ramp Lead covering the Gate and sends the alert to every on-shift Ramp Lead at once. This never waits for the model. With no Ramp Lead on shift the supervisor is told.
- **Sign-off request** to a Ramp Lead when an Inspection has nothing open.
- **Work with one possible owner.**
- **Closing Tasks** when a Confirmation lands; following a Finding onto the Turn's latest Inspection after a re-inspection (people keep the same short label, F1); cancelling Tasks of an Inspection that a newer one replaced.
- **Timers and the Escalation ladder.**
- **Slash commands and answers to proposals.**

The model is woken for two things only:

- An Inspection left work that **more than one person could take** (for example a REMOVE Finding that a Ramp Agent or the Ramp Lead could remove). It chooses and writes the instruction.
- A person typed **free text**. It works out what is meant and uses its tools: assign or move a Task, log a Report, offer a proposal, answer a question, raise an Escalation.

If the model is unavailable, slow, refuses, runs out of turns or the spend cap is reached, code routes the same work by a fixed rule (covers the Gate, right role, signed in, fewest open Tasks) and tells the person who typed free text to use commands. All commands keep working.

## Tasks

| Type | From | Who may hold it |
|---|---|---|
| `ack_hold` | an open HOLD | Ramp Lead |
| `remove` | an open REMOVE or ADVISORY Finding; or a HOLD object a Ramp Lead sends someone to | Ramp Agent or Ramp Lead |
| `walk_and_report` | a person asked to go and look | Ramp Agent or Ramp Lead |
| `check_by_eye` | an unusable Angle | Ramp Lead |
| `report_outside_boundary` | a Finding outside the gate safety envelope | whoever may confirm that severity |
| `sign_off` | an Inspection with nothing open | Ramp Lead |

- Status: `assigned`, `accepted`, `reported`, `closed`, `cancelled`.
- Before a Task is created or moved, code checks: the person exists, is on Shift, has a permitted role; the Finding is open; the Task is not a duplicate. A refused call goes back to whoever asked.
- A Ramp Agent may be sent to remove a HOLD object and report back. The Ramp Lead still acknowledges and records it.
- A HOLD Task closes only when a Ramp Lead's Confirmation exists.
- The agent never starts a re-inspection. It proposes one and a person accepts.

## Proposals

The agent (or code, after `/done` on a REMOVE Task) asks one person a yes/no question, for example "Record F2 as removed, confirmed by you?". Accepting runs the same code path as the command, as that person. A proposal expires (120 s by default), is void if the Finding changed since it was asked, and can only be answered by the person it was put to.

## Escalation ladder

Thresholds are in `app/data/roster/escalation.json`, in demo seconds (minutes in real use). They run on the demo clock, so they scale with the speed control.

1. HOLD not acknowledged after 30 s: second call to that Ramp Lead; the supervisor is told.
2. Still not acknowledged after 60 s, or any open HOLD with scheduled pushback under 2 minutes: every on-shift Ramp Lead and the supervisor.
3. A Task with no Report after 60 s: the person is asked once. After 120 s: reassignment is offered to the Gate's Ramp Lead.
4. A HOLD recorded as removed whose new photo still shows the object: the Finding stays open, the removal Task reopens, the HOLD goes up one level.

## Shift and Handover

- `/break` takes a person off new work. It is refused while they hold an open HOLD Task.
- `/handover <person>` asks another on-shift person with a permitted role to take every open Task. Tasks move only when that person accepts. A Handover confirms nothing.

## Cost

- The spend cap `FOD_MAX_SPEND_USD` is checked before every wake and before every request inside a wake. The assistant panel's calls now count against the same cap and stop at it.
- Each wake is stateless: the prompt is built from the store. System prompt and tool list are byte-identical on every call so the prefix is cached.
- At most 6 model requests per wake, at most 20 wakes a minute; events for one Turn and messages from one person are merged into one wake.
- Every wake is recorded with tokens, cost and duration, and shown on the console and in the activity log.
- Measured on the scripted demo: 3 wakes, about $0.004 (see the rehearsal file).

## The log

Everything that happens is one entry in a chronological activity log: Inspections completed; Tasks assigned, accepted, reported, reopened, escalated, closed; every message; proposals and their answers; Confirmations with who and when; timers fired; refused commands; agent wakes with tool calls and cost. The terminal shows it live; `GET /api/agent/activity` serves it to the browser. A demo Reset clears it with the other records and keeps the Roster and sessions.

## Not built

- The chat page itself (built separately against section 5 of the contract).
- A dashboard panel for Tasks (`GET /api/agent/board` is there for it).
- A model-written Handover brief: the brief is composed by code.
- Channels other than the chat page; real sign-in; PIN attempt limits.
