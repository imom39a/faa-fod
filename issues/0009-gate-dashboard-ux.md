---
id: 9
title: "How should the 6-gate dashboard look and behave?"
labels: [wayfinder:prototype]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

Prototype the dashboard: gate overview (status per Gate: idle / aircraft on stand / inspecting / ALL CLEAR / FINDINGS / awaiting Confirmation), drill-in to a Turn's Inspections, multi-angle image viewer with Finding highlights, and the Confirmation flow (confirm, removed, false alarm). React to a clickable mock to settle layout and states.

## Resolution

Spec: [spec/dashboard-ux.md](../spec/dashboard-ux.md). Mock: [prototypes/dashboard/index.html](../prototypes/dashboard/index.html), with real photographs.
- Tiles overview with a "Needs a human" queue, ordered HOLDs first and then by time to pushback.
- One waiting status, "awaiting Confirmation", with the Verdict beneath it.
- REMOVE and ADVISORY Findings confirm in one step and can be confirmed together. A HOLD is Ramp Lead only, in two steps, and clears only after a re-inspection of that Angle comes back clean.
- A Ramp Lead can clear an unusable Angle by recording "checked by eye".
- Every Inspection needs an explicit sign-off showing all 6 Angles.
