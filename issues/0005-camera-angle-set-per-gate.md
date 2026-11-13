---
id: 5
title: "Which named camera angles make up one Inspection?"
labels: [wayfinder:grilling]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

Decide the fixed set of 4–6 named camera angles per Gate (e.g. nose, left wing/engine, right wing/engine, tail/aft, wide apron), what ground zone each must cover, and whether all Gates share the same set. Ideally checked against the airline's existing gate camera layout.

## Resolution

- **PoC aircraft:** narrowbody only (A320 family / 737), parked nose-in at a jet bridge.
- **Angles are defined by the zone they cover, not by camera.** One shared set for all 6 Gates. Each Gate has a mapping: Angle → camera, plus an optional crop region. One camera may supply several Angles, and an Angle may be a crop of a larger frame.
- **The 6 required Angles:**

| Angle | Zone it must cover |
|---|---|
| NOSE | ahead of the nose, nose gear, pushback path |
| ENG-L | left engine intake area, under the left wing |
| ENG-R | right engine intake area, under the right wing |
| CARGO | right side: forward and aft cargo doors, belt loader, bag carts |
| AFT | main gear, tail, area behind the aircraft |
| WIDE | raised view of the whole stand (context, and anything the others miss) |

- **One image per Angle per Inspection.** Arrival and pre-departure use the same 6 Angles. An on-demand re-check may cover only the failed or flagged Angles and inherits the other Angles' results from the earlier Inspection.
- **Coverage rule:** a missing, unusable (blur, glare) or blocked required Angle gives the Verdict **INCOMPLETE**, never ALL CLEAR. WIDE can't stand in for a zone-specific Angle.
- The real camera layout is unknown. The 6 Angles are the *target*. The staged-capture task records which ones the real cameras actually cover.
- Glossary updated: Angle, Zone, INCOMPLETE.

## Amendment (2026-11-13)

Adopting the airline turnaround FOD practice (user-supplied airline turnaround practice, unsourced; aligns with IATA IGOM-style practice. Verify in issue 0014):
- A Turn's Inspections are now **pre-arrival** (stand empty, before the aircraft enters) and **pre-departure** (after the jet bridge retracts and GSE clears, before engine start), plus on-demand. The post-block-in "arrival" Inspection is dropped.
- Pre-arrival frames can serve as clean per-Angle references for change detection. They're only a rough match for frames with an aircraft on stand.
- The PoC now covers 5 Gates, not 6 (user direction, ATL Concourse T example). "All 6 Gates" above reads as "all Gates".
