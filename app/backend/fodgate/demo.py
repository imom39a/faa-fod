"""Scripted timeline player for the demo (app/data/demo/timeline.json): play, pause, reset, speed.

The player only advances a clock and fires the timeline's events into the workflow. Inspections run in the
workflow's background pool, so the API stays responsive. Reset clears the database and keeps the LLM cache.
"""
from __future__ import annotations

import logging
import threading
import time

from .workflow import Workflow, WorkflowError

log = logging.getLogger("fodgate.demo")
SPEEDS = (1, 2, 5, 10)


class DemoPlayer:
    def __init__(self, workflow: Workflow, *, tick_s: float = 0.2):
        self.wf = workflow
        self.tick_s = tick_s
        self._lock = threading.RLock()
        self.playing = False
        self.speed = 1
        self.t = 0.0
        self._fired: set[tuple[str, int]] = set()
        self._pending_departures: list[str] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        workflow.clock = lambda: self.t

    # ------------------------------------------------------------------ timeline
    def _events(self) -> list[tuple[float, str, int, dict, dict]]:
        out = []
        for turn in self.wf.timeline.get("turns", []):
            for i, e in enumerate(turn.get("events", [])):
                out.append((float(e.get("t", 0)), turn["turn_id"], i, turn, e))
        return sorted(out, key=lambda x: (x[0], x[1], x[2]))

    @property
    def duration(self) -> float:
        return max((e[0] for e in self._events()), default=0.0)

    def info(self) -> dict:
        with self._lock:
            return {"playing": self.playing, "speed": self.speed, "t": round(self.t, 1), "duration": self.duration}

    # ------------------------------------------------------------------ controls
    def play(self) -> dict:
        with self._lock:
            if self.t < self.duration or not self._fired:
                self.playing = True
        return self.info()

    def pause(self) -> dict:
        with self._lock:
            self.playing = False
        return self.info()

    def reset(self) -> dict:
        with self._lock:
            self.playing = False
            self.t = 0.0
            self._fired.clear()
            self._pending_departures.clear()
            self.wf.reset()
        return self.info()

    def set_speed(self, speed) -> dict:
        if speed not in SPEEDS:
            raise WorkflowError(422, "invalid_request", f"speed must be one of {', '.join(map(str, SPEEDS))}")
        with self._lock:
            self.speed = int(speed)
        return self.info()

    # ------------------------------------------------------------------ clock
    def advance(self, dt: float) -> None:
        """Move the clock by `dt` real seconds (scaled by speed when playing) and fire what is due."""
        with self._lock:
            if self.playing:
                self.t = min(self.duration, self.t + dt * self.speed)
                for t, turn_id, i, turn, e in self._events():
                    if t > self.t:
                        break
                    if (turn_id, i) not in self._fired:
                        self._fired.add((turn_id, i))
                        self._fire(turn, e)
                if self.t >= self.duration:
                    self.playing = False
            # Departures wait for a person's sign-off, which can arrive while the clock is paused.
            self._pending_departures = [tid for tid in self._pending_departures if not self.wf.try_depart(tid)]

    def _fire(self, turn: dict, e: dict) -> None:
        kind = e.get("type")
        try:
            if kind == "stand_prep":
                self.wf.begin_turn(turn)
            elif kind == "inspection":
                self.wf.begin_turn(turn)
                self.wf.start_inspection(turn["gate"], kind=e.get("kind", "pre_departure"), scene_id=e.get("scene_id"))
            elif kind == "block_in":
                self.wf.begin_turn(turn)
                self.wf.block_in(turn["turn_id"])
            elif kind == "scheduled_pushback":
                if not self.wf.try_depart(turn["turn_id"]):
                    self._pending_departures.append(turn["turn_id"])
        except WorkflowError as err:
            log.warning("timeline event %s for %s skipped: %s", kind, turn.get("turn_id"), err.message)
            self.wf.store.add_event(type="timeline_event_skipped", turn_id=turn.get("turn_id"), gate=turn.get("gate"),
                                    t=self.t, data={"event": kind, "reason": err.message})

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            last = time.monotonic()
            while not self._stop.wait(self.tick_s):
                now = time.monotonic()
                try:
                    self.advance(now - last)
                except Exception:
                    log.exception("demo tick failed")
                last = now

        self._thread = threading.Thread(target=loop, name="demo-player", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
