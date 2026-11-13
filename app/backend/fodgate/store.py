"""SQLite store (app/var/fod.sqlite): Turns, Inspections (report JSON), Findings, Confirmations, events,
and the dispatch tables (roster, Tasks, Reports, messages, proposals, timers, agent wakes, activity log;
spec/dispatch.md).

The report JSON on the Inspection row is the record. The findings table is an index of it, rewritten on
every save, and the confirmations table is an append-only log of what people did.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from . import config
from .report import now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  turn_id TEXT UNIQUE NOT NULL, gate TEXT NOT NULL, flight TEXT, aircraft_type TEXT,
  phase TEXT NOT NULL, pushback_t REAL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inspections (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  inspection_id TEXT UNIQUE NOT NULL, turn_id TEXT NOT NULL, gate TEXT NOT NULL, kind TEXT NOT NULL,
  scene_id TEXT, parent_inspection_id TEXT, status TEXT NOT NULL, verdict TEXT,
  created_at TEXT NOT NULL, report TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS findings (
  inspection_id TEXT NOT NULL, finding_id TEXT NOT NULL, angle TEXT, severity TEXT, zone_tier TEXT,
  status TEXT, data TEXT NOT NULL, PRIMARY KEY (inspection_id, finding_id));
CREATE TABLE IF NOT EXISTS confirmations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  inspection_id TEXT NOT NULL, finding_id TEXT, action TEXT NOT NULL, role TEXT, name TEXT,
  at TEXT NOT NULL, data TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  turn_id TEXT, gate TEXT, type TEXT NOT NULL, at TEXT NOT NULL, t REAL, data TEXT);
CREATE INDEX IF NOT EXISTS idx_insp_turn ON inspections(turn_id, seq);
CREATE INDEX IF NOT EXISTS idx_turn_gate ON turns(gate, seq);
CREATE INDEX IF NOT EXISTS idx_event_turn ON events(turn_id, id);
"""

# Dispatch (spec/dispatch.md). People, shifts and sessions survive a demo Reset; the rest is cleared with it.
DISPATCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
  person_id TEXT PRIMARY KEY, name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('ramp_agent','ramp_lead','supervisor')),
  gates TEXT NOT NULL, pin_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS shifts (
  shift_id INTEGER PRIMARY KEY AUTOINCREMENT, person_id TEXT NOT NULL,
  status TEXT NOT NULL, started_at TEXT, ended_at TEXT, handed_to TEXT);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, person_id TEXT NOT NULL, created_at TEXT, last_seen TEXT);
CREATE TABLE IF NOT EXISTS tasks (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT UNIQUE,
  type TEXT NOT NULL, gate TEXT NOT NULL, turn_id TEXT NOT NULL, inspection_id TEXT NOT NULL,
  finding_id TEXT, finding_label TEXT, angle TEXT, severity TEXT,
  required_role TEXT NOT NULL, assignee_id TEXT, instruction TEXT, status TEXT NOT NULL,
  created_by TEXT NOT NULL, created_at TEXT, closed_at TEXT, close_reason TEXT,
  closed_by_confirmation_id INTEGER, escalation_level INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS task_reports (
  report_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, by_person_id TEXT NOT NULL,
  at TEXT NOT NULL, kind TEXT NOT NULL, raw_text TEXT, via TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  message_id INTEGER PRIMARY KEY AUTOINCREMENT, from_id TEXT NOT NULL, to_id TEXT NOT NULL,
  kind TEXT NOT NULL, text TEXT NOT NULL, task_id TEXT, proposal_id TEXT, at TEXT NOT NULL, t REAL,
  delivered_at TEXT);
CREATE TABLE IF NOT EXISTS proposals (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id TEXT UNIQUE, to_id TEXT NOT NULL,
  action TEXT NOT NULL, status TEXT NOT NULL, created_by TEXT NOT NULL,
  created_at TEXT, expires_t REAL, answered_at TEXT);
CREATE TABLE IF NOT EXISTS timers (
  timer_id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, kind TEXT NOT NULL,
  fire_t REAL NOT NULL, fired_at TEXT, cancelled INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS agent_wakes (
  wake_id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_event_id INTEGER, trigger TEXT, model TEXT,
  tokens_in INTEGER, tokens_out INTEGER, est_cost_usd REAL, tool_calls TEXT, outcome TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS finding_refs (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT UNIQUE, turn_id TEXT NOT NULL, gate TEXT NOT NULL,
  inspection_id TEXT NOT NULL, finding_id TEXT NOT NULL, superseded INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS agent_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, t REAL, kind TEXT NOT NULL, event TEXT NOT NULL,
  gate TEXT, turn_id TEXT, actor TEXT, text TEXT NOT NULL, data TEXT, console INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS idx_task_turn ON tasks(turn_id, status);
CREATE INDEX IF NOT EXISTS idx_msg_to ON messages(to_id, message_id);
"""
TABLES = ("turns", "inspections", "findings", "confirmations", "events",
          "tasks", "task_reports", "messages", "proposals", "timers", "agent_wakes", "finding_refs", "agent_log")


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or config.db_path())
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self.changed = threading.Condition()     # notified on every new event; the dispatcher sleeps on it
        self.epoch = 0                           # bumped by reset(), so cursors held elsewhere start again
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.executescript(DISPATCH_SCHEMA)
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def reset(self) -> None:
        """Clear every table (the LLM cache on disk is separate and is kept)."""
        with self._lock:
            for t in TABLES:
                self._db.execute(f"DELETE FROM {t}")
            self._db.execute("DELETE FROM sqlite_sequence")
            self._db.commit()
            self.epoch += 1
        self.notify()

    def notify(self) -> None:
        with self.changed:
            self.changed.notify_all()

    # ------------------------------------------------------------------ generic access (dispatch tables)
    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def execute(self, sql: str, args: tuple = ()) -> int:
        """Run one write. Returns the new row id for an INSERT, else the number of rows changed."""
        with self._lock:
            cur = self._db.execute(sql, args)
            self._db.commit()
            return cur.lastrowid if sql.lstrip()[:6].upper() == "INSERT" else cur.rowcount

    # ------------------------------------------------------------------ turns
    def create_turn(self, *, turn_id: str, gate: str, flight: str | None, aircraft_type: str | None,
                    phase: str = "stand_prep", pushback_t: float | None = None) -> dict:
        with self._lock:
            self._db.execute(
                "INSERT INTO turns (turn_id, gate, flight, aircraft_type, phase, pushback_t, created_at) "
                "VALUES (?,?,?,?,?,?,?)", (turn_id, gate, flight, aircraft_type, phase, pushback_t, now_iso()))
            self._db.commit()
        return self.get_turn(turn_id)

    def get_turn(self, turn_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM turns WHERE turn_id=?", (turn_id,)).fetchone()
        return dict(row) if row else None

    def set_turn_phase(self, turn_id: str, phase: str) -> None:
        with self._lock:
            self._db.execute("UPDATE turns SET phase=? WHERE turn_id=?", (phase, turn_id))
            self._db.commit()

    def current_turn(self, gate: str) -> dict | None:
        """The most recently started Turn at a Gate."""
        with self._lock:
            row = self._db.execute("SELECT * FROM turns WHERE gate=? ORDER BY seq DESC LIMIT 1", (gate,)).fetchone()
        return dict(row) if row else None

    def count_turns(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM turns").fetchone()[0]

    # ------------------------------------------------------------------ inspections
    def save_report(self, report: dict) -> None:
        """Insert or update an Inspection and rewrite its Findings index."""
        iid = report["inspection_id"]
        with self._lock:
            exists = self._db.execute("SELECT 1 FROM inspections WHERE inspection_id=?", (iid,)).fetchone()
            body = json.dumps(report, ensure_ascii=False)
            if exists:
                self._db.execute("UPDATE inspections SET status=?, verdict=?, kind=?, report=? WHERE inspection_id=?",
                                 (report["status"], report.get("verdict"), report["kind"], body, iid))
            else:
                self._db.execute(
                    "INSERT INTO inspections (inspection_id, turn_id, gate, kind, scene_id, parent_inspection_id, "
                    "status, verdict, created_at, report) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (iid, report["turn_id"], report["gate"], report["kind"], report.get("scene_id"),
                     report.get("parent_inspection_id"), report["status"], report.get("verdict"), now_iso(), body))
            self._db.execute("DELETE FROM findings WHERE inspection_id=?", (iid,))
            self._db.executemany(
                "INSERT INTO findings (inspection_id, finding_id, angle, severity, zone_tier, status, data) "
                "VALUES (?,?,?,?,?,?,?)",
                [(iid, f["finding_id"], f["angle"], f["severity"], f["zone_tier"], f["status"],
                  json.dumps(f, ensure_ascii=False)) for f in report.get("findings", [])])
            self._db.commit()

    def get_report(self, inspection_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT report FROM inspections WHERE inspection_id=?", (inspection_id,)).fetchone()
        return json.loads(row["report"]) if row else None

    def reports_for_turn(self, turn_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT report FROM inspections WHERE turn_id=? ORDER BY seq", (turn_id,)).fetchall()
        return [json.loads(r["report"]) for r in rows]

    def latest_report(self, turn_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT report FROM inspections WHERE turn_id=? ORDER BY seq DESC LIMIT 1",
                                   (turn_id,)).fetchone()
        return json.loads(row["report"]) if row else None

    def list_findings(self, inspection_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT data FROM findings WHERE inspection_id=? ORDER BY rowid",
                                    (inspection_id,)).fetchall()
        return [json.loads(r["data"]) for r in rows]

    # ------------------------------------------------------------------ confirmations and events
    def add_confirmation(self, *, inspection_id: str, finding_id: str | None, action: str, role: str, name: str,
                         data: dict | None = None) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO confirmations (inspection_id, finding_id, action, role, name, at, data) VALUES (?,?,?,?,?,?,?)",
                (inspection_id, finding_id, action, role, name, now_iso(), json.dumps(data or {}, ensure_ascii=False)))
            self._db.commit()

    def list_confirmations(self, inspection_id: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM confirmations", ()
        if inspection_id:
            q, args = q + " WHERE inspection_id=?", (inspection_id,)
        with self._lock:
            rows = self._db.execute(q + " ORDER BY id", args).fetchall()
        return [dict(r) | {"data": json.loads(r["data"] or "{}")} for r in rows]

    def add_event(self, *, type: str, turn_id: str | None = None, gate: str | None = None, t: float | None = None,
                  data: dict | None = None) -> None:
        with self._lock:
            self._db.execute("INSERT INTO events (turn_id, gate, type, at, t, data) VALUES (?,?,?,?,?,?)",
                             (turn_id, gate, type, now_iso(), t, json.dumps(data or {}, ensure_ascii=False)))
            self._db.commit()
        self.notify()

    def events_after(self, cursor: int) -> list[dict]:
        """Every event with an id above `cursor`, oldest first (the dispatcher's feed)."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM events WHERE id>? ORDER BY id", (cursor,)).fetchall()
        return [dict(r) | {"data": json.loads(r["data"] or "{}")} for r in rows]

    def annotate_confirmations(self, after_id: int, extra: dict) -> list[int]:
        """Merge `extra` (how a Confirmation was made: via, raw text, person) into the rows added after `after_id`."""
        with self._lock:
            rows = self._db.execute("SELECT id, data FROM confirmations WHERE id>? ORDER BY id", (after_id,)).fetchall()
            for r in rows:
                self._db.execute("UPDATE confirmations SET data=? WHERE id=?",
                                 (json.dumps(json.loads(r["data"] or "{}") | extra, ensure_ascii=False), r["id"]))
            self._db.commit()
        return [r["id"] for r in rows]

    def last_confirmation_id(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COALESCE(MAX(id), 0) FROM confirmations").fetchone()[0]

    def events_for_turn(self, turn_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT type, at, t, data FROM events WHERE turn_id=? ORDER BY id",
                                    (turn_id,)).fetchall()
        return [{"type": r["type"], "at": r["at"], "t": r["t"], **json.loads(r["data"] or "{}")} for r in rows]
