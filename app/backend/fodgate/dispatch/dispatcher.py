"""The dispatcher: an event-driven loop that turns Inspection results into Tasks for people (spec/dispatch.md).

Code first. Every state change in the store is an event; the dispatcher sleeps on the store's condition and
wakes when one arrives. Most events are handled here with fixed wording and no model: the HOLD alert, Tasks
that have only one possible owner, closing Tasks when a Confirmation lands, timers and Escalation. The model
(`agent.py`) is woken only when a person typed free text or when work could go to more than one person. If the
model is unavailable, slow, refused or over the spend cap, the same work is routed here by a fixed rule.

Nothing in this module records a Confirmation. That happens only in `commands.py`, as the signed-in person.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Callable

from .. import assistant, config, report as R
from ..llm import LLM, spend_allowed
from ..rules import load_rules
from ..workflow import Workflow
from . import agent as agent_mod
from .models import (ACTIVE, FINDING_TASKS, ROLE_LABEL, TASK_TYPES, TYPE_LABEL, WORK_ROLES, DispatchError,
                     required_role, role_may_take)
from .roster import Roster
from .tasks import Board
from .timers import Timers

log = logging.getLogger("fodgate.dispatch")

TURN_EVENTS = ("inspection_completed", "finding_acknowledged", "finding_confirmed", "angle_checked_by_eye",
               "inspection_signed_off", "departed")
MAX_WAKES_PER_MINUTE = 20
MAX_LEVEL = 2
DEFAULT_LADDER = {
    "hold_unacknowledged_s": [30, 60],          # level 1, then level 2
    "hold_pushback_under_min": 2.0,             # an open HOLD this close to scheduled pushback is level 2
    "unusable_pushback_under_min": 2.0,         # so is an unusable Angle nobody has re-inspected or checked
    "no_report_ask_s": 60, "no_report_offer_s": 120,
    "proposal_expires_s": 120,
}


def load_ladder() -> dict:
    f = config.escalation_path()
    data = json.loads(f.read_text()) if f.is_file() else {}
    return DEFAULT_LADDER | {k: v for k, v in data.items() if k in DEFAULT_LADDER}


OUTSIDE_WORD = {"ramp_1_control": "ramp1", "airport_operations": "airport-ops"}      # as typed after /reported
OUTSIDE_WHY = {"ramp_1_control": "the shared taxilane between stands", "airport_operations": "the movement area"}
_MOVEMENT_AREA = ("movement area", "taxiway", "runway", "zipper")


def outside_recipient(finding: dict) -> str:
    """Who debris outside the gate safety envelope is reported to (FOD-R10): the movement area goes to Airport
    Operations, the shared taxilane to Ramp 1 control. When the location text does not settle it, Ramp 1 control."""
    where = f"{finding.get('location_text') or ''} {finding.get('description') or ''}".lower()
    return "airport_operations" if any(w in where for w in _MOVEMENT_AREA) else "ramp_1_control"


def _short(text: str, limit: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


class Dispatcher:
    def __init__(self, wf: Workflow, llm: LLM | None = None, *, player=None, roster: dict | None = None,
                 ladder: dict | None = None, clock: Callable[[], float] | None = None,
                 create: Callable[..., object] | None = None, mode: str | None = None):
        self.wf, self.store, self.llm, self.player = wf, wf.store, llm, player
        self.mode = mode or config.agent_mode()          # on: model when available; anything else: code only
        self.create = create                             # replaces client.messages.create in tests
        self.lock = threading.RLock()                    # serialises every change to the board
        self._overtime = 0.0
        self.clock = clock or (lambda: self.wf.clock() + self._overtime)
        self.board = Board(self.store, self.clock)
        self.timers = Timers(self.store, self.clock)
        self.roster = Roster(self.store, roster)
        self.ladder = DEFAULT_LADDER | (ladder or load_ladder())
        self.rules = load_rules()
        last = self.store.query("SELECT COALESCE(MAX(id), 0) AS n FROM events")[0]["n"]
        self.cursor = last                               # events from before this process are not replayed
        self._epoch = self.store.epoch
        self._wakes: deque[dict] = deque()
        self._wake_cv = threading.Condition()
        self._wake_times: deque[float] = deque()
        self._routing_pending: set[str] = set()
        self._unroutable: set[tuple] = set()
        self._running_wakes = 0
        self._idle_announced = True
        self._model_note: str | None = None
        self.model_calls = 0                             # requests sent to the model by this dispatcher
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()

    # ------------------------------------------------------------------ threads
    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        with self.lock:
            self.resync()
            ok, why = self.model_ready()
            self.board.log("code", "Dispatcher started. " + (
                f"Agent model {config.AGENT_MODEL} is woken for free text and routing choices."
                if ok else f"Code-only routing ({why}). Slash commands work as usual.") + " Waiting for events.",
                           event="dispatcher_started")

        def loop():
            last = time.monotonic()
            while not self._stop.is_set():
                with self.store.changed:
                    self.store.changed.wait(0.5)         # the timeout only serves code timers; no model call
                now = time.monotonic()
                self._tick(now - last)
                last = now
                try:
                    self.step()
                except Exception:
                    log.exception("dispatcher step failed")
                if self._wakes:
                    with self._wake_cv:
                        self._wake_cv.notify_all()

        def worker():
            while not self._stop.is_set():
                with self._wake_cv:
                    if not self._wakes:
                        self._wake_cv.wait(0.5)
                try:
                    self.drain_wakes()
                except Exception:
                    log.exception("agent wake failed")

        for name, fn in (("dispatcher", loop), ("agent-wakes", worker)):
            th = threading.Thread(target=fn, name=name, daemon=True)
            th.start()
            self._threads.append(th)

    def stop(self) -> None:
        self._stop.set()
        self.store.notify()
        with self._wake_cv:
            self._wake_cv.notify_all()
        self._threads = []

    def _tick(self, dt: float) -> None:
        """Timers run on the demo clock. Once the scripted timeline has ended the clock keeps going here, so
        an Escalation that is still pending does not freeze."""
        p = self.player
        if p is not None and p.duration > 0 and p.t >= p.duration and not p.playing:
            self._overtime += dt * p.speed

    # ------------------------------------------------------------------ the loop body
    def step(self) -> None:
        """Handle new events and due timers. Pure code: this never calls the model."""
        with self.lock:
            if self.store.epoch != self._epoch:                 # demo Reset
                self._epoch, self.cursor, self._overtime = self.store.epoch, 0, 0.0
                self._wakes.clear()
                self._routing_pending.clear()
                self._unroutable.clear()
                self.board.alias.clear()
                self._idle_announced = True
                self.board.log("code", "Demo reset. Tasks, messages and timers cleared. Waiting for events.", event="demo_reset")
            for e in self.store.events_after(self.cursor):
                self.cursor = e["id"]
                try:
                    self._on_event(e)
                except Exception:
                    log.exception("event %s (%s) failed", e["id"], e["type"])
            for tm in self.timers.due():
                try:
                    self._on_timer(tm)
                except Exception:
                    log.exception("timer %s failed", tm["timer_id"])
            self._announce_idle()

    def settle(self, rounds: int = 20) -> None:
        """Run until nothing is left to do (tests and single-threaded use)."""
        for _ in range(rounds):
            self.step()
            if not self._wakes and not self.store.events_after(self.cursor):
                return
            self.drain_wakes()

    def resync(self) -> None:
        for gate in self.wf.gates:
            turn = self.store.current_turn(gate)
            if turn:
                self.sync_turn(turn["turn_id"])

    # ------------------------------------------------------------------ people and wording
    def _name(self, person_id: str | None) -> str:
        p = self.roster.person(person_id)
        return p["name"] if p else (person_id or "nobody")

    def _who(self, person_id: str | None) -> str:
        p = self.roster.person(person_id)
        return f"{p['name']} ({ROLE_LABEL[p['role']]})" if p else (person_id or "nobody")

    def _supervisors(self) -> list[dict]:
        return self.roster.people(role="supervisor")

    def _leads(self) -> list[dict]:
        return self.roster.people(on_shift=True, role="ramp_lead")

    def _pushback(self, turn: dict | None) -> str:
        m = self.wf._minutes_to_pushback(turn) if turn else None
        return "" if m is None else f"Scheduled pushback in {m} min."

    def _flight(self, turn: dict | None) -> str:
        return (turn or {}).get("flight") or ""

    def eligible(self, task_type: str, gate: str, severity: str | None = None) -> list[dict]:
        """People on shift who may be given this Task, best first: covers the Gate, a Ramp Agent for work a
        Ramp Agent may do (leads keep their hands free), signed in, fewest open Tasks."""
        out = []
        for p in self.roster.people(on_shift=True):
            if not role_may_take(p["role"], task_type):
                continue
            if task_type == "report_outside_boundary" and severity and not self.rules.role_may_confirm(p["role"], severity):
                continue
            out.append(p | {"open_tasks": len(self.board.tasks(assignee_id=p["person_id"]))})
        covering = [p for p in out if gate in p["gates"]]
        prefer = "ramp_lead" if required_role(task_type) == "ramp_lead" else "ramp_agent"
        return sorted(covering or out, key=lambda p: (p["role"] != prefer, not p["signed_in"], p["open_tasks"], p["person_id"]))

    # ------------------------------------------------------------------ events
    def _on_event(self, e: dict) -> None:
        kind, data = e["type"], e["data"]
        if kind == "person_message":
            self._on_person_message(data)
            return
        if kind not in TURN_EVENTS or not e["turn_id"]:
            return
        turn = self.store.get_turn(e["turn_id"])
        if turn is None:
            return
        latest = self.board.advance_refs(e["turn_id"])
        gate, by = e["gate"], data.get("by") or {}
        who = f"{by.get('name')} ({ROLE_LABEL.get(by.get('role'), by.get('role'))})"
        label = self.board.alias.get(data.get("finding_id") or "", data.get("finding_id"))

        def conf(action: str) -> dict:                          # a Confirmation: who, what, and the audit row
            return {"event": "confirmation", "turn": turn, "actor": by.get("name") or "?",
                    "data": {"action": action, "finding_id": label, "angle": data.get("angle"), "by": by,
                             "inspection_id": data.get("inspection_id")}}
        if kind == "inspection_completed":
            self._log_inspection(turn, self.store.get_report(data["inspection_id"]))
        elif kind == "finding_acknowledged":
            self.board.log("code", f"Recorded: {label} acknowledged by {who}.", **conf("acknowledged"))
        elif kind == "finding_confirmed":
            self.board.log("code", f"Recorded: {label} {data.get('outcome', '').replace('_', ' ')}, confirmed by {who}.",
                           **conf(data.get("outcome")))
        elif kind == "angle_checked_by_eye":
            self.board.log("code", f"Recorded: {gate} {data.get('angle')} checked by eye by {who}.", **conf("checked_by_eye"))
        elif kind == "inspection_signed_off":
            self.board.log("code", f"Inspection signed off by {who}. {gate} confirmed clear.", **conf("signoff"))
        elif kind == "departed":
            self.board.log("code", f"{gate} {self._flight(turn)} departed.", event="departed", turn=turn)
        del latest
        self.sync_turn(e["turn_id"])

    def _log_inspection(self, turn: dict, rep: dict | None) -> None:
        if rep is None:
            return
        labels = self.board.labels(rep["inspection_id"])
        kind = rep["kind"].replace("_", "-") + " Inspection"
        if rep["kind"] == "on_demand":
            fresh = [a["angle"] for a in rep["angles"] if a.get("source_inspection_id") == rep["inspection_id"]]
            kind = "re-inspection" + (f" of {', '.join(fresh)}" if fresh and len(fresh) < len(rep["angles"]) else "")
        lines = [f"{rep['gate']} {self._flight(turn)} {kind} done. "
                 f"Verdict {rep['verdict'].replace('_', ' ')} (advisory)."]
        for f in R.open_findings(rep):
            lines.append(f"{labels.get(f['finding_id'], '?'):<3} {f['severity']:<8} {f['angle']:<5} {f['rule_id']:<7} "
                         f"{_short(f['description'], 58)}")
        for a in R.unresolved_unusable_angles(rep):
            reason = next(x["unusable_reason"] for x in rep["angles"] if x["angle"] == a)
            lines.append(f"{a} unusable ({reason}): not covered by the cameras")
        if self._pushback(turn):
            lines.append(self._pushback(turn))
        self.board.log("code", "\n".join(lines), event="inspection_completed", turn=turn,
                       data={"inspection_id": rep["inspection_id"], "kind": rep["kind"], "verdict": rep["verdict"],
                             "highest_open_severity": rep["highest_open_severity"],
                             "open_findings": [labels.get(f["finding_id"]) for f in R.open_findings(rep)]})

    # ------------------------------------------------------------------ keeping Tasks in step with the record
    def needed(self, latest: dict) -> list[dict]:
        """The work an Inspection still asks of people, computed from the stored report. Severity is copied
        from the Finding; nothing here comes from the model."""
        labels, out = self.board.labels(latest["inspection_id"]), []
        for f in R.open_findings(latest):
            if f["zone_tier"] == "outside_boundary":
                kind = "report_outside_boundary"
            else:
                kind = "ack_hold" if f["severity"] == "HOLD" else "remove"
            out.append({"type": kind, "label": labels.get(f["finding_id"]), "angle": f["angle"], "finding": f})
        for a in R.unresolved_unusable_angles(latest):
            out.append({"type": "check_by_eye", "label": None, "angle": a, "finding": None})
        if not out:
            out.append({"type": "sign_off", "label": None, "angle": None, "finding": None})
        return out

    def sync_turn(self, turn_id: str, *, allow_wake: bool = True) -> None:
        """Close Tasks whose work a Confirmation has finished, point the rest at the Turn's latest Inspection,
        and find an owner for anything that has none."""
        with self.lock:
            turn = self.store.get_turn(turn_id)
            latest = self.board.advance_refs(turn_id)
            if turn is None or latest is None:
                return
            active = self.board.tasks(turn_id=turn_id)
            if turn["phase"] == "departed" or latest["status"] == "confirmed":
                conf = self.store.query("SELECT MAX(id) AS id FROM confirmations WHERE inspection_id=? AND action='signoff'",
                                        (latest["inspection_id"],))[0]["id"]
                self._close(active, "Inspection signed off", conf)
                return
            labels = self.board.labels(latest["inspection_id"])
            by_label = {labels[f["finding_id"]]: f for f in latest["findings"] if f["finding_id"] in labels}
            unresolved = R.unresolved_unusable_angles(latest)
            needed = self.needed(latest)
            for t in active:
                if t["type"] in FINDING_TASKS:
                    f = by_label.get(t["finding_label"])
                    if f is None:
                        self._close([t], "replaced by a newer Inspection", None, cancelled=True)
                    elif not R.is_open(f):
                        conf = f.get("confirmation") or {}
                        how = conf.get("outcome") or "reported"
                        who = (conf.get("confirmed_by") or (f.get("acknowledged") or {}).get("by") or {}).get("name", "?")
                        self._close([t], f"{t['finding_label']} {how.replace('_', ' ')}, confirmed by {who}",
                                    self._confirmation_id(t["finding_label"]))
                    else:
                        self.board.update_task(t["task_id"], inspection_id=latest["inspection_id"],
                                               finding_id=f["finding_id"])
                        if t["type"] == "ack_hold" and f["status"] == "acknowledged" and t["status"] == "assigned":
                            self.board.update_task(t["task_id"], status="accepted")
                            self.timers.cancel(t["task_id"], ("hold_unack_1", "hold_unack_2"))
                elif t["type"] == "check_by_eye":
                    if t["angle"] in unresolved:
                        self.board.update_task(t["task_id"], inspection_id=latest["inspection_id"])
                    else:
                        self._close([t], f"{t['angle']} re-inspected or checked by eye", None)
                elif t["type"] == "sign_off":
                    if needed[0]["type"] == "sign_off":
                        self.board.update_task(t["task_id"], inspection_id=latest["inspection_id"])
                    else:
                        self._close([t], "the Inspection has open work again", None, cancelled=True)
            have = {(t["type"], t["finding_label"] or t["angle"] or "") for t in self.board.tasks(turn_id=turn_id)}
            missing = [n for n in needed if (n["type"], n["label"] or n["angle"] or "") not in have]
            if missing:
                self._route(turn, latest, missing, allow_wake)

    def _confirmation_id(self, label: str) -> int | None:
        ids = [fid for fid, lab in self.board.alias.items() if lab == label]
        if not ids:
            return None
        marks = ",".join("?" * len(ids))
        return self.store.query(f"SELECT MAX(id) AS id FROM confirmations WHERE finding_id IN ({marks})", tuple(ids))[0]["id"]

    def _close(self, tasks: list[dict], reason: str, confirmation_id: int | None, *, cancelled: bool = False) -> None:
        for t in tasks:
            self.board.close_task(t["task_id"], reason=reason, confirmation_id=confirmation_id, cancelled=cancelled)
            self.timers.cancel(t["task_id"])
        if tasks:
            ids = ", ".join(t["task_id"] for t in tasks)
            self.board.log("code", f"Task{'s' if len(tasks) > 1 else ''} {ids} {'cancelled' if cancelled else 'closed'}: "
                                   f"{reason}. Timers cancelled.", event="task_cancelled" if cancelled else "task_closed", task=tasks[0],
                           data={"task_ids": [t["task_id"] for t in tasks], "reason": reason, "confirmation_id": confirmation_id})

    def _route(self, turn: dict, latest: dict, missing: list[dict], allow_wake: bool) -> None:
        """Find an owner for work that has none. HOLD alerts and sign-off requests are always sent by code,
        at once. The model is asked only when the rest could go to more than one person."""
        rest = []
        for m in missing:
            if m["type"] in ("ack_hold", "sign_off"):
                self._assign_by_code(turn, m)
            else:
                rest.append(m)
        if not rest or turn["turn_id"] in self._routing_pending:
            return
        choice = any(len(self.eligible(m["type"], turn["gate"], (m["finding"] or {}).get("severity"))) > 1 for m in rest)
        if allow_wake and choice:
            ok, why = self.model_ready()
            if ok:
                self._routing_pending.add(turn["turn_id"])
                self._queue({"kind": "routing", "turn_id": turn["turn_id"], "gate": turn["gate"],
                             "trigger": "inspection_completed"})
                return
            self._note_model(why)
        for m in rest:
            self._assign_by_code(turn, m)

    def _note_model(self, why: str) -> None:
        if self.mode == "on" and why != self._model_note:
            self._model_note = why
            self.board.log("code", f"Agent model not used ({why}). Routing by fixed rule; slash commands work as usual.",
                           event="model_unavailable", data={"reason": why})

    def _assign_by_code(self, turn: dict, m: dict) -> None:
        severity = (m["finding"] or {}).get("severity")
        people = self.eligible(m["type"], turn["gate"], severity)
        key = (turn["turn_id"], m["type"], m["label"] or m["angle"] or "")
        if not people:
            if key not in self._unroutable:                  # never stay silent when work has no owner
                self._unroutable.add(key)
                what = f"{TYPE_LABEL[m['type']]} {m['label'] or m['angle'] or ''}".strip()
                text = (f"Cannot route '{what}' at {turn['gate']}: nobody on shift may take it"
                        + (" (a Ramp Lead is required)." if required_role(m["type"]) == "ramp_lead" else "."))
                for s in self._supervisors():
                    self.board.send(s["person_id"], text)
                self.board.log("code", text + " Supervisor told.", event="unroutable", turn=turn)
            return
        try:
            self.assign(type=m["type"], gate=turn["gate"], finding_label=m["label"], angle=m["angle"],
                        assignee_id=people[0]["person_id"], instruction=None, created_by="code")
        except DispatchError as err:
            log.warning("code routing of %s refused: %s", key, err)

    # ------------------------------------------------------------------ assigning (code and the agent tool)
    def assign(self, *, type: str, gate: str, finding_label: str | None, angle: str | None, assignee_id: str,
               instruction: str | None, created_by: str) -> dict:
        """Create a Task for a person. Every check is made here, whoever asks. Raises DispatchError."""
        with self.lock:
            if type not in TASK_TYPES:
                raise DispatchError(f"type must be one of {', '.join(TASK_TYPES)}")
            turn = self.store.current_turn(gate) if gate in self.wf.gates else None
            if turn is None or turn["phase"] == "departed":
                raise DispatchError(f"There is no Turn in progress at Gate {gate}")
            latest = self.board.advance_refs(turn["turn_id"])
            if latest is None:
                raise DispatchError(f"Gate {gate} has no finished Inspection yet")
            if latest["status"] == "confirmed":
                raise DispatchError(f"The latest Inspection at {gate} is already signed off")
            person = self.roster.person(assignee_id)
            if person is None:
                raise DispatchError(f"No such person: {assignee_id}")
            if person["shift"] != "on":
                raise DispatchError(f"{person['name']} is not on shift ({person['shift']})")
            if not role_may_take(person["role"], type):
                raise DispatchError(f"A '{TYPE_LABEL[type]}' Task can only go to a Ramp Lead; "
                                    f"{person['name']} is a {ROLE_LABEL[person['role']]}")
            f, severity = None, None
            if type in FINDING_TASKS:
                try:
                    ref, report, f = self.board.resolve(finding_label)
                except DispatchError:
                    raise DispatchError(f"finding_id is required for a '{type}' Task; open Findings at {gate}: "
                                        + (", ".join(n["label"] for n in self.needed(latest) if n["label"]) or "none")) from None
                if ref["turn_id"] != turn["turn_id"]:
                    raise DispatchError(f"{ref['label']} is not at Gate {gate}")
                if not R.is_open(f):
                    raise DispatchError(f"{ref['label']} is already closed by a Confirmation")
                outside = f["zone_tier"] == "outside_boundary"
                if type == "ack_hold" and (f["severity"] != "HOLD" or outside):
                    raise DispatchError(f"{ref['label']} is not a HOLD inside the gate safety envelope")
                if type == "report_outside_boundary" and not outside:
                    raise DispatchError(f"{ref['label']} is inside the gate safety envelope")
                if type in ("remove", "walk_and_report") and outside:
                    raise DispatchError(f"{ref['label']} is outside the gate safety envelope: it is reported, not removed "
                                        "by the ramp crew (use report_outside_boundary)")
                if type == "report_outside_boundary" and not self.rules.role_may_confirm(person["role"], f["severity"]):
                    raise DispatchError(f"Only a Ramp Lead can record a {f['severity']} Finding as reported")
                finding_label, angle, severity = ref["label"], f["angle"], f["severity"]
            elif type == "check_by_eye":
                if angle not in R.unresolved_unusable_angles(latest):
                    raise DispatchError(f"{angle} at {gate} is not an unusable Angle waiting for a check")
                finding_label = None
            else:
                if R.open_findings(latest) or R.unresolved_unusable_angles(latest):
                    raise DispatchError(f"{gate} still has open Findings or unusable Angles; it cannot be signed off yet")
                finding_label, angle = None, None
            for t in self.board.tasks(turn_id=turn["turn_id"]):
                if t["type"] == type and (t["finding_label"] or t["angle"] or "") == (finding_label or angle or ""):
                    raise DispatchError(f"Already assigned: {t['task_id']} ({TYPE_LABEL[type]}) is with {self._name(t['assignee_id'])}")
            task = self.board.create_task(
                type=type, gate=gate, turn_id=turn["turn_id"], inspection_id=latest["inspection_id"],
                finding_id=f["finding_id"] if f else None, finding_label=finding_label, angle=angle, severity=severity,
                required_role=required_role(type), assignee_id=person["person_id"],
                instruction=_short(instruction, 300) if instruction else self._default_instruction(type, gate, angle, f),
                created_by=created_by)
            self._idle_announced = False
            self.board.send(person["person_id"], self._task_text(task, f, turn, latest),
                            kind="agent" if created_by == "agent" else "code",
                            from_id="agent" if created_by == "agent" else "code", task_id=task["task_id"])
            self._start_timers(task, turn)
            if created_by != "agent":                           # the agent's own calls are logged by its tool wrapper
                self.board.log("code", f"{task['task_id']} {TYPE_LABEL[type]} {finding_label or angle or gate} "
                                       f"-> {self._who(person['person_id'])}.", event="task_assigned", task=task,
                               data=self.board.task_view(task))
            if type == "ack_hold":
                others = [p for p in self._leads() if p["person_id"] != person["person_id"]]
                for p in others:
                    self.board.send(p["person_id"], f"HOLD at {gate} {angle} ({finding_label}): {_short(f['description'])} "
                                    f"({f['rule_id']}). Assigned to {person['name']}. No action for you unless it escalates.",
                                    task_id=task["task_id"])
                self.board.log("code", "HOLD alert delivered to every on-shift Ramp Lead: "
                               + ", ".join(p["person_id"] for p in [person] + others) + ".", event="hold_alert", task=task,
                               data={"task_id": task["task_id"], "delivered_to": [p["person_id"] for p in [person] + others]})
            return task

    @staticmethod
    def _default_instruction(type: str, gate: str, angle: str | None, f: dict | None) -> str:
        if type == "ack_hold":
            return f"Acknowledge and clear the HOLD at {gate} {angle}: {_short(f['description'])}"
        if type == "remove":
            return f"Remove the object flagged at {gate} {angle}: {_short(f['description'], 110)}"
        if type == "walk_and_report":
            return f"Walk to {gate} {angle}, look for the flagged object and report back: {_short(f['description'], 110)}"
        if type == "report_outside_boundary":
            return (f"Report the object outside the gate safety envelope at {gate} to "
                    f"{assistant.RECIPIENTS[outside_recipient(f)]}; do not remove it: {_short(f['description'], 90)}")
        if type == "check_by_eye":
            return f"Check {gate} {angle} by eye or re-inspect it"
        return f"Sign off the latest Inspection at {gate}"

    def _task_text(self, task: dict, f: dict | None, turn: dict, latest: dict) -> str:
        tid, gate, angle, label = task["task_id"], task["gate"], task["angle"], task["finding_label"]
        push = self._pushback(turn)
        if task["type"] == "ack_hold":
            return (f"HOLD at {gate} {angle} ({label}): {_short(f['description'])} ({f['rule_id']}). "
                    f"{self._flight(turn)}: {push or 'no scheduled pushback time.'} Nothing moves until a Ramp Lead "
                    f"clears this. Type /ack {label} when someone is going to it. Task {tid}.")
        if task["type"] in ("remove", "walk_and_report"):
            return (f"Task {tid}: {task['instruction'].rstrip('.')} ({task['severity']}, {gate} {angle}, {label}). "
                    f"Report back here when done, or type /done {tid}.")
        if task["type"] == "report_outside_boundary":
            to = outside_recipient(f)
            draft = assistant.Tools(latest, turn).draft_outside_boundary_report(to, [f["finding_id"]])
            return (f"Task {tid}: {_short(f['description'])} lies outside the gate safety envelope at {gate} "
                    f"({label}, {task['severity']}). Do not remove it: it is not the ramp crew's to remove. Report it to "
                    f"{assistant.RECIPIENTS[to]} ({OUTSIDE_WHY[to]}), then record who you told: "
                    f"/reported {label} {OUTSIDE_WORD[to]}. Draft to send (written by code from the camera images; "
                    f"check it first):\n\n{draft}")
        if task["type"] == "check_by_eye":
            reason = next((a["unusable_reason"] for a in latest["angles"] if a["angle"] == angle), "unusable")
            return (f"Task {tid}: {gate} {angle} is unusable ({reason}), so the Inspection is INCOMPLETE. "
                    f"Take a new photo with /reinspect {gate} {angle}, or check it in person and record /eye {gate} {angle}.")
        return (f"Task {tid}: {gate} {self._flight(turn)} has no open Findings. Ready for your sign-off: "
                f"/signoff {gate}. {push}").strip()

    def _start_timers(self, task: dict, turn: dict) -> None:
        tid, lad = task["task_id"], self.ladder
        self.timers.cancel(tid)
        if task["type"] == "ack_hold":
            if task["status"] == "assigned":
                self.timers.set("hold_unack_1", lad["hold_unacknowledged_s"][0], tid)
                self.timers.set("hold_unack_2", lad["hold_unacknowledged_s"][1], tid)
            if turn.get("pushback_t") is not None:
                self.timers.set_at("hold_pushback", turn["pushback_t"] - lad["hold_pushback_under_min"] * 60, tid)
        elif task["type"] != "sign_off":
            self.timers.set("no_report_ask", lad["no_report_ask_s"], tid)
            self.timers.set("no_report_offer", lad["no_report_offer_s"], tid)
            if task["type"] == "check_by_eye" and turn.get("pushback_t") is not None:
                self.timers.set_at("unusable_pushback", turn["pushback_t"] - lad["unusable_pushback_under_min"] * 60, tid)

    def reassign(self, task_id: str, assignee_id: str, reason: str, by: str) -> dict:
        with self.lock:
            task = self.board.need_task(task_id)
            if task["status"] not in ACTIVE:
                raise DispatchError(f"{task['task_id']} is {task['status']}")
            person = self.roster.person(assignee_id)
            if person is None:
                raise DispatchError(f"No such person: {assignee_id}")
            if person["shift"] != "on":
                raise DispatchError(f"{person['name']} is not on shift ({person['shift']})")
            if not role_may_take(person["role"], task["type"]):
                raise DispatchError(f"A '{TYPE_LABEL[task['type']]}' Task can only go to a Ramp Lead; "
                                    f"{person['name']} is a {ROLE_LABEL[person['role']]}")
            if person["person_id"] == task["assignee_id"]:
                raise DispatchError(f"{task['task_id']} is already with {person['name']}")
            old = task["assignee_id"]
            status = "accepted" if task["type"] == "ack_hold" and task["status"] == "accepted" else "assigned"
            task = self.board.update_task(task["task_id"], assignee_id=person["person_id"], status=status)
            turn = self.store.get_turn(task["turn_id"])
            self._start_timers(task, turn)
            self.board.send(person["person_id"], f"Task {task['task_id']} has moved to you from {self._name(old)} "
                            f"({_short(reason, 120)}): {task['instruction']} ({task['severity'] or task['type']}, "
                            f"{task['gate']} {task['angle'] or ''} {task['finding_label'] or ''}).".replace("  ", " "),
                            task_id=task["task_id"])
            if old:
                self.board.send(old, f"Task {task['task_id']} has moved to {person['name']}.", task_id=task["task_id"])
            if by != "agent":
                self.board.log("code", f"{task['task_id']} moved from {self._name(old)} to {self._who(person['person_id'])}: "
                                       f"{_short(reason, 80)}.", event="task_reassigned", task=task, actor=by,
                               data={"task_id": task["task_id"], "from": old, "to": person["person_id"], "reason": reason})
            return task

    # ------------------------------------------------------------------ Handover (moves Tasks; confirms nothing)
    def sole_lead_leaving(self, person: dict, what: str) -> bool:
        """Tell the supervisor when the only Ramp Lead on shift tries to leave while a HOLD is open at their
        Gates. Returns whether that was the case."""
        if person["role"] != "ramp_lead" or [p for p in self._leads() if p["person_id"] != person["person_id"]]:
            return False
        holds = [t for t in self.board.tasks() if t["type"] == "ack_hold" and t["gate"] in person["gates"]]
        if not holds:
            return False
        where = ", ".join(f"{t['finding_label']} at {t['gate']}" for t in holds)
        text = (f"{person['name']} is the only Ramp Lead on shift and {what} while a HOLD is open ({where}). "
                "Nothing has moved. A Ramp Lead is needed: /shift <person> on.")
        for s in self._supervisors():
            self.board.send(s["person_id"], text, task_id=holds[0]["task_id"])
        self.board.log("code", text + " Supervisor told.", event="sole_lead_leaving", task=holds[0],
                       actor=person["person_id"], data={"person_id": person["person_id"], "holds": [t["task_id"] for t in holds]})
        return True

    def start_handover(self, person: dict, target: dict) -> dict:
        """Ask `target` to take every open Task of `person`. Nothing moves until they accept."""
        with self.lock:
            tasks = self.board.tasks(assignee_id=person["person_id"])
            prop = self.board.create_proposal(
                to_id=target["person_id"], created_by=person["person_id"],
                expires_t=self.clock() + self.ladder["proposal_expires_s"],
                action={"kind": "handover", "from_id": person["person_id"],
                        "text": f"take over {len(tasks)} Task(s) from {person['name']}"})
            self.timers.set("handover_timeout", self.ladder["proposal_expires_s"], prop["proposal_id"])
            self.board.send(target["person_id"], agent_mod.handover_brief(self, person["person_id"], target["person_id"])
                            + f"\nTake these over?   [y / n]   ({prop['proposal_id']})", from_id=person["person_id"],
                            proposal_id=prop["proposal_id"])
            self.board.log("code", f"Handover asked: {self._who(person['person_id'])} to {self._who(target['person_id'])}, "
                                   f"{len(tasks)} open Task{'s' if len(tasks) != 1 else ''} ({prop['proposal_id']}). "
                                   "Nothing moves until it is accepted.", event="handover_requested", actor=person["person_id"],
                           data={"from": person["person_id"], "to": target["person_id"],
                                 "tasks": [t["task_id"] for t in tasks], "proposal_id": prop["proposal_id"]})
            ok, _ = self.model_ready()
            if ok:                                               # the list above is the brief; the model adds a summary
                self._queue({"kind": "handover", "from_id": person["person_id"], "to_id": target["person_id"],
                             "proposal_id": prop["proposal_id"], "trigger": "handover_requested"})
            return prop

    def complete_handover(self, person: dict, action: dict) -> list[str]:
        """`person` accepted: move every open Task of the first person to them and end that person's Shift.
        Timers are rows keyed by Task, so a running Escalation carries on against the new holder."""
        with self.lock:
            src = self.roster.person(action["from_id"])
            moved, kept = [], []
            for t in self.board.tasks(assignee_id=src["person_id"]):
                if not role_may_take(person["role"], t["type"]) or person["shift"] != "on":
                    kept.append(t["task_id"])
                    continue
                self.board.update_task(t["task_id"], assignee_id=person["person_id"])
                moved.append(t["task_id"])
                self.board.log("code", f"{t['task_id']} moved from {src['name']} to {self._who(person['person_id'])}: "
                                       f"Handover.", event="task_reassigned", task=t, actor=src["person_id"],
                               data={"task_id": t["task_id"], "from": src["person_id"], "to": person["person_id"],
                                     "reason": "Handover"})
            if not kept:
                self.roster.set_shift(src["person_id"], "off", handed_to=person["person_id"])
            ended = "" if kept else f" {src['name']}'s Shift has ended."
            self.board.send(src["person_id"], f"{person['name']} accepted the Handover: {', '.join(moved) or 'no Tasks'} "
                            f"moved." + (f" {', '.join(kept)} stayed with you ({person['name']} cannot take "
                                         f"{'them' if len(kept) > 1 else 'it'})." if kept else " Your Shift has ended. "
                                         "Type /back if you return."))
            self.board.log("code", f"Handover: {', '.join(moved) or 'no Tasks'} moved from {src['name']} to "
                                   f"{self._who(person['person_id'])}.{ended}", event="handover", actor=person["person_id"],
                           data={"from": src["person_id"], "to": person["person_id"], "tasks": moved, "kept": kept,
                                 "shift_ended": not kept})
            return [f"Handover accepted: {', '.join(moved) or 'no Tasks'} "
                    f"{'is' if len(moved) == 1 else 'are'} now yours. Running timers carry on.{ended}"]

    def handover_not_taken(self, prop: dict, how: str) -> None:
        """Declined or timed out: the Tasks stay where they are and the first person is told."""
        src, dst = prop["action"]["from_id"], prop["to_id"]
        self.board.send(src, f"{self._name(dst)} {how} your Handover ({prop['proposal_id']}). Your Tasks stay with you. "
                        "You are still on shift.")
        self.board.log("code", f"Handover from {self._name(src)} to {self._name(dst)} {how} ({prop['proposal_id']}). "
                               "No Task moved.", event="handover_declined" if how == "declined" else "handover_expired",
                       actor=dst, data={"from": src, "to": dst, "proposal_id": prop["proposal_id"]})

    def _handover_timed_out(self, proposal_id: str) -> None:
        prop = self.board.proposal(proposal_id)
        if prop is None or prop["status"] not in ("pending", "expired"):
            return
        if prop["status"] == "pending":
            self.store.execute("UPDATE proposals SET status='expired' WHERE proposal_id=?", (proposal_id,))
        self.handover_not_taken(prop, "did not answer")

    # ------------------------------------------------------------------ Reports (never a Confirmation)
    def record_report(self, task: dict, person: dict, kind: str, raw_text: str | None, via: str) -> dict:
        """Record what a person said about a Task and tell whoever has to act on it. The Finding is untouched:
        only that person's own command, or a proposal they accept, can record a Confirmation."""
        with self.lock:
            self.board.add_report(task["task_id"], by_person_id=person["person_id"], kind=kind, raw_text=raw_text, via=via)
            tid, label, gate, angle = task["task_id"], task["finding_label"], task["gate"], task["angle"]
            out = {"task_id": tid, "kind": kind, "finding_still_open": bool(label), "told": [], "proposal_id": None,
                   "lines": []}
            if kind == "accepted":
                if task["status"] == "assigned" and task["type"] != "ack_hold":
                    self.board.update_task(tid, status="accepted")
            elif kind in ("done", "not_found"):
                if task["type"] != "ack_hold":
                    self.board.update_task(tid, status="reported")
                    self.timers.cancel(tid, ("no_report_ask", "no_report_offer"))
            elif kind == "blocked":
                self.timers.cancel(tid, ("no_report_ask", "no_report_offer"))
            self.board.log("code", f"Report on {tid} by {person['name']}: {kind.replace('_', ' ')} ({via.replace('_', ' ')})."
                           + (f" Finding {label} stays open." if label else ""),
                           event="task_accepted" if kind == "accepted" else "task_reported", task=task, actor=person["person_id"],
                           data={"task_id": tid, "kind": kind, "via": via, "raw_text": raw_text})
            f = None
            if label:
                try:
                    _, _, f = self.board.resolve(label)
                except DispatchError:
                    f = None
            hold = f is not None and f["severity"] == "HOLD" and f["zone_tier"] != "outside_boundary"
            if kind == "blocked":
                targets = self._owners(task, exclude=person["person_id"])
                for p in targets:
                    self.board.send(p["person_id"], f"{person['name']} cannot do {tid} ({task['instruction']}): "
                                    f"{_short(raw_text or 'no reason given', 160)}. To move it: /reassign {tid} <person>, "
                                    "or tell me who should take it.", task_id=tid)
                out["told"] = [p["person_id"] for p in targets]
                out["lines"].append(f"Logged: you cannot do {tid}. {self._names(targets)} told.")
            elif kind in ("done", "not_found") and task["type"] in ("remove", "walk_and_report") and hold:
                targets = self._owners(task, exclude=None, hold_label=label)
                for p in targets:
                    if kind == "done":
                        text = (f"{person['name']} reports the object for HOLD {label} at {gate} {angle} is removed ({tid}). "
                                f"That is a Report, not a Confirmation: only a Ramp Lead can record it. /removed {label} "
                                f"takes a new photo of {angle}; the HOLD clears only if the new photo is clean.")
                    else:
                        text = (f"{person['name']} reports they could not find the object for HOLD {label} at {gate} {angle} "
                                f"({tid}). The HOLD stays open. /reinspect {gate} {angle} takes a new photo; "
                                f"/false-alarm {label} <reason> or /not-found {label} are yours to record.")
                    self.board.send(p["person_id"], text, task_id=tid)
                out["told"] = [p["person_id"] for p in targets]
                out["lines"].append(f"Logged your Report on {tid}. {label} stays open: a Ramp Lead records HOLDs. "
                                    f"{self._names(targets)} told.")
                lead = next((p for p in targets if p["role"] == "ramp_lead"), None)
                if kind == "not_found" and lead is not None:     # code asks; a person decides; nothing is recorded
                    try:
                        prop = self.propose_reinspection(lead["person_id"], gate, angle,
                                                         f"{person['name']} could not find the object for HOLD {label}", "code")
                        out["proposal_id"] = prop["proposal_id"]
                    except DispatchError:
                        pass
                if via == "free_text":                           # a command gets these lines as its reply
                    self.board.send(person["person_id"], out["lines"][-1], task_id=tid)
                    out["told"].append(person["person_id"])
            elif kind in ("done", "not_found") and task["type"] in ("remove", "walk_and_report") and f is not None:
                out["lines"].append(f"Logged your Report on {tid}. {label} stays open until a Confirmation is recorded.")
                if self.rules.role_may_confirm(person["role"], f["severity"]):
                    try:
                        prop = self.propose_confirmation(person["person_id"], label,
                                                         "removed" if kind == "done" else "not_found_on_walk", None, "code")
                        out["proposal_id"] = prop["proposal_id"]
                        if via == "free_text":
                            out["told"].append(person["person_id"])
                    except DispatchError as err:
                        out["lines"].append(str(err))
            elif kind in ("done", "not_found"):
                hint = {"ack_hold": f"/removed {label} records a HOLD as removed (it takes a new photo first).",
                        "check_by_eye": f"/eye {gate} {angle} records the check; /reinspect {gate} {angle} takes a new photo.",
                        "sign_off": f"/signoff {gate} records the sign-off.",
                        "report_outside_boundary": f"/reported {label} records that it was reported."}.get(task["type"], "")
                out["lines"].append(f"Logged your Report on {tid}. A Report does not record anything on the Inspection. {hint}".strip())
            else:
                out["lines"].append(f"Logged on {tid}: {kind}.")
            return out

    def _owners(self, task: dict, *, exclude: str | None, hold_label: str | None = None) -> list[dict]:
        """Who is told about a Report: the Ramp Lead holding the HOLD, else the Gate's leads, else supervisors."""
        people = []
        if hold_label:
            for t in self.board.tasks(turn_id=task["turn_id"]):
                if t["type"] == "ack_hold" and t["finding_label"] == hold_label and t["assignee_id"]:
                    people.append(self.roster.person(t["assignee_id"]))
        if not people:
            leads = self._leads()
            people = [p for p in leads if task["gate"] in p["gates"]] or leads
        people = [p for p in people if p and p["person_id"] != exclude]
        return people or self._supervisors()

    @staticmethod
    def _names(people: list[dict]) -> str:
        return ", ".join(p["name"] for p in people) or "Nobody"

    # ------------------------------------------------------------------ proposals (a person must accept)
    def propose_confirmation(self, to_id: str, finding_label: str, outcome: str, false_alarm_reason: str | None,
                             created_by: str) -> dict:
        """Offer a person a Confirmation to accept with `y`. Refused when that person's role may not record it.
        Accepting is handled in commands.py, as that person; this only writes the offer."""
        from ..workflow import FALSE_ALARM_REASONS
        with self.lock:
            person = self.roster.person(to_id)
            if person is None or person["role"] not in WORK_ROLES:
                raise DispatchError(f"{to_id} is not a Ramp Agent or Ramp Lead on the roster")
            if outcome not in ("removed", "false_alarm", "not_found_on_walk"):
                raise DispatchError("outcome must be removed, false_alarm or not_found_on_walk")
            ref, report, f = self.board.resolve(finding_label)
            if not R.is_open(f):
                raise DispatchError(f"{ref['label']} is already closed by a Confirmation")
            if not self.rules.role_may_confirm(person["role"], f["severity"]):
                raise DispatchError(f"Refused: only a Ramp Lead can confirm a {f['severity']} Finding; "
                                    f"{person['name']} is a {ROLE_LABEL[person['role']]}")
            if outcome == "false_alarm" and false_alarm_reason not in FALSE_ALARM_REASONS:
                raise DispatchError(f"false_alarm_reason must be one of {', '.join(FALSE_ALARM_REASONS)}")
            hold_removed = f["severity"] == "HOLD" and outcome == "removed"
            if hold_removed and f["status"] != "acknowledged":
                raise DispatchError(f"{ref['label']} is a HOLD that has not been acknowledged; the Ramp Lead types /ack {ref['label']} first")
            for p in self.board.pending_proposals(person["person_id"]):
                a = p["action"]
                if a.get("kind") == "confirm" and a.get("label") == ref["label"] and a.get("outcome") == outcome:
                    raise DispatchError(f"Already proposed to {person['name']}: {p['proposal_id']}")
            words = {"removed": "removed", "false_alarm": f"a false alarm ({false_alarm_reason})",
                     "not_found_on_walk": "not found on walk"}[outcome]
            prop = self.board.create_proposal(
                to_id=person["person_id"], created_by=created_by, expires_t=self.clock() + self.ladder["proposal_expires_s"],
                action={"kind": "confirm", "label": ref["label"], "outcome": outcome, "turn_id": ref["turn_id"],
                        "false_alarm_reason": false_alarm_reason if outcome == "false_alarm" else None,
                        "finding_status": f["status"], "text": f"record {ref['label']} as {words}"})
            self.board.send(person["person_id"], f"Record {ref['label']} ({_short(f['description'], 60)}, {report['gate']} "
                            f"{f['angle']}) as {words}, confirmed by you?"
                            + (f" A new photo of {f['angle']} is taken first." if hold_removed else "")
                            + f"   [y / n]   ({prop['proposal_id']})", kind="agent" if created_by == "agent" else "code",
                            from_id=created_by, proposal_id=prop["proposal_id"])
            return prop

    def propose_reinspection(self, to_id: str, gate: str, angle: str, reason: str, created_by: str) -> dict:
        with self.lock:
            person = self.roster.person(to_id)
            if person is None or person["role"] not in WORK_ROLES:
                raise DispatchError(f"{to_id} is not a Ramp Agent or Ramp Lead on the roster")
            turn = self.store.current_turn(gate) if gate in self.wf.gates else None
            latest = self.board.settled_latest(turn["turn_id"]) if turn and turn["phase"] != "departed" else None
            if latest is None:
                raise DispatchError(f"Gate {gate} has no finished Inspection in a Turn in progress")
            if angle not in config.ANGLES:
                raise DispatchError(f"angle must be one of {', '.join(config.ANGLES)}")
            for p in self.board.pending_proposals(person["person_id"]):
                if p["action"].get("kind") == "reinspect" and p["action"].get("gate") == gate and p["action"].get("angle") == angle:
                    raise DispatchError(f"Already proposed to {person['name']}: {p['proposal_id']}")
            prop = self.board.create_proposal(
                to_id=person["person_id"], created_by=created_by, expires_t=self.clock() + self.ladder["proposal_expires_s"],
                action={"kind": "reinspect", "gate": gate, "angle": angle, "turn_id": turn["turn_id"],
                        "text": f"take a new photo of {gate} {angle}"})
            self.board.send(person["person_id"], f"Take a new photo of {gate} {angle} now ({_short(reason, 120)})? "
                            f"A re-inspection never closes a Finding by itself.   [y / n]   ({prop['proposal_id']})",
                            kind="agent" if created_by == "agent" else "code", from_id=created_by,
                            proposal_id=prop["proposal_id"])
            return prop

    # ------------------------------------------------------------------ timers and Escalation
    def _on_timer(self, tm: dict) -> None:
        if tm["kind"] == "handover_timeout":                    # this timer's task_id column holds a proposal ID
            self._handover_timed_out(tm["task_id"])
            return
        task = self.board.task(tm["task_id"])
        if task is None or task["status"] not in ACTIVE:
            return
        tid, kind, lad = task["task_id"], tm["kind"], self.ladder
        waiting = task["status"] in ("assigned", "accepted")
        if kind == "hold_unack_1" and task["status"] == "assigned":
            self.escalate(task, f"not acknowledged after {lad['hold_unacknowledged_s'][0]:g} s", level=1, by="timer")
        elif kind == "hold_unack_2" and task["status"] == "assigned":
            self.escalate(task, f"not acknowledged after {lad['hold_unacknowledged_s'][1]:g} s", level=2, by="timer")
        elif kind == "hold_pushback":
            self.escalate(task, f"HOLD still open with scheduled pushback under {lad['hold_pushback_under_min']:g} min",
                          level=2, by="timer")
        elif kind == "unusable_pushback":
            self.escalate(task, f"{task['angle']} is still unusable and unchecked with scheduled pushback under "
                          f"{lad['unusable_pushback_under_min']:g} min", level=2, by="timer")
        elif kind == "no_report_ask" and waiting and task["assignee_id"]:
            self.board.send(task["assignee_id"], f"Any update on {tid} ({task['instruction']})? Reply here, or type "
                            f"/done {tid} or /cant {tid} <reason>.", kind="timer", task_id=tid)
            self.board.log("timer", f"{tid} has no Report after {lad['no_report_ask_s']:g} s. Asked {self._name(task['assignee_id'])}.",
                           event="timer_fired", task=task, actor="timer", data={"task_id": tid, "timer": kind})
        elif kind == "no_report_offer" and waiting:
            targets = self._owners(task, exclude=task["assignee_id"])
            for p in targets:
                self.board.send(p["person_id"], f"{tid} ({task['instruction']}) has no Report from "
                                f"{self._name(task['assignee_id'])} after {lad['no_report_offer_s']:g} s. To move it: "
                                f"/reassign {tid} <person>, or tell me who should take it.", kind="timer", task_id=tid)
            self.board.log("timer", f"{tid} still has no Report after {lad['no_report_offer_s']:g} s. "
                                    f"Offered reassignment to {self._names(targets)}.", event="timer_fired", task=task,
                           actor="timer", data={"task_id": tid, "timer": kind})

    def escalate(self, task: dict, reason: str, *, level: int | None = None, by: str = "code",
                 again_at_top: bool = False) -> dict:
        """Raise a Task one level (or to `level`) and tell the people that level names. Escalation only tells
        people; the system never holds or releases a pushback. `again_at_top` tells the top level's people once
        more when the Task is already there (a second "still there")."""
        with self.lock:
            task = self.board.need_task(task["task_id"])
            if task["status"] not in ACTIVE:
                raise DispatchError(f"{task['task_id']} is {task['status']}")
            new = min(MAX_LEVEL, level if level is not None else task["escalation_level"] + 1)
            if level is None and task["escalation_level"] >= MAX_LEVEL and not again_at_top:
                raise DispatchError(f"{task['task_id']} is already at the top Escalation level; the supervisor has been told")
            if new < task["escalation_level"]:
                new = task["escalation_level"]
            self.board.update_task(task["task_id"], escalation_level=new)
            tid, gate, label, angle = task["task_id"], task["gate"], task["finding_label"], task["angle"]
            turn = self.store.get_turn(task["turn_id"])
            owner = self._name(task["assignee_id"])
            subject = f"HOLD {label} at {gate} {angle}" if task["type"] == "ack_hold" else \
                f"{tid} ({TYPE_LABEL[task['type']]} at {gate} {label or angle or ''})".replace(" )", ")")
            told: list[str] = []

            def tell(person_id: str, text: str) -> None:
                if person_id and person_id not in told:
                    self.board.send(person_id, text, kind="timer", task_id=tid)
                    told.append(person_id)

            if new <= 1:
                if task["assignee_id"]:
                    tell(task["assignee_id"], f"Second call: {subject}: {reason}. {self._pushback(turn)} "
                         + (f"Type /ack {label} when someone is going to it." if task["type"] == "ack_hold"
                            and task["status"] == "assigned" else f"/removed {label} takes a new photo once it is gone."
                            if task["type"] == "ack_hold" else f"Reply here or type /done {tid}."))
            else:
                for p in self._leads():
                    tell(p["person_id"], f"Escalation level {new}: {subject}: {reason}. Assigned to {owner}. "
                         f"{self._pushback(turn)} " + (f"Any Ramp Lead can take it: /ack {label}." if task["type"] == "ack_hold"
                                                      else f"To move it: /reassign {tid} <person>."))
            for s in self._supervisors():
                tell(s["person_id"], f"Escalation level {new}: {subject}, assigned to {owner}: {reason}. {self._pushback(turn)}".strip())
            self.board.log("timer" if by == "timer" else "code",
                           f"{tid} {subject if task['type'] == 'ack_hold' else ''}: {reason}. Escalation level {new}. "
                           f"Told: {', '.join(told) or 'nobody on shift'}.".replace("  ", " "), event="task_escalated", task=task,
                           actor=by, data={"task_id": tid, "level": new, "reason": reason, "notified": told})
            return {"task_id": tid, "level": new, "notified": told}

    def hold_still_present(self, label: str, by_person_id: str | None = None) -> list[str]:
        """A HOLD was recorded as removed but the new photo still shows the object: the Finding stays open (the
        Workflow decided that), the removal Task reopens, the HOLD goes up one level and the people that level
        names are told. Returns the lines for the Ramp Lead who recorded it, with who else could be sent."""
        with self.lock:
            rows = [t for t in self.store.query("SELECT * FROM tasks WHERE finding_label=? ORDER BY seq", (label,))
                    if t["status"] in ACTIVE]
            lines, level, reopened = [], None, []
            for t in rows:
                if t["type"] in ("remove", "walk_and_report"):
                    self.board.update_task(t["task_id"], status="assigned")
                    self._start_timers(self.board.task(t["task_id"]), self.store.get_turn(t["turn_id"]))
                    if t["assignee_id"]:
                        self.board.send(t["assignee_id"], f"The new photo of {t['gate']} {t['angle']} still shows the "
                                        f"object for {label}. {t['task_id']} is open again: please go back and report here.",
                                        task_id=t["task_id"])
                    self.board.log("code", f"{t['task_id']} reopened: the new photo still shows the object for {label}.",
                                   event="task_reopened", task=t, data={"task_id": t["task_id"], "to": t["assignee_id"]})
                    reopened.append(t)
                elif t["type"] == "ack_hold":
                    level = self.escalate(t, "the re-inspection still shows the object", again_at_top=True)["level"]
            hold = next((t for t in rows if t["type"] == "ack_hold"), None)
            if level is not None:
                lines.append(f"{label} is at Escalation level {level}; the people for that level have been told.")
            if hold is not None:
                for t in reopened:
                    others = self._able(t["type"], t["gate"], (t["assignee_id"], by_person_id))
                    lines.append(f"{t['task_id']} ({TYPE_LABEL[t['type']]}) is open again with {self._name(t['assignee_id'])}."
                                 + (f" To send someone else: /reassign {t['task_id']} <person>. On shift and able: "
                                    f"{', '.join(others)}." if others else " Nobody else on shift can take it."))
                if not reopened:
                    able = self._able("remove", hold["gate"], (by_person_id,))
                    lines.append(f"Nobody is assigned to remove it. To send someone: /send <person> {label}."
                                 + (f" On shift and able: {', '.join(able)}." if able else ""))
            return lines

    def _able(self, task_type: str, gate: str, exclude: tuple) -> list[str]:
        """Names of everyone on shift whose role may take this Task, people who cover the Gate first."""
        people = [p for p in self.roster.people(on_shift=True) if role_may_take(p["role"], task_type)
                  and p["person_id"] not in exclude]
        return [p["name"] for p in sorted(people, key=lambda p: (gate not in p["gates"], p["role"] != "ramp_agent", p["person_id"]))]

    # ------------------------------------------------------------------ waking the model
    def model_ready(self) -> tuple[bool, str]:
        """Whether the model may be woken now. The spend cap is checked here, before every wake."""
        if self.mode != "on":
            return False, "FOD_AGENT is not 'on'"
        ok, why = spend_allowed()
        if not ok:
            return False, why
        if self.create is None:
            if self.llm is None:
                return False, "no Claude client"
            ok, why = self.llm.available()
            if not ok:
                return False, why
        now = time.monotonic()
        while self._wake_times and now - self._wake_times[0] > 60:
            self._wake_times.popleft()
        if len(self._wake_times) >= MAX_WAKES_PER_MINUTE:
            return False, f"wake rate limit ({MAX_WAKES_PER_MINUTE} a minute)"
        return True, "ok"

    def _queue(self, req: dict) -> None:
        for q in self._wakes:                                   # coalesce: one wake per Turn, one per person
            if q["kind"] == req["kind"] == "message" and q["person_id"] == req["person_id"]:
                q["message_ids"] += req["message_ids"]
                return
            if q["kind"] == req["kind"] == "routing" and q["turn_id"] == req["turn_id"]:
                return
            if q["kind"] == req["kind"] == "handover" and q["proposal_id"] == req["proposal_id"]:
                return
        self._wakes.append(req)
        self._idle_announced = False
        with self._wake_cv:
            self._wake_cv.notify_all()

    def _on_person_message(self, data: dict) -> None:
        msg = self.board.message(data.get("message_id"))
        if msg is None:
            return
        ok, why = self.model_ready()
        if ok:
            self._queue({"kind": "message", "person_id": msg["from_id"], "message_ids": [msg["message_id"]],
                         "trigger": "human_message"})
        else:
            self._note_model(why)
            self._free_text_fallback(msg["from_id"], why)

    def _free_text_fallback(self, person_id: str, why: str) -> None:
        self.board.send(person_id, f"I cannot read free text right now ({why}). Your message is logged for the "
                        "supervisor. Slash commands work as usual: /tasks, /done <task>, /help.")
        self.board.log("code", f"Free text from {self._name(person_id)} not interpreted ({why}). They were told to use slash commands.",
                       event="free_text_not_interpreted", actor=person_id, data={"reason": why})

    def drain_wakes(self) -> None:
        while True:
            with self.lock:
                if not self._wakes:
                    return
                req = self._wakes.popleft()
                self._running_wakes += 1
            try:
                self._run_wake(req)
            finally:
                with self.lock:
                    self._running_wakes -= 1
        # not reached

    def _counted_create(self) -> Callable[..., object]:
        inner = self.create or agent_mod.sdk_create(self.llm)

        def create(**kw):
            self.model_calls += 1
            return inner(**kw)
        return create

    def _run_wake(self, req: dict) -> None:
        ok, why = self.model_ready()                             # includes the spend cap, every time
        result, tools = None, None
        if ok:
            self._wake_times.append(time.monotonic())
            where = {"turn": self.store.get_turn(req["turn_id"])} if req["kind"] == "routing" else {}
            with self.lock:
                prompt = agent_mod.build_prompt(self, req)
            self.board.log("wake", f"trigger={req['trigger']}  model={config.AGENT_MODEL.replace('claude-', '')}",
                           event="agent_wake_started", actor="agent", **where, data={"trigger": req["trigger"]})
            tools = agent_mod.AgentTools(self)
            began = time.monotonic()
            try:
                result = agent_mod.wake(tools, prompt, create=self._counted_create())
            except Exception:
                log.exception("agent wake crashed")
                result = {"outcome": "failed: internal error", "tokens_in": 0, "tokens_out": 0, "est_cost_usd": 0.0,
                          "tool_calls": [], "text": ""}
            self.store.execute(
                "INSERT INTO agent_wakes (trigger_event_id, trigger, model, tokens_in, tokens_out, est_cost_usd, "
                "tool_calls, outcome, at) VALUES (?,?,?,?,?,?,?,?,?)",
                (None, req["trigger"], config.AGENT_MODEL, result["tokens_in"], result["tokens_out"],
                 result["est_cost_usd"], json.dumps(result["tool_calls"]), result["outcome"], R.now_iso()))
            result["seconds"] = round(time.monotonic() - began, 1)
            if result["outcome"] == "ok":
                if result["text"]:
                    self.board.log("agent", _short(result["text"], 220), event="agent_note", actor="agent", **where)
            else:
                self.board.log("code", f"Agent wake ended without finishing ({result['outcome']}). Code takes over.",
                               event="agent_wake_failed", **where, data={"outcome": result["outcome"]})
            cost = self.cost()
            self.board.log("cost", f"wake ${result['est_cost_usd']:.4f} in {result['seconds']:g} s   agent session ${cost['agent_session_usd']:.4f}   "
                                   f"process ${cost['process_usd']:.4f}"
                           + (f" of ${cost['cap_usd']:.2f} cap" if cost["cap_usd"] is not None else ""),
                           event="agent_wake", actor="agent", **where,
                           data={"trigger": req["trigger"], "model": config.AGENT_MODEL, "outcome": result["outcome"],
                                 "tokens_in": result["tokens_in"], "tokens_out": result["tokens_out"],
                                 "est_cost_usd": result["est_cost_usd"], "tool_calls": result["tool_calls"],
                                 "seconds": result["seconds"]})
        else:
            self._note_model(why)
        with self.lock:
            if req["kind"] == "routing":
                self._routing_pending.discard(req["turn_id"])
                self.sync_turn(req["turn_id"], allow_wake=False)     # anything the model left unowned
            elif req["kind"] == "handover":
                pass                                             # the code-written brief already went out
            elif result is None or (result["outcome"] != "ok" and req["person_id"] not in (tools.messaged if tools else ())):
                self._free_text_fallback(req["person_id"], why if result is None else result["outcome"])
        self.store.notify()

    # ------------------------------------------------------------------ views
    def cost(self) -> dict:
        from ..llm import process_spend
        row = self.store.query("SELECT COALESCE(SUM(est_cost_usd), 0) AS usd, COUNT(*) AS n, "
                               "COALESCE(SUM(tokens_in), 0) AS tin, COALESCE(SUM(tokens_out), 0) AS tout FROM agent_wakes")[0]
        return {"agent_session_usd": round(row["usd"], 6), "wakes": row["n"], "tokens_in": row["tin"],
                "tokens_out": row["tout"], "model_requests": self.model_calls,
                "process_usd": round(process_spend()["usd"], 6), "cap_usd": config.max_spend_usd()}

    def _announce_idle(self) -> None:
        if self._idle_announced or self._wakes or self._running_wakes or self.board.tasks(limit=1):
            return
        self._idle_announced = True
        self.board.log("idle", f"No open Tasks. Waiting for events. Agent session cost ${self.cost()['agent_session_usd']:.4f}.",
                       event="idle")

    def view(self) -> dict:
        """Read-only picture for GET /api/agent/board."""
        with self.lock:
            ok, why = self.model_ready()
            tasks = self.store.query("SELECT * FROM tasks ORDER BY seq DESC LIMIT 100")[::-1]
            return {"mode": self.mode, "model": config.AGENT_MODEL, "model_available": ok, "model_note": why,
                    "clock_t": round(self.clock(), 1),
                    "tasks": [self.board.task_view(t) | {"reports": [
                        {k: r[k] for k in ("by_person_id", "at", "kind", "raw_text", "via")}
                        for r in self.board.reports(t["task_id"])]} for t in tasks],
                    "roster": [p | {"open_tasks": len(self.board.tasks(assignee_id=p["person_id"]))}
                               for p in self.roster.people()],
                    "timers": [{"task_id": t["task_id"], "kind": t["kind"], "fire_t": t["fire_t"]} for t in self.timers.pending()],
                    "activity": self.board.activity(max(0, self.store.query(
                        "SELECT COALESCE(MAX(log_id), 0) AS n FROM agent_log")[0]["n"] - 60)),
                    "cost": self.cost()}
