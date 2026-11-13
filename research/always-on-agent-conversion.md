# Converting the Gate FOD PoC into an always-on terminal agent

Date: 2026-11-13. Read-only study: no code was changed, nothing was run from the cloned repository, no API calls were made.

**Recommendation in one paragraph.** Build option B: keep the existing backend untouched as the authority, and add a thin, event-driven dispatch loop of our own inside the same process, using the plain Messages API tool loop the project already has in `assistant.py` (Haiku 5.5). The repository we were pointed at (`rosscrooke/always-on-agent`) is **not a framework**: it contains no code, only synthetic data for a hackathon exercise, so there is nothing to adopt. The agent proposes and routes work; code enforces every rule; only an identified human's own command creates a Confirmation.

How to read this document: statements tagged **[Verified]** were read directly in a file (path and line given). Statements tagged **[Inferred]** are my interpretation or design judgement. Cost figures are estimates until measured.

---

## 1. The "framework": what `rosscrooke/always-on-agent` actually is

Cloned to `/private/tmp/claude-501/-Users-vinothshanmugam-code-anthropic-basecamp-faa-fod/5c5e895c-d4e1-4cc3-a487-481894efcd4a/scratchpad/aoa/repo` (paths below are relative to that directory). Every file was read in full; it is 14 files, about 16 KB.

### 1.1 Verified facts

| Question | Finding | Evidence |
|---|---|---|
| What is it? | A "Synthetic Enterprise Repo": "the working environment for the Always-On Ops Agent. Fork or clone this into a GitHub repo on your own account, then point your routine at it." | `README.md:1-3` |
| Contents | `issues/` (5 synthetic incident JSON files), `runbooks/` (3 Markdown playbooks), `deploys/recent.json` (5 deploys), `contracts/` (3 vendor contracts), `compliance-policy.md` | `README.md:7-11`; file listing |
| Code | **None.** No source files, no package manifest, no lockfile, no scripts, no configuration. GitHub reports `language: null`. | file listing; GitHub API repo metadata |
| Agent loop | Not present. The only mention of an agent is that a "routine" is pointed at the repo "via the Routines UI". | `README.md:3`, `README.md:24` |
| Triggers / scheduling | Not present in the repo. One sentence implies a recurring job: "The compliance routine scans `contracts/` against this policy and opens issues for any violations." | `compliance-policy.md:3` |
| Memory / state | Not present. The data files themselves are the state: issues have `status`, `severity: null`, `assignee: null`, `comments: []` fields meant to be filled in. | `issues/PROD-4521.json:4-11` (all five issues have the same shape) |
| Tools | None defined. | whole repo |
| How humans talk to it | Not defined. No terminal, Slack or SMS channel. The runbook text mentions paging a channel ("page #payments-oncall") only as incident-handling prose. | `runbooks/payment-service-degraded.md:19-21` |
| Roster / multi-agent | None. No roster, shift, assignment or acknowledgement concept. `assignee` is a null field on issues. | `issues/*.json:7` |
| Model / SDK | None named anywhere. | whole repo |
| Dependencies | None. | whole repo |
| Tests | None. | whole repo |
| Docs | One 25-line README. It references a parent folder that is not in this repo: `../partner-basecamp-hackathon/01-always-on-ops-agent/synthetic-repo/*`. | `README.md:21` |
| Licence | **None.** No LICENSE file; GitHub API returns `license: null`. | file listing; GitHub API |
| History | One commit: `84b552c`, 2026-05-20, "Add files via upload". One branch (`main`), no tags. | `git log` |
| Activity | 31 stars, 225 forks, created 2026-05-20. Four pull requests from forks, none merged (PR 8 "Add Always-On Ops Agent exercise details and implementation plan", closed unmerged; PR 9 "triage and correlation features", open). | GitHub API |
| Data provenance | "All data is fictional." | `README.md:13` |

The three scenarios the data supports can be read off the files: incident triage with deploy correlation (`issues/` + `deploys/recent.json` + `runbooks/`; for example `issues/PROD-4521.json:10` cites `PaymentService.java:142`, which `runbooks/payment-service-degraded.md:16` names as a known bug, and `deploys/recent.json:4-16` shows a deploy 14 minutes earlier), and contract compliance drift (`compliance-policy.md` against `contracts/`, described as "Card C" in `README.md:10`).

### 1.2 Inferences

- **[Inferred]** "Routine" and "Routines UI" refer to Claude Code Routines (scheduled cloud agents run on a cron schedule or trigger against a GitHub repository). The repo does not say so. If true, the "always-on" in the exercise means "a cloud agent that wakes on a schedule and works on a git repo", not a process that runs continuously in a terminal.
- **[Inferred]** The actual exercise instructions (scenario cards, prompts) live in the unpublished `partner-basecamp-hackathon/01-always-on-ops-agent/` folder referenced at `README.md:21`. The same author's sibling repos (`specialist-swarm`, `institutional-memory`) do contain Python scripts and scenario cards, which suggests this repo is one card's data pack. I listed those repos' file names only; I did not read their contents.
- **[Inferred]** The unmerged pull requests are attendees' exercise submissions, not framework code. I did not review their contents.

### 1.3 What can be borrowed, and what is risky

Borrowable as *patterns* only (there is no code to reuse):
1. **State as plain records the agent annotates**: issues with `severity`, `assignee`, `comments` to fill in. Our tasks table is the same idea.
2. **Runbooks as retrievable procedure text**: our equivalent is `spec/fod-rules.md` / `fod-rules.json`, already loaded by `get_rule`.
3. **A scheduled "scan and open issues" job**: maps to a shift-handover or end-of-shift summary.

Risks:
- **No licence.** Default copyright applies; copying its files into our repo is not clearly permitted. We need none of them.
- **No pinned behaviour.** A plan that says "based on this framework" has no API, loop or channel to build on. Anyone on the team expecting a `pip install` will lose time.
- **Wrong shape for us if the Routine reading is right** [Inferred]: a cloud routine cannot reach a laptop's `localhost:8000`, cannot see the local images or SQLite file, wakes on a schedule rather than on events, and has no channel to named people. A ramp HOLD needs a reaction in seconds.
- **Hard-rule mismatch.** The exercise's agent sets severity itself (`"severity": null` to be filled, `issues/PROD-4521.json:5`, with a "Severity guide" in prose at `runbooks/payment-service-degraded.md:18-21`). Our rule is the opposite: severity is computed in code. That pattern must not be copied.
- The repo contains no executable content and no instructions aimed at an agent beyond the README's shell snippet (`README.md:17-24`), which was not run.

**Consequence for the task brief.** The brief says to fall back to the Claude Agent SDK if the repo is "unreachable or empty". It is reachable and not empty, but it is empty *of framework*. The design below is therefore based on Anthropic's own surfaces, using current facts from the `claude-api` skill (model table cached 2026-11-03).

---

## 2. Mapping the PoC onto an always-on agent

### 2.1 What exists today (all [Verified] in the project)

| Piece | Where | Relevant behaviour |
|---|---|---|
| Pipeline | `app/backend/fodgate/pipeline.py:318` `run_inspection` | Deterministic stages; Haiku only decides FOD-or-not per Candidate |
| Rules | `rules.py:64` `severity`, `rules.py:103` `role_may_confirm`; `report.py:32` `compute_verdict` | Severity, rule ID, Verdict and role permission in code. Roles table: `ramp_agent: [REMOVE, ADVISORY]`, `ramp_lead: [HOLD, REMOVE, ADVISORY]` (`app/data/rules/fod-rules.json`) |
| Confirmation rules | `workflow.py:120-171` | Role check (`:134`), HOLD must be acknowledged first (`:144-146`), HOLD "removed" re-inspects and records only if the object is gone (`:152-171`) |
| Sign-off | `workflow.py:213-232` | Refused with open Findings or unresolved unusable Angles |
| Checked by eye | `workflow.py:198-211` | Ramp Lead only |
| Unusable means INCOMPLETE | `report.py:43-44`; failed run marks all Angles unusable `workflow.py:320-335` | Never ALL CLEAR |
| Queue | `workflow.py:445-471` | "Needs a human": HOLDs first, then minutes to pushback |
| Scheduler | `demo.py:77-91` | A clock thread fires scripted events; departures wait for sign-off (`:91`, `workflow.py:372-383`) |
| Store | `store.py:16-40` | SQLite: turns, inspections, findings, confirmations (append-only), events |
| Event log | `store.py:158` `add_event`; called from `workflow.py:351` | Every state change already writes an event row with an auto-increment id |
| Assistant | `assistant.py:47-61` tools, `:157-215` loop | Haiku manual tool loop, five read-only tools, injectable `create` for tests |
| Spend guard | `llm.py:298-305`; `run.sh` sets `FOD_MAX_SPEND_USD=1.00` | Process-wide stop when the cap is reached |
| Model guard | `config.py:15`, `:56-60` | Only Haiku 5.5 or Sonnet 5.5 accepted |
| Identity | `api.py:29-31`; `AGENTS.md:48` | `role` and `name` are taken from the request body; "No sign-in: the role switch stands in for it" |

### 2.2 Reused as-is

- `pipeline.py`, `rules.py`, `report.py`, `detect/`, `llm.py`, `scenes.py`: no change.
- `workflow.py`: no change to any rule. It stays the **only** code that writes Confirmations.
- `store.py`: existing tables unchanged; new tables added beside them.
- `demo.py`: unchanged; it remains the source of scripted Turns for the demo. In production the same `begin_turn / start_inspection / block_in / try_depart` calls would be fed by a schedule feed.
- `api.py` and the dashboard: unchanged and still served, as a second view of the same state (useful on the projector during the demo).
- `assistant.py`: its loop shape, error mapping (`:218-240`) and the five read tools are reused by the dispatch agent.

### 2.3 What becomes an agent tool

Read tools (wrap existing calls): gate state and queue (`workflow.py:435`), a report summary (`assistant.py:73`), a Finding, a rule, the Turn's events.
Action tools (new, all non-clearing): assign a task, send a message, start an escalation, propose a re-inspection, propose a Confirmation *to a named human*, draft the outside-boundary report (existing), write a handover brief.
**Not tools, ever:** `confirm_finding`, `confirm_all`, `checked_by_eye`, `signoff`. These stay reachable only from a human's own command.

### 2.4 What is new

| New piece | Purpose | Decided by |
|---|---|---|
| Roster and shifts | Who is on, in which role, covering which Gates, with a sign-in PIN | Data + code |
| Tasks | A unit of work for one person: "remove", "walk and verify", "acknowledge HOLD", "check by eye", "report to Ramp 1 control", "sign off" | Agent proposes; code validates role, shift, Gate |
| Task acknowledgement | The person accepts the task ("on it"). Distinct from the HOLD Confirmation step "acknowledged", which stays Ramp Lead only (`spec/dashboard-ux.md:11`) | Human command |
| Report-back channel | A terminal client per person; free text or slash commands | Human |
| Re-evaluation triggers | An inspection completes; a person reports; a timer fires; a re-inspection still shows the object; a Turn nears pushback; someone goes off shift | Code raises the event; agent decides the next routing step |
| Escalation timers | For example a HOLD not acknowledged within N minutes, or open work with pushback closer than M minutes | **Code** (a timer table and the existing clock), not the model |
| Shift handover | Outgoing Ramp Lead hands open tasks to a named incoming lead, who must accept | Agent writes the brief; code moves the tasks; humans hand over and accept |

One distinction carries the whole design and matches the team's own example ("Ramp Agent Kim: remove the bolt at T5 ENG-R"):

> A **Task** is physical work and can go to anyone suitable. A **Report** is what that person says happened. A **Confirmation** is the record that closes a Finding, and it keeps its existing rules.

So a Ramp Agent can be sent to pick up a HOLD object and can report "done", but that report does not close the Finding. The Ramp Lead still acknowledges, then records "removed", which makes the code re-photograph the Angle (`workflow.py:152-171`).

### 2.5 The terminal experience

One process, three kinds of terminal pane:
- **Agent console** (`python -m fodgate.agent`): the always-on process. Shows a live log of events, the agent's decisions, tasks, timers and running cost. A supervisor can type here.
- **Person consoles** (`python -m fodgate.join`): one per signed-in person. Shows only that person's messages and tasks; accepts slash commands and free text.

Mock transcript: the scripted `demo-hold` scene at Gate T5 (a hammer in the ENG-R zone, HOLD, and a bag tag by the belt loader at CARGO, REMOVE; `app/data/demo/timeline.json`, Turn `T5-DL1776`). Two people: **Kim (Ramp Agent)** and **Okafor (Ramp Lead)**. Lines starting `[code]` are deterministic; lines starting `agent>` are model-written text; nothing else is the model.

```
=== AGENT CONSOLE ===========================================================
04:05 [code]  T5 DL1776 pre-departure Inspection done. Verdict FINDINGS (advisory).
              F1 HOLD   ENG-R  FOD-R1  hammer on pavement, right engine intake zone
              F2 REMOVE CARGO  FOD-R3  bag tag by belt loader
              Pushback in 1.8 min.
04:05 [wake]  trigger=inspection_completed  model=haiku-5-5
04:05 agent>  assign_task(K-12 "acknowledge HOLD F1", to=okafor)      [code: ok, role ramp_lead]
04:05 agent>  assign_task(K-13 "remove bag tag F2 at T5 CARGO", to=kim) [code: ok]
04:05 [code]  timer set: K-12 unacknowledged in 30 s -> escalate
04:05 [cost]  wake $0.0016   session $0.0214

=== OKAFOR (Ramp Lead) ======================================================
04:05 agent>  HOLD at T5 ENG-R: hammer in the right engine intake zone (FOD-R1).
              DL1776 pushes in 1.8 min. Nothing moves until you clear this.
              Type /ack F1 when someone is going to it.

=== KIM (Ramp Agent) ========================================================
04:05 agent>  Task K-13: remove the bag tag by the belt loader, T5 CARGO (REMOVE).
kim>   /ack F1
04:05 [code]  Refused (role_not_allowed): only a Ramp Lead can confirm a HOLD Finding.

=== AGENT CONSOLE ===========================================================
04:06 [timer] K-12 not acknowledged after 30 s. Escalation level 1.
04:06 agent>  send_message(okafor, "Second call: HOLD F1 at T5 still unacknowledged, 1.3 min to pushback")
04:06 agent>  send_message(supervisor, "T5 HOLD unacknowledged by Ramp Lead Okafor for 30 s")

=== OKAFOR ==================================================================
okafor> /ack F1
04:06 [code]  Recorded: F1 acknowledged by Okafor (Ramp Lead).
okafor> send kim, she's closest
04:06 [wake]  trigger=human_message
04:06 agent>  assign_task(K-14 "remove the hammer at T5 ENG-R and report back", to=kim)

=== KIM =====================================================================
04:06 agent>  Task K-14: remove the hammer at T5 ENG-R (HOLD). Report back here when done.
kim>   got the hammer, its in the fod bin. bag tag picked up too
04:07 [wake]  trigger=human_message
04:07 agent>  Logged your report on K-14 (hammer). I have told Okafor; a Ramp Lead records HOLDs.
              For the bag tag: record F2 as removed by you?   [y / n]
kim>   y
04:07 [code]  Recorded: F2 removed, confirmed by Kim (Ramp Agent).

=== OKAFOR ==================================================================
04:07 agent>  Kim reports the hammer at T5 ENG-R is removed (K-14). Only you can record it.
              /removed F1 re-photographs ENG-R; the HOLD clears only if the new photo is clean.
okafor> /removed F1
04:07 [code]  Re-inspecting T5 ENG-R ...
04:07 [code]  New photo is clean. Recorded: F1 removed, confirmed by Okafor (Ramp Lead).
04:07 agent>  T5 has no open Findings. Ready for your sign-off. 0.6 min to pushback.
okafor> /signoff T5
04:07 [code]  Inspection signed off by Okafor (Ramp Lead). T5 confirmed clear.

=== AGENT CONSOLE ===========================================================
04:07 [code]  Tasks K-12, K-13, K-14 closed. Timers cancelled. T5 DL1776 departed.
04:07 [idle]  no open tasks at T5. Waiting for events. Session cost $0.0297.
```

Two branches worth showing if time allows: Kim replies "can't find it" (the agent proposes `not_found_on_walk` for a REMOVE, or for a HOLD tells the Ramp Lead and proposes a re-inspection); and the re-photograph still shows the object (the code leaves the HOLD open, `workflow.py:160`, and the agent reassigns and escalates).

---

## 3. Design options

### Option A: adopt the framework, plug our backend in as tools

There is no framework to adopt (section 1). The nearest real reading is "do what the exercise does": a Claude Code Routine pointed at a GitHub repo. [Inferred] That would mean exporting our state to files in a repo (like their `issues/*.json`), and having a scheduled cloud agent read them and write assignments back as files or comments.

- **Effort:** 8 to 12 hours, most of it on plumbing that adds nothing: exporting state, syncing a repo, getting people's replies into the repo.
- **Risk:** high. Minute-scale or slower wakeups for a hazard that needs seconds; the cloud sandbox cannot reach the laptop backend or its images; no channel to named people; rule enforcement would rest on prompt text unless every write is re-validated on the laptop; no licence on the source repo; Routine billing and limits are unknown to us and unverified here.
- **Demo:** a repo where JSON files gain `assignee` values every few minutes. Not a terminal agent, not live.

### Option B: keep our backend, add a thin always-on loop of our own

A dispatcher thread in the backend process (the same pattern as `DemoPlayer`, `api.py:62-70`) waits on the events table. Most events are handled by code. When judgement or language is needed, it runs one short, stateless Haiku tool loop (the `assistant.py` pattern) whose tools can only read, assign, message and propose. People connect from terminal clients.

Two ways to write the loop, both on Anthropic's own surfaces:

| | Plain Messages API manual loop (recommended) | Claude Agent SDK |
|---|---|---|
| Fit | Identical to `assistant.py:179-204`, already tested with a fake `create` (`tests/test_assistant.py`) | A separate product: the Claude Code harness with built-in file, shell and web tools (per the `claude-api` skill's surface table) |
| New dependencies | None (`anthropic>=1.0` is already in `pyproject.toml`) | A new package and its runtime |
| Safety surface | Exactly the tools we define | Built-in tools must be switched off; a ramp dispatcher has no use for shell or file access |
| Cost control | We own every call, so the spend cap and model guard apply directly | Harness prompt overhead per wake is larger and not ours to trim |
| Verified here | Yes, against project code and the skill | **No.** The skill does not cover Agent SDK code; I did not verify its current API |

The SDK's Tool Runner (`client.beta.messages.tool_runner` with `@beta_tool`) is a reasonable middle path, but it is a beta helper and would replace 25 lines we already have and test.

- **Effort:** 12 to 16 person-hours for the core (two people, one day): about 3 h data model and dispatcher, 3 h agent loop and tools, 3 h terminal client and identity, 2 h timers and escalation, 2 h tests, 1 to 2 h demo script and rehearsal. Handover adds about 2 h.
- **Risk:** low to medium. All hard rules stay where they are. The main risks are scope (terminal UX polish) and letting free-text interpretation creep into Confirmations (handled in section 4.2).
- **Demo:** the transcript in 2.5, live, with the existing dashboard beside it showing the same Gate turning from HOLD to confirmed clear.

### Option C: hybrid

Option B for everything live, plus one idea borrowed from the exercise: a **scheduled, non-urgent job** that reads the day's records and produces a shift report (open items, false-alarm reasons, time-to-acknowledge per HOLD, repeat locations). Locally this is a timer event that runs one Haiku call over the append-only confirmations and events tables. It could later be a Routine or a Managed Agents scheduled deployment (cron, minute granularity, per the skill) if the records are exported somewhere a cloud agent can read.

- **Effort:** B plus 2 to 3 hours.
- **Risk:** same as B; the extra piece is read-only.
- **Demo:** B, ending with "and at shift change it writes this handover", shown as text.

### Recommendation

**Option B, with the manual Messages API loop, and C's handover brief as the stretch goal.** It is the only option that produces a terminal agent reacting within seconds, it adds no dependency, it reuses a loop that is already tested, and it leaves every safety rule in code that the README reports as covered by 142 backend tests (`README.md:101`; not run in this study). Be plain with judges that the linked repository is a data pack and that the "always-on" behaviour is our own event-driven loop.

---

## 4. Safety and cost

### 4.1 How the hard rules stay enforced

Principle: **the agent proposes and routes; code and humans decide.**

| Hard rule | Enforcement with the agent in place |
|---|---|
| Severity and Verdict computed in code | Unchanged (`rules.py:64`, `report.py:32`). No tool takes a severity, rule ID or Verdict as input. Tasks copy severity from the Finding row; the model cannot set it. |
| Nothing clears without a human Confirmation | The agent's tool list contains no call into `confirm_finding`, `confirm_all`, `checked_by_eye` or `signoff`. Add a test like the existing `test_tools_are_exactly_the_five_read_only_ones` that pins the tool list, and a second test that no function in `fodgate/dispatch/agent.py` imports or references those four methods. |
| Only a Ramp Lead clears a HOLD | Unchanged (`workflow.py:134`). In addition the dispatcher refuses to assign an "acknowledge HOLD" or "sign off" task to anyone whose roster role is not `ramp_lead`. |
| HOLD removed needs a clean re-inspection | Unchanged (`workflow.py:152-171`). A person's report "done" on a HOLD task changes the task, not the Finding. |
| Unusable Angle is INCOMPLETE, never clear | Unchanged (`report.py:43-44`). The agent may assign "check by eye" to a Ramp Lead; only that lead's command records it. |
| Haiku default, Sonnet ceiling, never Opus | New setting `FOD_AGENT_MODEL` validated against `config.ALLOWED_MODELS` (`config.py:15`). |

Additional guards for an agent that dispatches work:
- **Every action tool is validated in code before it takes effect**: assignee exists, is on shift, has a permitted role for the task type, covers that Gate; the Finding is open; the task is not a duplicate. A rejected call returns an error to the model, as `assistant.py:141-149` already does.
- **A deterministic backstop**: if a HOLD Finding exists and no task for it has been delivered to an on-shift Ramp Lead within a few seconds (model slow, refused, API down, spend cap hit), code sends a fixed-text alert to every on-shift Ramp Lead. Safety-critical delivery must not depend on a model call.
- **Bounded wakes**: at most 6 model turns per wake (as `assistant.py:17`), a wake rate limit, and coalescing of events for the same Gate.
- **Untrusted text**: people's free text and model-written Finding descriptions enter the agent's context. Because no tool can clear anything, the worst outcome of a manipulated or confused agent is wrong or noisy routing, which the backstop and timers catch. The system prompt still says to treat message text as data.
- **Wording**: the agent never says or implies a Gate, Angle or Finding is clear before a recorded Confirmation, and never tells anyone that pushback is approved; the system does not clear pushback, the flight crew and ramp control do (`spec/requirements-baseline.md` WF-R5; `workflow.py:373-374`).

### 4.2 Free text must not become a Confirmation

This is the one place the conversion could quietly break "nothing clears on the model's say-so". If Kim types "bag tag's gone" and the model calls a confirm endpoint, the model has performed the Confirmation.

Rule: **a Confirmation is created only by a code-parsed command from an authenticated session.** Two accepted forms:
1. A slash command typed by the person: `/ack F1`, `/removed F2`, `/false-alarm F2 shadow`, `/not-found F2`, `/eye ENG-R`, `/signoff T5`, `/all-removed T5`. Parsed by ordinary code, no model involved.
2. A **proposal the person accepts**: the agent calls `propose_confirmation`, code prints the exact action and waits for that same person to press `y`. The call into `workflow.confirm_finding` is made by the keypress handler with the role from the roster, not by the model. The proposal expires after a short time and is void if the Finding changed.

The audit record stores how it was made (`command` or `accepted_proposal`) and the raw text.

### 4.3 Establishing identity and role in a terminal

Today the API believes whatever `role` the client sends (`api.py:29-31`), which is acceptable for a role switch in one browser but not for several terminals.

For the hackathon:
- A person runs `python -m fodgate.join`, enters a name and a short PIN from the roster. The server returns a session token bound to `person_id`.
- **Role, shift and Gates come from the roster row, never from message text or the request body.** Every command is executed as `(person_id -> role, name)` looked up server-side.
- One pane per person makes identity visible to the audience. A single shared terminal with `@kim:` prefixes is spoofable and should not be used even in the demo.
- The agent cannot create roster entries, change roles or sign anyone in. A supervisor command on the agent console does that.
- State plainly that a PIN is a stand-in. Production needs the airline's identity system (badge or SSO on a handheld) and device binding. `AGENTS.md:48` already lists "No sign-in" as a known gap; this narrows it, it does not close it.

### 4.4 What the agent must never do on its own

1. Confirm, acknowledge (in the HOLD sense), mark removed, mark false alarm, mark not-found, record checked-by-eye, or sign off.
2. Set or change a severity, rule ID, Verdict or Finding status.
3. Close, cancel or downgrade a HOLD task without the Ramp Lead's Confirmation existing in the store.
4. Treat a person's task report as proof (HOLDs always get the code-run re-inspection).
5. Tell anyone a Gate is clear or that an aircraft may move.
6. Assign HOLD acknowledgement, checked-by-eye or sign-off to a non-lead, or assign anything to a person who is off shift.
7. Send the outside-boundary report to Ramp 1 control or Airport Operations itself; it drafts, a person sends (as today, `assistant.py:56-58`).
8. Change the roster, shifts, PINs, timers' thresholds, the model, or the spend cap.
9. Start paid re-inspections without limit. Open question 3 covers whether it may start any.
10. Stay silent on failure: if it cannot route something, it must raise it to the supervisor console.

### 4.5 Model choice

- **Default `claude-haiku-5-5`**, effort `low` or `medium`, adaptive thinking left on (it is on by default on this model). The work is routing, extraction from short messages and short wording, which is what the skill describes Haiku 5.5 for.
- **Ceiling `claude-sonnet-5-5`** behind a setting, off by default, for example only for the handover brief. Note Sonnet 5.5 rejects forced `tool_choice` and `thinking: disabled`; use `tool_choice: auto` with strict tools as `assistant.py:41-44` already does.
- **Never Opus or Fable.** Enforced by `config.ALLOWED_MODELS`.
- Handle `stop_reason: "refusal"` (already done at `assistant.py:199`); Haiku 5.5 has no server-side fallback, so a refusal becomes "raise to supervisor".
- Do not change `temperature`, `top_p` or `top_k`; non-default values are rejected on Haiku 5.5.

### 4.6 Cost per hour at 5 Gates (estimate)

Prices used (skill table cached 2026-11-03, same as `llm.py:30-32`): Haiku 5.5 $0.10 input / $0.50 output per million tokens for prompts up to 100K tokens ($0.50 / $2.50 above that); cache reads at 0.1x input. Sonnet 5.5 $2 / $10.

Assumptions, all to be replaced by measured `usage` after the first run (the skill warns that token guesses are often off by 3 to 10 times):
- Real-time operation: 5 Gates, about 6 Turns an hour, so about 12 scheduled Inspections plus about 4 re-inspections an hour.
- One agent wake is about 2 model requests, each about 4,000 input tokens (system prompt, tool definitions, a state snapshot, the triggering message) and about 500 output tokens including thinking. That is about $0.0013 per wake uncached, a little less with the system prompt and tools cached.
- About 40 wakes an hour: about 10 Inspection results that need routing, about 25 human messages, about 5 timer or exception events.

| Component | Per hour |
|---|---|
| Inspections: 16 x $0.008 (measured, `README.md:66`) | about $0.13 |
| Agent wakes: 40 x about $0.0015 | about $0.06 |
| Idle time | $0.00 |
| **Total, Haiku** | **about $0.20 an hour; plan for $0.10 to $0.50** |
| Same with the agent on Sonnet 5.5 (20x on the agent part) | about $1.30 to $1.50 an hour |

For contrast, waking Haiku on a 5-second poll with the same 4,000-token prompt is 720 calls an hour, about $0.45 an hour for the agent alone while nothing is happening, and about $9 an hour on Sonnet. One scripted 6-minute demo run should cost roughly $0.05 to $0.10 for the agent (Inspections replay from the committed cache for free), which fits inside the `run.sh` cap of $1.00.

### 4.7 Keeping it idle-cheap

- **Wake on events, never on a clock tick that calls a model.** The events table already records every state change with an increasing id (`store.py:158`). The dispatcher keeps a cursor and blocks on a `threading.Condition` that `add_event` notifies (or reads SQLite every 0.5 s, which costs nothing). No event, no call.
- **Code first.** Most events need no model: starting a timer, closing tasks when a Confirmation lands, the HOLD backstop alert, slash commands. The model is called only for free text, for choosing among several valid routings, and for writing text.
- **Timers are rows, fired by code** on the existing demo clock (`workflow.clock`), so they scale with the speed control and cost nothing while pending.
- **Stateless wakes.** Each wake builds a short prompt from the store; memory is SQLite, not a growing conversation. This avoids compaction and keeps every prompt far below the 100K-token point where Haiku 5.5 pricing rises fivefold.
- **Stable prefix.** Keep the system prompt and tool list byte-identical and first, with the changing state last, so the prefix can be cached (minimum cacheable prefix on Haiku 5.5 is 512 tokens per the skill; check `usage.cache_read_input_tokens`).
- **Close the spend-cap gap.** [Verified] The cap is only checked inside `LLM._guarded` (`llm.py:298-305`). The assistant path calls `add_spend` (`assistant.py:210`, `llm.py:234-240`), which adds to the total but never trips the stop, and `llm.available()` (`llm.py:262-270`) only reports a stop that `_guarded` has already set. An always-on loop built on the assistant pattern would therefore run past `FOD_MAX_SPEND_USD` unless a pipeline call happened to follow. The dispatcher must check the cap itself before every wake.
- **A visible meter.** Print per-wake and session cost on the agent console and store it per wake.

---

## 5. Build plan for option B

### 5.1 Ordered steps

1. **Decide the four blocking questions** (5.6, numbers 1 to 4). Thirty minutes, before any code.
2. **Data model.** Add the new tables to `store.py` and to `TABLES` so Reset clears them (`store.py:40`). Unit tests.
3. **Event wake-up.** Add a `Condition` notified by `Store.add_event`, and `events_after(cursor)`. No model yet.
4. **Dispatcher core, code only.** Thread started in the app lifespan beside the player (`api.py:64-70`). Deterministic handling: create tasks from a completed Inspection's open Findings and unusable Angles, close tasks when Confirmations land, HOLD backstop alert, timers. At this point the system already distributes work with fixed wording and no API spend.
5. **Sessions and person endpoints.** `POST /api/agent/join`, `GET /api/agent/inbox`, `POST /api/agent/say`, `POST /api/agent/command`. Role resolved from the roster server-side.
6. **Terminal clients.** `fodgate.join` (person) and `fodgate.agent` (console that also starts the server and dispatcher). Standard library only.
7. **Agent loop.** Copy the loop shape from `assistant.py:157-215` into `dispatch/agent.py` with the tool list in 5.3, an injectable `create`, the cap check, and the model setting. Tests with a fake `create`, as in `tests/test_assistant.py`.
8. **Proposals.** `propose_confirmation` plus the `y / n` handler that calls `Workflow` as the person.
9. **Escalation ladder** on timers; thresholds in a small JSON file.
10. **Tests that pin the rules** (5.5), then run the existing 142 backend tests unchanged.
11. **Demo timeline and rehearsal** with a recorded cost.
12. **Stretch:** shift handover; dashboard panel listing tasks.
13. **Docs in the same change** (`AGENTS.md:8-9` requires it): add a "Dispatch" section to `spec/`, the new endpoints to `app/CONTRACT.md`, and new terms to `GLOSSARY.md` (Task, Report, Roster, Shift, Escalation, Handover).

### 5.2 Files to add or touch

```
app/backend/fodgate/dispatch/__init__.py
app/backend/fodgate/dispatch/models.py       # task types, statuses, allowed role per task type
app/backend/fodgate/dispatch/roster.py       # roster, shifts, sessions, PIN check
app/backend/fodgate/dispatch/tasks.py        # create / assign / report / close; validation
app/backend/fodgate/dispatch/timers.py       # timer rows, due check on workflow.clock
app/backend/fodgate/dispatch/dispatcher.py   # event cursor, code-first routing, wake decisions, backstop
app/backend/fodgate/dispatch/agent.py        # SYSTEM prompt, TOOLS, wake(): Haiku tool loop
app/backend/fodgate/dispatch/commands.py     # slash-command parser -> Workflow calls as the person
app/backend/fodgate/agent.py                 # `python -m fodgate.agent`: server + dispatcher + console
app/backend/fodgate/join.py                  # `python -m fodgate.join`: person console
app/data/roster/roster.json                  # demo people, roles, Gates, PINs (demo only)
app/data/roster/escalation.json              # thresholds
app/backend/tests/test_dispatch_rules.py     # the safety tests in 5.5
app/backend/tests/test_dispatch_agent.py     # loop with a fake `create`
app/backend/tests/test_commands.py
```
Touched: `store.py` (tables, wake-up), `api.py` (mount `/api/agent/*`, start dispatcher), `config.py` (`FOD_AGENT_MODEL`, `FOD_AGENT`, thresholds path), `run.sh` (optional `--agent`), plus the three documents in step 13. `workflow.py`, `rules.py`, `report.py`, `pipeline.py`, `llm.py` and `assistant.py`: no change (optionally move the cap check into a shared helper in `llm.py`).

Run the dispatcher **in the backend process**. [Verified] `Workflow` serialises report updates with an in-process lock (`workflow.py:52`) and `Store` uses one connection with its own lock (`store.py:46-47`); a second process writing the same SQLite file would bypass both.

### 5.3 Tool list (the model's entire reach)

Read tools:
```
get_board() -> {gates: GateState[], queue: QueueItem[], open_tasks: Task[], on_shift: Person[]}
get_inspection(inspection_id: str) -> ReportSummary            # as assistant.Tools.get_report
get_finding(inspection_id: str, finding_id: str) -> Finding
get_rule(rule_id: str) -> {id, text, basis}
get_task(task_id: str) -> Task & {reports: Report[]}
list_people(gate: str | null, role: "ramp_agent" | "ramp_lead" | null) -> Person[]   # on-shift only
```
Action tools (each validated in code; none can clear anything):
```
assign_task(type: TaskType, gate: str, inspection_id: str, finding_id: str | null,
            angle: Angle | null, assignee_id: str, instruction: str) -> Task
reassign_task(task_id: str, assignee_id: str, reason: str) -> Task
send_message(to_id: str, text: str, task_id: str | null) -> {message_id}
log_report(task_id: str, kind: "accepted" | "done" | "not_found" | "blocked" | "note",
           source_message_id: str) -> Report            # records what a person said; never touches a Finding
propose_confirmation(to_id: str, inspection_id: str, finding_id: str,
                     outcome: "removed" | "false_alarm" | "not_found_on_walk",
                     false_alarm_reason: "shadow" | "marking" | "equipment_in_place" | "other" | null)
                     -> {proposal_id, expires_in_s}     # refused in code if the person's role may not confirm it
propose_reinspection(to_id: str, inspection_id: str, angle: Angle, reason: str) -> {proposal_id}
escalate(task_id: str, reason: str) -> {level, notified: str[]}      # targets come from escalation.json
draft_outside_boundary_report(inspection_id: str, recipient: "ramp_1_control" | "airport_operations",
                              finding_ids: str[]) -> str             # existing tool; text only
write_handover_brief(from_id: str, to_id: str) -> str                # text only; code moves the tasks
```
`TaskType = "ack_hold" | "remove" | "walk_and_report" | "check_by_eye" | "report_outside_boundary" | "sign_off"`. All tools are `strict: true` with `additionalProperties: false`, as in `assistant.py:41-44`.

Human commands (parsed by code in `commands.py`, never by the model):
```
/tasks   /accept K-14   /done K-14 [note]   /cant K-14 <reason>
/ack F1   /removed F1   /false-alarm F2 <reason>   /not-found F2   /all-removed T5
/reinspect T5 ENG-R   /eye T4 ENG-R   /signoff T5
/handover <person>   /accept-handover   /break   /back
```

### 5.4 Data model additions

```sql
CREATE TABLE people   (person_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                       role TEXT NOT NULL CHECK (role IN ('ramp_agent','ramp_lead','supervisor')),
                       gates TEXT NOT NULL,            -- JSON list
                       pin_hash TEXT NOT NULL);
CREATE TABLE shifts   (shift_id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL,
                       status TEXT NOT NULL,           -- on | break | off
                       started_at TEXT, ended_at TEXT, handed_to TEXT);
CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, person_id TEXT NOT NULL, created_at TEXT, last_seen TEXT);
CREATE TABLE tasks    (task_id TEXT PRIMARY KEY, type TEXT NOT NULL, gate TEXT NOT NULL, turn_id TEXT NOT NULL,
                       inspection_id TEXT NOT NULL,    -- updated to the Turn's latest Inspection
                       finding_id TEXT, angle TEXT,
                       severity TEXT,                  -- copied from the Finding by code, never from the model
                       required_role TEXT NOT NULL, assignee_id TEXT, instruction TEXT,
                       status TEXT NOT NULL,           -- assigned | accepted | reported | closed | escalated | cancelled
                       created_by TEXT NOT NULL,       -- agent | code | <person_id>
                       created_at TEXT, closed_at TEXT,
                       closed_by_confirmation_id INTEGER,   -- null unless a Confirmation closed it
                       escalation_level INTEGER NOT NULL DEFAULT 0);
CREATE TABLE task_reports (report_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                       by_person_id TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL,
                       raw_text TEXT, via TEXT NOT NULL);   -- command | free_text
CREATE TABLE messages (message_id INTEGER PRIMARY KEY AUTOINCREMENT, from_id TEXT NOT NULL, to_id TEXT NOT NULL,
                       text TEXT NOT NULL, task_id TEXT, at TEXT NOT NULL, delivered_at TEXT);
CREATE TABLE proposals (proposal_id TEXT PRIMARY KEY, to_id TEXT NOT NULL, action TEXT NOT NULL,   -- JSON
                       status TEXT NOT NULL,           -- pending | accepted | declined | expired | void
                       created_at TEXT, expires_at TEXT, answered_at TEXT);
CREATE TABLE timers   (timer_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, kind TEXT NOT NULL,
                       fire_t REAL NOT NULL, fired_at TEXT, cancelled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE agent_wakes (wake_id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_event_id INTEGER, trigger TEXT,
                       model TEXT, tokens_in INTEGER, tokens_out INTEGER, est_cost_usd REAL,
                       tool_calls TEXT, outcome TEXT, at TEXT);
```
The existing `confirmations` table gains nothing structural; put `via` and `proposal_id` in its existing `data` JSON column (`store.py:142-148`).

Design point to verify in a test: [Inferred from `workflow.py:242-248` and `report.py:36-38`] a re-inspection creates a new Inspection that becomes the Turn's latest, and sign-off and departure look at the latest (`workflow.py:378-379`). Tasks must therefore follow the Turn and re-point to the latest Inspection, and a Confirmation typed against an older Inspection after a re-inspection must be redirected or refused, otherwise a Finding could be closed on a superseded report while its carried copy stays open.

Default escalation ladder (code; thresholds in demo seconds for the demo, minutes in real use):
1. HOLD not acknowledged by the Ramp Lead in 30 s: repeat to that lead, notify the supervisor.
2. Still unacknowledged at 60 s, or any open HOLD with pushback under 2 minutes: alert every on-shift Ramp Lead and the supervisor console.
3. Task accepted but no report in N: ask once, then offer reassignment to the lead.
4. Re-inspection still shows the object: reopen the removal task, raise one level.
The system never holds or releases a pushback; escalation only tells people (`workflow.py:373-374`).

### 5.5 Tests that must exist before the demo

- The agent's tool names equal the list in 5.3 exactly.
- No tool handler reaches `confirm_finding`, `confirm_all`, `checked_by_eye` or `signoff` (assert with a spy `Workflow`).
- With a fake model that tries everything, no Confirmation row is ever written without a human command or accepted proposal.
- `propose_confirmation` for a HOLD to a Ramp Agent is refused; `/ack` on a HOLD by a Ramp Agent returns `role_not_allowed`.
- A "done" report on a HOLD task leaves the Finding open.
- A HOLD with the model unavailable still reaches every on-shift Ramp Lead (backstop).
- The spend cap stops wakes; idle time makes zero model calls.
- Role in a request body is ignored; the roster role is used.
- All existing backend tests pass unchanged, with Claude mocked (`AGENTS.md:35`). I did not run them in this study.

### 5.6 Demo script (about 3.5 minutes)

Layout: left half, three terminal panes (Agent console, Kim, Okafor); right half, the existing dashboard. Use a short dedicated timeline containing the T5 `demo-hold` Turn and one clean Turn, at 2x.

| Time | Action | Point made |
|---|---|---|
| 0:00 | "This is the PoC you saw as a dashboard. Now it runs as an always-on agent with a crew." Show the roster; Kim and Okafor sign in with PINs. | Named people, roles from the roster |
| 0:25 | Press Play. Agent console sits at "Waiting for events", cost counter not moving. | Idle costs nothing |
| 0:45 | T5 pre-departure Inspection lands: hammer at ENG-R (HOLD), bag tag at CARGO (REMOVE). Agent messages Okafor and assigns Kim the bag tag. | Detection to distribution in seconds; severity came from code |
| 1:10 | Kim types `/ack F1`. Refused. | Only a Ramp Lead touches a HOLD |
| 1:20 | Wait for the 30 s timer. Agent re-pings Okafor and notifies the supervisor. | Escalation is a code timer, not a model poll |
| 1:40 | Okafor `/ack F1`, then types "send kim, she's closest". Agent assigns Kim the walk. | Plain language in, structured task out |
| 2:00 | Kim: "got the hammer, bag tag picked up too". Agent logs the report, asks Kim to confirm the bag tag (`y`), and tells Okafor only he can record the HOLD. | A report is not a Confirmation; the agent proposes, the person decides |
| 2:30 | Okafor `/removed F1`. Code re-photographs ENG-R; clean; recorded. Dashboard tile changes. | The system looks again before believing anyone |
| 2:50 | Okafor `/signoff T5`. Tasks close, timers cancel, Turn departs. | Nothing cleared without a person |
| 3:05 | Show the audit trail for T5 and the session cost line (a few cents). | Record and cost |
| 3:20 | Stretch: Okafor `/handover <name>`; show the brief. State the limits: stand-in photos, PIN is not real sign-in, the linked repo was a data pack and the loop is ours. | Honesty about gaps |

Fallback if the API is unavailable on stage: step 4's code-only dispatcher still distributes the HOLD and the slash commands still work; only free-text interpretation is lost. Rehearse that path once.

### 5.7 Open questions for the team

1. **Framework expectation.** Is using the linked repository a judging requirement, or only a suggestion? It has no code. If a Routine is required, option C's shift report is the natural place for one.
2. **Who may do the physical removal of a HOLD object?** This plan lets a Ramp Agent be sent, with the Ramp Lead still acknowledging and recording. Does that match the intended reading of WF-R5 and `spec/dashboard-ux.md:11` ("Acknowledged means someone is going to it")?
3. **May the agent start a re-inspection itself?** RU-5 says "any role can request a re-inspection", but the agent is not a role and `workflow._actor` only accepts the two human roles (`workflow.py:38-43`). Re-inspection never clears anything, but it costs money and creates a new Inspection that needs sign-off. Default here: the agent proposes, a person accepts.
4. **Spec change.** Adding roster, tasks and terminal sign-in changes approved behaviour (UI-5 in particular). Who approves the new "Dispatch" section, and does `app/CONTRACT.md` ("Do not change this file", line 3) still apply now that the parallel build is finished?
5. **Escalation ladder.** What are the real thresholds, and who is the last rung (duty manager, Ramp 1 control)? Does an unacknowledged HOLD near pushback notify anyone outside the ramp crew? The PoC must not imply it holds the aircraft.
6. **Is the dashboard kept?** This plan keeps it as a second view. If judges want terminal only, the photo crops, which are the strongest evidence, need another way to be seen (a link printed in the terminal).
7. **Channels beyond the terminal.** Is terminal enough, or is Slack or SMS expected? A channel adapter is one small interface (`send`, `receive`), but any outside service sends names and gate details off the laptop and needs its own identity mapping.
8. **Identity.** Is a PIN acceptable for the demo, and what is the production story (badge, SSO, handheld)?
9. **Model for the agent.** Haiku only, or allow `FOD_AGENT_MODEL=claude-sonnet-5-5` for the handover brief?
10. **Budget.** What spend is allowed for building and rehearsing this? Measured cost should replace the estimates in 4.6 after the first live run.
11. **Break and absence.** If the only on-shift Ramp Lead goes on break with a HOLD open, what should happen? Proposed: `/break` is refused while that person holds an open HOLD task unless handed over.

---

## Sources

- Framework repository, cloned 2026-11-13, commit `84b552c`: every file read; paths and lines cited inline. GitHub API metadata for stars, forks, licence, pull requests.
- Project files read: `README.md`, `AGENTS.md`, `GLOSSARY.md`, `spec/architecture.md`, `spec/requirements-baseline.md`, `spec/dashboard-ux.md`, `app/CONTRACT.md`, `app/backend/README.md`, `app/backend/pyproject.toml`, `run.sh`, `app/data/demo/timeline.json`, the demo scenes' `scene.json`, and in `app/backend/fodgate/`: `workflow.py`, `demo.py`, `assistant.py`, `store.py`, `api.py`, `config.py`, `report.py`, parts of `llm.py` and `rules.py`, and the outline of `pipeline.py`.
- Claude API facts (model IDs, prices, Haiku 5.5 behaviour, caching minimum, tool runner, scheduled deployments): the `claude-api` skill bundled with this session, model table cached 2026-11-03. Prices should be rechecked before budgeting.
- Not verified: the Claude Agent SDK's current API, Claude Code Routines' limits and billing, and the contents of the framework repo's unmerged pull requests and the author's other repositories.
