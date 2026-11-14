"""When the report isn't "done": not found, and still there (issue #4). No API calls."""
import json

import pytest

from fodgate.workflow import WorkflowError
from tests.dispatch_rig import FakeModel, Rig, rig, scenes, tool_use  # noqa: F401


def log_not_found(task_id):
    """A model that only classifies the message: it logs one not-found Report and stops."""
    def turn(kw):
        mid = json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1])["messages"][0]["message_id"]
        return [tool_use(1, "log_report", task_id=task_id, kind="not_found", source_message_id=mid)]
    return turn


def remove_task(r):
    return next(t for t in r.tasks() if t["type"] == "remove" and t["finding_label"] == "F2")


# ---------------------------------------------------------------------- not found: REMOVE / ADVISORY
def test_button_and_plain_text_not_found_end_the_same_way_for_a_remove_finding(scenes, fake_llm):
    outcomes = []
    for via in ("button", "text"):
        model = FakeModel()
        r = Rig(fake_llm, mode="on" if via == "text" else "code", create=model)
        r.store.reset(); r.d.step()
        r.inspect()
        task = remove_task(r)
        assert task["assignee_id"] == "kim" and task["severity"] == "REMOVE"
        if via == "button":
            r.cmd("kim", f"/cant-find {task['task_id']}")
        else:
            model.turns = [log_not_found(task["task_id"]), "Logged."]
            r.say("kim", "cant find it anywhere, looked all round the belt loader")
        (rep,) = r.board.reports(task["task_id"])
        (prop,) = r.board.pending_proposals("kim")
        outcomes.append((rep["kind"], remove_task(r)["status"], prop["action"]["kind"], prop["action"]["outcome"],
                         prop["created_by"], r.finding("F2")["status"], len(r.confirmations())))
        assert rep["via"] == ("command" if via == "button" else "free_text")
        assert any("not found on walk, confirmed by you?" in m for m in r.inbox("kim")[-2:])
        r.wf.shutdown()
    assert outcomes[0] == outcomes[1] == ("not_found", "reported", "confirm", "not_found_on_walk", "code", "open", 0)


def test_not_found_on_walk_is_recorded_only_when_the_reporter_accepts(rig):
    rig.inspect()
    task = remove_task(rig)
    rig.cmd("kim", f"/cant-find {task['task_id']} nothing by the loader")
    assert rig.confirmations() == [] and rig.finding("F2")["status"] == "open"
    out = rig.cmd("kim", "n")                                   # declining leaves the Finding open and the Task with her
    assert "nothing was recorded" in out[0]
    assert rig.confirmations() == [] and rig.finding("F2")["status"] == "open"
    assert remove_task(rig)["assignee_id"] == "kim" and remove_task(rig)["status"] == "reported"
    rig.cmd("kim", f"/cant-find {task['task_id']}")             # asked again, and this time she accepts
    rig.cmd("kim", "y")
    (c,) = rig.confirmations()
    assert (c["action"], c["name"], c["role"]) == ("not_found_on_walk", "Kim", "ramp_agent")
    assert c["data"]["via"] == "accepted_proposal" and c["data"]["person_id"] == "kim"
    assert rig.finding("F2")["status"] == "confirmed"
    assert rig.board.task(task["task_id"])["status"] == "closed"


def test_cant_find_is_only_for_the_assignee_and_only_for_removal_tasks(rig):
    rig.inspect()
    with pytest.raises(WorkflowError) as e:
        rig.cmd("patel", f"/cant-find {remove_task(rig)['task_id']}")
    assert e.value.code == "not_your_task"
    with pytest.raises(WorkflowError) as e:
        rig.cmd("okafor", f"/cant-find {rig.task('ack_hold')['task_id']}")
    assert e.value.code == "invalid_command"
    assert rig.board.reports(rig.task("ack_hold")["task_id"]) == []


# ---------------------------------------------------------------------- not found: HOLD
@pytest.mark.parametrize("via", ["button", "text"])
def test_not_found_on_a_hold_records_nothing_and_asks_the_ramp_lead_about_a_new_photo(scenes, fake_llm, via):
    model = FakeModel()
    r = Rig(fake_llm, mode="on" if via == "text" else "code", create=model)
    r.inspect("pd-stuck")
    r.cmd("okafor", "/ack F1")
    r.cmd("okafor", "/send kim F1 go and get it")
    walk = next(t for t in r.tasks() if t["type"] == "remove" and t["finding_label"] == "F1")
    before = len(r.confirmations())
    if via == "button":
        out = r.cmd("kim", f"/cant-find {walk['task_id']}")
        assert "a Ramp Lead records HOLDs" in out[0]
    else:
        model.turns = [log_not_found(walk["task_id"]), "Logged."]
        r.say("kim", "no sign of it by the engine")
        assert "a Ramp Lead records HOLDs" in r.inbox("kim")[-1]
    assert len(r.confirmations()) == before and r.finding("F1")["status"] == "acknowledged"   # nothing recorded
    assert r.board.pending_proposals("kim") == []                # never a proposal to the Ramp Agent
    (prop,) = r.board.pending_proposals("okafor")
    assert prop["action"] == prop["action"] | {"kind": "reinspect", "gate": "T5", "angle": "ENG-R"}
    assert prop["created_by"] == "code"
    lead = r.inbox("okafor")
    assert any("could not find the object for HOLD F1" in m and "The HOLD stays open" in m for m in lead)
    assert "Take a new photo of T5 ENG-R now" in lead[-1]
    # the agent (or code) never starts the re-inspection: there is still only the first Inspection
    assert len(r.store.reports_for_turn("T5-DL1776")) == 1
    r.cmd("okafor", "y")                                         # the Ramp Lead decides to look again
    reps = r.store.reports_for_turn("T5-DL1776")
    assert len(reps) == 2 and reps[-1]["kind"] == "on_demand"
    assert r.finding("F1")["status"] == "acknowledged" and R_open(r, "F1")     # a re-inspection closes nothing
    r.cmd("okafor", "/false-alarm F1 shadow")                    # false alarm stays the Ramp Lead's to record
    assert r.confirmations()[-1]["action"] == "false_alarm" and r.confirmations()[-1]["name"] == "Okafor"
    r.wf.shutdown()


def R_open(r, label) -> bool:
    from fodgate import report as R
    return R.is_open(r.finding(label))


def test_a_ramp_lead_can_decline_the_new_photo_and_keep_the_hold_open(rig):
    rig.inspect("pd-stuck")
    rig.cmd("okafor", "/ack F1")
    rig.cmd("okafor", "/send kim F1")
    walk = next(t for t in rig.tasks() if t["type"] == "remove")
    rig.cmd("kim", f"/cant-find {walk['task_id']}")
    rig.cmd("okafor", "n")
    assert len(rig.store.reports_for_turn("T5-DL1776")) == 1 and R_open(rig, "F1")
    assert rig.task("ack_hold")["status"] == "accepted"


# ---------------------------------------------------------------------- still there
def test_still_there_keeps_the_hold_open_reopens_the_removal_and_escalates_twice(rig):
    rig.inspect("pd-stuck")
    rig.cmd("okafor", "/ack F1")
    rig.cmd("okafor", "/send kim F1 remove the bolt")
    walk = next(t for t in rig.tasks() if t["type"] == "remove")
    rig.cmd("kim", f"/done {walk['task_id']}")
    assert rig.board.task(walk["task_id"])["status"] == "reported"
    hold = rig.task("ack_hold")
    assert hold["escalation_level"] == 0
    sup, lead_n = len(rig.inbox("dana")), len(rig.inbox("okafor"))

    out = rig.cmd("okafor", "/removed F1")                       # the new photo still shows it
    assert "still shows the object" in out[0] and "nothing was recorded" in out[0]
    assert R_open(rig, "F1") and rig.finding("F1")["status"] == "acknowledged"           # the Finding is still open
    assert [c["action"] for c in rig.confirmations()] == ["acknowledged"]              # and no "removed" exists
    again = rig.board.task(walk["task_id"])
    assert again["status"] == "assigned" and again["assignee_id"] == "kim"             # the Task is open again
    assert f"{walk['task_id']} is open again" in rig.inbox("kim")[-1]
    assert rig.task("ack_hold")["escalation_level"] == 1                                # one level up
    assert any("Second call: HOLD F1" in m and "still shows the object" in m for m in rig.inbox("okafor")[lead_n:])
    assert any("Escalation level 1" in m for m in rig.inbox("dana")[sup:])              # that level's people were told
    esc = [e for e in rig.board.activity() if e["event"] == "task_escalated"][-1]
    assert esc["data"]["level"] == 1 and set(esc["data"]["notified"]) == {"okafor", "dana"}
    # the Ramp Lead is told plainly and offered a move to someone on shift who may take it
    text = " ".join(out)
    assert "Escalation level 1" in text and f"/reassign {walk['task_id']} <person>" in text
    offered = text.split("On shift and able:")[1]
    assert "Patel" in offered and "Reyes" in offered             # on shift, with a role that may take it
    assert "Kim" not in offered and "Okafor" not in offered      # not the current holder, not the Ramp Lead asking
    assert "Dana" not in offered                                 # a supervisor is never offered a Task
    assert "/removed F1 takes a new photo once it is gone" in " ".join(rig.inbox("okafor")[lead_n:])

    # reassignment goes only to an on-shift person with an allowed role, and the previous holder is told
    rig.d.roster.set_shift("patel", "off")
    with pytest.raises(WorkflowError) as e:
        rig.cmd("okafor", f"/reassign {walk['task_id']} patel")
    assert "not on shift" in e.value.message
    with pytest.raises(WorkflowError):
        rig.cmd("okafor", f"/reassign {walk['task_id']} dana")
    rig.d.roster.set_shift("patel", "on")
    rig.cmd("okafor", f"/reassign {walk['task_id']} patel")
    assert rig.board.task(walk["task_id"])["assignee_id"] == "patel"
    assert f"{walk['task_id']} has moved to Patel" in rig.inbox("kim")[-1]

    # a second "still there" raises the level again and reaches the supervisor
    sup = len(rig.inbox("dana"))
    rig.cmd("patel", f"/done {walk['task_id']}")
    out = rig.cmd("okafor", "/removed F1")
    assert rig.task("ack_hold")["escalation_level"] == 2 and R_open(rig, "F1")
    assert any("Escalation level 2" in m for m in rig.inbox("dana")[sup:])
    assert any("Escalation level 2" in m for m in rig.inbox("reyes"))                   # every Ramp Lead on shift
    assert rig.board.task(walk["task_id"])["status"] == "assigned"

    # a third time: already at the top, and the top level's people are still told (never silent)
    sup = len(rig.inbox("dana"))
    rig.cmd("okafor", "/removed F1")
    assert rig.task("ack_hold")["escalation_level"] == 2
    assert any("still shows the object" in m for m in rig.inbox("dana")[sup:])
    assert [c["action"] for c in rig.confirmations()] == ["acknowledged"]


def test_still_there_with_nobody_sent_offers_to_send_someone(rig):
    rig.inspect("pd-stuck")
    rig.cmd("okafor", "/ack F1")
    out = " ".join(rig.cmd("okafor", "/removed F1"))
    assert "Nobody is assigned to remove it" in out and "/send <person> F1" in out and "Kim" in out
    assert rig.task("ack_hold")["escalation_level"] == 1


def test_both_cases_work_with_no_model_and_fixed_wording(scenes, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from fodgate.llm import LLM
    from tests.conftest import Brain
    r = Rig(LLM(transport=Brain()), mode="code")
    r.inspect()
    task = remove_task(r)
    r.cmd("kim", f"/cant-find {task['task_id']}")
    r.cmd("kim", "y")
    assert r.confirmations()[-1]["action"] == "not_found_on_walk"
    r.cmd("okafor", "/ack F1")
    r.cmd("okafor", "/removed F1")                               # pd-hold has a clean after frame: it clears
    assert r.finding("F1")["status"] == "confirmed"
    assert r.d.model_calls == 0
    r.say("kim", "cant find the other one either")              # free text without a model: told to use the buttons
    assert "cannot read free text right now" in r.inbox("kim")[-1]
    r.wf.shutdown()
