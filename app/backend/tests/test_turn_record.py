"""GET /api/turns/{turn_id}/record: every Inspection, Task, Report and Confirmation of one Turn in time order
(app/CONTRACT.md, "Turn record"). Read-only, and it never calls a model. No test calls the Claude API."""
import json

import pytest
from fastapi.testclient import TestClient

from fodgate import turn_record
from fodgate.api import create_app
from fodgate.store import Store
from fodgate.workflow import WorkflowError
from tests.dispatch_rig import ROSTER, TURN, FakeModel, Rig, rig, scenes, tool_use  # noqa: F401

ENTRY_KEYS = {"seq", "at", "t", "kind", "event", "person", "text", "refs", "data"}


def walk(rig):
    """A HOLD taken from its Inspection to sign-off: escalated once, acknowledged, a Report on the REMOVE Task,
    the Confirmations, a clean new photo and the sign-off."""
    rig.inspect()
    rig.advance(31)                                            # nobody acknowledged the HOLD: level 1
    rig.cmd("okafor", "/ack F1")
    remove = rig.task("remove")
    rig.cmd("kim", f"/done {remove['task_id']} bag tag binned")  # a Report: what Kim said
    (prop,) = rig.board.pending_proposals("kim")
    rig.cmd("kim", f"y {prop['proposal_id']}")                 # a Confirmation: what was recorded
    rig.cmd("okafor", "/removed F1")
    rig.cmd("okafor", "/signoff T5")
    return turn_record.build(rig.store, TURN["turn_id"])


def brief(rec):
    return [(e["kind"], e["event"], (e["person"] or {}).get("person_id")) for e in rec["entries"]]


def test_a_hold_from_inspection_to_signoff_in_time_order(rig):
    rec = walk(rig)
    assert set(rec) == {"turn_id", "gate", "flight", "generated_at", "cost", "entries"}
    assert (rec["turn_id"], rec["gate"], rec["flight"]) == (TURN["turn_id"], "T5", "DL1776")
    entries = rec["entries"]
    assert all(set(e) == ENTRY_KEYS for e in entries)
    assert [e["seq"] for e in entries] == list(range(len(entries)))
    assert [e["at"] for e in entries] == sorted(e["at"] for e in entries) and entries[0]["at"].endswith("Z")
    assert {e["kind"] for e in entries} == {"inspection", "task", "report", "confirmation"}
    assert brief(rec) == [
        ("inspection", "started", None),
        ("inspection", "completed", None),
        ("task", "assigned", "okafor"),                        # K-1 acknowledge the HOLD
        ("task", "assigned", "kim"),                           # K-2 remove the REMOVE Finding
        ("task", "escalated", "okafor"),
        ("confirmation", "acknowledged", "okafor"),
        ("report", "done", "kim"),
        ("confirmation", "removed", "kim"),
        ("task", "closed", "kim"),
        ("inspection", "reinspected", "okafor"),               # "removed" on a HOLD takes a new photo first
        ("inspection", "completed", None),
        ("confirmation", "removed", "okafor"),                 # recorded before the Task it closed
        ("task", "closed", "okafor"),
        ("task", "assigned", "okafor"),                        # K-3 sign off
        ("confirmation", "signoff", "okafor"),
        ("task", "closed", "okafor"),
    ]
    roles = {e["person"]["person_id"]: e["person"]["role"] for e in entries if e["person"]}
    assert roles == {"okafor": "ramp_lead", "kim": "ramp_agent"}
    assert all(e["person"]["name"] for e in entries if e["person"])
    assert all(isinstance(e["text"], str) and e["text"] and "\n" not in e["text"] for e in entries)

    first, again = entries[1], entries[10]
    assert first["data"]["verdict"] == "FINDINGS" and first["data"]["est_cost_usd"] > 0
    assert again["refs"]["inspection_id"] != first["refs"]["inspection_id"]
    assert entries[9]["data"]["reason"] == "hold_removed" and entries[9]["data"]["angles"] == ["ENG-R"]
    esc = entries[4]
    assert esc["data"]["level"] == 1 and esc["data"]["by"] == "timer" and esc["refs"]["task_id"] == "K-1"
    hold_ack = entries[5]
    assert hold_ack["refs"]["finding_id"] and hold_ack["refs"]["angle"] == "ENG-R"
    assert hold_ack["data"]["finding_label"] == "F1" and hold_ack["data"]["via"] == "command"
    assert entries[13]["data"]["task_type"] == "sign_off"


def test_a_report_and_a_confirmation_stay_separate_kinds(rig):
    rec = walk(rig)
    (report,) = [e for e in rec["entries"] if e["kind"] == "report"]
    remove = rig.task("remove", active=False)
    assert report["event"] == "done" and report["refs"]["task_id"] == remove["task_id"]
    assert report["data"]["raw_text"] == "bag tag binned" and report["data"]["via"] == "command"
    assert '"bag tag binned"' in report["text"]
    assert report["person"] == {"person_id": "kim", "name": "Kim", "role": "ramp_agent"}
    confs = [e for e in rec["entries"] if e["kind"] == "confirmation"]
    assert [c["event"] for c in confs] == ["acknowledged", "removed", "removed", "signoff"]
    assert [c["data"]["confirmation_id"] for c in confs] == [c["id"] for c in rig.confirmations()]
    kims = next(c for c in confs if c["person"]["person_id"] == "kim")
    assert kims["data"]["via"] == "accepted_proposal" and kims["data"]["proposal_id"]
    assert kims["data"]["finding_label"] == "F2"
    assert kims["refs"]["task_id"] is None and "raw_text" in kims["data"]
    assert len(rig.store.query("SELECT * FROM task_reports")) == 1


def test_cost_is_the_inspections_plus_the_agent_wakes_tied_to_the_turn(scenes, fake_llm):
    def routing(kw):                                           # the agent gives the REMOVE Finding to Kim
        ctx = json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1])
        (work,) = ctx["work_needing_an_owner"]
        return [tool_use(1, "assign_task", type=work["type"], gate=ctx["gate"],
                         inspection_id=ctx["inspection"]["inspection_id"], finding_id=work["finding_id"], angle=None,
                         assignee_id="kim", instruction="Remove the bag tag by the belt loader at T5 CARGO")]
    r = Rig(fake_llm, mode="on", create=FakeModel(routing, "Assigned."))
    try:
        r.inspect()
        r.say("kim", "where is the tug?")                     # a wake for a typed message: no Turn of its own
        rec = turn_record.build(r.store, TURN["turn_id"])
        assigned = [e for e in rec["entries"] if e["kind"] == "task" and e["event"] == "assigned"]
        assert [(e["person"]["person_id"], e["data"]["by"]) for e in assigned] == [("okafor", "code"), ("kim", "agent")]
        insp = sum(json.loads(row["report"])["run_metadata"]["est_cost_usd"]
                   for row in r.store.query("SELECT report FROM inspections"))
        wakes = r.store.query("SELECT est_cost_usd FROM agent_wakes ORDER BY wake_id")
        assert len(wakes) == 2 and insp > 0
        cost = rec["cost"]
        assert cost["inspections_usd"] == pytest.approx(insp)
        assert cost["agent_usd"] == pytest.approx(wakes[0]["est_cost_usd"]) and cost["agent_usd"] > 0
        assert cost["total_usd"] == pytest.approx(cost["inspections_usd"] + cost["agent_usd"])
        assert "1 agent wake" in cost["note"]
    finally:
        r.wf.shutdown()


def test_confirmations_made_without_the_dispatcher_still_appear_in_order(scenes, fake_llm):
    r = Rig(fake_llm, mode="off")
    try:
        r.wf.begin_turn(TURN)
        rep = r.wf.start_inspection("T5", kind="pre_departure", scene_id="pd-hold", background=False)
        remove = next(f for f in rep["findings"] if f["severity"] == "REMOVE")
        r.wf.confirm_finding(rep["inspection_id"], remove["finding_id"], outcome="false_alarm", role="ramp_lead",
                             name="Okafor", false_alarm_reason="shadow")
        rec = turn_record.build(r.store, TURN["turn_id"])
        assert brief(rec) == [("inspection", "started", None), ("inspection", "completed", None),
                              ("confirmation", "false_alarm", "okafor")]       # the person_id from the Roster
        conf = rec["entries"][-1]
        assert conf["data"]["via"] == "dashboard" and conf["data"]["outcome_details"]["false_alarm_reason"] == "shadow"
        assert rec["cost"]["agent_usd"] == 0 and rec["cost"]["note"] is None
    finally:
        r.wf.shutdown()


def test_unknown_task_types_are_listed_by_name(rig):
    rig.inspect()
    rig.store.execute("UPDATE tasks SET type='marshal_tug' WHERE task_id='K-2'")        # a type added by a later ticket
    rec = turn_record.build(rig.store, TURN["turn_id"])
    task = next(e for e in rec["entries"] if e["refs"]["task_id"] == "K-2")
    assert task["data"]["task_type"] == "marshal_tug" and "marshal tug" in task["text"]


def test_report_events_use_the_command_names_and_keep_the_stored_kind(rig):
    rig.inspect()
    remove = rig.task("remove")
    rig.cmd("kim", f"/accept {remove['task_id']}")
    rig.cmd("kim", f"/cant {remove['task_id']} tug in the way")
    rec = turn_record.build(rig.store, TURN["turn_id"])
    reports = [(e["event"], e["data"]["report_kind"], e["data"]["raw_text"]) for e in rec["entries"] if e["kind"] == "report"]
    assert reports == [("accept", "accepted", None), ("cant", "blocked", "tug in the way")]


def test_a_board_task_names_its_finding_in_its_own_inspection(rig):
    rep = rig.inspect()
    remove = next(t for t in rig.d.view()["tasks"] if t["type"] == "remove")
    assert remove["finding_id"] == rig.task("remove")["finding_label"]                 # the short label, "F2"
    assert remove["inspection_id"] == rep["inspection_id"]
    finding = next(f for f in rep["findings"] if f["finding_id"] == remove["inspection_finding_id"])
    assert finding["severity"] == "REMOVE"              # the dashboard opens this Finding from the Task's link


# ---------------------------------------------------------------------- over HTTP
@pytest.fixture
def client(scenes, fake_llm):
    app = create_app(store=Store(), llm=fake_llm, start_player=False, agent_mode="code", roster=ROSTER)
    with TestClient(app) as c:
        c.d, c.wf = app.state.dispatcher, app.state.workflow
        c.wf.begin_turn(TURN)
        c.wf.start_inspection("T5", kind="pre_departure", scene_id="pd-hold", background=False)
        c.d.settle()
        yield c


def test_the_endpoint_is_read_only_and_never_calls_a_model(client, brain):
    tables = ("tasks", "task_reports", "confirmations", "events", "agent_log", "messages", "agent_wakes", "inspections")

    def count():
        return {t: client.d.store.query(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"] for t in tables}
    before, calls, wakes = count(), len(brain.calls), client.d.model_calls
    r = client.get(f"/api/turns/{TURN['turn_id']}/record")
    assert r.status_code == 200
    body = r.json()
    assert body["turn_id"] == TURN["turn_id"] and [e["seq"] for e in body["entries"]] == list(range(len(body["entries"])))
    assert {"inspection", "task"} <= {e["kind"] for e in body["entries"]}
    assert set(body["cost"]) == {"inspections_usd", "agent_usd", "total_usd", "note"}
    assert len(brain.calls) == calls and client.d.model_calls == wakes and count() == before
    assert client.post(f"/api/turns/{TURN['turn_id']}/record").status_code == 404      # nothing here writes


def test_an_unknown_turn_is_404(client):
    r = client.get("/api/turns/T5-NOPE/record")
    assert r.status_code == 404 and r.json() == {"error": "not_found", "message": "Turn T5-NOPE not found"}
    with pytest.raises(WorkflowError) as e:
        turn_record.build(client.d.store, "T5-NOPE")
    assert e.value.status == 404


def test_a_handover_appears_and_moves_the_holder(rig):
    rig.inspect()
    rig.cmd("okafor", "/handover reyes")
    rig.cmd("reyes", "y")                                      # the Handover log row has no turn_id
    rig.advance(31)                                            # the HOLD is still not acknowledged: level 1
    rec = turn_record.build(rig.store, TURN["turn_id"])
    hold = [e for e in rec["entries"] if e["kind"] == "task" and e["refs"]["task_id"] == "K-1"]
    moved = next(e for e in hold if e["event"] == "handover")
    assert moved["data"]["log_event"] == "handover" and (moved["data"]["from"], moved["data"]["to"]) == ("okafor", "reyes")
    assert moved["person"]["person_id"] == "reyes" and "Handover" in moved["text"]
    later = hold[hold.index(moved) + 1:]
    assert later and all(e["person"]["person_id"] == "reyes" for e in later)


def test_an_unknown_task_event_appears_by_name(rig):
    rig.inspect()
    task = rig.board.task("K-2")
    rig.board.log("code", "K-2 handed to Patel at the stand.", event="task_handed_over", task=task,
                  actor="kim", data={"task_id": "K-2", "from": "kim", "to": "patel"})   # added by a later ticket
    rig.board.log("code", "K-2 looked at.", event="task_viewed", task=task, data={"task_id": "K-2"})
    rig.board.log("code", "Not about a Task.", event="weather_note", task=task, data={"task_id": "K-2"})
    rec = turn_record.build(rig.store, TURN["turn_id"])
    events = [(e["event"], (e["person"] or {}).get("person_id")) for e in rec["entries"]
              if e["kind"] == "task" and e["refs"]["task_id"] == "K-2"]
    assert ("handed_over", "patel") in events and ("viewed", "patel") in events
    assert not any(e["event"] == "weather_note" for e in rec["entries"])
    moved = next(e for e in rec["entries"] if e["event"] == "handed_over")
    assert moved["data"]["by"] == "kim" and "handed to Patel" in moved["text"]
