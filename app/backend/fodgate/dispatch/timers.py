"""Timers are rows fired by code on the demo clock. A pending timer costs nothing and never calls a model."""
from __future__ import annotations

from typing import Callable

from ..report import now_iso
from ..store import Store


class Timers:
    def __init__(self, store: Store, clock: Callable[[], float]):
        self.store = store
        self.clock = clock

    def set(self, kind: str, after_s: float, task_id: str | None = None) -> int:
        return self.store.execute("INSERT INTO timers (task_id, kind, fire_t) VALUES (?,?,?)",
                                  (task_id, kind, self.clock() + max(0.0, after_s)))

    def set_at(self, kind: str, fire_t: float, task_id: str | None = None) -> int:
        return self.store.execute("INSERT INTO timers (task_id, kind, fire_t) VALUES (?,?,?)", (task_id, kind, fire_t))

    def cancel(self, task_id: str, kinds: tuple[str, ...] | None = None) -> None:
        q, args = "UPDATE timers SET cancelled=1 WHERE task_id=? AND fired_at IS NULL AND cancelled=0", [task_id]
        if kinds:
            q, args = q + f" AND kind IN ({','.join('?' * len(kinds))})", args + list(kinds)
        self.store.execute(q, tuple(args))

    def due(self) -> list[dict]:
        """Timers whose time has come, oldest first. Each is marked fired before it is returned."""
        rows = self.store.query("SELECT * FROM timers WHERE fired_at IS NULL AND cancelled=0 AND fire_t<=? "
                                "ORDER BY fire_t, timer_id", (self.clock(),))
        for r in rows:
            self.store.execute("UPDATE timers SET fired_at=? WHERE timer_id=?", (now_iso(), r["timer_id"]))
        return rows

    def pending(self) -> list[dict]:
        return self.store.query("SELECT * FROM timers WHERE fired_at IS NULL AND cancelled=0 ORDER BY fire_t")
