"""Shared rig for the dispatch tests: synthetic scenes, a five-person roster, a hand-driven clock and a
scripted stand-in for the agent model. No test calls the Claude API."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fodgate.dispatch import Dispatcher, commands
from fodgate.store import Store
from fodgate.workflow import Workflow
from tests.conftest import make_scene

OBJ = [400, 250, 416, 266]
OUTSIDE = [300, 100, 316, 116]          # above the envelope polygon on the WIDE view
ROSTER = {"people": [
    {"person_id": "kim", "name": "Kim", "role": "ramp_agent", "gates": ["T5", "T8"], "pin": "1111"},
    {"person_id": "okafor", "name": "Okafor", "role": "ramp_lead", "gates": ["T5", "T8"], "pin": "2222"},
    {"person_id": "patel", "name": "Patel", "role": "ramp_agent", "gates": ["T1", "T2", "T4"], "pin": "3333"},
    {"person_id": "reyes", "name": "Reyes", "role": "ramp_lead", "gates": ["T1", "T2", "T4"], "pin": "4444"},
    {"person_id": "dana", "name": "Dana", "role": "supervisor", "gates": ["T1", "T2", "T4", "T5", "T8"], "pin": "9999"},
]}
TURN = {"turn_id": "T5-DL1776", "gate": "T5", "flight": "DL1776", "aircraft_type": "757-200",
        "events": [{"t": 600, "type": "scheduled_pushback"}]}


def msg(stop, *blocks, tokens_in=1000, tokens_out=100):
    return SimpleNamespace(stop_reason=stop, content=list(blocks),
                           usage=SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out,
                                                 cache_creation_input_tokens=0, cache_read_input_tokens=0))


def tool_use(i, name, **inp):
    return SimpleNamespace(type="tool_use", id=f"tu_{i}", name=name, input=inp)


def text(t):
    return SimpleNamespace(type="text", text=t)


class FakeModel:
    """Plays a list of turns: each is a list of tool_use blocks, or a string for the final text. When the
    script runs out it ends the turn. Records every request."""

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests: list[dict] = []
        self.results: list[list[dict]] = []          # tool_result blocks the loop sent back

    def __call__(self, **kw):
        self.requests.append(kw)
        last = kw["messages"][-1]
        if isinstance(last["content"], list):
            self.results.append(last["content"])
        if not self.turns:
            return msg("end_turn", text("done"))
        turn = self.turns.pop(0)
        if callable(turn):
            turn = turn(kw)
        if isinstance(turn, str):
            return msg("end_turn", text(turn))
        return msg("tool_use", *turn)


class Rig:
    def __init__(self, llm, *, mode="code", create=None):
        self.t = 0.0
        self.store = Store()
        self.wf = Workflow(self.store, llm, clock=lambda: self.t)
        self.d = Dispatcher(self.wf, llm, roster=ROSTER, clock=lambda: self.t, create=create, mode=mode)
        self.board = self.d.board

    def inspect(self, scene="pd-hold", *, kind="pre_departure", turn=TURN) -> dict:
        self.wf.begin_turn(turn)
        rep = self.wf.start_inspection(turn["gate"], kind=kind, scene_id=scene, background=False)
        self.d.settle()
        return rep

    def advance(self, seconds: float) -> None:
        self.t += seconds
        self.d.settle()

    def person(self, pid: str) -> dict:
        return self.d.roster.person(pid)

    def cmd(self, pid: str, line: str) -> list[str]:
        out = commands.run_command(self.d, self.person(pid), line)
        self.d.settle()
        return out

    def say(self, pid: str, line: str) -> int:
        """What POST /api/agent/say does with free text."""
        mid = self.board.send("agent", line, kind="person", from_id=pid)
        self.store.add_event(type="person_message", data={"message_id": mid, "person_id": pid})
        self.d.settle()
        return mid

    def inbox(self, pid: str) -> list[str]:
        return [m["text"] for m in self.board.thread(pid) if m["to"] == pid]

    def tasks(self, **kw) -> list[dict]:
        return self.board.tasks(**kw)

    def task(self, type: str, active: bool = True) -> dict:
        return next(t for t in self.board.tasks(active=active) if t["type"] == type)

    def latest(self) -> dict:
        return self.store.latest_report(TURN["turn_id"])

    def finding(self, label: str) -> dict:
        return self.board.resolve(label)[2]

    def confirmations(self) -> list[dict]:
        return self.store.list_confirmations()


@pytest.fixture
def scenes(data_dir):
    make_scene("pd-hold", objects={"ENG-R": [OBJ], "CARGO": [OBJ]}, after_clean=("ENG-R", "CARGO"))   # HOLD + REMOVE
    make_scene("pd-stuck", objects={"ENG-R": [OBJ]})                    # no `after` frame: a new photo shows it again
    make_scene("pd-glare", declared_unusable={"ENG-L": "glare"}, after_clean=("ENG-L",))
    make_scene("pa-clean", kind="pre_arrival")
    make_scene("pd-outside", objects={"WIDE": [OUTSIDE]})               # debris outside the gate safety envelope
    make_scene("pd-two-glare", declared_unusable={"ENG-L": "glare", "AFT": "blur"})   # no `after`: stays unusable


@pytest.fixture
def rig(scenes, fake_llm):
    r = Rig(fake_llm)
    yield r
    r.wf.shutdown()
