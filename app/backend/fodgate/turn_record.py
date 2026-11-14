"""The record of one Turn (GET /api/turns/{turn_id}/record; app/CONTRACT.md section 2, "Turn record").

Every Inspection, Task, Report and Confirmation of the Turn, in time order, with who did each and the cost of
the Turn. Read-only: this module only reads the store and never calls a model.

A Report is what a person said about a Task (the task_reports table). A Confirmation is what was recorded
(the confirmations table). They are separate kinds of entry and are never merged.

Order. Times in the store have one-second resolution, so many entries share an `at`. Ties are broken by the
activity log (agent_log), which is one ordered sequence of what happened: each entry is anchored to the log
row that recorded it where there is one. Entries with no log row (for example when the dispatcher is off)
come after anchored ones of the same second, Inspections before Tasks, Reports and Confirmations, each in the
order its own table holds them.
"""
from __future__ import annotations

import json
import math
import re

from .dispatch.models import ROLE_LABEL, TYPE_LABEL
from .report import now_iso
from .store import Store
from .workflow import WorkflowError

KIND_RANK = {"inspection": 0, "task": 1, "report": 2, "confirmation": 3}
_TASK_ID = re.compile(r'"task_id":\s*"([^"]+)"')
# Task log events that are not Task entries: a Report is read from the task_reports table instead.
_REPORT_EVENTS = ("task_accepted", "task_reported")


def _named_tasks(data: dict) -> list[str]:
    """The Task IDs a log row names: task_ids, tasks (a Handover) or task_id."""
    ids = data.get("task_ids") or data.get("tasks") or [data.get("task_id")]
    return [x for x in ids if isinstance(x, str)] if isinstance(ids, list) else []


def _is_task_event(event: str) -> bool:
    """A log event about a Task's life (task_*, handover*), including names added by later tickets."""
    return (event.startswith("task_") or event.startswith("handover")) and event not in _REPORT_EVENTS


def _json(s: str | None) -> dict:
    try:
        out = json.loads(s or "{}")
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


class _People:
    """Roster lookups. A stored person_id gives the name and role; a stored name and role give the person_id."""

    def __init__(self, store: Store):
        self.rows = {r["person_id"]: r for r in store.query("SELECT person_id, name, role FROM people")}

    def by_id(self, person_id: str | None) -> dict | None:
        if not person_id:
            return None
        r = self.rows.get(str(person_id).strip().lower())
        if r is None:
            return {"person_id": person_id, "name": None, "role": None}
        return {"person_id": r["person_id"], "name": r["name"], "role": r["role"]}

    def by_name(self, name: str | None, role: str | None, person_id: str | None = None) -> dict | None:
        if person_id:
            p = self.by_id(person_id)
            return p | {"name": p["name"] or name, "role": p["role"] or role}
        if not name and not role:
            return None
        match = next((r for r in self.rows.values() if (r["name"] or "").lower() == (name or "").lower()
                      and r["role"] == role), None)
        return {"person_id": match["person_id"] if match else None, "name": name, "role": role}


def _who(p: dict | None) -> str:
    if not p or not (p.get("name") or p.get("person_id")):
        return "nobody"
    name = p.get("name") or p.get("person_id")
    return f"{name} ({ROLE_LABEL.get(p.get('role'), p.get('role'))})" if p.get("role") else name


def _refs(inspection_id=None, task_id=None, finding_id=None, angle=None) -> dict:
    return {"inspection_id": inspection_id, "task_id": task_id, "finding_id": finding_id, "angle": angle}


def build(store: Store, turn_id: str) -> dict:
    """The Turn record. Raises WorkflowError 404 for an unknown Turn."""
    turn = store.get_turn(turn_id)
    if turn is None:
        raise WorkflowError(404, "not_found", f"Turn {turn_id} not found")
    people = _People(store)
    reports = {r["inspection_id"]: r for r in store.reports_for_turn(turn_id)}
    tasks = {t["task_id"]: t for t in store.query("SELECT * FROM tasks WHERE turn_id=? ORDER BY seq", (turn_id,))}
    log = _turn_log(store, turn_id, set(tasks))
    labels = _labels(store, turn_id, reports)
    entries: list[dict] = []
    entries += _inspections(store, turn_id, reports, log, people)
    entries += _tasks(tasks, log, people)
    entries += _reports(store, tasks, log, people)
    entries += _confirmations(store, reports, log, people, labels)

    entries.sort(key=lambda e: (e["at"] or "", e["_anchor"], KIND_RANK[e["kind"]], e["_src"]))
    for i, e in enumerate(entries):
        e["seq"] = i
    return {"turn_id": turn["turn_id"], "gate": turn["gate"], "flight": turn["flight"], "generated_at": now_iso(),
            "cost": _cost(store, turn_id, reports, log), "entries": [_shape(e) for e in entries]}


def _shape(e: dict) -> dict:
    keys = ("seq", "at", "t", "kind", "event", "person", "text", "refs", "data")
    return {k: e.get(k) for k in keys}


def _entry(kind: str, event: str, *, at: str | None, t, person: dict | None, text: str, refs: dict, data: dict,
           anchor: float | None, src: int) -> dict:
    return {"kind": kind, "event": event, "at": at, "t": t, "person": person, "text": text, "refs": refs, "data": data,
            "_anchor": math.inf if anchor is None else anchor, "_src": src}


# ---------------------------------------------------------------------- the activity log, used as the spine
def _turn_log(store: Store, turn_id: str, task_ids: set[str]) -> list[dict]:
    """The Turn's activity log rows, plus rows with no turn_id that act on this Turn's Tasks: the agent's tool
    calls and Task events such as a Handover, which can move Tasks of several Turns at once."""
    rows = store.query("SELECT * FROM agent_log WHERE turn_id=? OR turn_id IS NULL ORDER BY log_id", (turn_id,))
    out = []
    for r in rows:
        r = r | {"data": _json(r["data"])}
        if r["event"] == "agent_tool":
            tid = _agent_tool_task(r["data"])
            if tid not in task_ids:
                continue
            r["data"] = r["data"] | {"task_id": tid}
        elif r["turn_id"] != turn_id and not (_is_task_event(r["event"]) and set(_named_tasks(r["data"])) & task_ids):
            continue
        out.append(r)
    return out


def _agent_tool_task(data: dict) -> str | None:
    if data.get("tool") not in ("assign_task", "reassign_task") or not data.get("ok"):
        return None
    if data["tool"] == "reassign_task":
        return str((data.get("args") or {}).get("task_id") or "").strip().upper() or None
    m = _TASK_ID.search(str(data.get("result") or ""))
    return m.group(1) if m else None


def _first(log: list[dict], used: set[int], pred) -> dict | None:
    """The first log row not yet used that matches; marks it used."""
    for r in log:
        if r["log_id"] not in used and pred(r):
            used.add(r["log_id"])
            return r
    return None


# ---------------------------------------------------------------------- Inspections
def _inspections(store: Store, turn_id: str, reports: dict, log: list[dict], people: _People) -> list[dict]:
    out, seen = [], set()
    events = store.query("SELECT id, type, at, t, data FROM events WHERE turn_id=? AND type IN "
                         "('inspection_started','inspection_completed') ORDER BY id", (turn_id,))
    completed_anchor = {r["data"].get("inspection_id"): r["log_id"] for r in log if r["event"] == "inspection_completed"}
    for ev in events:
        data = _json(ev["data"])
        iid = data.get("inspection_id")
        rep = reports.get(iid)
        if rep is None:
            continue
        seen.add((iid, ev["type"]))
        anchor = completed_anchor.get(iid)
        if ev["type"] == "inspection_started":
            out.append(_started(rep, data, ev["at"], ev["t"], people,
                                None if anchor is None else anchor - 0.5, ev["id"]))
        else:
            out.append(_completed(rep, data, ev["at"], ev["t"], anchor, ev["id"]))
    for iid, rep in reports.items():                   # Inspections whose events are missing: use the report itself
        if (iid, "inspection_started") not in seen:
            out.append(_started(rep, {}, rep.get("captured_at"), None, people, None, 0))
        if (iid, "inspection_completed") not in seen and rep.get("status") != "inspecting" and rep.get("analysed_at"):
            out.append(_completed(rep, {}, rep["analysed_at"], None, completed_anchor.get(iid), 0))
    return out


def _kind_name(rep: dict) -> str:
    return {"pre_arrival": "Pre-arrival Inspection", "pre_departure": "Pre-departure Inspection",
            "on_demand": "Re-inspection"}.get(rep["kind"], f"{rep['kind'].replace('_', ' ')} Inspection")


def _started(rep: dict, data: dict, at, t, people: _People, anchor, src) -> dict:
    by = data.get("by") or {}
    person = people.by_name(by.get("name"), by.get("role")) if by else None
    angles = data.get("angles") or []
    redo = rep["kind"] == "on_demand"
    text = f"{_kind_name(rep)}{' of ' + ', '.join(angles) if angles else ''} started at {rep['gate']}"
    text += f", requested by {_who(person)}." if person else "."
    if data.get("reason") == "hold_removed":
        text += " A HOLD was recorded as removed: a new photo is taken first."
    return _entry("inspection", "reinspected" if redo else "started", at=at, t=t, person=person, text=text,
                  refs=_refs(rep["inspection_id"], angle=angles[0] if len(angles) == 1 else None),
                  data={"inspection_kind": rep["kind"], "scene_id": rep.get("scene_id"), "angles": angles,
                        "reason": data.get("reason"), "parent_inspection_id": rep.get("parent_inspection_id")},
                  anchor=anchor, src=src)


def _completed(rep: dict, data: dict, at, t, anchor, src) -> dict:
    """As it was when the Inspection finished: the event keeps that; the stored report has moved on since
    (Confirmations update it)."""
    meta = rep.get("run_metadata") or {}
    fresh = [f for f in rep.get("findings", []) if not f.get("carried_from_finding_id")]
    verdict = data.get("verdict", rep.get("verdict"))
    text = (f"{_kind_name(rep)} done at {rep['gate']}. Verdict {(verdict or 'none').replace('_', ' ')} (advisory), "
            f"{len(fresh)} new Finding{'s' if len(fresh) != 1 else ''}.")
    return _entry("inspection", "completed", at=at, t=t, person=None, text=text, refs=_refs(rep["inspection_id"]),
                  data={"inspection_kind": rep["kind"], "verdict": verdict,
                        "highest_open_severity": data.get("highest_open_severity", rep.get("highest_open_severity")),
                        "missing_angles": data.get("missing_angles", rep.get("missing_angles") or []),
                        "new_findings": len(fresh), "est_cost_usd": round(float(meta.get("est_cost_usd") or 0), 6),
                        "spent_usd": round(float(meta.get("spent_usd") or 0), 6)},
                  anchor=anchor, src=src)


# ---------------------------------------------------------------------- Tasks
def _task_label(task: dict) -> str:
    what = TYPE_LABEL.get(task["type"], task["type"].replace("_", " "))
    where = " ".join(x for x in (task["finding_label"], task["gate"], task["angle"]) if x)
    return f"{task['task_id']} ({what}{', ' + where if where else ''})"


def _tasks(tasks: dict, log: list[dict], people: _People) -> list[dict]:
    out, holder, assigned, closed = [], {}, set(), set()

    def add(task: dict, event: str, row: dict | None, text: str, data: dict, person_id: str | None, at=None) -> None:
        out.append(_entry("task", event, at=row["at"] if row else at, t=row["t"] if row else None,
                          person=people.by_id(person_id), text=text,
                          refs=_refs(data.pop("inspection_id", None) or task["inspection_id"], task["task_id"],
                                     task["finding_id"], task["angle"]),
                          data={"task_type": task["type"], "finding_label": task["finding_label"],
                                "severity": task["severity"]} | data,
                          anchor=row["log_id"] if row else None, src=task["seq"]))

    for r in log:
        d, ev = r["data"], r["event"]
        if ev == "agent_tool":
            tid = d["task_id"]
            task, args = tasks[tid], d.get("args") or {}
            to = str(args.get("assignee_id") or "").strip().lower() or None
            if d["tool"] == "assign_task" and tid not in assigned:
                assigned.add(tid)
                holder[tid] = to or task["assignee_id"]
                add(task, "assigned", r, f"{_task_label(task)} assigned to {_who(people.by_id(holder[tid]))} by the agent.",
                    {"by": "agent", "instruction": args.get("instruction") or task["instruction"]}, holder[tid])
            elif d["tool"] == "reassign_task":
                old, holder[tid] = holder.get(tid), to
                add(task, "reassigned", r, f"{_task_label(task)} moved from {_who(people.by_id(old))} to "
                    f"{_who(people.by_id(to))} by the agent: {args.get('reason') or 'no reason given'}.",
                    {"by": "agent", "from": old, "to": to, "reason": args.get("reason")}, to)
            continue
        for tid in [x for x in _named_tasks(d) if x in tasks]:
            task = tasks[tid]
            if ev == "task_assigned" and tid not in assigned:
                assigned.add(tid)
                holder[tid] = d.get("assignee_id") or task["assignee_id"]
                by = d.get("created_by") or task["created_by"]
                add(task, "assigned", r, f"{_task_label(task)} assigned to {_who(people.by_id(holder[tid]))} by {by}.",
                    {"by": by, "instruction": d.get("instruction") or task["instruction"],
                     "inspection_id": d.get("inspection_id")}, holder[tid])
            elif ev == "task_reassigned":
                old, holder[tid] = d.get("from"), d.get("to")
                add(task, "reassigned", r, f"{_task_label(task)} moved from {_who(people.by_id(old))} to "
                    f"{_who(people.by_id(d.get('to')))}: {d.get('reason') or 'no reason given'}.",
                    {"by": r["actor"], "from": old, "to": d.get("to"), "reason": d.get("reason")}, d.get("to"))
            elif ev == "task_escalated":
                add(task, "escalated", r, f"{_task_label(task)} escalated to level {d.get('level')}: {d.get('reason')}. "
                    f"Told: {', '.join(d.get('notified') or []) or 'nobody on shift'}.",
                    {"by": r["actor"], "level": d.get("level"), "reason": d.get("reason"),
                     "notified": d.get("notified") or []}, holder.get(tid, task["assignee_id"]))
            elif ev == "task_reopened":
                add(task, "reopened", r, f"{_task_label(task)} reopened: {r['text'].split(': ', 1)[-1]}",
                    {"by": r["actor"]}, holder.get(tid, task["assignee_id"]))
            elif ev in ("task_closed", "task_cancelled") and tid not in closed:
                closed.add(tid)
                event = "closed" if ev == "task_closed" else "cancelled"
                add(task, event, r, f"{_task_label(task)} {event}: {d.get('reason') or task['close_reason']}.",
                    {"reason": d.get("reason") or task["close_reason"], "confirmation_id": d.get("confirmation_id")},
                    holder.get(tid, task["assignee_id"]))
            elif _is_task_event(ev) and ev not in ("task_assigned", "task_closed", "task_cancelled"):
                # Any other Task event (a Handover, or one a later ticket adds) appears by name with the log's own
                # text. Where it names a person it moved the Task "to", that person holds the Task from now on.
                if isinstance(d.get("to"), str) and d["to"].strip():
                    holder[tid] = d["to"].strip().lower()
                add(task, ev.removeprefix("task_"), r, f"{_task_label(task)}: {r['text']}",
                    {"by": r["actor"], "log_event": ev} | {k: d[k] for k in ("from", "to", "reason", "level") if k in d},
                    holder.get(tid, task["assignee_id"]))

    first_ref = {}                                   # the first log row that names a Task (its first message)
    for r in log:
        tid = r["data"].get("task_id")
        if tid in tasks:
            first_ref.setdefault(tid, r)
    for tid, task in tasks.items():                  # Tasks the log does not cover: use the Task row itself
        if tid not in assigned:
            row = first_ref.get(tid)
            add(task, "assigned", None, f"{_task_label(task)} assigned to {_who(people.by_id(task['assignee_id']))}.",
                {"by": task["created_by"], "instruction": task["instruction"]}, task["assignee_id"], at=task["created_at"])
            if row is not None:
                out[-1]["_anchor"] = row["log_id"] - 0.5
        if tid not in closed and task["status"] in ("closed", "cancelled") and task["closed_at"]:
            add(task, task["status"], None, f"{_task_label(task)} {task['status']}: {task['close_reason']}.",
                {"reason": task["close_reason"], "confirmation_id": task["closed_by_confirmation_id"]},
                task["assignee_id"], at=task["closed_at"])
    return out


# ---------------------------------------------------------------------- Reports (what a person said)
# A Report event is named as in the commands (/accept, /done, /cant): accepted -> accept, blocked -> cant; data.report_kind
# keeps the stored kind.
REPORT_EVENT = {"accepted": "accept", "blocked": "cant"}


def _reports(store: Store, tasks: dict, log: list[dict], people: _People) -> list[dict]:
    if not tasks:
        return []
    marks = ",".join("?" * len(tasks))
    rows = store.query(f"SELECT * FROM task_reports WHERE task_id IN ({marks}) ORDER BY report_id", tuple(tasks))
    used: set[int] = set()
    out = []
    for r in rows:
        task = tasks[r["task_id"]]
        row = _first(log, used, lambda x: x["event"] in ("task_accepted", "task_reported")
                     and x["data"].get("task_id") == r["task_id"] and x["data"].get("kind") == r["kind"])
        person = people.by_id(r["by_person_id"])
        said = f' Said: "{r["raw_text"]}".' if r["raw_text"] else ""
        out.append(_entry("report", REPORT_EVENT.get(r["kind"], r["kind"]), at=r["at"], t=row["t"] if row else None, person=person,
                          text=f"Report on {_task_label(task)} by {_who(person)}: {r['kind'].replace('_', ' ')} "
                               f"(by {r['via'].replace('_', ' ')}).{said}",
                          refs=_refs(task["inspection_id"], task["task_id"], task["finding_id"], task["angle"]),
                          data={"report_id": r["report_id"], "report_kind": r["kind"], "raw_text": r["raw_text"],
                                "via": r["via"], "finding_label": task["finding_label"]},
                          anchor=row["log_id"] if row else None, src=r["report_id"]))
    return out


# ---------------------------------------------------------------------- Confirmations (what was recorded)
def _labels(store: Store, turn_id: str, reports: dict) -> dict[str, str]:
    """finding_id -> short label (F1), including the IDs a Finding had in earlier Inspections."""
    labels = {r["finding_id"]: r["label"] for r in store.query(
        "SELECT finding_id, label FROM finding_refs WHERE turn_id=? AND label IS NOT NULL", (turn_id,))}
    for rep in reversed(list(reports.values())):    # newest first, so a label flows back to the IDs it came from
        for f in rep.get("findings", []):
            if f.get("carried_from_finding_id") and f["finding_id"] in labels:
                labels.setdefault(f["carried_from_finding_id"], labels[f["finding_id"]])
    return labels


_ACTION_TEXT = {"acknowledged": "acknowledged", "removed": "removed", "false_alarm": "recorded as a false alarm",
                "not_found_on_walk": "not found on walk", "checked_by_eye": "checked by eye"}


def _confirmations(store: Store, reports: dict, log: list[dict], people: _People, labels: dict) -> list[dict]:
    out, used = [], set()
    # The dispatcher can close a Task on a Confirmation before it logs the Confirmation itself (both events in one
    # batch, as when a HOLD's new photo comes back clean). The Confirmation comes first: it is what closed the Task.
    closed_by: dict[int, int] = {}
    for r in log:
        cid = r["data"].get("confirmation_id") if r["event"] in ("task_closed", "task_cancelled") else None
        if cid is not None:
            closed_by.setdefault(cid, r["log_id"])
    rows = [c for c in store.list_confirmations() if c["inspection_id"] in reports]
    for c in rows:
        data = c["data"] or {}
        rep = reports[c["inspection_id"]]
        finding = next((f for f in rep.get("findings", []) if f["finding_id"] == c["finding_id"]), None)
        angle = data.get("angle") or (finding or {}).get("angle")
        row = _first(log, used, lambda x: x["event"] == "confirmation"
                     and x["data"].get("inspection_id") == c["inspection_id"] and x["data"].get("action") == c["action"]
                     and (x["data"].get("by") or {}).get("name") == c["name"])
        label = labels.get(c["finding_id"]) or (row["data"].get("finding_id") if row and c["finding_id"] else None)
        person = people.by_name(c["name"], c["role"], data.get("person_id"))
        via = data.get("via") or "dashboard"
        if c["action"] == "signoff":
            what = f"Inspection signed off at {rep['gate']}"
        elif c["finding_id"]:
            what = (f"{label or c['finding_id']} ({(finding or {}).get('severity') or '?'}, {angle or '?'}) "
                    f"{_ACTION_TEXT.get(c['action'], c['action'].replace('_', ' '))}")
        else:
            what = " ".join(x for x in (rep["gate"], angle, _ACTION_TEXT.get(c["action"], c["action"].replace("_", " "))) if x)
        out.append(_entry("confirmation", c["action"], at=c["at"], t=row["t"] if row else None, person=person,
                          text=f"Recorded: {what}, by {_who(person)} (via {via.replace('_', ' ')}).",
                          refs=_refs(c["inspection_id"], None, c["finding_id"], angle),
                          data={"confirmation_id": c["id"], "via": via, "raw_text": data.get("raw_text"),
                                "proposal_id": data.get("proposal_id"), "finding_label": label,
                                "severity": (finding or {}).get("severity"),
                                "outcome_details": {k: data.get(k) for k in
                                                    ("false_alarm_reason", "possible_source", "after_photo_ref")
                                                    if data.get(k) is not None}},
                          anchor=min(row["log_id"] if row else math.inf, closed_by.get(c["id"], math.inf) - 0.5),
                          src=c["id"]))
    return out


# ---------------------------------------------------------------------- cost
def _cost(store: Store, turn_id: str, reports: dict, log: list[dict]) -> dict:
    insp = sum(float((r.get("run_metadata") or {}).get("est_cost_usd") or 0) for r in reports.values())
    agent = sum(float(r["data"].get("est_cost_usd") or 0) for r in log if r["event"] == "agent_wake")
    total_wakes = store.query("SELECT COUNT(*) AS n FROM agent_wakes")[0]["n"]
    tied = store.query("SELECT COUNT(*) AS n FROM agent_log WHERE event='agent_wake' AND turn_id IS NOT NULL")[0]["n"]
    untied = max(0, total_wakes - tied)
    note = (f"{untied} agent wake{'s' if untied != 1 else ''} for messages people typed belong to no Turn and "
            "are not counted here." if untied else None)
    return {"inspections_usd": round(insp, 6), "agent_usd": round(agent, 6), "total_usd": round(insp + agent, 6),
            "note": note}
