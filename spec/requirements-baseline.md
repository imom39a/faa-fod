# Requirements Baseline: Gate FOD Inspection PoC (v1.0, approved 2026-11-13)

Example deployment: **Delta at ATL Concourse T, 5 Gates**. Terms follow `GLOSSARY.md`.
Issue: 0016 ("What is the approved requirements baseline for the Delta ATL Concourse T PoC?").

**Status.** Approved by the user on 2026-11-13. Companion specs: `fod-rules.md`, `inspection-report-schema.md`, `dashboard-ux.md`, `test-data-plan.md`, `architecture.md`.

**How to read the Source column.** Issue numbers refer to `issues/`. "WF-n" is step n of the workflow table in `research/gate-turnaround-fod-workflow.md`. Status words: *Binding* (CFR or ATL airport rule), *FAA-rec* (FAA advisory), *Industry* (IATA IGOM), *PoC choice* (ours).

## 1. Scope

| ID | Requirement | Source |
|---|---|---|
| SC-1 | The PoC monitors 5 Gates at one example site (Delta, ATL Concourse T). Gate list: ST-1. | User direction; 0015 |
| SC-2 | Narrowbody aircraft only, parked nose-in at a jet bridge. | 0005 |
| SC-3 | The PoC detects FOD on the ground and GSE staging violations. It does not assess aircraft condition. | 0001 scope; 0006 |
| SC-4 | No real airport camera data is used. All imagery is real photographs from openly licensed internet sources, with debris composited in for ground truth. Attribution is recorded for every image. | User direction; 0013 |
| SC-5 | The system is advisory. A human Confirmation is required before any Gate is shown as clear. | 0001; 0006 |
| SC-6 | Out of scope: live camera integration, widebody aircraft, multi-airport, links to airline ops systems, aircraft damage detection. | 0001 |

## 2. Workflow

No federal rule prescribes a gate FOD workflow (AC 00-34B). The PoC workflow follows IATA IGOM and FAA advisory guidance, plus ATL's tenant rules.

| ID | Requirement | Source |
|---|---|---|
| WF-R1 | Each Turn has a **pre-arrival Inspection** of the empty stand, run just before the aircraft enters. | WF-2 (Industry: IGOM 4.1.1(b); FAA-rec: AC 150/5210-24A §4.3.2.3.1) |
| WF-R2 | The pre-arrival Inspection also checks that GSE, chocks and cones are outside the equipment restraint line (FOD-R9). | WF-4 (Industry: IGOM 4.1.1(d); Binding at ATL: staging violations) |
| WF-R3 | Each Turn has a **pre-departure Inspection**, run after the jet bridge retracts and GSE clears, before pushback. | WF-9, WF-10 (FAA-rec: AC 00-65A App. A; -24A §4.3.2.3.1) |
| WF-R4 | Any role can request an **on-demand Inspection** of one or more Angles during the Turn. Angles not re-captured inherit their earlier result. | WF-8; 0005 |
| WF-R5 | A HOLD Finding blocks the Gate from being shown as clear until a **Ramp Lead** confirms it removed or a false alarm. The Ramp Lead then tells the flight crew the ground is ready. The system does not clear pushback; the flight crew and ramp control do. | WF-13 (PoC choice for HOLD; FAA-rec: AC 00-65A ¶11.7, ¶11.13) |
| WF-R6 | FOD outside the gate safety envelope is routed to ramp control and/or Airport Operations according to the local agreement, and is not assigned to the ramp crew (FOD-R10).  ATL routing: ST-3. | WF-14 (FAA-rec: -24A §3.3.1; Binding at ATL: movement area is Airport Ops) |
| WF-R7 | A confirmed-clean pre-arrival Inspection becomes the reference frame for that Gate's later Inspections. | 0012 evidence; WF-2 |
| WF-R8 | Snow, ice, spills and live wildlife are shown as non-FOD observations and stay outside the Verdict (FOD-R7). | WF-3; 0006 |
| WF-R9 | A Turn starts at stand preparation (before the pre-arrival Inspection) and ends at pushback.  | 0014 open point |
| WF-R10 | A post-departure stand check is not a separate Inspection in the PoC. The next Turn's pre-arrival Inspection covers it. | WF-15 (Practice only) |

**What the cameras cannot verify** (shown in the UI as outside the system's coverage, never as "clear"): that a person walked the stand, briefings, engine and beacon state, door and panel latches, serviceability of chocks and cones, anything between Inspections, anything hidden behind the aircraft or GSE. Source: WF table, "Camera can't verify" column.

## 3. Angles and coverage

| ID | Requirement | Source |
|---|---|---|
| AN-1 | An Inspection covers 6 Angles: NOSE, ENG-L, ENG-R, CARGO, AFT, WIDE, each defined by the ground zone it shows. One image per Angle. | 0005 |
| AN-2 | Each Gate has a mapping from Angle to camera and optional crop region. One camera may supply several Angles. | 0005 |
| AN-3 | A missing or unusable Angle (missing, glare, blur, blocked, low light) makes the Inspection INCOMPLETE. WIDE cannot stand in for another Angle. | 0005; FOD-R6 |
| AN-4 | Each Gate's mapping also records the gate safety envelope and equipment restraint line as regions in the WIDE image, so FOD-R9 and FOD-R10 can be evaluated. The FAA has no standard for these markings, so they are mapped per Gate. | 0014 open point 4 |

## 4. Rules and severity

| ID | Requirement | Source |
|---|---|---|
| RU-1 | The agent applies rule set `spec/fod-rules.md` v0.2 (FOD-R1 to R10). Every Finding cites one rule ID, and the rule's basis is shown with it. | 0006 |
| RU-2 | Severity is HOLD, REMOVE or ADVISORY, set by zone tier (Critical, Service, General, Outside boundary) and object class (hard, light, unidentified, natural). | 0006 |
| RU-3 | Severity is computed in code from zone tier and object class, not taken from the model's own severity value. | 0012 evidence (model disagreed with the matrix once) |
| RU-4 | There is no minimum object size. Confidence is displayed and never lowers severity. | 0006 |
| RU-5 | A Ramp Agent can confirm REMOVE and ADVISORY Findings. Only a Ramp Lead can confirm a HOLD. Any role can request a re-inspection. | 0006; WF-13 |
| RU-6 | Rule citations distinguish FAA advisory text, IATA IGOM, ATL airport rules and airline program rules. No rule is presented as a federal requirement unless it is one. | 0002; 0014 |

## 5. Detection pipeline

| ID | Requirement | Source |
|---|---|---|
| PL-1 | A local model proposes Candidates from each Angle image at full resolution. No image leaves the machine at this stage. | User direction; 0007 |
| PL-2 | The Candidate proposer is change detection against the Gate's reference frame, with DINOv2 patch comparison added on night or low-contrast Angles. Open-vocabulary detection (OWLv2) and a local VLM verifier are not used. | 0012 evidence |
| PL-3 | For each Candidate, Claude receives the Candidate crop, the matching crop of the reference frame, a downscaled view of the whole Angle, and the rule set. It returns FOD or not, category, object class and a description, as structured output. | 0012 evidence (the reference crop is what made decisions reliable) |
| PL-4 | Decisions use Claude Haiku 5.5 only. Sonnet 5.5 stays available as a setting but is off by default (the ceiling; never Opus), because escalation was about 75% of the hybrid's cost and recovered no missed object in testing. | 0012 evidence; user ceiling of Sonnet |
| PL-5 | The safety net for Critical Angles is a tiled Haiku pass whose results go through the same decision step, replacing the whole-frame check, which found only half the objects on its own. | 0012 evidence |
| PL-6 | Candidates Claude rejects are kept as dismissed Candidates with a one-line reason. | 0010 |
| PL-7 | Opus is not used. | User direction |
| PL-8 | When a Gate has no reference frame yet (first Inspection, or camera moved), the Inspection falls back to a tiled Claude pass on every Angle and says so in the report. | Gap found while drafting: 0012 notes change detection needs a confirmed-clean reference |

## 6. Report and records

| ID | Requirement | Source |
|---|---|---|
| RP-1 | Every Inspection produces a report following `spec/inspection-report-schema.md`. | 0010 |
| RP-2 | Verdict precedence is FINDINGS, then INCOMPLETE, then ALL CLEAR. Missing Angles are always listed. | 0010 |
| RP-3 | Each Finding is highlighted by a pixel bounding box, padded to a minimum size on screen, with a verbal location. | 0007 |
| RP-4 | Each Finding records its Confirmation: outcome, role and name, time, optional after-photo, optional possible source. | 0010; -24A §6.1.1 |
| RP-5 | Every report records rule-set version, model names and versions, tokens, estimated cost and stage timings. | 0010 |
| RP-6 | The PoC keeps a record for every Inspection, including ALL CLEAR ones, although no source requires it. Retention is not enforced in the PoC; the stated target for production is at least 2 years. | 0014 open point 1; -24A §6.1.4 |

## 7. Dashboard

| ID | Requirement | Source |
|---|---|---|
| UI-1 | An overview shows the 5 Gates with status: idle, awaiting pre-arrival, inspecting, ALL CLEAR (advisory), FINDINGS, INCOMPLETE, awaiting Confirmation, confirmed clear. | 0009 prototype |
| UI-2 | A Gate's status shows the highest severity among its unconfirmed Findings. A HOLD shows even when the Verdict is INCOMPLETE. | 0006 |
| UI-3 | A Turn view shows its Inspections in order, each Confirmation, and the 6 Angle images with Finding boxes linked to a Findings list. | 0009 prototype |
| UI-4 | Statuses that come from the system alone are visibly marked advisory. Only a human-confirmed Gate shows as confirmed clear. | 0009 prototype; SC-5 |
| UI-5 | A role switch (Ramp Agent, Ramp Lead) stands in for sign-in. | 0006 |
| UI-6 | All images shown are real photographs. | User direction |
| UI-7 | Overview layout, Confirmation steps and urgency ordering: the six open questions in `prototypes/dashboard/NOTES.md`. Settled in `spec/dashboard-ux.md`. | 0009 |

## 8. Cost, speed and accuracy targets

Measured on 22 composited 4K frames (28 objects). These are evidence from an easy test set, not guarantees.

| ID | Requirement | Source |
|---|---|---|
| NF-1 | Cost target: at most $0.05 per 6-Angle Inspection. Measured: $0.03 to $0.04 hybrid, about $0.008 with Haiku-only decisions. | 0012 evidence |
| NF-2 | Speed target: an Inspection completes within 20 seconds. Measured: about 12 to 17 seconds. | 0012 evidence |
| NF-3 | Accuracy bar on the PoC test set: recall of at least 90% overall and 95% in Critical zones, and at most 0.5 false alarms per clean Angle. Measured: 96 to 100% recall, 0.10 false alarms. | 0012 evidence; AC 150/5220-24 as reference only |
| NF-4 | Known limits are stated in the demo: objects under about 20 px, deep shadow at dusk, and that the test references are simulated with nothing moving between frames. | 0007; 0012 |
| NF-5 | The local stage runs on an Apple Silicon laptop (M1 Pro, 16 GB) without a GPU server. | 0012 evidence; user's drone-lab setup |

## 9. Test data

Source: `research/gate-image-archives.md` (issue 0013). The detailed plan is settled in issue 0008 after this baseline is approved.

| ID | Requirement | Source |
|---|---|---|
| TD-1 | The test set covers all 6 Angles, both Inspection kinds (empty stand and aircraft on stand), day and night, and clean frames as well as frames with debris. Images come from Wikimedia Commons through the manifest script, which records attribution for each. | 0004; 0013 |
| TD-2 | Ground truth is a box, category and zone for every composited item. | 0004 |
| TD-3 | Clean frames with normal clutter, and clean frames edited without adding debris, are included to measure false alarms and to check the detector is not reacting to the editing itself. | 0004 |
| TD-5 | ENG-L and AFT are thin in public photos (about 4% and 0% of usable images). The gap is filled by cropping those zones out of wide frames and by mirroring ENG-R photos to stand in for ENG-L, each labelled as such. | 0013 |
| TD-6 | Target size: about 30 Inspections (180 Angle images), a third of them pre-arrival empty-stand sets, at least 20% night or wet. | 0013 yield estimate |
| TD-8 | Images are downloaded with an anonymous client that sends no user or project details. | User decision |
| TD-7 | Attribution is shown wherever an image is displayed. Faces and airline livery are checked before any showing outside the company. | 0013 licence conditions |
| TD-4 | Thresholds are fixed on one part of the test set and results reported on another. | 0012 caveat (thresholds were tuned on the same set) |

## 10. Example site

Source: `research/atl-concourse-t-site.md` (issue 0015). The site is an example: gate names and routing are modelled on public facts, and the PoC does not claim to reflect Delta's actual operation.

| ID | Requirement | Source |
|---|---|---|
| ST-1 | The 5 Gates are T1, T2, T4, T5 and T8. T1 is the end of the pier, T2 tests a shared boundary with T1, T4 is a mid-concourse baseline, T5 has odd spacing next to the gap where T6 would be, and T8 neighbours other airlines' gates. Only T1 to T3 are confirmed as Delta gates; T4, T5 and T8 are likely but unverified. | 0015 |
| ST-2 | All 5 Gates face Ramp 1, the taxilane shared with Concourse A. | 0015 (FAA airport diagram) |
| ST-3 | Routing of FOD outside the stand follows ATL's published split: the shared taxilane between stands goes to ramp control for the airlines' contractor AATC; the movement area beyond the zipper marking goes to Airport Operations. | 0015 (lease §12.01.B, §12.01.D; ATL training guide); FOD-R10 |
| ST-4 | The demo labels ramp control as "Ramp 1 control" and does not name its operator, because no primary source confirms who runs it. | 0015 |
| ST-5 | The equipment restraint line and gate safety envelope are presented as airline practice (IATA IGOM), not ATL rules. ATL's published rules shown in the demo are: no parking under jet bridges, and staging and unsecured-FOD violation classes. | 0015; 0014 |
| ST-6 | Aircraft types shown are Delta narrowbodies that fit the stands: A220, A319, A320, A321, 717, 737-800/-900ER, 757. | 0015 |
| ST-7 | No openly licensed photo shows a numbered T gate at apron level. Gate imagery in the demo is real photos of comparable stands elsewhere, labelled as stand-ins. | 0015; SC-4 |

## 11. What the PoC offers

Source: `research/delta-flow-and-poc-offer.md` (issue 0017).

**Offer statement.** A gate-level FOD check on the cameras Delta already has. Before each arrival and each pushback, the system inspects six zones at the stand and flags each piece of debris or misplaced GSE with a photo crop, a severity and the rule behind it. If it cannot see a zone, it says so. Nothing clears without a person, and every Confirmation is kept as a record.

| ID | Requirement | Source |
|---|---|---|
| OF-1 | Against the 15-step workflow, the PoC automates the pre-arrival FOD check, the GSE staging check and the pre-departure FOD check (steps 2, 4, 10). It supports steps 8, 9, 11 and 15 through on-demand Inspections, and records steps 3, 13 and 14. It claims no role in briefings, marshalling, block-in, GSE approach or headset comms (steps 1, 5, 6, 7, 12). | 0017 capability matrix |
| OF-2 | The PoC does not do turn-milestone timing, people or PPE detection, continuous video monitoring, or movement-area FOD. Existing products cover those. | 0017 vendor landscape |
| OF-3 | Each Inspection report can be exported as JSON, as the hand-off point for ramp tower or turnaround tools. No integration is built. | 0017 scope |
| OF-4 | The demo shows five moments: (1) a small bolt in an engine intake zone raising a HOLD, with current and reference crops side by side; (2) GSE inside the equipment restraint line at pre-arrival raising a REMOVE; (3) glare on an engine Angle giving INCOMPLETE; (4) a Ramp Agent refused on a HOLD, the Ramp Lead confirming removal, a re-inspection returning ALL CLEAR, and the record; (5) debris beyond the stand routed out under FOD-R10, with the Inspection's cost shown. | 0017 demo moments |
| OF-5 | Add `spill` as a non-FOD observation kind, because Delta has publicly named oil spills as something it wants AI to spot. The PoC shows it and does not assign severity. | 0017 (Delta's Amsterdam case study); WF-3 |
| OF-6 | The demo states its gaps: snapshots not continuous coverage, composited test data only, 12 to 17 seconds per Inspection, unknown camera access at ATL. | 0017 gaps |
