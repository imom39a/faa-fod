# Notes for coding agents

Read `README.md` first for what this is and how to run it. This file covers what you need before changing anything.

## Orientation

- The app is in `app/`: `backend/` (Python 3.12, FastAPI, package `fodgate`), `frontend/` (Vite, React, TypeScript), `data/` (scenes, rule set, demo schedule).
- `spec/` holds the approved decisions. `spec/requirements-baseline.md` is the index; each requirement names its source. Change behaviour only in line with these, or update the spec in the same change and say so.
- `app/CONTRACT.md` fixes the data layout and the API between backend, dashboard and data. If you change an endpoint or a field, change the contract, the backend, the dashboard types (`app/frontend/src/api/`) and the dashboard mock together.
- `spec/design-system.md` fixes how every screen looks and is laid out (the "Ops console": page rail, Gate strip on every page, grey display with colour only for abnormal states). Read it before adding or changing a screen. The shell is `app/frontend/src/components/AppShell.tsx`; every colour is a token in `:root` of `app/frontend/src/styles.css`; `src/design.test.ts` checks the rules code can check. The product name in the UI is StandClear (`src/lib/brand.ts`).
- `GLOSSARY.md` defines the vocabulary (Gate, Turn, Inspection, Angle, Candidate, Finding, Verdict, Confirmation, Ramp Agent, Ramp Lead, Roster, Shift, Task, Report, Escalation, Handover). Use these words exactly in code, API and UI.
- The always-on agent is `app/backend/fodgate/dispatch/` (spec: `spec/dispatch.md`, API: `app/CONTRACT.md` section 5). It is started from a terminal and used from the browser: `dispatcher.py` is the code-only event loop, `agent.py` the Haiku tool loop, `commands.py` the slash commands. `fodgate/agent.py` is the process entry point with the display-only console.
- Later flows live in the same modules: Handover and break (`commands.py`, `Dispatcher.start_handover` / `complete_handover`), not found and still there (`Dispatcher.record_report`, `hold_still_present`), unusable views and debris outside the envelope (`Dispatcher._task_text`, `outside_recipient`, `/reported`). Tests: `tests/test_handover.py`, `test_not_found_still_there.py`, `test_other_work.py`. The chat page's buttons are in `app/frontend/src/lib/taskActions.ts`; the mock copy of the dispatcher is `app/frontend/src/mock/dispatch.ts` and must be changed with the backend.
- Agent evals: `app/backend/fodgate/agent_evals.py`, scenarios in `app/data/agent-evals/` (README there), suite tests in `tests/test_agent_evals.py`. `fodgate/synthetic.py` builds the tiny scenes that the tests and the evals share.
- The dashboard's read-only views of the agent: Crew and Tasks (`app/frontend/src/components/CrewTasksPage.tsx`, `lib/crewTasks.ts`, `store/boardStore.ts`, route `#/crew`, from `GET /api/agent/board`) and the Turn record (`components/TurnRecord.tsx`, `lib/turnRecord.ts`, backend `app/backend/fodgate/turn_record.py`, `GET /api/turns/{turn_id}/record`). Keep both read-only. Mock sample data for them: `src/mock/crewSample.ts` and `src/mock/turnRecord.ts`. Tests: `src/lib/crewTasks.test.ts` (Task order, unknown Task types, links), `src/store/boardStore.test.ts`, `src/lib/turnRecord.test.ts`, `src/mock/crewSample.test.ts`, `src/mock/turnRecord.test.ts`, `src/route.crew.test.ts`, and `app/backend/tests/test_turn_record.py`.
- `prototypes/` is throwaway evidence. Do not import from it or extend it.
- `issues/` is the decision record. Each file is one closed decision; `0001-map-...md` indexes them.

## Commands

```bash
./setup.sh                                     # install everything, build the dashboard
./run.sh                                       # app on http://localhost:8000
./run-agent.sh                                 # the same app with the always-on agent and its live log
cd app/backend  && uv run python -m fodgate.rehearse --keyless   # agent demo over HTTP, two scripted people, no cost
cd app/backend  && uv run pytest               # must pass before you finish
cd app/frontend && npm test && npm run build   # must pass before you finish
cd app/frontend && npm run dev:mock           # dashboard with no backend; Crew and Tasks at http://localhost:5173/#/crew
cd app/backend  && uv run python -m fodgate.evaluate --dry-run   # local detection scoring, no API cost
cd app/backend  && uv run python -m fodgate.agent_evals --dry-run     # agent evals with a scripted stand-in, no API cost
cd app/backend  && uv run python -m fodgate.rehearse_flows --keyless  # Handover, not found, still there, glare, outside: no API cost
```

## Rules that must hold

- **Severity, rule ID and Verdict are computed in code** (`app/backend/fodgate/rules.py`, `report.py`) from `app/data/rules/fod-rules.json`. Never take them from model output.
- **Nothing clears without a person.** No code path may confirm a Finding, sign off an Inspection or change a Verdict on the model's say-so. Neither the assistant nor the always-on agent has a tool that does any of these.
- **In `fodgate/dispatch/`, only `commands.py` may call `confirm_finding`, `confirm_all`, `checked_by_eye` or `signoff`**, and only as the signed-in person: a slash command, or that person's yes to a proposal. A Report ("done") never closes a Finding. `tests/test_dispatch_rules.py` pins this and the agent's tool list; if you add a tool, it must not be able to clear anything.
- **Code, not the model, takes the step after a Report.** After a done or not-found Report, code creates the proposal (or, for a HOLD, tells the Ramp Lead and offers a new photo). In a Handover, code writes the brief and moves the Tasks; timers are not restarted. The report draft for debris outside the envelope is a code template. Do not move any of these into the model.
- **If you change agent behaviour, run the agent evals** (`--dry-run` always; live with `--max-usd 0.50` when the prompt or tools changed) and add a scenario for the new behaviour. Never loosen a scenario to make it pass; a safety violation is reported to the team at once.
- **Role comes from the roster on the server** for `/api/agent/*`. Never read a role from a request body or from message text there.
- **The HOLD alert is sent by code**, at once, to every Ramp Lead on shift. It must not depend on a model call. Idle time makes no model calls: wake on store events and code timers, never poll the model.
- **Only a Ramp Lead confirms a HOLD**, in two steps (acknowledged, then removed), and "removed" clears it only if a re-inspection of that Angle is clean.
- **An unusable Angle makes the Verdict INCOMPLETE**, never ALL CLEAR. A failed analysis marks the Angle unusable.
- **Models:** `claude-haiku-5-5` by default; `claude-sonnet-5-5` only behind `FOD_ESCALATION`. Opus is not used; the backend rejects it. The always-on agent runs on `claude-haiku-5-5` only.
- **A Report and a Confirmation stay separate.** The Turn record shows them as different kinds of entry; never merge them. New Task types must show by name on Crew and Tasks without a dashboard change. New Task log events (`task_*`, `handover*`) reach the Turn record by name; the record tracks who holds a Task only for events whose data names a `to`.
- **UI changes follow `spec/design-system.md`.** Use the tokens and the existing components; no literal colours outside `:root` of `styles.css`; saturated colour only for HOLD, REMOVE, ADVISORY and INCOMPLETE, always with a text label and an icon; new pages go inside `AppShell` and keep the Gate strip visible. If a change needs to break one of these, change the design system and `src/design.test.ts` in the same change and say so.
- **Real photographs only**, openly licensed, with attribution recorded in `app/data/ATTRIBUTION.md` and shown in the UI.

## Money and secrets

- The team's API balance is small. Tests mock Claude and must stay that way. Set `FOD_MAX_SPEND_USD` when running anything live, and prefer `--dry-run` and `--limit N` on the scoring script.
- `FOD_MAX_SPEND_USD` covers the pipeline, the assistant and the agent. Anything new that calls Claude must call `llm.spend_allowed()` before each request and `llm.add_spend()` after. One scripted agent demo costs about $0.004; `FOD_AGENT=code` runs it without the model.
- Claude results are saved by content hash in `app/var/cache/` and committed, so the demo replays for free. If you change a prompt, a schema, a crop size or the model, the saved results stop matching: re-run the demo and the scoring once with a key, then commit the new cache files.
- The key lives in `.env`, which is ignored. Never print, log or commit it.

## Data

- Scenes are generated by `app/tools/` from the manifests in `app/tools/manifest/`. Do not hand-edit files under `app/data/scenes/`; change the manifest and rebuild, then run `app/tools/validate_data.py`.
- Detector thresholds were fixed on a separate 22-frame set. Do not tune them on the 30 scoring Inspections in `app/data/testset.json`.

## Known gaps

- The equipment-inside-the-restraint-line check (FOD-R9) has little test evidence; the lines were drawn by eye on stand-in photos.
- Accuracy numbers come from pasted debris and simulated reference images.
- No real sign-in. The dashboard's role switch stands in for it, and its endpoints trust the role the browser sends. The always-on agent's endpoints use a roster PIN and resolve the role on the server, which narrows the gap without closing it.
- Agent wakes took 3 to 8 seconds in the agent evals and 7 to 24 seconds in the first rehearsal.
- The agent's wording check refuses any message containing phrases such as "is clear", including a correct refusal like "I can't tell Okafor the gate is clear". The agent rewords and nothing unsafe is sent, but a wake can be wasted (see the issue list).
- No camera scene has a real "still there" photo; the tests use a synthetic one and `rehearse_flows` derives one at run time.
- The recipient for debris outside the envelope is chosen from words in the location text (movement area, taxiway, runway, zipper), not from geometry. The person can always pick the other recipient when recording.
- The mock dispatcher marks free-text Reports `via: "agent"` where the backend says `free_text`, and does not mirror the model's Handover summary.
- Crew and Tasks and the Turn record were checked in a browser in mock mode and against the real backend with `FOD_AGENT=code`. In mock mode at load, the sample Tasks are not links (no mock Inspection holds their Findings at demo time 0).
- The Turn record's agent cost leaves out agent wakes for messages people typed, because those belong to no Turn. The record's `cost.note` says how many were left out.
- A Task links to its Finding only through `inspection_finding_id` on the Board. If a change to the dispatcher drops that field, links fall back to the Inspection.
- No live cameras, schedule feed or integrations. Each Inspection report can be exported as JSON.
