---
id: 1
title: "Map: AI-enabled FOD gate inspection PoC"
labels: [wayfinder:map]
status: closed
---

## Destination

**Reached 2026-11-13.** The build-ready spec is the six files in `spec/`: `requirements-baseline.md`, `fod-rules.md`, `inspection-report-schema.md`, `dashboard-ux.md`, `test-data-plan.md`, `architecture.md` plus `GLOSSARY.md`.

A **build-ready spec** for a proof-of-concept: a web dashboard that tracks **5 Gates** (example deployment: **Delta at ATL Concourse T**), and a local-first, Claude-powered agent that analyses multi-angle images per Inspection (pre-arrival + pre-departure) within an FAA-aligned gate turnaround FOD workflow and returns ALL CLEAR or highlighted Findings, each tied to an FAA-derived rule and confirmed by a human. Done when an approved, traceable requirements baseline exists and nothing is left to decide before someone builds it.

## Notes

- **Domain:** airline ramp / gate FOD safety. Source of truth for rules is FAA AC 150/5210-24A (Airport FOD Management, 2024; supersedes -24), via https://www.faa.gov/airports/airport_safety/fod. Airline SOPs layer on later.
- **Vocabulary:** use `GLOSSARY.md` (Gate, Turn, Inspection, Finding, Verdict, Confirmation). Consult the `domain-modeling` skill on every ticket.
- **Standing preferences:** Claude is advisory and a human Confirmation clears a Gate. Prefer recall over precision. **No real airport data during the PoC:** test and demo imagery comes from openly licensed internet sources. Coarse highlights are acceptable. Use pre-prepared, labelled image sets with no live cameras. **Local-first, cheap models:** local image models do the pixel work wherever possible. The LLM is used for decisions and the agentic workflow. Default is Claude Haiku 5.5, with Sonnet 5.5 as the ceiling; Opus is not used. Flag it if IT mandates Bedrock or Vertex.
- **Real imagery only:** every prototype, demo and test uses real aircraft and gate photographs (openly licensed, attributed), never SVG or illustrated stand-ins. Debris may be composited into real photos for ground truth.
- **Throwaway prototypes are allowed inside tickets** to ground decisions; they are evidence, not the build.
- **Tracker:** local markdown. Each ticket is `issues/NNNN-slug.md` with frontmatter `id`, `title`, `labels`, `parent: 1`, `blocked_by: [ids]`, `assignee` (the claim), `status: open|closed`. Frontier = open, unassigned tickets whose `blocked_by` are all closed. Research findings live in `research/<name>.md`, linked from the ticket. (Not a git repo, so there are no research branches.)

## Decisions so far

<!-- one line per closed ticket -->

- [What FOD categories, severities and required actions does FAA guidance define?](0002-faa-fod-guidance-extraction.md): AC -24A gives FOD sources, typical types and gate hotspots but no severity scale (only immediate hazard vs remove promptly), so the severity scale and pushback-hold rules are ours to define. Retention: 2 years recommended.
- [What can Claude's vision API actually do for multi-image FOD detection?](0003-claude-vision-capabilities-for-fod.md): Claude can handle the images and return approximate pixel boxes as structured JSON for about $0.01–0.30 per Inspection. The open risk is small debris after downscaling, so plan for crop/tile and measure it in the spike.
- [What FOD image data can we use or generate for testing?](0004-fod-test-data-sources.md): no public data matches the gate view. FOD-A (MIT) is only good for checking object recognition. The core test set must be staged at our own gates with the AC 150/5220-24 test-object kit, plus clean frames and synthetic insertions with a no-op control.
- [Which named camera angles make up one Inspection?](0005-camera-angle-set-per-gate.md): *(amended: pre-arrival replaces arrival)* 6 zone-based Angles (NOSE, ENG-L, ENG-R, CARGO, AFT, WIDE), narrowbody only, one image each, per-Gate camera/crop mapping. A missing or unusable Angle gives INCOMPLETE.
- [What FOD rule set and severity-to-action mapping will the agent apply?](0006-fod-rule-set-and-severity-actions.md): *(amended: FOD-R9 GSE staging, FOD-R10 escalate outside-boundary FOD to Airport Ops)* rules FOD-R1..R8 in `spec/fod-rules.md`, with HOLD/REMOVE/ADVISORY set by zone tier × object class. Critical zones (engines, nose) are always HOLD, and only a Ramp Lead can clear a HOLD.
- [How well does Claude find and highlight FOD in gate images, and what highlight form do we commit to?](0007-claude-detection-feasibility-spike.md): pixel bbox plus verbal location. Claude-only baseline is 93% recall at about $0.19 per Inspection (Sonnet, tiled). Architecture redirected to local-first: a local detector proposes Candidates, Haiku decides (Sonnet as ceiling), with a Haiku safety net on the Critical Angles.
- [What does an Inspection report contain (Finding and Verdict schema)?](0010-finding-and-verdict-report-schema.md): `spec/inspection-report-schema.md`. Verdict precedence is FINDINGS > INCOMPLETE > ALL CLEAR, missing Angles always listed. Findings are traceable (detected_by / decided_by, rule and model versions, cost metadata); dismissed Candidates and non-FOD observations are kept outside the Verdict.
- [What gate turnaround FOD workflow do FAA rules and industry standards require, step by step?](0014-gate-turnaround-fod-workflow-requirements.md): no federal rule prescribes a gate FOD workflow. IATA IGOM 4.1.1 and FAA people-safety ACs back pre-arrival and pre-departure checks. A 15-step workflow table is ready. Corrected: the flight crew clears pushback, and outside-envelope FOD goes to ramp control / Airport Ops per agreement.
- [What does Delta's turnaround and FOD flow look like publicly, what tools already exist, and where does our PoC add value?](0017-delta-flow-and-poc-offer.md): no public Delta FOD or gate-camera program in the US; turnaround-camera vendors time events but none publishes per-item debris Findings with severity. The PoC automates the two FOD walks and GSE staging (workflow steps 2, 4, 10). Offer statement and five demo moments are ready.
- [What are the facts of ATL Concourse T as the example site, and which 5 Delta gates do we model?](0015-atl-concourse-t-delta-example-site.md): all T gates face Ramp 1; Delta confirmed at T1–T3; recommended gates T1, T2, T4, T5, T8. At ATL the airline clears its own stand, the airlines' contractor AATC maintains the shared taxilane, and Airport Ops takes the movement area. Ramp 1's operator is unverified.
- [Which internet image archives can supply an openly licensed gate/apron test set per Angle?](0013-internet-gate-image-archives.md): Wikimedia Commons is the source; about 450–600 usable images projected, strong on WIDE, NOSE and CARGO, very thin on ENG-L and AFT and on empty stands. No Concourse T imagery. A manifest script with attribution exists.
- [Which local detector proposes Candidates well enough to replace Claude-only detection?](0012-local-detector-vs-claude-baseline.md): change detection against a reference frame, plus DINOv2 on night Angles; Haiku decides. On the spike set the hybrid beat Claude-only on recall and false alarms at about a fifth of the cost, but is slower and the test flatters it.
- [What is the approved requirements baseline for the Delta ATL Concourse T PoC?](0016-poc-requirements-baseline.md): `spec/requirements-baseline.md` v1.0 approved. Gates T1, T2, T4, T5, T8; Haiku-only decisions; targets of $0.05, 20 s, 90%/95% recall; test set of about 30 Inspections.
- [How should the 6-gate dashboard look and behave?](0009-gate-dashboard-ux.md): `spec/dashboard-ux.md`. Tiles plus a "Needs a human" queue; HOLD clears only by a Ramp Lead after a clean re-inspection; unusable Angles can be cleared by eye by a Ramp Lead.
- [What layout and visual style should the dashboard use for field operations?](0019-ui-direction-ops-console.md): `spec/design-system.md`. The "Ops console": a grey display with colour only for abnormal states, a page rail, a Gate strip on every page and a Gates table in place of tiles. Chosen from three prototypes on the real pages.
- [What test data set and ground-truth labelling will the PoC use?](0008-test-data-plan-and-ground-truth.md): `spec/test-data-plan.md`. 30 Inspections of real Commons photos with composited debris, fixed thresholds, scored against the baseline targets.
- [What architecture and stack does the PoC build use?](0018-poc-architecture-and-stack.md): `spec/architecture.md`. One local FastAPI + React app; pipeline and Verdict in code, Haiku for decisions and a tool-using assistant that cannot change Verdicts.

## Not yet specified

Nothing. The way to the destination is clear.

## Out of scope

- Aircraft damage / condition detection (open panels, dents): a separate maintenance domain.
- Multi-airport rollout.
- Live camera integration, including burst or best-frame capture: after the PoC. The per-Gate camera mapping and one-image-per-Angle input are the hand-off points.
- Links to ops systems (flight schedule, crew alerting, work orders, weather data): after the PoC. The JSON report export is the hand-off point.
- Enforced record retention and audit storage: after the PoC. The stated production target is at least 2 years.
- [Capture a pilot set of staged FOD images from our gate cameras](0011-capture-pilot-staged-gate-images.md): real airport data only becomes available *after* the PoC is shown (regulated access). The checklist is kept for the post-PoC pilot.
- Widebody aircraft: they need their own Angle set ([Which named camera angles make up one Inspection?](0005-camera-angle-set-per-gate.md)).
