---
id: 7
title: "How well does Claude find and highlight FOD in gate images, and what highlight form do we commit to?"
labels: [wayfinder:prototype]
parent: 1
blocked_by: [3, 4]
assignee: claude
status: closed
---

## Question

Run a throwaway spike: send a small labelled sample (clean + debris images, several angles) to Claude and measure misses, false alarms, and localisation quality. Decide the highlight form the PoC commits to (bounding box, rough region, image grid cell, or a verbal location), and whether single-pass or multi-pass analysis (e.g. tile/crop then re-check) is needed.

## Resolution

Evidence: [prototypes/spike/RESULTS.md](../prototypes/spike/RESULTS.md). 132 real API calls on 22 real 4K gate frames with composited debris, about $3.10.
- **Highlight form:** pixel bounding box, padded to a minimum size on screen, with a verbal location as secondary text. Box centres were within 1–3 px when the object was found.
- **Claude-only baseline (the bar to beat):** Sonnet 5.5 with tiles reached 93% recall, about 0.7 false alarms per clean image (mostly low confidence), about $0.19 and 6–9 s per 6-Angle Inspection. Haiku with tiles reached 89% recall with 2–5× the false alarms. Opus was no better than Sonnet.
- **Accepted limits for the PoC:** objects under about 20 px and deep dusk shadow were missed by every configuration. Re-measure on the staged captures.
- **Architecture redirected by the user to local-first:**
  1. A local detector scans every Angle at full resolution and proposes Candidates.
  2. Claude Haiku (the default) gets the Candidate crops, a downscaled frame for context, and the rule set. It decides FOD or not, category, zone, severity and rule, then the Verdict.
  3. Escalate to **Sonnet 5.5 (the ceiling; no Opus)** for reasoning that needs it, mainly uncertain Candidates in Critical zones.
  4. Safety net: a cheap Haiku whole-frame check on the Critical Angles (ENG-L, ENG-R, NOSE) to catch what the detector misses.
  5. The agent workflow (re-inspect, INCOMPLETE, Confirmation) runs on Claude.
- The local-detector comparison is a new ticket (0012).
