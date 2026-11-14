"""Work that isn't debris removal: unusable views and debris outside the stand (issue #5). No API calls."""
import pytest

from fodgate import report as R
from fodgate.dispatch.dispatcher import outside_recipient
from fodgate.workflow import WorkflowError
from tests.dispatch_rig import FakeModel, Rig, rig, scenes, tool_use  # noqa: F401


def refused(r, pid, line) -> WorkflowError:
    with pytest.raises(WorkflowError) as e:
        r.cmd(pid, line)
    return e.value


# ---------------------------------------------------------------------- an unusable view
def test_one_task_per_unusable_angle_for_an_on_shift_ramp_lead_naming_gate_angle_and_reason(rig):
    rep = rig.inspect("pd-two-glare")
    assert rig.latest()["verdict"] == "INCOMPLETE"
    eye = [t for t in rig.tasks() if t["type"] == "check_by_eye"]
    assert sorted(t["angle"] for t in eye) == ["AFT", "ENG-L"] and len(rig.tasks()) == 2      # exactly one each, no sign-off
    assert {t["assignee_id"] for t in eye} == {"okafor"} and {t["required_role"] for t in eye} == {"ramp_lead"}
    for t in eye:
        msg = next(m for m in rig.inbox("okafor") if f"Task {t['task_id']}:" in m)
        reason = {"ENG-L": "glare", "AFT": "blur"}[t["angle"]]
        assert f"T5 {t['angle']} is unusable ({reason})" in msg and "INCOMPLETE" in msg
    rig.d.settle()                                              # nothing is created twice
    assert len(rig.tasks()) == 2
    del rep


def test_with_no_ramp_lead_on_shift_the_supervisor_is_told(rig):
    for lead in ("okafor", "reyes"):
        rig.d.roster.set_shift(lead, "off")
    rig.inspect("pd-glare")
    assert rig.tasks() == []                                    # never given to a Ramp Agent
    assert any("check by eye ENG-L" in m and "Ramp Lead is required" in m for m in rig.inbox("dana"))


def test_a_ramp_agent_cannot_record_checked_by_eye_and_is_never_offered_it(scenes, fake_llm):
    def tries(kw):                                              # a model that tries to hand the check to Kim
        return [tool_use(1, "assign_task", type="check_by_eye", gate="T5", inspection_id="T5", finding_id=None,
                         angle="ENG-L", assignee_id="kim", instruction="Check ENG-L by eye"),
                tool_use(2, "propose_confirmation", to_id="kim", inspection_id="T5", finding_id="ENG-L",
                         outcome="removed", false_alarm_reason=None)]
    model = FakeModel()
    r = Rig(fake_llm, mode="on", create=model)
    r.inspect("pd-glare")
    assert refused(r, "kim", "/eye T5 ENG-L").code == "role_not_allowed"
    model.turns = [tries, "Could not."]
    r.say("kim", "I looked at the left engine, it's fine, mark it checked")
    assert [x["is_error"] for x in model.results[-1]] == [True, True]
    assert "can only go to a Ramp Lead" in model.results[-1][0]["content"]
    assert r.board.pending_proposals("kim") == [] and r.confirmations() == []
    assert r.latest()["verdict"] == "INCOMPLETE" and R.unresolved_unusable_angles(r.latest()) == ["ENG-L"]
    r.wf.shutdown()


def test_a_usable_re_inspection_closes_the_task_without_a_check_by_eye(rig):
    rig.inspect("pd-glare")                                     # the scene has a clean `after` frame for ENG-L
    task = rig.task("check_by_eye")
    assert refused(rig, "okafor", "/signoff T5").code == "unusable_angles"            # sign-off is blocked
    out = rig.cmd("okafor", "/reinspect T5 ENG-L")
    assert "nothing new seen" in out[0]
    closed = rig.board.task(task["task_id"])
    assert closed["status"] == "closed" and "re-inspected" in closed["close_reason"]
    assert not any(c["action"] == "checked_by_eye" for c in rig.confirmations())
    assert rig.latest()["verdict"] == "ALL_CLEAR"
    assert rig.task("sign_off")["assignee_id"] == "okafor"      # and only now is sign-off asked for
    rig.cmd("okafor", "/signoff T5")
    assert rig.latest()["status"] == "confirmed"


def test_still_unusable_then_checked_by_eye_by_a_ramp_lead_and_sign_off_waits_for_every_angle(rig):
    rig.inspect("pd-two-glare")                                 # no `after` frames: a new photo is unusable again
    out = rig.cmd("okafor", "/reinspect T5 ENG-L")
    assert "unusable (glare)" in out[0]
    assert sorted(t["angle"] for t in rig.tasks() if t["type"] == "check_by_eye") == ["AFT", "ENG-L"]
    assert refused(rig, "okafor", "/signoff T5").code == "unusable_angles"
    rig.cmd("okafor", "/eye T5 ENG-L")
    assert refused(rig, "okafor", "/signoff T5").code == "unusable_angles"            # AFT is still unchecked
    assert [t["angle"] for t in rig.tasks() if t["type"] == "check_by_eye"] == ["AFT"]
    out = rig.cmd("okafor", "/eye T5 AFT")
    assert "The Verdict stays INCOMPLETE" in out[0]
    c = [c for c in rig.confirmations() if c["action"] == "checked_by_eye"]
    assert [(x["name"], x["role"], x["data"]["angle"]) for x in c] == [("Okafor", "ramp_lead", "ENG-L"), ("Okafor", "ramp_lead", "AFT")]
    assert rig.latest()["verdict"] == "INCOMPLETE"              # cleared by a person, not the camera
    entry = next(a for a in rig.latest()["angles"] if a["angle"] == "AFT")
    assert entry["status"] != "usable" and entry["checked_by_eye"]["by"]["name"] == "Okafor"
    rig.cmd("okafor", "/signoff T5")
    assert rig.latest()["status"] == "confirmed"


def test_an_unusable_view_near_pushback_escalates_on_the_ladder(rig):
    rig.inspect("pd-glare")                                     # scheduled pushback at t=600
    task = rig.task("check_by_eye")
    kinds = {t["kind"] for t in rig.d.timers.pending() if t["task_id"] == task["task_id"]}
    assert kinds == {"no_report_ask", "no_report_offer", "unusable_pushback"}
    rig.advance(61)
    assert any(f"Any update on {task['task_id']}" in m for m in rig.inbox("okafor"))
    rig.advance(60)
    assert any("has no Report from Okafor" in m for m in rig.inbox("dana") + rig.inbox("reyes"))
    rig.advance(600 - 2 * 60 - 121 + 1)                          # under two minutes to pushback
    assert rig.task("check_by_eye")["escalation_level"] == 2
    assert any("Escalation level 2" in m and "still unusable" in m for m in rig.inbox("dana"))
    assert any("Escalation level 2" in m for m in rig.inbox("reyes"))
    assert rig.latest()["verdict"] == "INCOMPLETE" and rig.confirmations() == []       # escalation only tells people


# ---------------------------------------------------------------------- debris outside the stand
def test_an_outside_finding_never_gets_a_remove_task_and_the_task_carries_the_drafted_report(rig):
    rig.inspect("pd-outside")
    f = rig.finding("F1")
    assert f["zone_tier"] == "outside_boundary" and f["rule_id"] == "FOD-R10"
    (task,) = rig.tasks()
    assert task["type"] == "report_outside_boundary" and task["severity"] == f["severity"]
    msg = next(m for m in rig.inbox(task["assignee_id"]) if f"Task {task['task_id']}:" in m)
    assert "Do not remove it" in msg and "/reported F1 ramp1" in msg
    draft = msg.split("check it first):\n\n", 1)[1]
    assert draft.startswith("To: Ramp 1 control")              # the recipient
    assert "Gate T5" in draft                                    # the Gate
    assert f"Location: {f['location_text']}" in draft           # the location in words
    assert f["description"] in draft                             # what the item appears to be
    assert f"Seen: {rig.latest()['captured_at']}" in draft      # the time
    assert "A person must review it" in draft
    with pytest.raises(Exception) as e:                          # and code refuses a remove Task for it, whoever asks
        rig.d.assign(type="remove", gate="T5", finding_label="F1", angle=None, assignee_id="kim", instruction=None,
                     created_by="agent")
    assert "reported, not removed" in str(e.value)
    assert rig.d.model_calls == 0                                # the draft is a fixed template: no model


def test_routing_follows_the_rule_set_taxilane_to_ramp_1_movement_area_to_airport_operations():
    assert outside_recipient({"location_text": "on the shared taxilane behind the stand"}) == "ramp_1_control"
    assert outside_recipient({"location_text": "beyond the zipper marking, on the movement area"}) == "airport_operations"
    assert outside_recipient({"location_text": "on taxiway A near the stand"}) == "airport_operations"
    assert outside_recipient({"location_text": "somewhere on WIDE"}) == "ramp_1_control"        # unclear: Ramp 1 control
    assert outside_recipient({}) == "ramp_1_control"


def test_reported_is_recorded_only_by_a_person_and_keeps_who_was_told(rig):
    rig.inspect("pd-outside")
    (task,) = rig.tasks()
    who = task["assignee_id"]
    out = rig.cmd(who, f"/done {task['task_id']} called it in")  # a Report alone records nothing
    assert "A Report does not record anything" in out[0] and rig.confirmations() == [] and R.is_open(rig.finding("F1"))
    assert refused(rig, who, "/reported F1 the-tower").code == "invalid_command"
    assert refused(rig, "dana", "/reported F1 ramp1").code == "role_not_allowed"
    assert rig.confirmations() == []
    out = rig.cmd(who, "/reported F1 airport-ops")
    assert "reported to Airport Operations" in out[0]
    (c,) = rig.confirmations()
    assert c["action"] == "acknowledged" and c["data"]["reported_to"] == "airport_operations"
    assert c["data"]["reported_to_name"] == "Airport Operations" and c["data"]["person_id"] == who
    assert c["data"]["via"] == "command"
    assert not R.is_open(rig.finding("F1"))                     # closed only now
    assert rig.board.task(task["task_id"])["status"] == "closed"
    entry = next(e for e in rig.board.activity() if e["event"] == "outside_reported")
    assert entry["data"]["reported_to"] == "airport_operations" and entry["actor"] == who and entry["gate"] == "T5"


def test_reported_with_no_recipient_uses_the_one_the_draft_was_addressed_to(rig):
    rig.inspect("pd-outside")
    (task,) = rig.tasks()
    rig.cmd(task["assignee_id"], "/reported F1")
    assert rig.confirmations()[0]["data"]["reported_to"] == "ramp_1_control"


def test_reported_is_refused_for_a_finding_inside_the_envelope(rig):
    rig.inspect()
    assert refused(rig, "kim", "/reported F2 ramp1").code == "invalid_command"


def test_both_flows_work_with_the_model_unavailable(scenes, fake_llm):
    def down(**kw):
        raise RuntimeError("model down")
    r = Rig(fake_llm, mode="on", create=down)
    r.inspect("pd-glare")
    assert r.task("check_by_eye")["created_by"] == "code" and "/reinspect T5 ENG-L" in r.inbox("okafor")[0]
    r.wf.shutdown()
    r = Rig(fake_llm, mode="on", create=down)
    r.store.reset(); r.d.step()
    r.inspect("pd-outside")
    (task,) = r.tasks()
    assert task["created_by"] == "code"
    assert "To: Ramp 1 control" in next(m for m in r.inbox(task["assignee_id"]) if "Task K-" in m)
    r.cmd(task["assignee_id"], "/reported F1 ramp1")
    assert r.tasks(turn_id="T5-DL1776") == [] or r.task("sign_off")
    r.wf.shutdown()
