---
id: 18
title: "What architecture and stack does the PoC build use?"
labels: [wayfinder:grilling]
parent: 1
blocked_by: []
assignee: claude
status: closed
---

## Question

The pipeline shape is fixed by the requirements baseline (local Candidates, Haiku decisions, human Confirmation). Decide the rest: app shape (one local app or separate services), language and framework for the dashboard and the pipeline, where Inspections, images and reference frames are stored, how an Inspection is triggered in the demo (scripted Turn timeline or manual), how Claude is called (direct structured-output calls or an agent loop with tools), how the rule set is packaged into prompts, and how the demo is run and reset.

## Resolution

Spec: [spec/architecture.md](../spec/architecture.md).
- One local app: FastAPI backend running the pipeline, React dashboard, SQLite plus image files.
- The pipeline and the Verdict are ordinary code. Claude Haiku makes the per-Candidate decision through structured output.
- A Haiku assistant agent with tools handles explanations, re-inspection suggestions and drafting reports for debris outside the stand. It cannot change a Verdict, severity or Confirmation.
- The rule set file is the single source for both the prompt and the severity table.
- The demo runs a scripted Turn timeline with speed control and reset.
