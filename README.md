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

The dashboard is called **StandClear**. The dark rail on the left switches pages. The strip across the top shows every gate on every page: grey while normal, coloured when something is wrong.

**Demo controls** (press the clock at the top right)
- **Play / Pause / Reset:** run, stop or restart the scripted schedule. Reset wipes the records.
- **1x to 10x:** how fast the schedule's clock runs.
- **Ramp Agent / Ramp Lead:** who you are acting as. Only a Ramp Lead can clear a HOLD.

**The Gates table** shows each gate's flight, status and the system's result:
- **ALL CLEAR:** nothing found.
- **FINDINGS:** debris or misplaced equipment found. Severity is **HOLD** (aircraft must not move), **REMOVE** (clear before departure) or **ADVISORY** (log it).
- **INCOMPLETE:** a camera view was unusable, so the system will not call the stand clear.

**"Needs a human" queue** lists every gate waiting on a person: HOLDs first, then whichever gate is closest to pushback.

**A walkthrough**
1. Press Play at 2x.
2. When a HOLD appears in the queue, click it. You see six photos with a box on the object and the rule it breaks.
3. As Ramp Agent, try **Acknowledge**. You are refused.
4. Switch to Ramp Lead. Press **Acknowledge**, then **Removed**. The system re-photographs that view; the HOLD clears only if the new photo is clean.
5. Press **Sign off Inspection**. The gate turns to "Confirmed clear".

The demo stages five moments: a small bolt in an engine intake zone (HOLD), equipment parked inside the restraint line before arrival (REMOVE), glare on an engine view (INCOMPLETE), the Ramp Lead-only HOLD clearance, and debris beyond the stand routed to ramp control.

## Always-on agent

The same PoC can run as an **always-on agent**: it manages a roster of people, gives them the work each Inspection produces, takes their reports back and looks again after every change. It is started from a terminal; people use it from the browser. The dashboard above is unchanged and remains the place to inspect photos, Findings and Confirmations.

```bash
./run-agent.sh              # API, dashboard, agent and a live log in this terminal
```

Open http://localhost:8000 and press **Play** at 2x (or start with `./run-agent.sh --play --speed 2`). It plays a short schedule (`app/data/demo/timeline-agent.json`): one clean Turn at T8 and the T5 Turn with a hammer by the right engine (HOLD) and a bag tag by the belt loader (REMOVE).

**The three views**

| View | What it is |
|---|---|
| Terminal | The agent's console. Display only: events, the agent's decisions, Tasks, timers and running cost. Lines marked `[code]` are ordinary code, `agent>` is the model, `[timer]` is a code timer, `[cost]` is measured spend. |
| Dashboard | As before: the Gates table, photos, Findings, Confirmations. |
| Chat page | Where each person signs in, gets Tasks, reports back and records Confirmations. Open it at http://localhost:8000/#/chat and sign in with a name and PIN from the Roster. `uv run python -m fodgate.rehearse` (from `app/backend`) plays two people over the same API and prints both chat threads. |

**Crew and Tasks, and the Turn record.** Both are read-only: neither one can confirm, sign off or reassign anything.

- **Crew and Tasks** (http://localhost:8000/#/crew, the "Crew and Tasks" link in the top bar) shows who is on shift, with role and Gates, and who is on a break. It shows every open Task (what it is, its Gate and Finding, who has it, its status and how long it has been open), the Escalations in progress with the level reached, recent agent activity and the session cost. It reads `GET /api/agent/board` every second. HOLDs come first, then the higher Escalation level. Click a Task to open its Turn at that Finding. A Task type added later shows by its name and instruction.
- **The Turn record** is on each Turn's page: press "Show Turn record". It lists every Inspection, Task, Report and Confirmation of the Turn in time order, with who did each and when, and the Turn's cost. It updates while it is open. "Download JSON" saves it as `turn-<turn_id>-record.json`. It comes from `GET /api/turns/{turn_id}/record`. A Report (what a person said) and a Confirmation (what was recorded) are separate kinds of entry.
- To see both without the backend, use the dashboard's mock mode (`app/frontend/README.md`).

**The roster** (`app/data/roster/roster.json`; the PINs are demo stand-ins for sign-in, not secrets)

| Person | Role | Gates | PIN |
|---|---|---|---|
| Kim | Ramp Agent | T5, T8 | 1111 |
| Okafor | Ramp Lead | T5, T8 | 2222 |
| Patel | Ramp Agent | T1, T2, T4 | 3333 |
| Reyes | Ramp Lead | T1, T2, T4 | 4444 |
| Dana | Supervisor | all | 9999 |

**Walkthrough** (about 3.5 minutes at 2x; Kim and Okafor signed in)

1. Press Play. The terminal sits at "Waiting for events" and the cost does not move: idle time makes no model calls.
2. T8's clean pre-arrival Inspection lands. Code asks Okafor to sign off (`/signoff T8`). No model call.
3. T5's pre-departure Inspection lands: F1 HOLD at ENG-R, F2 REMOVE at CARGO. Code sends the HOLD alert to every Ramp Lead on shift at once. The agent is woken once to choose who removes the bag tag, and gives it to Kim.
4. Kim sends `/ack F1`. Refused: only a Ramp Lead can touch a HOLD.
5. Wait 30 seconds of schedule time. A code timer calls Okafor a second time and tells the supervisor.
6. Okafor sends `/ack F1`, then types "send kim, she's closest". The agent turns that into a Task for Kim.
7. Kim types "got the hammer, its in the fod bin. bag tag picked up too". The agent logs two Reports, asks Kim to confirm the bag tag (she answers yes), and code tells Okafor that only he can record the HOLD. Both Findings were still open until then.
8. Okafor sends `/removed F1`. Code takes a new photo of ENG-R; it is clean; the Confirmation is recorded.
9. Okafor sends `/signoff T5`. Tasks close, timers are cancelled, the gate turns to "Confirmed clear" on the dashboard.
10. Open the activity log (`GET /api/agent/activity`): every step with who and when, and the session cost (about $0.004).

**More that people can do in the chat page** (each is a button; the same words work as typed commands)

- **Not found.** On a removal Task, "Not found" is a Report. For a REMOVE or ADVISORY Finding the person is then asked "Record F2 as not found on walk?" and it is recorded only if they accept. For a HOLD nothing is recorded: the Ramp Lead is told and is offered a new photo of that Angle.
- **Still there.** When a Ramp Lead presses "Removed" on a HOLD and the new photo still shows the object, the HOLD stays open, the removal Task reopens, the Escalation level goes up by one and the Ramp Lead is told who else on Shift could be sent.
- **An unusable view.** The Gate's Ramp Lead gets one Task per unusable Angle: "Re-inspect" takes a new photo, and if it is still unusable "Checked by eye" records that a person cleared the zone. Only a Ramp Lead can press it, and sign-off waits for it.
- **Debris outside the stand.** The Task says not to remove the item and carries a drafted report addressed to Ramp 1 control (shared taxilane) or Airport Operations (movement area). The person sends it, then presses "Reported to Ramp 1 control" or "Reported to Airport Ops". Only that closes the Finding, and the record keeps who was told.
- **Break, back, and Handover.** "Go on a break" stops new Tasks coming; it is refused while you hold an open HOLD Task. "Hand over…" asks one person to take all your open Tasks: they get a brief and accept or decline. Nothing moves until they accept; then your Shift ends and running timers carry on against them. Example:

  ```
  Okafor: Hand over… -> Reyes        "Asked Reyes (Ramp Lead) to take over 1 Task. They stay yours until they accept."
  Reyes:  Accept                      "Handover accepted: K-1 is now yours. Running timers carry on. Okafor's Shift has ended."
  Okafor: Back on shift               "You are back on shift."
  ```

All five played end to end, with chat threads and cost: `research/always-on-agent-flows-rehearsal.md`. To replay them: `cd app/backend && uv run python -m fodgate.rehearse_flows --keyless` (no key, no cost).

**What keeps it safe**

- The agent proposes and routes. It has no tool that confirms a Finding, records a check by eye, signs off, or changes a severity or a Verdict.
- A Confirmation is recorded only from a command a signed-in person sent, or from a question that same person answered yes to.
- A person's "done" is a Report, not a Confirmation. A HOLD is still re-photographed before it counts.
- Role comes from the roster on the server, not from what the browser sends.
- If Claude is unavailable or the spend cap is reached, code still delivers the HOLD and routes the rest by a fixed rule, and every command works. Try it: `FOD_AGENT=code ./run-agent.sh`.

**Limits to state**: the PIN is not real sign-in; the older dashboard endpoints still accept whatever role the browser sends; the terminal is a display, not a control; the linked "always-on agent" repository was a data pack, so the loop is this project's own. Details: `spec/dispatch.md`. A recorded run with costs: `research/always-on-agent-rehearsal.md`.

## Agent evals

A separate check of whether the always-on agent behaves correctly: 54 scenarios (routing, safety, understanding plain-language reports, proposals, Escalation, cost), each checked by code that reads the database and the agent's tool calls. It does not replace the detection scoring below.

```bash
cd app/backend
uv run python -m fodgate.agent_evals --dry-run          # scripted stand-in for the agent: no key, no cost
uv run python -m fodgate.agent_evals --max-usd 0.50     # live on Claude Haiku 5.5; stops at the cap (a full run costs about $0.02)
uv run python -m fodgate.agent_evals --only adv-        # a subset, by scenario ID or prefix
uv run python -m fodgate.agent_evals --compare app/var/agent-evals/results.json   # how many scenarios changed since that run
```

Results are written to `app/var/agent-evals/results.json` and `summary.md`. One safety violation fails the run (exit code 2). The scenarios are JSON files in `app/data/agent-evals/scenarios/`; the README beside them explains the format and how to add one. First live runs: `app/AGENT-EVAL-RESULTS.md` (54 of 54 passed twice, no safety violation, $0.045 in total).

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
| `app/backend/` | FastAPI app: detection pipeline, Confirmation rules, demo player, assistant, always-on agent (`fodgate/dispatch/`), scoring |
| `app/frontend/` | React dashboard |
| `app/data/` | Test set (30 Inspections), 5 demo scenes, demo schedules, roster and Escalation thresholds, rule set, photo attribution |
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
uv run pytest                                  # 187 tests, Claude mocked, no API calls
uv run python -m fodgate.rehearse --keyless    # the agent demo over HTTP with no key and no cost

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
| The agent console says "Agent model not used" | No key, the spend cap was reached, or `FOD_AGENT=code`. Work is still routed by code and commands work |
| Free text gets "I cannot read free text right now" | Same cause. Use the commands (`/help`) |

## Image credits

Every photograph is openly licensed (mostly CC BY-SA, some CC BY, CC0 and public domain). Sources, authors and licences are in `app/data/ATTRIBUTION.md` and shown under each image in the dashboard. Debris cut-outs come from the FOD-A dataset (MIT licence). If you share images from this repository, the attribution must go with them.
