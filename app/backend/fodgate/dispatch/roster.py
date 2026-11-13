"""Roster, Shifts and chat sessions. A PIN from the roster file stands in for sign-in (demo only).

Role, Shift and Gates always come from the roster row looked up by the session token. Nothing a client sends
in a request body, and nothing the model writes, can change them.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time

from .. import config
from ..report import now_iso
from ..store import Store
from ..workflow import WorkflowError
from .models import PERSON_ROLES, SHIFT_STATUSES

SIGNED_IN_WINDOW_S = 15.0        # the chat page polls its inbox about once a second


def _hash(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


def load_roster_file() -> dict:
    f = config.roster_path()
    return json.loads(f.read_text()) if f.is_file() else {"people": []}


class Roster:
    def __init__(self, store: Store, data: dict | None = None):
        self.store = store
        self._seen: dict[str, float] = {}            # person_id -> monotonic time of the last inbox poll
        self.load(load_roster_file() if data is None else data)

    def load(self, data: dict) -> None:
        """Replace the people table with the roster file. People who left the file lose their sessions."""
        ids = []
        for p in data.get("people", []):
            pid, role = str(p["person_id"]).lower(), p["role"]
            if role not in PERSON_ROLES:
                raise ValueError(f"roster: {pid} has unknown role {role!r}")
            ids.append(pid)
            self.store.execute(
                "INSERT INTO people (person_id, name, role, gates, pin_hash) VALUES (?,?,?,?,?) "
                "ON CONFLICT(person_id) DO UPDATE SET name=excluded.name, role=excluded.role, gates=excluded.gates, "
                "pin_hash=excluded.pin_hash",
                (pid, p["name"], role, json.dumps(p.get("gates", [])), _hash(pid, str(p["pin"]))))
            if not self.store.query("SELECT 1 FROM shifts WHERE person_id=?", (pid,)):
                self.set_shift(pid, p.get("shift", "on"))
        marks = ",".join("?" * len(ids))
        for table in ("people", "shifts", "sessions"):
            self.store.execute(f"DELETE FROM {table} WHERE person_id NOT IN ({marks})", tuple(ids))

    # ------------------------------------------------------------------ people
    def _view(self, row: dict) -> dict:
        shift = self.store.query("SELECT status FROM shifts WHERE person_id=? ORDER BY shift_id DESC LIMIT 1",
                                 (row["person_id"],))
        seen = self._seen.get(row["person_id"])
        return {"person_id": row["person_id"], "name": row["name"], "role": row["role"],
                "gates": json.loads(row["gates"]), "shift": shift[0]["status"] if shift else "off",
                "signed_in": seen is not None and time.monotonic() - seen < SIGNED_IN_WINDOW_S}

    def person(self, person_id: str | None) -> dict | None:
        rows = self.store.query("SELECT * FROM people WHERE person_id=?", ((person_id or "").strip().lower(),))
        return self._view(rows[0]) if rows else None

    def find(self, who: str | None) -> dict | None:
        """By person_id or by name, ignoring case."""
        key = (who or "").strip().lower().lstrip("@")
        rows = self.store.query("SELECT * FROM people WHERE person_id=? OR lower(name)=?", (key, key))
        return self._view(rows[0]) if rows else None

    def people(self, *, on_shift: bool = False, role: str | None = None, gate: str | None = None) -> list[dict]:
        out = [self._view(r) for r in self.store.query("SELECT * FROM people ORDER BY role, person_id")]
        return [p for p in out if (not on_shift or p["shift"] == "on") and (role is None or p["role"] == role)
                and (gate is None or gate in p["gates"])]

    def set_shift(self, person_id: str, status: str, handed_to: str | None = None) -> None:
        if status not in SHIFT_STATUSES:
            raise WorkflowError(422, "invalid_request", f"shift must be one of {', '.join(SHIFT_STATUSES)}")
        self.store.execute("UPDATE shifts SET ended_at=? WHERE person_id=? AND ended_at IS NULL", (now_iso(), person_id))
        self.store.execute("INSERT INTO shifts (person_id, status, started_at, handed_to) VALUES (?,?,?,?)",
                           (person_id, status, now_iso(), handed_to))

    # ------------------------------------------------------------------ sessions
    def join(self, who: str, pin: str) -> tuple[str, dict]:
        """Check the PIN and open a session. Returns (token, person). The token is shown once, stored hashed."""
        person = self.find(who)
        rows = self.store.query("SELECT pin_hash FROM people WHERE person_id=?", (person["person_id"],)) if person else []
        if not rows or not secrets.compare_digest(rows[0]["pin_hash"], _hash(person["person_id"], str(pin))):
            raise WorkflowError(401, "bad_credentials", "Unknown person or wrong PIN")
        token = secrets.token_urlsafe(24)
        self.store.execute("INSERT INTO sessions (token_hash, person_id, created_at, last_seen) VALUES (?,?,?,?)",
                           (_hash(token), person["person_id"], now_iso(), now_iso()))
        self.touch(person["person_id"])
        return token, self.person(person["person_id"])

    def session(self, token: str | None) -> tuple[str, dict]:
        """(token_hash, person) for a session token. 401 when it is missing or unknown."""
        th = _hash(token or "")
        rows = self.store.query("SELECT person_id FROM sessions WHERE token_hash=?", (th,))
        person = self.person(rows[0]["person_id"]) if rows else None
        if person is None:
            raise WorkflowError(401, "not_signed_in", "Sign in first: POST /api/agent/join with a roster name and PIN")
        return th, person

    def touch(self, person_id: str) -> None:
        self._seen[person_id] = time.monotonic()
