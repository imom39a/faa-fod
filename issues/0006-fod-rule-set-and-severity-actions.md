---
id: 6
title: "What FOD rule set and severity-to-action mapping will the agent apply?"
labels: [wayfinder:grilling]
parent: 1
blocked_by: [2]
assignee: claude
status: closed
---

## Question

Using the FAA extraction, decide the PoC's rule set: FOD categories the agent must recognise, severity levels, which zones matter (e.g. engine intake area vs gate edge), and the action each severity triggers (e.g. hold pushback, remove & log, informational). Decide how each rule is identified so Findings can cite it.

## Resolution

The rule set is in [spec/fod-rules.md](../spec/fod-rules.md). In short:
- Airline program rules FOD-R1..R8, each citing its FAA basis (AC 150/5210-24A, 14 CFR 139).
- Three severity levels: **HOLD**, **REMOVE**, **ADVISORY**. Only a Ramp Lead can clear a HOLD.
- Zone tiers: Critical (ENG-L, ENG-R, NOSE), Service (CARGO, AFT), General (WIDE only). Severity comes from zone tier × object class (hard / light / unidentified / natural). Anything in a Critical zone is HOLD.
- 9 categories, including "Unidentified object". No minimum size. Confidence never lowers severity.
- Snow, ice and live wildlife are non-FOD observations. GSE in its normal position is not FOD; loose or misplaced GSE is.
- Gate status shows the highest unconfirmed severity.

## Amendment (2026-11-13)

From the airline turnaround practice (user-supplied airline turnaround practice, unsourced; aligns with IATA IGOM-style practice. Verify in issue 0014):
- **FOD-R9 (equipment staging):** at pre-arrival, GSE parked inside the equipment restraint line is a Finding at REMOVE severity (it must be moved before the aircraft enters). It's an *equipment staging* Finding, separate from the FOD categories.
- **Fourth zone tier, outside gate boundary:** a Finding outside the gate safety envelope (taxi lane, adjacent stand) is marked `responsible_party: airport`. The action is to notify Airport Operations, not ramp removal.
- **Ramp Lead** = the pushback lead / headset operator who clears engine start and pushback.
