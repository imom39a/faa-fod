---
id: 19
title: "What layout and visual style should the dashboard use for field operations?"
labels: [wayfinder:prototype]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

The functions of the dashboard are in place (Gates, Turn view, chat, Crew and Tasks, activity log). Choose a professional layout and style suited to ramp and control-room use, and record it so later screens follow it.

## Resolution

Spec: [spec/design-system.md](../spec/design-system.md). `spec/dashboard-ux.md` is amended to match.

Three directions were built on the real pages and compared in the browser (branch `prototype/field-ui`, `?variant=A|B|C`):
- A, handheld and daylight: light theme, bottom tab bar, action cards first.
- B, ops console: grey display with colour only for abnormal states, a page rail, a Gate strip on every page, a Gates table.
- C, split view and night: near-black theme, a Gate list beside the open Turn, one "next up" action.

B was chosen.
- The display is grey when normal; saturated colour is used only for HOLD, REMOVE, ADVISORY and INCOMPLETE, and never without a label and an icon.
- A page rail on the left and a Gate strip across the top of every page replace the top bar.
- The Gates page is counters, a table with one row per Gate, and the "Needs a human" queue numbered in priority order. This replaces the tiles decided in 0009.
- The demo controls and the role switch move into a tray behind the demo clock.
- All colours are tokens in one place; `app/frontend/src/design.test.ts` checks that, the 44px touch target and text contrast.
- The UI is named StandClear.

Not decided here: a dark variant for night use (C showed one way), and a phone-first layout for Ramp Agents (A showed one way). The console layout works at phone width but is not tuned for it.
