"""The board: Tasks, Reports, messages, proposals, the console log and the short Finding labels.

Everything here is bookkeeping about who was asked to do what and what they said. Nothing in this module
touches a Finding, a Verdict or a Confirmation: a Report changes a Task, never a Finding.
"""
from __future__ import annotations

import json
from typing import Callable

from .. import report as R
from ..detect.geometry import MATCH_RADIUS, same_object, scale_for
from ..pipeline import carried_copy
from ..report import now_iso
from ..store import Store
from .models import ACTIVE, REPORT_KINDS, DispatchError

_ACTIVE_SQL = "(" + ",".join(f"'{s}'" for s in ACTIVE) + ")"


def follow_finding(old: dict, new_report: dict, new_width: int | None = None) -> dict | None:
    """The Finding in `new_report` (a re-inspection of the report `old` came from) that is the same object:
    the carried copy, or a fresh Finding at the same place on the same Angle."""
    copy = carried_copy(new_report, old)
    if copy is not None:
        return copy
    entry = next((a for a in new_report["angles"] if a["angle"] == old["angle"]), {})
    radius = MATCH_RADIUS * scale_for(new_width or entry.get("width") or 3840)
    return next((f for f in new_report["findings"] if f["angle"] == old["angle"]
                 and not f.get("carried_from_finding_id") and same_object(f["bbox"], old["bbox"], radius)), None)


class Board:
    def __init__(self, store: Store, clock: Callable[[], float]):
        self.store = store
        self.clock = clock
        self.alias: dict[str, str] = {}          # every raw finding_id a label has had -> the label

    # ------------------------------------------------------------------ activity log and messages
    def log(self, kind: str, text: str, *, event: str, task: dict | None = None, turn: dict | None = None,
            gate: str | None = None, actor: str = "code", data: dict | None = None, console: bool = True) -> int:
        """One entry in the activity log: the record of everything that happened, in order. `kind` is how the
        agent console shows it (code | wake | agent | timer | cost | idle | person | message); `event` is what
        happened; `console` says whether the terminal prints it."""
        src = task or turn or {}
        return self.store.execute(
            "INSERT INTO agent_log (at, t, kind, event, gate, turn_id, actor, text, data, console) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (now_iso(), round(self.clock(), 1), kind, event, gate or src.get("gate"), src.get("turn_id"), actor, text,
             json.dumps(data or {}, ensure_ascii=False), 1 if console else 0))

    def activity(self, after: int = 0, *, gate: str | None = None, turn_id: str | None = None,
                 console_only: bool = False, limit: int = 500) -> list[dict]:
        q, args = "SELECT * FROM agent_log WHERE log_id>?", [after]
        if gate:
            q, args = q + " AND gate=?", args + [gate]
        if turn_id:
            q, args = q + " AND turn_id=?", args + [turn_id]
        if console_only:
            q += " AND console=1"
        rows = self.store.query(q + " ORDER BY log_id LIMIT ?", tuple(args + [limit]))
        return [{"id": r["log_id"], "at": r["at"], "t": r["t"], "kind": r["kind"], "event": r["event"], "gate": r["gate"],
                 "turn_id": r["turn_id"], "actor": r["actor"], "text": r["text"], "data": json.loads(r["data"] or "{}")}
                for r in rows]

    def send(self, to_id: str, text: str, *, kind: str = "code", from_id: str = "code", task_id: str | None = None,
             proposal_id: str | None = None) -> int:
        """Put a message in a person's thread (or, from a person, in the agent's). kind: code | agent | timer |
        person | command. Every message is also an entry in the activity log."""
        mid = self.store.execute(
            "INSERT INTO messages (from_id, to_id, kind, text, task_id, proposal_id, at, t) VALUES (?,?,?,?,?,?,?,?)",
            (from_id, to_id, kind, text, task_id, proposal_id, now_iso(), round(self.clock(), 1)))
        typed = kind in ("person", "command") and to_id in ("agent", "code")
        self.log("person" if typed else "message", f"{from_id}> {text}" if typed else f"{from_id} to {to_id}: {text}",
                 event="message", task=self.task(task_id) if task_id else None, actor=from_id, console=typed,
                 data={"message_id": mid, "from": from_id, "to": to_id, "kind": kind, "task_id": task_id,
                       "proposal_id": proposal_id})
        return mid

    def message(self, message_id: int) -> dict | None:
        rows = self.store.query("SELECT * FROM messages WHERE message_id=?", (message_id,))
        return rows[0] if rows else None

    def thread(self, person_id: str, after: int = 0, limit: int = 500) -> list[dict]:
        """One person's chat thread: every message to or from them with an id above `after`, oldest first."""
        rows = self.store.query("SELECT * FROM messages WHERE (to_id=? OR from_id=?) AND message_id>? "
                                "ORDER BY message_id LIMIT ?", (person_id, person_id, after, limit))
        undelivered = [r["message_id"] for r in rows if r["to_id"] == person_id and not r["delivered_at"]]
        if undelivered:
            self.store.execute("UPDATE messages SET delivered_at=? WHERE to_id=? AND message_id<=? AND delivered_at IS NULL",
                               (now_iso(), person_id, undelivered[-1]))
        return [{"message_id": r["message_id"], "from": r["from_id"], "to": r["to_id"], "kind": r["kind"],
                 "text": r["text"], "task_id": r["task_id"], "proposal_id": r["proposal_id"], "at": r["at"], "t": r["t"]}
                for r in rows]

    def conversation(self, person_id: str, limit: int = 8) -> list[dict]:
        rows = self.store.query("SELECT message_id, from_id, to_id, kind, text FROM messages WHERE to_id=? OR from_id=? "
                                "ORDER BY message_id DESC LIMIT ?", (person_id, person_id, limit))
        return rows[::-1]

    # ------------------------------------------------------------------ tasks
    def create_task(self, *, type: str, gate: str, turn_id: str, inspection_id: str, finding_id: str | None,
                    finding_label: str | None, angle: str | None, severity: str | None, required_role: str,
                    assignee_id: str | None, instruction: str, created_by: str) -> dict:
        seq = self.store.execute(
            "INSERT INTO tasks (type, gate, turn_id, inspection_id, finding_id, finding_label, angle, severity, "
            "required_role, assignee_id, instruction, status, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (type, gate, turn_id, inspection_id, finding_id, finding_label, angle, severity, required_role,
             assignee_id, instruction, "assigned", created_by, now_iso()))
        self.store.execute("UPDATE tasks SET task_id=? WHERE seq=?", (f"K-{seq}", seq))
        return self.task(f"K-{seq}")

    def task(self, task_id: str | None) -> dict | None:
        rows = self.store.query("SELECT * FROM tasks WHERE upper(task_id)=?", ((task_id or "").strip().upper(),))
        return rows[0] if rows else None

    def need_task(self, task_id: str | None) -> dict:
        t = self.task(task_id)
        if t is None:
            raise DispatchError(f"No Task {task_id}")
        return t

    def tasks(self, *, turn_id: str | None = None, assignee_id: str | None = None, active: bool = True,
              limit: int = 200) -> list[dict]:
        q, args = "SELECT * FROM tasks WHERE 1=1", []
        if active:
            q += f" AND status IN {_ACTIVE_SQL}"
        if turn_id:
            q, args = q + " AND turn_id=?", args + [turn_id]
        if assignee_id:
            q, args = q + " AND assignee_id=?", args + [assignee_id]
        return self.store.query(q + " ORDER BY seq DESC LIMIT ?", tuple(args + [limit]))[::-1]

    def update_task(self, task_id: str, **fields) -> dict:
        sets = ", ".join(f"{k}=?" for k in fields)
        self.store.execute(f"UPDATE tasks SET {sets} WHERE task_id=?", tuple(fields.values()) + (task_id,))
        return self.task(task_id)

    def close_task(self, task_id: str, *, reason: str, confirmation_id: int | None = None, cancelled: bool = False) -> dict:
        return self.update_task(task_id, status="cancelled" if cancelled else "closed", closed_at=now_iso(),
                                close_reason=reason, closed_by_confirmation_id=confirmation_id)

    def add_report(self, task_id: str, *, by_person_id: str, kind: str, raw_text: str | None, via: str) -> dict:
        """Record what a person said about a Task. This never changes a Finding."""
        if kind not in REPORT_KINDS:
            raise DispatchError(f"kind must be one of {', '.join(REPORT_KINDS)}")
        rid = self.store.execute("INSERT INTO task_reports (task_id, by_person_id, at, kind, raw_text, via) "
                                 "VALUES (?,?,?,?,?,?)", (task_id, by_person_id, now_iso(), kind, raw_text, via))
        return self.store.query("SELECT * FROM task_reports WHERE report_id=?", (rid,))[0]

    def reports(self, task_id: str) -> list[dict]:
        return self.store.query("SELECT * FROM task_reports WHERE task_id=? ORDER BY report_id", (task_id,))

    @staticmethod
    def task_view(t: dict) -> dict:
        return {"task_id": t["task_id"], "type": t["type"], "gate": t["gate"], "turn_id": t["turn_id"],
                "inspection_id": t["inspection_id"], "finding_id": t["finding_label"], "angle": t["angle"],
                "severity": t["severity"], "required_role": t["required_role"], "assignee_id": t["assignee_id"],
                "instruction": t["instruction"], "status": t["status"], "created_by": t["created_by"],
                "escalation_level": t["escalation_level"], "created_at": t["created_at"], "closed_at": t["closed_at"],
                "close_reason": t["close_reason"], "closed_by_confirmation_id": t["closed_by_confirmation_id"]}

    # ------------------------------------------------------------------ Finding labels (F1, F2, ...)
    def settled_latest(self, turn_id: str) -> dict | None:
        """The Turn's newest Inspection that has finished running."""
        reports = [r for r in self.store.reports_for_turn(turn_id) if r["status"] != "inspecting"]
        return reports[-1] if reports else None

    def advance_refs(self, turn_id: str) -> dict | None:
        """Move every label of this Turn onto the Turn's latest Inspection and label Findings seen for the
        first time. A re-inspection gives Findings new IDs; people keep using the same short label. Labels whose
        Inspection is not an ancestor of the latest one are marked superseded. Returns the latest report."""
        reports = [r for r in self.store.reports_for_turn(turn_id) if r["status"] != "inspecting"]
        if not reports:
            return None
        latest, by_id = reports[-1], {r["inspection_id"]: r for r in reports}
        chain, cur = [], latest                                   # latest back to the root of its chain
        while cur is not None:
            chain.append(cur)
            cur = by_id.get(cur.get("parent_inspection_id"))
        chain.reverse()
        position = {r["inspection_id"]: i for i, r in enumerate(chain)}
        refs = self.store.query("SELECT * FROM finding_refs WHERE turn_id=? AND superseded=0", (turn_id,))
        for ref in refs:
            if ref["inspection_id"] == latest["inspection_id"]:
                continue
            i = position.get(ref["inspection_id"])
            f = next((x for x in chain[i]["findings"] if x["finding_id"] == ref["finding_id"]), None) if i is not None else None
            for nxt in chain[i + 1:] if f is not None else []:
                f = follow_finding(f, nxt)
                if f is None:
                    break
            if f is None:
                self.store.execute("UPDATE finding_refs SET superseded=1 WHERE seq=?", (ref["seq"],))
            else:
                self.alias[f["finding_id"]] = ref["label"]
                self.store.execute("UPDATE finding_refs SET inspection_id=?, finding_id=? WHERE seq=?",
                                   (latest["inspection_id"], f["finding_id"], ref["seq"]))
        known = {r["finding_id"] for r in self.store.query(
            "SELECT finding_id FROM finding_refs WHERE inspection_id=? AND superseded=0", (latest["inspection_id"],))}
        for f in latest["findings"]:
            if f["finding_id"] not in known and R.is_open(f):
                seq = self.store.execute("INSERT INTO finding_refs (turn_id, gate, inspection_id, finding_id) VALUES (?,?,?,?)",
                                         (turn_id, latest["gate"], latest["inspection_id"], f["finding_id"]))
                self.store.execute("UPDATE finding_refs SET label=? WHERE seq=?", (f"F{seq}", seq))
                self.alias[f["finding_id"]] = f"F{seq}"
        for ref in refs:
            self.alias.setdefault(ref["finding_id"], ref["label"])
        return latest

    def labels(self, inspection_id: str) -> dict[str, str]:
        """finding_id -> label for the Findings of one Inspection."""
        return {r["finding_id"]: r["label"] for r in self.store.query(
            "SELECT finding_id, label FROM finding_refs WHERE inspection_id=? AND superseded=0", (inspection_id,))}

    def ref(self, label: str | None) -> dict | None:
        rows = self.store.query("SELECT * FROM finding_refs WHERE upper(label)=?", ((label or "").strip().upper(),))
        return rows[0] if rows else None

    def resolve(self, label: str | None) -> tuple[dict, dict, dict]:
        """(ref, latest report, Finding) for a label, always on the Turn's latest Inspection."""
        ref = self.ref(label)
        if ref is None:
            raise DispatchError(f"No Finding {label}")
        self.advance_refs(ref["turn_id"])
        ref = self.ref(label)
        if ref["superseded"]:
            raise DispatchError(f"Finding {ref['label']} belongs to an Inspection that a newer one has replaced")
        report = self.store.get_report(ref["inspection_id"])
        finding = next((f for f in report["findings"] if f["finding_id"] == ref["finding_id"]), None)
        if finding is None:
            raise DispatchError(f"Finding {ref['label']} is no longer in the latest Inspection")
        return ref, report, finding

    # ------------------------------------------------------------------ proposals
    def create_proposal(self, *, to_id: str, action: dict, created_by: str, expires_t: float) -> dict:
        seq = self.store.execute("INSERT INTO proposals (to_id, action, status, created_by, created_at, expires_t) "
                                 "VALUES (?,?,?,?,?,?)", (to_id, json.dumps(action), "pending", created_by, now_iso(), expires_t))
        self.store.execute("UPDATE proposals SET proposal_id=? WHERE seq=?", (f"P-{seq}", seq))
        self.log("code", f"Asked {to_id} ({created_by}): {action.get('text')}?  [y / n]  (P-{seq})", event="proposal_created",
                 actor=created_by, gate=action.get("gate"), turn={"turn_id": action.get("turn_id")} if action.get("turn_id") else None,
                 data={"proposal_id": f"P-{seq}", "to": to_id, "action": action}, console=created_by != "agent")
        return self.proposal(f"P-{seq}")

    def proposal(self, proposal_id: str | None) -> dict | None:
        rows = self.store.query("SELECT * FROM proposals WHERE upper(proposal_id)=?", ((proposal_id or "").strip().upper(),))
        return rows[0] | {"action": json.loads(rows[0]["action"])} if rows else None

    def pending_proposals(self, to_id: str) -> list[dict]:
        """Oldest first. Proposals past their time are marked expired here, by code."""
        self.store.execute("UPDATE proposals SET status='expired' WHERE status='pending' AND expires_t<=?", (self.clock(),))
        rows = self.store.query("SELECT * FROM proposals WHERE to_id=? AND status='pending' ORDER BY seq", (to_id,))
        return [r | {"action": json.loads(r["action"])} for r in rows]

    def set_proposal(self, proposal_id: str, status: str) -> None:
        self.store.execute("UPDATE proposals SET status=?, answered_at=? WHERE proposal_id=?", (status, now_iso(), proposal_id))
        p = self.proposal(proposal_id)
        self.log("code", f"{p['to_id']} answered {proposal_id} ({p['action'].get('text')}): {status}.", event="proposal_answered",
                 actor=p["to_id"], gate=p["action"].get("gate"),
                 turn={"turn_id": p["action"].get("turn_id")} if p["action"].get("turn_id") else None,
                 data={"proposal_id": proposal_id, "status": status, "action": p["action"]})

    def proposal_view(self, p: dict) -> dict:
        return {"proposal_id": p["proposal_id"], "kind": p["action"].get("kind"), "question": p["action"].get("text"),
                "action": {k: v for k, v in p["action"].items() if k not in ("text", "finding_status")},
                "created_by": p["created_by"], "created_at": p["created_at"], "status": p["status"],
                "expires_t": p["expires_t"], "expires_in_s": max(0.0, round(p["expires_t"] - self.clock(), 1))}
