"""Derived fields of an Inspection report: open Findings, highest open severity, Verdict."""
from __future__ import annotations

from datetime import datetime, timezone

from .rules import highest_severity


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_open(finding: dict) -> bool:
    """A Finding is open until a Confirmation closes it. An airport-routed (outside boundary) Finding also
    counts as closed once it is acknowledged, i.e. reported to Ramp 1 control / Airport Operations."""
    if finding.get("status") == "confirmed":
        return False
    if finding.get("zone_tier") == "outside_boundary" and finding.get("status") == "acknowledged":
        return False
    return True


def open_findings(report: dict) -> list[dict]:
    return [f for f in report.get("findings", []) if is_open(f)]


def unresolved_unusable_angles(report: dict) -> list[str]:
    """Unusable Angles nobody has checked by eye. (Re-inspecting an Angle produces a new Inspection.)"""
    return [a["angle"] for a in report.get("angles", []) if a["status"] != "usable" and not a.get("checked_by_eye")]


def compute_verdict(findings: list[dict], angles: list[dict]) -> str:
    """Verdict precedence: FINDINGS > INCOMPLETE > ALL_CLEAR (RP-2).

    Findings already closed by a Confirmation (carried into an on-demand Inspection from an Angle that was not
    re-captured) do not count: the Verdict describes what this Inspection still sees as unresolved.
    An unusable Angle makes the Inspection INCOMPLETE even when a Ramp Lead has checked it by eye: the
    cameras did not cover it, and the report says so.
    """
    if any(is_open(f) for f in findings):
        return "FINDINGS"
    if any(a["status"] != "usable" for a in angles):
        return "INCOMPLETE"
    return "ALL_CLEAR"


def refresh(report: dict) -> dict:
    """Recompute the fields that change with Confirmations. The Verdict is the result of the analysis and is
    not rewritten by a Confirmation; `status` and `highest_open_severity` are."""
    report["highest_open_severity"] = highest_severity([f["severity"] for f in open_findings(report)])
    if report.get("status") != "inspecting":
        report["status"] = "confirmed" if report.get("inspection_signoff") else "awaiting_confirmation"
    return report
