"""Task types, statuses and who may be given what (spec/dispatch.md)."""
from __future__ import annotations

TASK_TYPES = ("ack_hold", "remove", "walk_and_report", "check_by_eye", "report_outside_boundary", "sign_off")
ACTIVE = ("assigned", "accepted", "reported")           # anything else is closed or cancelled
REPORT_KINDS = ("accepted", "done", "not_found", "blocked", "note")
PERSON_ROLES = ("ramp_agent", "ramp_lead", "supervisor")
WORK_ROLES = ("ramp_agent", "ramp_lead")                # the roles the Workflow accepts for Confirmations
SHIFT_STATUSES = ("on", "break", "off")
ROLE_LABEL = {"ramp_agent": "Ramp Agent", "ramp_lead": "Ramp Lead", "supervisor": "Supervisor"}

LEAD_ONLY = ("ack_hold", "check_by_eye", "sign_off")    # never assigned to anyone but a Ramp Lead
FINDING_TASKS = ("ack_hold", "remove", "walk_and_report", "report_outside_boundary")

TYPE_LABEL = {"ack_hold": "acknowledge HOLD", "remove": "remove", "walk_and_report": "walk and report",
              "check_by_eye": "check by eye", "report_outside_boundary": "report outside the envelope",
              "sign_off": "sign off"}


def required_role(task_type: str) -> str:
    """`ramp_lead` or `any` (a Ramp Agent or a Ramp Lead). Supervisors are never given Tasks."""
    return "ramp_lead" if task_type in LEAD_ONLY else "any"


def role_may_take(role: str, task_type: str) -> bool:
    if role not in WORK_ROLES:
        return False
    return role == "ramp_lead" or required_role(task_type) == "any"


class DispatchError(Exception):
    """A routing action was refused by code. The text goes back to whoever asked (a person or the model)."""
