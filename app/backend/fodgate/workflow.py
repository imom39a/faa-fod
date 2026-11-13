"""Confirmation rules, Inspection lifecycle, Gate status and the "Needs a human" queue.

Rules (spec/fod-rules.md, spec/dashboard-ux.md, app/CONTRACT.md section 2):
- A Ramp Agent confirms REMOVE and ADVISORY Findings; only a Ramp Lead confirms a HOLD.
- A HOLD is acknowledged first. "removed" on a HOLD runs a re-inspection of that Angle (the scene's `after`
  frame when there is one); the Confirmation is recorded only if the new frame no longer shows the object.
- Sign-off needs no open Findings and every unusable Angle re-inspected usable or checked by eye (Ramp Lead).
- Nothing here lets the system, or the assistant, clear a Gate: only a person's Confirmation does (SC-5).
"""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from . import config, pipeline, report as R
from .llm import LLM
from .rules import SEVERITY_ORDER, load_rules
from .scenes import Scene, SceneNotFound, load_scene, load_timeline
from .store import Store

log = logging.getLogger("fodgate.workflow")

ROLES = ("ramp_agent", "ramp_lead")
OUTCOMES = ("acknowledged", "removed", "false_alarm", "not_found_on_walk")
FALSE_ALARM_REASONS = ("shadow", "marking", "equipment_in_place", "other")
KINDS = ("pre_arrival", "pre_departure", "on_demand")


class WorkflowError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _actor(role: str, name: str) -> dict:
    if role not in ROLES:
        raise WorkflowError(422, "invalid_request", f"role must be one of {', '.join(ROLES)}")
    if not isinstance(name, str) or not name.strip():
        raise WorkflowError(422, "invalid_request", "name is required")
    return {"role": role, "name": name.strip()}


class Workflow:
    def __init__(self, store: Store, llm: LLM | None, *, clock: Callable[[], float] = lambda: 0.0,
                 max_parallel_inspections: int = 3):
        self.store = store
        self.llm = llm
        self.clock = clock                       # demo seconds; drives minutes_to_pushback
        self._lock = threading.RLock()           # serialises read-modify-write of reports
        self._pool = ThreadPoolExecutor(max_workers=max_parallel_inspections, thread_name_prefix="inspection")
        self._generation = 0                     # bumped on reset so late results are discarded
        self._timeline: dict | None = None
        self._timeline_mtime: float | None = None

    # ------------------------------------------------------------------ lifecycle
    @property
    def timeline(self) -> dict:
        """The demo timeline, re-read when the file changes (the data set may arrive after the server starts)."""
        f = config.timeline_path()
        mtime = f.stat().st_mtime if f.is_file() else None
        if self._timeline is None or mtime != self._timeline_mtime:
            try:
                self._timeline = load_timeline()
            except ValueError:                           # half-written file: keep what we had
                self._timeline = self._timeline or {"gates": list(config.DEFAULT_GATES), "turns": []}
            self._timeline_mtime = mtime
        return self._timeline

    @property
    def gates(self) -> list[str]:
        return list(self.timeline.get("gates") or config.DEFAULT_GATES)

    def reset(self) -> None:
        with self._lock:
            self._generation += 1
            self.store.reset()
            self._timeline = None

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ lookups
    def report(self, inspection_id: str) -> dict:
        rep = self.store.get_report(inspection_id)
        if rep is None:
            raise WorkflowError(404, "not_found", f"Inspection {inspection_id} not found")
        return rep

    def _settled(self, inspection_id: str) -> dict:
        rep = self.report(inspection_id)
        if rep["status"] == "inspecting":
            raise WorkflowError(409, "inspection_in_progress", "The Inspection is still running")
        return rep

    @staticmethod
    def _finding(rep: dict, finding_id: str) -> dict:
        f = next((f for f in rep["findings"] if f["finding_id"] == finding_id), None)
        if f is None:
            raise WorkflowError(404, "not_found", f"Finding {finding_id} not found in this Inspection")
        return f

    @staticmethod
    def _angle(rep: dict, angle: str) -> dict:
        if angle not in config.ANGLES:
            raise WorkflowError(404, "not_found", f"Unknown Angle {angle}")
        a = next((a for a in rep["angles"] if a["angle"] == angle), None)
        if a is None:
            raise WorkflowError(404, "not_found", f"Angle {angle} is not part of this Inspection")
        return a

    def _save(self, rep: dict) -> dict:
        R.refresh(rep)
        self.store.save_report(rep)
        return rep

    # ------------------------------------------------------------------ Confirmations
    def confirm_finding(self, inspection_id: str, finding_id: str, *, outcome: str, role: str, name: str,
                        false_alarm_reason: str | None = None, possible_source: str | None = None) -> dict:
        by = _actor(role, name)
        if outcome not in OUTCOMES:
            raise WorkflowError(422, "invalid_request", f"outcome must be one of {', '.join(OUTCOMES)}")
        if false_alarm_reason is not None and false_alarm_reason not in FALSE_ALARM_REASONS:
            raise WorkflowError(422, "invalid_request",
                                f"false_alarm_reason must be one of {', '.join(FALSE_ALARM_REASONS)}")
        rules = load_rules()
        with self._lock:
            rep = self._settled(inspection_id)
            f = self._finding(rep, finding_id)
            if f["status"] == "confirmed":
                raise WorkflowError(409, "already_confirmed", "This Finding already has a Confirmation")
            if not rules.role_may_confirm(role, f["severity"]):
                raise WorkflowError(403, "role_not_allowed", f"Only a Ramp Lead can confirm a {f['severity']} Finding")
            if outcome == "acknowledged":
                f["status"] = "acknowledged"
                f["acknowledged"] = {"by": by, "at": R.now_iso()}
                self.store.add_confirmation(inspection_id=inspection_id, finding_id=finding_id, action="acknowledged",
                                            role=by["role"], name=by["name"])
                self._event(rep, "finding_acknowledged", finding_id=finding_id, by=by)
                return self._save(rep)
            hold_removed = f["severity"] == "HOLD" and outcome == "removed"
            if hold_removed and f["status"] != "acknowledged":
                raise WorkflowError(409, "hold_needs_acknowledge",
                                    "A HOLD Finding must be acknowledged before it can be recorded as removed")
            if not hold_removed:
                self._record(rep, f, outcome=outcome, by=by, false_alarm_reason=false_alarm_reason,
                             possible_source=possible_source)
                return self._save(rep)

        # HOLD recorded as removed: look again before believing it.
        new = self._reinspect(rep, [f["angle"]], by, reason="hold_removed")
        with self._lock:
            parent = self.report(inspection_id)
            new = self.report(new["inspection_id"])
            pf = self._finding(parent, finding_id)
            copy = pipeline.carried_copy(new, pf)
            entry = next(a for a in new["angles"] if a["angle"] == pf["angle"])
            if copy is not None and entry["status"] == "usable" and entry["source_inspection_id"] == new["inspection_id"]:
                at = R.now_iso()
                for rpt, finding in ((parent, pf), (new, copy)):
                    self._record(rpt, finding, outcome="removed", by=by, possible_source=possible_source,
                                 after_photo_ref=entry["image_ref"], at=at, audit=rpt is parent)
                new["verdict"] = R.compute_verdict(new["findings"], new["angles"])
                meta = new["run_metadata"]
                meta["notes"] = [n for n in meta.get("notes", []) if pf["finding_id"] not in n] + [
                    f"{pf['angle']}: Finding {pf['finding_id']} recorded as removed by {by['name']} (Ramp Lead); "
                    "the re-inspection frame no longer shows it"]
                self._save(parent)
            return self._save(new)

    def _record(self, rep: dict, f: dict, *, outcome: str, by: dict, false_alarm_reason: str | None = None,
                possible_source: str | None = None, after_photo_ref: str | None = None, at: str | None = None,
                audit: bool = True) -> None:
        f["confirmation"] = {
            "outcome": outcome,
            "false_alarm_reason": (false_alarm_reason or "other") if outcome == "false_alarm" else None,
            "confirmed_by": by, "confirmed_at": at or R.now_iso(),
            "after_photo_ref": after_photo_ref, "possible_source": possible_source,
        }
        f["status"] = "confirmed"
        if audit:
            self.store.add_confirmation(inspection_id=rep["inspection_id"], finding_id=f["finding_id"], action=outcome,
                                        role=by["role"], name=by["name"], data=f["confirmation"])
            self._event(rep, "finding_confirmed", finding_id=f["finding_id"], outcome=outcome, by=by)

    def confirm_all(self, inspection_id: str, *, role: str, name: str) -> dict:
        """Mark every open REMOVE / ADVISORY Finding as removed. HOLDs are never part of this."""
        by = _actor(role, name)
        with self._lock:
            rep = self._settled(inspection_id)
            for f in rep["findings"]:
                if f["status"] != "confirmed" and f["severity"] in ("REMOVE", "ADVISORY"):
                    self._record(rep, f, outcome="removed", by=by)
            return self._save(rep)

    def checked_by_eye(self, inspection_id: str, angle: str, *, role: str, name: str) -> dict:
        by = _actor(role, name)
        with self._lock:
            rep = self._settled(inspection_id)
            a = self._angle(rep, angle)
            if role != "ramp_lead":
                raise WorkflowError(403, "role_not_allowed", "Only a Ramp Lead can record an Angle as checked by eye")
            if a["status"] == "usable":
                raise WorkflowError(409, "angle_usable", f"{angle} is usable; there is nothing to check by eye")
            a["checked_by_eye"] = {"by": by, "at": R.now_iso()}
            self.store.add_confirmation(inspection_id=inspection_id, finding_id=None, action="checked_by_eye",
                                        role=by["role"], name=by["name"], data={"angle": angle})
            self._event(rep, "angle_checked_by_eye", angle=angle, by=by)
            return self._save(rep)

    def signoff(self, inspection_id: str, *, role: str, name: str) -> dict:
        by = _actor(role, name)
        with self._lock:
            rep = self._settled(inspection_id)
            if rep.get("inspection_signoff"):
                raise WorkflowError(409, "already_signed_off", "This Inspection is already signed off")
            still_open = R.open_findings(rep)
            if still_open:
                raise WorkflowError(409, "open_findings",
                                    f"{len(still_open)} Finding(s) are still open: " +
                                    ", ".join(f["finding_id"] for f in still_open))
            unresolved = R.unresolved_unusable_angles(rep)
            if unresolved:
                raise WorkflowError(409, "unusable_angles",
                                    "Unusable Angles must be re-inspected or checked by eye: " + ", ".join(unresolved))
            rep["inspection_signoff"] = {"by": by, "at": R.now_iso()}
            self.store.add_confirmation(inspection_id=inspection_id, finding_id=None, action="signoff",
                                        role=by["role"], name=by["name"])
            self._event(rep, "inspection_signed_off", by=by)
            return self._save(rep)

    # ------------------------------------------------------------------ Inspections
    def reinspect(self, inspection_id: str, angle: str, *, role: str, name: str) -> dict:
        """On-demand re-inspection of one Angle (any role). Other Angles inherit their earlier result."""
        by = _actor(role, name)
        rep = self._settled(inspection_id)
        self._angle(rep, angle)
        return self._reinspect(rep, [angle], by, reason="requested")

    def _reinspect(self, parent: dict, angles: list[str], by: dict | None, *, reason: str) -> dict:
        scene = self._scene(parent.get("scene_id"))
        placeholder = self._placeholder(gate=parent["gate"], turn_id=parent["turn_id"], kind="on_demand",
                                        scene_id=scene.scene_id, parent_id=parent["inspection_id"])
        self.store.save_report(placeholder)
        self._event(placeholder, "inspection_started", kind="on_demand", angles=angles, reason=reason, by=by)
        return self._run(placeholder, scene, parent=parent, angles=angles, generation=self._generation)

    def start_inspection(self, gate: str, *, kind: str, scene_id: str | None = None, background: bool = True) -> dict:
        """Manual or scripted trigger. Returns the report with status `inspecting`; analysis runs in the
        background so the API stays responsive."""
        if gate not in self.gates:
            raise WorkflowError(404, "not_found", f"Unknown Gate {gate}")
        if kind not in KINDS:
            raise WorkflowError(422, "invalid_request", f"kind must be one of {', '.join(KINDS)}")
        turn = self.store.current_turn(gate)
        if turn is not None and turn["phase"] == "departed":
            turn = None
        latest = self.store.latest_report(turn["turn_id"]) if turn else None
        if scene_id is None and turn is not None:
            scene_id = self._scripted_scene(turn["turn_id"], kind) or (latest or {}).get("scene_id")
        if scene_id is None:
            raise WorkflowError(422, "invalid_request", "scene_id is required: this Turn has no scripted scene")
        scene = self._scene(scene_id)
        if turn is None:                                   # nothing scheduled at this Gate: an ad-hoc Turn
            turn = self.store.create_turn(turn_id=f"{gate}-MANUAL-{uuid.uuid4().hex[:6]}", gate=gate, flight="MANUAL",
                                          aircraft_type=None)
            self.store.add_event(type="stand_prep", turn_id=turn["turn_id"], gate=gate, t=self.clock(),
                                 data={"manual": True})
        parent = None
        if kind == "on_demand" and latest is not None and latest["status"] != "inspecting" \
                and latest.get("scene_id") == scene.scene_id:
            parent = latest
        if kind in ("pre_arrival", "pre_departure"):
            self.store.set_turn_phase(turn["turn_id"], kind)
        placeholder = self._placeholder(gate=gate, turn_id=turn["turn_id"], kind=kind, scene_id=scene.scene_id,
                                        parent_id=parent["inspection_id"] if parent else None)
        self.store.save_report(placeholder)
        self._event(placeholder, "inspection_started", kind=kind, scene_id=scene.scene_id)
        if background:
            self._pool.submit(self._run, placeholder, scene, parent=parent, angles=None, generation=self._generation,
                              kind=kind)
            return placeholder
        return self._run(placeholder, scene, parent=parent, angles=None, generation=self._generation, kind=kind)

    def _run(self, placeholder: dict, scene: Scene, *, parent: dict | None, angles: list[str] | None,
             generation: int, kind: str | None = None) -> dict:
        iid = placeholder["inspection_id"]
        try:
            rep = pipeline.run_inspection(scene, gate=placeholder["gate"], turn_id=placeholder["turn_id"],
                                          kind=kind or placeholder["kind"], llm=self.llm, inspection_id=iid,
                                          parent=parent, angles=angles)
        except Exception:                                   # never leave an Inspection stuck in `inspecting`
            log.exception("Inspection %s failed", iid)
            rep = self._failed(placeholder)
        with self._lock:
            if generation != self._generation:              # the demo was reset while this ran
                return rep
            rep["captured_at"] = placeholder["captured_at"]
            self._save(rep)
            self._event(rep, "inspection_completed", verdict=rep["verdict"],
                        highest_open_severity=rep["highest_open_severity"], missing_angles=rep["missing_angles"])
        return rep

    @staticmethod
    def _placeholder(*, gate: str, turn_id: str, kind: str, scene_id: str, parent_id: str | None) -> dict:
        return {
            "schema_version": config.SCHEMA_VERSION, "rule_set_version": load_rules().version,
            "inspection_id": pipeline.new_inspection_id(), "gate": gate, "turn_id": turn_id, "kind": kind,
            "parent_inspection_id": parent_id, "captured_at": R.now_iso(), "analysed_at": None,
            "verdict": None, "highest_open_severity": None, "missing_angles": [],
            "angles": [], "findings": [], "dismissed_candidates": [], "observations": [],
            "inspection_signoff": None,
            "run_metadata": {"local_models": [], "llm_calls": [],
                             "timings_ms": {"local": 0, "haiku": 0, "sonnet": 0, "total": 0}},
            "status": "inspecting", "scene_id": scene_id,
        }

    @staticmethod
    def _failed(placeholder: dict) -> dict:
        rep = dict(placeholder)
        rep["status"] = "awaiting_confirmation"
        rep["analysed_at"] = R.now_iso()
        rep["angles"] = [{"angle": a, "image_ref": None, "camera_id": f"{rep['gate']}-CAM-{a}", "crop": None,
                          "status": "unusable", "unusable_reason": pipeline.ANALYSIS_FAILED,
                          "assessed_by": "local_check", "source_inspection_id": rep["inspection_id"],
                          "image_url": None, "reference_url": None, "width": None, "height": None,
                          "checked_by_eye": None,
                          "attribution": {"title": None, "url": None, "author": None, "licence": None, "derived": None},
                          "analysis": None} for a in config.ANGLES]
        rep["missing_angles"] = list(config.ANGLES)
        rep["verdict"] = "INCOMPLETE"
        rep["run_metadata"] = dict(rep["run_metadata"], notes=["The Inspection failed to run; see the server log"])
        return rep

    def _scene(self, scene_id: str | None) -> Scene:
        try:
            return load_scene(scene_id or "")
        except SceneNotFound:
            raise WorkflowError(404, "not_found", f"Scene {scene_id} not found") from None

    def _scripted_scene(self, turn_id: str, kind: str) -> str | None:
        for turn in self.timeline.get("turns", []):
            if turn.get("turn_id") == turn_id:
                for e in turn.get("events", []):
                    if e.get("type") == "inspection" and e.get("kind") == kind:
                        return e.get("scene_id")
        return None

    def _event(self, rep: dict, type: str, **data) -> None:
        self.store.add_event(type=type, turn_id=rep["turn_id"], gate=rep["gate"], t=self.clock(),
                             data={"inspection_id": rep["inspection_id"], **data})

    # ------------------------------------------------------------------ Turns (driven by the demo player)
    def begin_turn(self, spec: dict) -> dict:
        existing = self.store.get_turn(spec["turn_id"])
        if existing:
            return existing
        pushback = next((e["t"] for e in spec.get("events", []) if e.get("type") == "scheduled_pushback"), None)
        turn = self.store.create_turn(turn_id=spec["turn_id"], gate=spec["gate"], flight=spec.get("flight"),
                                      aircraft_type=spec.get("aircraft_type"), pushback_t=pushback)
        self.store.add_event(type="stand_prep", turn_id=turn["turn_id"], gate=turn["gate"], t=self.clock())
        return turn

    def block_in(self, turn_id: str) -> None:
        turn = self.store.get_turn(turn_id)
        if turn and turn["phase"] != "departed":
            self.store.set_turn_phase(turn_id, "on_stand")
            self.store.add_event(type="block_in", turn_id=turn_id, gate=turn["gate"], t=self.clock())

    def try_depart(self, turn_id: str) -> bool:
        """Scheduled pushback. The Turn is shown as departed only once its latest Inspection is signed off;
        until then the Gate keeps asking for a person (the system itself never clears or holds a pushback)."""
        turn = self.store.get_turn(turn_id)
        if turn is None or turn["phase"] == "departed":
            return True
        latest = self.store.latest_report(turn_id)
        if latest is not None and latest["status"] != "confirmed":
            return False
        self.store.set_turn_phase(turn_id, "departed")
        self.store.add_event(type="departed", turn_id=turn_id, gate=turn["gate"], t=self.clock())
        return True

    # ------------------------------------------------------------------ views
    def _minutes_to_pushback(self, turn: dict) -> float | None:
        if turn.get("pushback_t") is None or turn["phase"] == "departed":
            return None
        return round(max(0.0, turn["pushback_t"] - self.clock()) / 60.0, 1)

    def turn_view(self, turn_id: str) -> dict:
        turn = self.store.get_turn(turn_id)
        if turn is None:
            raise WorkflowError(404, "not_found", f"Turn {turn_id} not found")
        reports = self.store.reports_for_turn(turn_id)
        return {"turn_id": turn["turn_id"], "gate": turn["gate"], "flight": turn["flight"],
                "aircraft_type": turn["aircraft_type"], "phase": turn["phase"],
                "minutes_to_pushback": self._minutes_to_pushback(turn),
                "latest_inspection_id": reports[-1]["inspection_id"] if reports else None,
                "inspections": reports, "events": self.store.events_for_turn(turn_id)}

    def gate_state(self, gate: str) -> tuple[dict, dict | None]:
        """(GateState, QueueItem or None)."""
        turn = self.store.current_turn(gate)
        if turn is None:
            return {"gate": gate, "status": "idle", "verdict": None, "highest_open_severity": None, "turn": None}, None
        latest = self.store.latest_report(turn["turn_id"])
        running = latest is not None and latest["status"] == "inspecting"
        settled = latest if latest is not None and not running else None
        phase = turn["phase"]
        if phase == "departed":
            status = "departed"
        elif running:
            status = "inspecting"
        elif phase == "on_stand":
            status = "on_stand"
        elif latest is None:
            status = "awaiting_pre_arrival"
        else:
            status = "confirmed_clear" if latest["status"] == "confirmed" else "awaiting_confirmation"
        minutes = self._minutes_to_pushback(turn)
        state = {
            "gate": gate, "status": status,
            "verdict": settled["verdict"] if settled else None,
            "highest_open_severity": settled["highest_open_severity"] if settled else None,
            "turn": {"turn_id": turn["turn_id"], "flight": turn["flight"], "aircraft_type": turn["aircraft_type"],
                     "phase": phase, "minutes_to_pushback": minutes,
                     "latest_inspection_id": latest["inspection_id"] if latest else None},
        }
        item = None
        if settled is not None and settled["status"] != "confirmed" and phase != "departed":
            item = queue_item(gate, turn["turn_id"], settled, minutes)
        return state, item

    def state(self) -> tuple[list[dict], list[dict]]:
        gates, queue = [], []
        for g in self.gates:
            s, item = self.gate_state(g)
            gates.append(s)
            if item:
                queue.append(item)
        return gates, sort_queue(queue)


def queue_item(gate: str, turn_id: str, rep: dict, minutes: float | None) -> dict:
    still_open = R.open_findings(rep)
    unresolved = R.unresolved_unusable_angles(rep)
    severity = rep.get("highest_open_severity")
    if severity == "HOLD":
        holds = [f for f in still_open if f["severity"] == "HOLD"]
        reason = "hold"
        text = f"HOLD on {holds[0]['angle']}: {holds[0]['description']}" if len(holds) == 1 else \
            f"{len(holds)} HOLD Findings ({', '.join(sorted({f['angle'] for f in holds}))})"
    elif still_open:
        reason = "findings"
        text = f"{len(still_open)} Finding{'s' if len(still_open) != 1 else ''} to confirm"
    elif unresolved:
        reason = "incomplete"
        text = f"{', '.join(unresolved)} unusable: re-inspect or check by eye"
    else:
        reason = "signoff"
        text = "Ready for sign-off"
    return {"gate": gate, "turn_id": turn_id, "inspection_id": rep["inspection_id"], "reason": reason,
            "severity": severity, "minutes_to_pushback": minutes, "text": text}


def sort_queue(items: list[dict]) -> list[dict]:
    """HOLDs first, then by time to scheduled pushback (soonest first; unknown times last)."""
    return sorted(items, key=lambda q: (0 if q["severity"] == "HOLD" else 1,
                                        q["minutes_to_pushback"] if q["minutes_to_pushback"] is not None else float("inf"),
                                        SEVERITY_ORDER.get(q["severity"], 3), q["gate"]))
