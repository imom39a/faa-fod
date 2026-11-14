# Dashboard UX (PoC v1.0)

Decided in issue 0009. Reference mock: `prototypes/dashboard/index.html` (throwaway; variant A tiles plus variant B's queue). Requirements: `spec/requirements-baseline.md` section 7. Layout, colours and components: `spec/design-system.md` (issue 0019), which replaced the tiles and the top bar of the reference mock.

- **Shell:** a page rail on the left and a Gate strip across the top of every page, one cell per Gate (T1, T2, T4, T5, T8). The demo controls and the role switch are in a tray behind the demo clock.
- **Overview:** counters of what is waiting on a person (by reason) and of Gates confirmed clear; a table with one row per Gate (flight, status, Verdict, highest open severity, time to pushback); a "Needs a human" queue beside the table, numbered in priority order.
- **Statuses:** idle, awaiting pre-arrival, inspecting, awaiting Confirmation (with the Verdict shown beneath: ALL CLEAR, FINDINGS or INCOMPLETE), confirmed clear. Anything not yet confirmed by a person is marked advisory. A Gate shows the highest severity among its unconfirmed Findings.
- **Queue order:** HOLDs first, then by time to scheduled pushback.
- **Turn view:** Inspections in time order with each Confirmation; the 6 Angle images with Finding boxes linked to the Findings list; current and reference crops side by side for each Finding.
- **Confirming Findings:**
  - REMOVE and ADVISORY: single step (removed, false alarm with a reason, or not found on walk). One "all removed" action confirms them together.
  - HOLD: Ramp Lead only, one at a time, in two steps. "Acknowledged" means someone is going to it. "Removed" triggers a re-inspection of that Angle, and the HOLD clears only if the new image is clean.
- **Unusable Angle:** re-inspect it, or a Ramp Lead records "checked by eye" with their name. The record shows the Angle was cleared by a person.
- **Sign-off:** every Inspection needs an explicit sign-off. The sign-off screen shows all 6 Angle thumbnails; opening each is not required.
- **Roles:** a Ramp Agent / Ramp Lead switch stands in for sign-in.
- **Crew and Tasks view** (issue #2): who is on Shift (role, Gates) and who is on a break; every open Task as one row (what, Gate, Finding, assignee, status, how long open), with the Escalation level reached and the time to the next timer on the row of each escalated Task; the last few closed Tasks; recent agent activity; the session cost. Task order: open Tasks before closed ones; then HOLDs first; then the higher Escalation level; then REMOVE, ADVISORY and no severity; then the oldest open Task first (for closed Tasks, the most recently closed first); then the Task ID. It updates within about one second. A HOLD and an escalated Task differ by text and shape, not by colour alone. A Task type the dashboard does not know shows its name and instruction. Clicking a Task opens its Turn at that Finding, or at the Inspection when the Task has no Finding. The view is read-only: links only, no action that confirms, signs off or reassigns.
- **Turn record** (issue #2): on the Turn view, every Inspection, Task, Report and Confirmation of the Turn in time order, with person, role and time, and the Turn's cost; it downloads as JSON. It is closed until the viewer opens it, and updates while open. A Report (what a person said) and a Confirmation (what was recorded) look different. The record is read-only: a show and hide button and a download link, nothing that writes.
- **Attribution** is shown for every photograph.
