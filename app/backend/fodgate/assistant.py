"""Assistant agent: Claude Haiku with read-only tools.

It explains Findings, suggests Angles to re-inspect and drafts the report to Ramp 1 control or Airport
Operations for debris outside the gate safety envelope (FOD-R10). It has no tool that changes a Verdict, a
severity or a Confirmation: every tool only reads the stored report or the rule set, or composes text.
"""
from __future__ import annotations

import json
from typing import Callable

from . import config, report as R
from .llm import LLM, LLMUnavailable, add_spend
from .rules import load_rules
from .workflow import WorkflowError

MAX_TURNS = 6
RECIPIENTS = {"ramp_1_control": "Ramp 1 control", "airport_operations": "Airport Operations"}

SYSTEM = """You are the assistant inside an airline gate FOD (Foreign Object Debris) inspection dashboard. A Ramp Agent or Ramp Lead is looking at one Inspection and asks you about it.

You can: explain why something was flagged (always cite the rule ID and its basis from the tools), suggest which Angles to re-inspect, and draft the report to Ramp 1 control or Airport Operations for debris outside the gate safety envelope (FOD-R10).
You cannot change a Verdict, a severity or a Confirmation, and you must never say or imply that a Gate, Angle or Finding is clear: the system is advisory and only a person's Confirmation clears anything. Only a Ramp Lead can confirm a HOLD. If asked to clear, confirm or downgrade something, say that a person has to do it in the dashboard.

Use the tools to read the report before answering; do not guess what it contains. Use the project's terms exactly: Gate, Turn, Inspection, Finding, Candidate, Verdict, Angle, Confirmation, HOLD, REMOVE, ADVISORY, gate safety envelope, equipment restraint line.
Routing for debris outside the gate safety envelope: the shared taxilane between stands goes to Ramp 1 control; the movement area beyond the zipper marking goes to Airport Operations. When the location does not settle it, draft for Ramp 1 control and say so. Draft the report only with the draft_outside_boundary_report tool, and tell the user the draft is ready for them to review and send.

Suggest re-inspecting an Angle when it is unusable, when the user asks what to check again, or when a Finding there is low confidence or has just been dealt with. Keep answers short and practical: a few sentences a person on the ramp can act on."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "suggested_reinspect_angles": {"type": "array", "items": {"type": "string", "enum": config.ANGLES}},
    },
    "required": ["reply", "suggested_reinspect_angles"],
    "additionalProperties": False,
}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": properties, "required": required,
                             "additionalProperties": False}}


TOOLS = [
    _tool("get_report", "Read a summary of the Inspection the user is looking at: Verdict, Angles, Findings "
          "(with IDs, severity, rule ID and status), observations, dismissed Candidates and cost.", {}, []),
    _tool("get_finding", "Read one Finding in full, including its rule text and basis and any Confirmation.",
          {"finding_id": {"type": "string"}}, ["finding_id"]),
    _tool("get_rule", "Read one rule of the FOD rule set (FOD-R1 .. FOD-R10): its text and its basis.",
          {"rule_id": {"type": "string"}}, ["rule_id"]),
    _tool("list_unusable_angles", "List the Angles of this Inspection that are unusable, with the reason and "
          "whether a Ramp Lead has checked them by eye.", {}, []),
    _tool("draft_outside_boundary_report", "Compose the draft report for Findings outside the gate safety envelope "
          "(FOD-R10). It only writes text for a person to review and send; nothing is sent or changed. Pass an "
          "empty finding_ids list to include every outside-boundary Finding.",
          {"recipient": {"type": "string", "enum": list(RECIPIENTS)},
           "finding_ids": {"type": "array", "items": {"type": "string"}}}, ["recipient", "finding_ids"]),
]
TOOL_NAMES = [t["name"] for t in TOOLS]


# ---------------------------------------------------------------------- tools (read-only)
class Tools:
    def __init__(self, report: dict, turn: dict | None = None):
        self.report = report
        self.turn = turn or {}
        self.rules = load_rules()
        self.draft: str | None = None

    def get_report(self) -> dict:
        r = self.report
        return {
            "inspection_id": r["inspection_id"], "gate": r["gate"], "kind": r["kind"], "status": r["status"],
            "verdict": r["verdict"], "highest_open_severity": r["highest_open_severity"],
            "missing_angles": r["missing_angles"], "signed_off": bool(r.get("inspection_signoff")),
            "angles": [{"angle": a["angle"], "status": a["status"], "unusable_reason": a["unusable_reason"],
                        "analysis": a.get("analysis"), "checked_by_eye": bool(a.get("checked_by_eye"))}
                       for a in r["angles"]],
            "findings": [{"finding_id": f["finding_id"], "angle": f["angle"], "severity": f["severity"],
                          "rule_id": f["rule_id"], "zone_tier": f["zone_tier"], "finding_type": f["finding_type"],
                          "category": f["category"], "description": f["description"], "confidence": f["confidence"],
                          "status": f["status"], "responsible_party": f["responsible_party"]} for f in r["findings"]],
            "observations": r.get("observations", []),
            "dismissed_candidates": len(r.get("dismissed_candidates", [])),
            "est_cost_usd": r.get("run_metadata", {}).get("est_cost_usd"),
            "notes": r.get("run_metadata", {}).get("notes", []),
        }

    def get_finding(self, finding_id: str) -> dict:
        f = next((f for f in self.report["findings"] if f["finding_id"] == finding_id), None)
        if f is None:
            raise KeyError(f"No Finding {finding_id} in this Inspection. IDs: "
                           + ", ".join(x["finding_id"] for x in self.report["findings"]))
        return {k: v for k, v in f.items() if k not in ("crop_url", "reference_crop_url")}

    def get_rule(self, rule_id: str) -> dict:
        rule = self.rules.rule(rule_id.strip().upper())
        if rule is None:
            raise KeyError(f"No rule {rule_id}. Rules are FOD-R1 to FOD-R10.")
        return rule

    def list_unusable_angles(self) -> list[dict]:
        return [{"angle": a["angle"], "unusable_reason": a["unusable_reason"],
                 "checked_by_eye": a.get("checked_by_eye")} for a in self.report["angles"] if a["status"] != "usable"]

    def draft_outside_boundary_report(self, recipient: str, finding_ids: list[str]) -> str:
        r = self.report
        items = [f for f in r["findings"] if f["zone_tier"] == "outside_boundary"
                 and (not finding_ids or f["finding_id"] in finding_ids)]
        if not items:
            self.draft = None
            return "There are no Findings outside the gate safety envelope in this Inspection, so there is nothing to report."
        rule = self.rules.rule("FOD-R10")
        flight = self.turn.get("flight")
        lines = [
            f"To: {RECIPIENTS.get(recipient, RECIPIENTS['ramp_1_control'])}",
            f"From: Ramp crew, Gate {r['gate']}" + (f" (flight {flight})" if flight else ""),
            f"Subject: FOD outside the gate safety envelope near Gate {r['gate']}",
            f"Seen: {r['captured_at']} (Inspection {r['inspection_id']}, {r['kind'].replace('_', '-')}, WIDE camera)",
            "",
            f"The gate FOD inspection system flagged {len(items)} item{'s' if len(items) != 1 else ''} outside our "
            "gate safety envelope. The ramp crew has not been assigned to remove "
            f"{'them' if len(items) != 1 else 'it'}.",
            "",
        ]
        for n, f in enumerate(items, 1):
            cat = self.rules.categories.get(f["category"] or "", {}).get("label", "Unidentified object")
            lines.append(f"{n}. {f['description']} ({cat}, size {f['size']}, {f['confidence']} confidence). "
                         f"Location: {f['location_text']}. Displayed severity: {f['severity']}. "
                         f"Image {f['image_ref']}, box {f['bbox']}.")
        lines += ["", f"Rule: {rule['id']}. {rule['text']}", f"Basis: {rule['basis']}", "",
                  "Requested action: please arrange inspection and removal, and tell the gate when the area is clear.",
                  "This is a draft written by the inspection system from camera images. A person must review it "
                  "before it is sent."]
        self.draft = "\n".join(lines)
        return self.draft

    def call(self, name: str, args: dict) -> tuple[str, bool]:
        """Run one tool. Returns (result text, is_error). Unknown tools are refused."""
        if name not in TOOL_NAMES:
            return f"Unknown tool {name}", True
        try:
            out = getattr(self, name)(**(args or {}))
        except (KeyError, TypeError) as e:
            return str(e).strip("'\""), True
        return out if isinstance(out, str) else json.dumps(out, ensure_ascii=False), False


# ---------------------------------------------------------------------- agent loop
def _field(block, name: str):
    return block.get(name) if isinstance(block, dict) else getattr(block, name, None)


def answer(*, report: dict, message: str, llm: LLM | None, turn: dict | None = None,
           create: Callable[..., object] | None = None) -> dict:
    """Run the assistant on one user message. `create` replaces `client.messages.create` in tests.
    Returns {"reply", "suggested_reinspect_angles", "draft_report", "usage"}."""
    if not message or not message.strip():
        raise WorkflowError(422, "invalid_request", "message is required")
    if report.get("status") == "inspecting":
        raise WorkflowError(409, "inspection_in_progress", "The Inspection is still running")
    tools = Tools(report, turn)
    if create is None:
        if llm is None:
            raise WorkflowError(503, "assistant_unavailable", "The assistant needs the Claude API, which is not configured")
        ok, why = llm.available()
        if not ok:
            raise WorkflowError(503, "assistant_unavailable", f"The assistant is unavailable: {why}")
        create = _sdk_create(llm)

    messages: list[dict] = [{"role": "user", "content": (
        f"Inspection {report['inspection_id']} at Gate {report['gate']} ({report['kind']}). "
        f"Verdict: {report['verdict']}. Question from the user:\n{message.strip()}")}]
    tokens_in = tokens_out = 0
    final_text = ""
    for _ in range(MAX_TURNS):
        resp = create(model=config.HAIKU, max_tokens=4000, system=SYSTEM, tools=TOOLS,
                      output_config={"effort": "medium", "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
                      messages=messages)
        usage = _field(resp, "usage")
        tokens_in += int(_field(usage, "input_tokens") or 0)
        tokens_out += int(_field(usage, "output_tokens") or 0)
        content = _field(resp, "content") or []
        stop = _field(resp, "stop_reason")
        if stop == "tool_use":
            results = []
            for b in content:
                if _field(b, "type") == "tool_use":
                    text, is_error = tools.call(_field(b, "name"), _field(b, "input"))
                    results.append({"type": "tool_result", "tool_use_id": _field(b, "id"), "content": text,
                                    "is_error": is_error})
            messages.append({"role": "assistant", "content": content})   # thinking blocks go back unchanged
            messages.append({"role": "user", "content": results})        # all results in one message
            continue
        final_text = next((_field(b, "text") for b in content if _field(b, "type") == "text"), "") or ""
        if stop == "refusal":
            final_text = json.dumps({"reply": "I can't help with that request.", "suggested_reinspect_angles": []})
        break
    else:
        final_text = json.dumps({"reply": "I could not finish reading the report. Please ask again.",
                                 "suggested_reinspect_angles": []})
    try:
        parsed = json.loads(final_text)
        reply, angles = str(parsed.get("reply", "")), parsed.get("suggested_reinspect_angles", [])
    except (json.JSONDecodeError, AttributeError):
        reply, angles = final_text, []
    cost = add_spend(config.HAIKU, tokens_in, tokens_out)
    return {"reply": reply or "I have no answer for that.",
            "suggested_reinspect_angles": [a for a in config.ANGLES if a in (angles or [])],
            "draft_report": tools.draft,
            "usage": {"model": config.HAIKU, "purpose": "workflow", "tokens_in": tokens_in, "tokens_out": tokens_out,
                      "est_cost_usd": round(cost, 6)}}


def _sdk_create(llm: LLM) -> Callable[..., object]:
    import anthropic
    client = llm.anthropic_client()

    def create(**kw):
        try:
            return client.messages.create(**kw)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            llm._stop("API key rejected")
            raise WorkflowError(503, "assistant_unavailable", "The assistant is unavailable: API key rejected") from None
        except anthropic.RateLimitError:
            raise WorkflowError(503, "assistant_unavailable", "The assistant is busy (rate limited); try again") from None
        except anthropic.APIStatusError as e:
            msg = str(getattr(e, "message", "")).lower()
            if e.status_code == 402 or "credit" in msg or "billing" in msg:
                llm._stop(f"billing / credit error (HTTP {e.status_code})")
            raise WorkflowError(503, "assistant_unavailable", f"The assistant is unavailable (HTTP {e.status_code})") from None
        except anthropic.APIConnectionError:
            raise WorkflowError(503, "assistant_unavailable", "The assistant is unavailable: network error") from None
        except LLMUnavailable as e:
            raise WorkflowError(503, "assistant_unavailable", f"The assistant is unavailable: {e}") from None

    return create
