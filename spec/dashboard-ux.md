# Dashboard UX (PoC v1.0)

Decided in issue 0009. Reference mock: `prototypes/dashboard/index.html` (throwaway; variant A tiles plus variant B's queue). Requirements: `spec/requirements-baseline.md` section 7.

- **Overview:** one tile per Gate (T1, T2, T4, T5, T8) with a "Needs a human" queue beside the tiles.
- **Statuses:** idle, awaiting pre-arrival, inspecting, awaiting Confirmation (with the Verdict shown beneath: ALL CLEAR, FINDINGS or INCOMPLETE), confirmed clear. Anything not yet confirmed by a person is marked advisory. A Gate shows the highest severity among its unconfirmed Findings.
- **Queue order:** HOLDs first, then by time to scheduled pushback.
- **Turn view:** Inspections in time order with each Confirmation; the 6 Angle images with Finding boxes linked to the Findings list; current and reference crops side by side for each Finding.
- **Confirming Findings:**
  - REMOVE and ADVISORY: single step (removed, false alarm with a reason, or not found on walk). One "all removed" action confirms them together.
  - HOLD: Ramp Lead only, one at a time, in two steps. "Acknowledged" means someone is going to it. "Removed" triggers a re-inspection of that Angle, and the HOLD clears only if the new image is clean.
- **Unusable Angle:** re-inspect it, or a Ramp Lead records "checked by eye" with their name. The record shows the Angle was cleared by a person.
- **Sign-off:** every Inspection needs an explicit sign-off. The sign-off screen shows all 6 Angle thumbnails; opening each is not required.
- **Roles:** a Ramp Agent / Ramp Lead switch stands in for sign-in.
- **Attribution** is shown for every photograph.
