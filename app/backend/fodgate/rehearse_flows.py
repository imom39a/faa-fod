"""`python -m fodgate.rehearse_flows`: play the flows added after the first demo, with scripted people.

Five short stories on the real demo scenes: a Shift Handover, "not found" (a REMOVE Finding, then a HOLD),
"still there" (a HOLD recorded as removed whose new photo still shows it), an unusable view, and debris outside
the gate safety envelope. It runs the Workflow and the dispatcher in this process with a hand-driven clock, so
it is quick and repeatable. People's lines are scripted; the agent is the real model unless --keyless is given.
It prints Markdown: each person's chat thread, the activity log, the Confirmations and the measured cost.

  uv run python -m fodgate.rehearse_flows --max-usd 0.25        # live agent (claude-haiku-5-5)
  uv run python -m fodgate.rehearse_flows --keyless             # code only: no model call, buttons only
  uv run python -m fodgate.rehearse_flows --only still-there

The Inspections replay the saved Claude results in app/var/cache/, so they cost nothing. "Still there" needs a
scene whose re-inspection shows the object again: the script derives one in a scratch folder from `demo-bolt` by
leaving out its clean after frame, so the new photo is the first photo again. Nothing under app/data changes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import config, llm as llm_mod
from .dispatch import Dispatcher, commands
from .llm import LLM
from .store import Store
from .workflow import Workflow, WorkflowError

GATE, TURN_ID = "T5", "T5-DL1776"
SCENES = ("demo-hold", "demo-bolt", "demo-glare", "demo-outside")


class Stage:
    def __init__(self, keyless: bool):
        self.keyless, self.t, self.lines = keyless, 0.0, []
        self.real_data, self.real_cache = config.data_dir(), config.cache_dir()
        self.tmp = Path(tempfile.mkdtemp(prefix="fod-flows-"))
        data = self.tmp / "data"
        (data / "scenes").mkdir(parents=True)
        for name in ("rules", "roster"):
            os.symlink(self.real_data / name, data / name)
        for sid in SCENES:
            os.symlink(self.real_data / "scenes" / sid, data / "scenes" / sid)
        stuck = data / "scenes" / "demo-stuck"                    # demo-bolt with no clean after frame for the HOLD
        shutil.copytree(self.real_data / "scenes" / "demo-bolt", stuck)
        scene = json.loads((self.real_data / "scenes" / "demo-bolt" / "scene.json").read_text())
        scene["scene_id"] = "demo-stuck"
        for a in scene["angles"].values():
            if a.get("ground_truth"):
                a["after"] = None
        (stuck / "scene.json").write_text(json.dumps(scene))
        os.environ["FOD_DATA_DIR"], os.environ["FOD_VAR_DIR"] = str(data), str(self.tmp / "var")
        self.store = Store()
        self.llm = LLM(cache_dir=self.real_cache)

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ one story
    def begin(self, title: str, scene: str, issue: str) -> None:
        self.t = 0.0
        self.store.reset()
        self.wf = Workflow(self.store, self.llm, clock=lambda: self.t)
        self.d = Dispatcher(self.wf, None if self.keyless else self.llm, clock=lambda: self.t,
                            mode="code" if self.keyless else "on")
        for p in self.d.roster.people():
            self.d.roster.set_shift(p["person_id"], "on")
            self.d.roster.touch(p["person_id"])
        self.out(f"\n## {title}\n\nIssue {issue}. Scene `{scene}` at Gate {GATE}.\n\n**What was done**\n")
        self.wf.begin_turn({"turn_id": TURN_ID, "gate": GATE, "flight": "DL1776", "aircraft_type": "757-200",
                            "events": [{"t": 600, "type": "scheduled_pushback"}]})
        self.wf.start_inspection(GATE, kind="pre_departure", scene_id=scene, background=False)
        self.d.settle()
        rep = self.store.latest_report(TURN_ID)
        self.step(f"Pre-departure Inspection finishes: Verdict {rep['verdict'].replace('_', ' ')}; Tasks: "
                  + (", ".join(f"{t['task_id']} {t['type']} {t['finding_label'] or t['angle'] or ''} with "
                               f"{self.d._name(t['assignee_id'])} (by {t['created_by']})" for t in self.d.board.tasks()) or "none"))

    def out(self, text: str) -> None:
        self.lines.append(text)

    def step(self, text: str) -> None:
        self.n = getattr(self, "n", 0) + 1 if self.lines and not self.lines[-1].startswith("\n## ") else 1
        self.out(f"{self.n}. {text}")

    def press(self, who: str, text: str) -> None:
        """A button on the chat page: a structured command, run as the signed-in person."""
        try:
            reply = commands.run_command(self.d, self.d.roster.person(who), text)
            self.step(f"{self.d._name(who)} presses a button (`{text}`). Reply: {reply[0]}")
        except WorkflowError as e:
            self.step(f"{self.d._name(who)} presses a button (`{text}`). **Refused** ({e.code}): {e.message}")
        self.d.settle()

    def type(self, who: str, text: str) -> None:
        mid = self.d.board.send("agent", text, kind="person", from_id=who)
        self.store.add_event(type="person_message", data={"message_id": mid, "person_id": who})
        self.d.settle()
        self.step(f"{self.d._name(who)} types: \"{text}\"")

    def holder(self, type: str, label: str) -> dict:
        return next(t for t in self.store.query("SELECT * FROM tasks ORDER BY seq DESC")
                    if t["type"] == type and label in (t["finding_label"], t["angle"]))

    def wait(self, seconds: float) -> None:
        end = self.t + seconds
        while self.t < end:
            self.t = min(end, self.t + 5)
            self.d.step()
        self.d.settle()
        self.step(f"{seconds:g} seconds of schedule time pass.")

    def end(self, people: list[str]) -> None:
        d = self.d
        for pid in people:
            self.out(f"\n**{d._name(pid)}'s chat thread**\n\n```")
            for m in d.board.thread(pid):
                who = d._name(m["from"]) if m["from"] not in ("agent", "code") else ("agent" if m["from"] == "agent" else "system")
                arrow = f"{who} to {d._name(m['to'])}" if m["to"] not in ("agent", "code") else f"{who}"
                self.out(f"[{m['t']:>5.0f}s] {arrow}: {m['text']}")
            self.out("```")
        self.out("\n**Activity log** (messages left out)\n\n```")
        for e in d.board.activity(limit=1000):
            if e["event"] not in ("message", "idle", "dispatcher_started", "demo_reset"):
                self.out(f"[{e['t']:>5.0f}s] {e['event']:<20} {e['actor']:<8} " + e["text"].replace("\n", " / ")[:230])
        self.out("```")
        confs = self.store.list_confirmations()
        self.out("\n**Confirmations recorded**: " + ("; ".join(
            f"{c['action']} by {c['name']} ({(c.get('data') or {}).get('via', '?').replace('_', ' ')}"
            + (f", told {(c.get('data') or {})['reported_to_name']}" if (c.get("data") or {}).get("reported_to_name") else "") + ")"
            for c in confs) or "none"))
        cost = d.cost()
        self.out(f"\n**Cost**: {cost['wakes']} agent wake{'s' if cost['wakes'] != 1 else ''}, "
                 f"${cost['agent_session_usd']:.4f}.")
        self.total = getattr(self, "total", 0.0) + cost["agent_session_usd"]
        self.wakes = getattr(self, "wakes", 0) + cost["wakes"]
        self.wf.shutdown()


# ---------------------------------------------------------------------- the five stories
def handover(s: Stage) -> None:
    s.begin("1. Shift Handover", "demo-hold", "#3")
    s.press("okafor", "/break")
    s.press("okafor", "/handover kim")
    s.press("okafor", "/handover reyes")
    s.press("reyes", "n")
    s.press("okafor", "/handover reyes")
    s.wait(35)
    s.press("reyes", "y")
    s.press("reyes", "/ack F1")
    s.end(["okafor", "reyes", "dana"])


def not_found(s: Stage) -> None:
    s.begin("2. Not found: a REMOVE Finding, then a HOLD", "demo-hold", "#4")
    bag = s.holder("remove", "F2")
    who = bag["assignee_id"]
    if s.keyless:
        s.press(who, f"/cant-find {bag['task_id']}")
    else:
        s.type(who, "cant find the bag tag anywhere, looked all round the belt loader")
    s.press(who, "y")
    s.press("okafor", "/ack F1")
    s.press("okafor", "/send kim F1 fetch the hammer by the right engine")
    walk = s.holder("remove", "F1")
    if s.keyless:
        s.press("kim", f"/cant-find {walk['task_id']}")
    else:
        s.type("kim", "no sign of any hammer by the right engine, walked it twice")
    s.press("okafor", "y")
    s.end(["kim", "okafor"])


def still_there(s: Stage) -> None:
    s.begin("3. Still there: a HOLD recorded as removed, but the new photo still shows it", "demo-stuck", "#4")
    s.press("okafor", "/ack F1")
    s.press("okafor", "/send kim F1 remove the bolt by the left engine")
    walk = s.holder("remove", "F1")
    s.press("kim", f"/done {walk['task_id']}")
    s.press("okafor", "/removed F1")
    s.press("okafor", f"/reassign {walk['task_id']} dana")
    s.press("okafor", f"/reassign {walk['task_id']} patel")
    s.press("patel", f"/done {walk['task_id']}")
    s.press("okafor", "/removed F1")
    s.end(["okafor", "kim", "patel", "dana"])


def unusable(s: Stage) -> None:
    s.begin("4. An unusable view", "demo-glare", "#5")
    eye = s.holder("check_by_eye", "ENG-R")
    s.press("kim", "/eye T5 ENG-R")
    s.press("okafor", "/signoff T5")
    s.press("okafor", "/reinspect T5 ENG-R")
    s.step(f"{eye['task_id']} is now {s.d.board.task(eye['task_id'])['status']}: "
           f"{s.d.board.task(eye['task_id'])['close_reason']}.")
    s.press("okafor", "/signoff T5")
    s.end(["okafor", "kim"])


def outside(s: Stage) -> None:
    s.begin("5. Debris outside the stand", "demo-outside", "#5")
    task = s.holder("report_outside_boundary", "F1")
    who = task["assignee_id"]
    s.press(who, f"/done {task['task_id']} rang it through")
    s.press("dana", "/reported F1")
    s.press(who, "/reported F1")
    s.end([who])


STORIES = {"handover": handover, "not-found": not_found, "still-there": still_there, "unusable": unusable,
           "outside": outside}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fodgate.rehearse_flows", description=__doc__.split("\n\n")[0])
    ap.add_argument("--keyless", action="store_true", help="no model: code-only routing, buttons only")
    ap.add_argument("--only", action="append", choices=list(STORIES), help="one story (repeatable)")
    ap.add_argument("--max-usd", type=float, default=0.25, help="spend cap for the live run")
    a = ap.parse_args(argv)
    if a.keyless:
        os.environ["FOD_ENV_FILE"] = "/dev/null"
        os.environ.pop("ANTHROPIC_API_KEY", None)
    else:
        os.environ["FOD_MAX_SPEND_USD"] = str(a.max_usd)
    s = Stage(a.keyless)
    try:
        if not a.keyless and not s.llm.available()[0]:
            print(f"Cannot run live: {s.llm.available()[1]}. Use --keyless.", file=sys.stderr)
            return 1
        for name in a.only or list(STORIES):
            STORIES[name](s)
    finally:
        s.close()
    spend = llm_mod.process_spend()
    mode = "code only, no API key" if a.keyless else f"live agent on `{config.AGENT_MODEL}`"
    print(f"# Rehearsal of the later flows ({mode})\n\n"
          f"- Command: `python -m fodgate.rehearse_flows{' --keyless' if a.keyless else ''}`\n"
          f"- Agent: {getattr(s, 'wakes', 0)} wakes, ${getattr(s, 'total', 0.0):.4f}\n"
          f"- Everything this process spent on Claude, Inspections included: ${spend['usd']:.4f} in {spend['calls']} "
          "uncached calls (the Inspections replay saved results)")
    print("\n".join(s.lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
