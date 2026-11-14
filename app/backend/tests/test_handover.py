"""Shift Handover, break and return (issue #3). Code only; where the model is used it is a scripted stand-in."""
import json

import pytest

from fodgate.dispatch.agent import handover_brief
from fodgate.workflow import WorkflowError
from tests.dispatch_rig import FakeModel, Rig, rig, scenes, tool_use  # noqa: F401


def refused(r, pid, line) -> WorkflowError:
    with pytest.raises(WorkflowError) as e:
        r.cmd(pid, line)
    return e.value


def test_handover_to_someone_off_shift_or_with_the_wrong_role_is_refused_and_names_the_problem(rig):
    rig.inspect()                                              # okafor: ack_hold K-1; kim: remove K-2
    hold = rig.task("ack_hold")
    err = refused(rig, "okafor", "/handover kim")              # a HOLD acknowledgement cannot go to a Ramp Agent
    assert err.code == "role_not_allowed" and hold["task_id"] in err.message and "Ramp Lead is required" in err.message
    assert "Kim is a Ramp Agent" in err.message
    rig.d.roster.set_shift("reyes", "off")
    err = refused(rig, "okafor", "/handover reyes")
    assert err.code == "refused" and "Reyes is not on shift (off)" in err.message
    assert rig.task("ack_hold")["assignee_id"] == "okafor" and rig.board.pending_proposals("reyes") == []
    assert refused(rig, "okafor", "/handover nobody").code == "invalid_command"
    assert refused(rig, "dana", "/handover reyes").code == "role_not_allowed"          # a supervisor holds no Tasks
    assert refused(rig, "patel", "/handover kim").code == "nothing_to_hand_over"


def test_nothing_moves_until_the_other_person_accepts_and_a_decline_is_told(rig):
    rig.inspect()
    out = rig.cmd("okafor", "/handover reyes")
    assert "stay yours until they accept" in out[0]
    assert rig.task("ack_hold")["assignee_id"] == "okafor" and rig.person("okafor")["shift"] == "on"
    (prop,) = rig.board.pending_proposals("reyes")
    assert prop["action"]["kind"] == "handover" and prop["created_by"] == "okafor"
    out = rig.cmd("reyes", "n")
    assert "no Task moved" in out[0]
    assert rig.task("ack_hold")["assignee_id"] == "okafor" and rig.person("okafor")["shift"] == "on"
    assert "Reyes declined your Handover" in rig.inbox("okafor")[-1] and "stay with you" in rig.inbox("okafor")[-1]
    events = [e["event"] for e in rig.board.activity()]
    assert "handover_requested" in events and "handover_declined" in events and "handover" not in events
    rig.advance(300)                                           # the timeout timer was cancelled by the answer
    assert sum("your Handover" in m for m in rig.inbox("okafor")) == 1


def test_no_answer_in_time_leaves_the_tasks_and_tells_the_first_person(rig):
    rig.inspect()
    rig.cmd("okafor", "/handover reyes")
    rig.advance(rig.d.ladder["proposal_expires_s"] + 1)
    assert rig.task("ack_hold")["assignee_id"] == "okafor" and rig.person("okafor")["shift"] == "on"
    assert "Reyes did not answer your Handover" in rig.inbox("okafor")[-1]
    assert rig.board.pending_proposals("reyes") == []
    assert refused(rig, "reyes", "y").code == "nothing_to_answer"
    assert [e["event"] for e in rig.board.activity()].count("handover_expired") == 1


def test_acceptance_moves_every_open_task_ends_the_shift_and_keeps_the_running_timers(rig):
    rig.inspect()
    hold = rig.task("ack_hold")
    rig.advance(10)
    before = {(t["kind"], t["fire_t"]) for t in rig.d.timers.pending() if t["task_id"] == hold["task_id"]}
    assert {k for k, _ in before} == {"hold_unack_1", "hold_unack_2", "hold_pushback"}
    rig.cmd("okafor", "/handover reyes")
    out = rig.cmd("reyes", "y")
    assert "Handover accepted" in out[0] and hold["task_id"] in out[0]
    assert rig.board.tasks(assignee_id="okafor") == []
    assert rig.task("ack_hold")["assignee_id"] == "reyes"
    assert rig.person("okafor")["shift"] == "off" and rig.person("reyes")["shift"] == "on"
    shift = rig.store.query("SELECT * FROM shifts WHERE person_id='okafor' ORDER BY shift_id DESC LIMIT 1")[0]
    assert shift["status"] == "off" and shift["handed_to"] == "reyes"
    assert "Your Shift has ended" in rig.inbox("okafor")[-1]
    # timers were not restarted: the same rows, the same times, now against the new holder
    after = {(t["kind"], t["fire_t"]) for t in rig.d.timers.pending() if t["task_id"] == hold["task_id"]}
    assert after == before
    rig.advance(21)                                            # 31 s after the HOLD alert: level 1 goes to Reyes
    assert rig.task("ack_hold")["escalation_level"] == 1
    assert any(m.startswith("Second call: HOLD F1") for m in rig.inbox("reyes"))
    assert not any(m.startswith("Second call") for m in rig.inbox("okafor"))
    # the Handover and each Task move are in the log with who, to whom and when
    log = rig.board.activity()
    move = next(e for e in log if e["event"] == "task_reassigned")
    assert move["data"] == {"task_id": hold["task_id"], "from": "okafor", "to": "reyes", "reason": "Handover"} and move["at"]
    done = next(e for e in log if e["event"] == "handover")
    assert done["data"]["from"] == "okafor" and done["data"]["to"] == "reyes" and done["data"]["tasks"] == [hold["task_id"]]
    assert done["data"]["shift_ended"] is True and done["actor"] == "reyes"
    # a Handover records no Confirmation
    assert rig.confirmations() == [] and rig.finding("F1")["status"] == "open"
    # new work no longer goes to the person who left; they can come back
    assert "okafor" not in [p["person_id"] for p in rig.d.eligible("ack_hold", "T5")]
    rig.cmd("okafor", "/back")
    assert rig.person("okafor")["shift"] == "on"


def test_the_brief_lists_exactly_the_open_tasks_in_the_database_with_reports_and_timers(rig):
    rig.inspect()
    rig.cmd("okafor", "/reassign " + rig.task("remove")["task_id"] + " okafor")       # the lead now holds two Tasks
    rig.cmd("okafor", "/accept " + rig.task("remove")["task_id"] + " on my way")
    rig.cmd("okafor", "/ack F1")
    rig.cmd("okafor", "/removed F1")                                # clean new photo: the HOLD Task closes
    closed = [t["task_id"] for t in rig.board.tasks(active=False) if t["status"] != "assigned" and t["closed_at"]]
    assert closed
    brief = handover_brief(rig.d, "okafor", "reyes")
    open_ids = [r["task_id"] for r in rig.store.query(
        "SELECT task_id FROM tasks WHERE assignee_id='okafor' AND status IN ('assigned','accepted','reported') ORDER BY seq")]
    listed = [line.split()[1] for line in brief.splitlines() if line.startswith("- ")]
    assert listed == open_ids and open_ids
    assert not any(c in brief for c in closed)
    assert f"{len(open_ids)} open Task" in brief.splitlines()[0]
    line = next(x for x in brief.splitlines() if x.startswith(f"- {open_ids[0]} "))
    assert "T5" in line and "F2" in line and "REMOVE" in line and "accepted" in line
    assert 'Report: accepted by Okafor ("on my way")' in line and "Timers: asked for an update in" in line
    assert "Nothing in this brief is a Confirmation" in brief
    rig.cmd("okafor", "/handover reyes")
    assert brief.splitlines()[1] in rig.inbox("reyes")[-1] and "Take these over?" in rig.inbox("reyes")[-1]


def test_break_rule_and_no_new_tasks_while_on_a_break(rig):
    rig.inspect()
    err = refused(rig, "okafor", "/break")
    assert err.code == "open_hold" and "/handover" in err.message
    assert rig.person("okafor")["shift"] == "on"
    out = rig.cmd("kim", "/break")                             # no HOLD Task: allowed, and she keeps her Task
    assert "on a break" in out[0] and "still hold 1 open Task" in out[0]
    assert rig.person("kim")["shift"] == "break"
    assert "kim" not in [p["person_id"] for p in rig.d.eligible("remove", "T5")]
    turn = {"turn_id": "T8-DL0458", "gate": "T8", "flight": "DL0458", "aircraft_type": "A220-300",
            "events": [{"t": 900, "type": "scheduled_pushback"}]}
    rig.inspect("pd-hold", turn=turn)
    new_remove = next(t for t in rig.tasks(turn_id="T8-DL0458") if t["type"] == "remove")
    assert new_remove["assignee_id"] != "kim"
    rig.cmd("kim", "/back")
    assert rig.person("kim")["shift"] == "on"
    assert [e["data"]["shift"] for e in rig.board.activity() if e["event"] == "shift_changed"] == ["break", "on"]


def test_the_only_ramp_lead_trying_to_leave_with_a_hold_open_reaches_the_supervisor(rig):
    rig.d.roster.set_shift("reyes", "off")
    rig.inspect()
    n = len(rig.inbox("dana"))
    err = refused(rig, "okafor", "/break")
    assert "supervisor has been told" in err.message
    assert "only Ramp Lead on shift" in rig.inbox("dana")[-1] and "tried to go on a break" in rig.inbox("dana")[-1]
    err = refused(rig, "okafor", "/handover kim")              # refused Handover: the same notice
    assert "supervisor has been told" in err.message
    assert "tried to hand over to Kim" in rig.inbox("dana")[-1] and len(rig.inbox("dana")) == n + 2
    assert [e["event"] for e in rig.board.activity()].count("sole_lead_leaving") == 2
    # with a second Ramp Lead on shift the supervisor is not disturbed
    rig.d.roster.set_shift("reyes", "on")
    refused(rig, "okafor", "/break")
    assert len(rig.inbox("dana")) == n + 2


def test_handover_works_without_the_model_and_the_model_only_adds_a_summary(scenes, fake_llm):
    r = Rig(fake_llm, mode="code")                             # no model at all
    r.inspect()
    r.cmd("okafor", "/handover reyes")
    brief = r.inbox("reyes")[-1]
    assert brief.startswith("Handover from Okafor (Ramp Lead) to Reyes (Ramp Lead): 1 open Task.")
    assert "- K-1 acknowledge HOLD at T5 ENG-R F1 (HOLD)" in brief
    r.cmd("reyes", "y")
    assert r.task("ack_hold")["assignee_id"] == "reyes"
    r.wf.shutdown()

    def summary(kw):
        ctx = json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1])
        assert ctx["trigger"] == "handover_requested" and ctx["to"]["person_id"] == "reyes"
        assert "- K-1 acknowledge HOLD" in ctx["brief_already_sent_by_code"]
        return [tool_use(1, "send_message", to_id="reyes", task_id=None,
                         text="One HOLD at T5 ENG-R (F1), not yet acknowledged. The second call is due soon.")]
    model = FakeModel(lambda kw: [tool_use(1, "assign_task", type="remove", gate="T5", inspection_id="T5",
                                           finding_id="F2", angle=None, assignee_id="kim", instruction="Remove it")],
                      "Assigned.", summary, "Sent the summary.")
    r = Rig(fake_llm, mode="on", create=model)
    r.store.reset()
    r.d.roster.set_shift("okafor", "on")                        # the store file is shared: he left in the run above
    r.d.step()
    r.inspect()
    r.cmd("okafor", "/handover reyes")
    texts = [m["text"] for m in r.board.thread("reyes") if m["to"] == "reyes"]
    code_brief = next(t for t in texts if "Take these over?" in t)
    assert "- K-1 acknowledge HOLD" in code_brief                       # the list is always code's
    assert any(t.startswith("One HOLD at T5 ENG-R") for t in texts)
    assert r.task("ack_hold")["assignee_id"] == "okafor"        # the model moved nothing
    r.cmd("reyes", "y")
    assert r.task("ack_hold")["assignee_id"] == "reyes" and r.confirmations() == []
    r.wf.shutdown()

    def boom(**kw):
        raise RuntimeError("model down")
    r = Rig(fake_llm, mode="on", create=boom)                   # model fails mid-handover: the brief still arrives
    r.store.reset()
    r.d.roster.set_shift("okafor", "on")
    r.d.step()
    r.inspect()
    r.cmd("okafor", "/handover reyes")
    assert "Take these over?" in r.inbox("reyes")[-1]
    assert not any("cannot read free text" in m for m in r.inbox("okafor") + r.inbox("reyes"))
    r.cmd("reyes", "y")
    assert r.task("ack_hold")["assignee_id"] == "reyes"
    r.wf.shutdown()
