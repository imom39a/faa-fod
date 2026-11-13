# Architecture (PoC v1.0)

Decided in issue 0018. Requirements: `spec/requirements-baseline.md`.

- **Shape:** one local app on one laptop (Apple Silicon). A Python backend (FastAPI) runs the pipeline and serves a React dashboard.
- **Storage:** SQLite for Turns, Inspections, Findings and Confirmations. Images and reference frames are files on disk. Each Inspection report can be exported as JSON.
- **Pipeline (ordinary code, same result for the same images):**
  1. Check each Angle is usable.
  2. Propose Candidates locally: change detection against the Gate's reference frame; DINOv2 patch comparison added on night or low-contrast Angles.
  3. Tiled Haiku pass on the Critical Angles as a safety net; its hits join the Candidates.
  4. One structured-output call to Haiku 5.5 per Candidate batch: FOD or not, category, object class, description. Inputs are the Candidate crop, the reference crop, a downscaled frame and the rule set.
  5. Code computes zone tier, severity, rule ID and the Verdict.
  - With no reference frame, steps 2 and 3 are replaced by a tiled Claude pass on every Angle, and the report says so.
- **Assistant agent (Haiku with tools):** explains why something was flagged, proposes which Angles to re-inspect, and drafts the report to ramp control or Airport Operations for debris outside the stand. It cannot change a Verdict, a severity or a Confirmation.
- **Models:** Haiku 5.5 by default. Sonnet 5.5 is a setting, off by default. Opus is not used.
- **Rules:** `spec/fod-rules.md` is the single source. A machine-readable copy of it is loaded into the prompt, and the same copy drives the severity table in code.
- **Demo:** a scripted timeline plays Turns across the 5 Gates (aircraft due, pre-arrival, on stand, pre-departure, pushback) with a speed control and a reset. Any Inspection can also be triggered by hand.
- **Secrets:** the API key is read from `.env` and never logged.
