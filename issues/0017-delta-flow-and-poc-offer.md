---
id: 17
title: "What does Delta's turnaround and FOD flow look like publicly, what tools already exist, and where does our PoC add value?"
labels: [wayfinder:research]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

From public sources:
- **Delta's** gate turnaround and FOD-related flow, especially at ATL: Delta-operated ramp control towers, Delta TechOps / ground ops safety programs, FOD prevention campaigns, the turn-time targets and the digital ramp tools Delta has announced (apps, sensors, computer vision, gate camera or "smart ramp" pilots), and Delta's SMS / safety culture statements.
- **Existing products** in the space: AI turnaround and apron cameras (e.g. Assaia ApronAI and similar vendors), FOD detection systems (runway radar/EO systems such as Tarsier, FODetect, iFerret), and airport digital-twin or gate-management vendors. Cover what each detects (turn milestones vs safety hazards vs FOD), where it's deployed (any US / Delta / ATL deployments), and how it integrates.

Then map our PoC's capabilities against Delta's 15-step workflow (research/gate-turnaround-fod-workflow.md) and against those products:
- which steps the PoC can **automate, verify, or record**
- which it can't
- where it's differentiated (gate-level FOD on existing cameras, FAA- and IGOM-traceable rules, local-first cost, a human-confirmed audit trail)

Output a capability/offer matrix that the requirements baseline (0016) can use to set the PoC's scope and pitch.

## Resolution

Findings: [research/delta-flow-and-poc-offer.md](../research/delta-flow-and-poc-offer.md). Claims are labelled primary, secondary or vendor claim.
- **Delta:** no public FOD program, US gate-camera pilot or current turn-time target was found. Deployed ramp tools at ATL are Baggage AI, autonomous jet bridges (Concourse B) and autonomous bag tugs (Concourse T bag room). At Amsterdam, Delta's tower uses the airport's Deep Turnaround cameras daily, and in that case study Delta says it wants AI to spot "oil spills or misplaced equipment". Delta's SMS language ("a human is always present in the safety system") matches the human Confirmation rule.
- **ATL:** the airport's camera AI is on security cameras, not the ramp. The only apron-camera trial found is Southwest's ApronAI on 18 gates (trade press, Dec 2023; current status unknown).
- **Vendors:** turnaround-camera products (Assaia, Synaptic, Deep Turnaround) time events and flag procedure breaches. None publishes per-item debris findings with severity. Stand-level FOD products (ADB SAFEGATE AiPRON FOD, ArgosAI A-PAC) have no public US deployment. Runway systems cover the movement area only. No pricing is public.
- **Capability matrix against the 15 workflow steps:** the PoC automates steps 2, 4 and 10; verifies 8, 9, 11 and 15; records 3, 13 and 14; has no role in 1, 5, 6, 7 and 12.
- **Differentiation:** per-item, rule-cited debris Findings on existing gate cameras; INCOMPLETE when a view is unusable; Ramp Lead-only HOLD clearance with an audit trail; about $0.03–0.04 per Inspection.
- **Gaps:** snapshots not continuous coverage, synthetic-only test data, 12–17 s latency, unknown camera access at ATL, no integrations.
- **Offer and five demo moments** are in the findings file, for the baseline (0016) to adopt.
