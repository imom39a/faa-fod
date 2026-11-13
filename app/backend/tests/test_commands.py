"""Slash commands: parsed by code, run as the signed-in person, recorded with how they were made."""
import pytest
from fastapi.testclient import TestClient

from fodgate.api import create_app
from fodgate.dispatch import commands
from fodgate.store import Store
from fodgate.workflow import WorkflowError
from tests.dispatch_rig import ROSTER, TURN, rig, scenes  # noqa: F401


def code(excinfo):
    return excinfo.value.status, excinfo.value.code


def test_what_counts_as_a_command():
    for t in ("/ack F1", " /tasks", "y", "Y", "n", "yes", "no", "/y P-2", "y P-2"):
        assert commands.is_command(t), t
    for t in ("got the hammer", "yeah it's done", "no idea where it is", "send kim /ack F1", ""):
        assert not commands.is_command(t), t


def test_unknown_and_malformed_commands(rig):
    rig.inspect()
    for line, expected in (("/clear T5", "invalid_command"), ("/ack", "invalid_command"), ("/ack hammer", "invalid_command"),
                           ("/ack F99", "not_found"), ("/signoff T9", "invalid_command"), ("/done", "invalid_command"),
                           ("/done K-99", "not_found"), ("/false-alarm F2 bored", "invalid_command"),
                           ("/reinspect T5 TAIL", "invalid_command"), ("/eye T5 NOSE", "angle_usable")):
        with pytest.raises(WorkflowError) as e:
            rig.cmd("okafor", line)
        assert e.value.code == expected, line
    assert rig.confirmations() == []


def test_hold_two_steps_then_signoff_with_audit_of_how_each_was_made(rig):
    rig.inspect()
    with pytest.raises(WorkflowError) as e:
        rig.cmd("okafor", "/removed F1")
    assert code(e) == (409, "hold_needs_acknowledge")
    assert rig.cmd("okafor", "/ack F1") == ["Recorded: F1 acknowledged by Okafor (Ramp Lead)."]
    assert rig.cmd("kim", "/removed F2 fell off a bag cart") == ["Recorded: F2 removed, confirmed by Kim (Ramp Agent)."]
    with pytest.raises(WorkflowError) as e:
        rig.cmd("kim", "/signoff T5")
    assert code(e) == (409, "open_findings") and "F1" in e.value.message and "insp-" not in e.value.message
    out = rig.cmd("okafor", "/removed F1")
    assert out == ["New photo of T5 ENG-R is clean. Recorded: F1 removed, confirmed by Okafor (Ramp Lead)."]
    assert "Re-inspecting T5 ENG-R ..." in rig.inbox("okafor")
    assert rig.task("sign_off")["assignee_id"] == "okafor"
    assert rig.cmd("okafor", "/signoff T5") == ["Inspection signed off by Okafor (Ramp Lead). T5 confirmed clear."]
    rows = rig.confirmations()
    assert [(c["action"], c["name"]) for c in rows] == [("acknowledged", "Okafor"), ("removed", "Kim"),
                                                       ("removed", "Okafor"), ("signoff", "Okafor")]
    assert all(c["data"]["via"] == "command" for c in rows)
    assert rows[1]["data"]["raw_text"] == "/removed F2 fell off a bag cart" and rows[1]["data"]["possible_source"] == "fell off a bag cart"
    assert rows[2]["data"]["after_photo_ref"]                 # the HOLD was re-photographed before it counted
    closed = {t["type"]: t for t in rig.tasks(active=False)}
    assert {t["status"] for t in closed.values()} == {"closed"}
    assert closed["ack_hold"]["closed_by_confirmation_id"] == rows[2]["id"]
    assert rig.wf.try_depart(TURN["turn_id"]) is True


def test_false_alarm_not_found_all_removed_and_reinspect(rig):
    rig.inspect()
    assert "nothing new seen" in rig.cmd("kim", "/reinspect T5 NOSE")[0]       # any role; closes nothing
    assert len(rig.latest()["findings"]) == 2 and rig.confirmations() == []
    out = rig.cmd("kim", "/all-removed T5")
    assert out[0].startswith("Recorded: 1 REMOVE / ADVISORY Finding at T5 removed") and "1 HOLD stays open" in out[0]
    assert rig.finding("F1")["status"] == "open"
    rig.cmd("okafor", "/false-alarm F1 shadow")               # a HOLD false alarm needs no acknowledge and no new photo
    c = rig.confirmations()[-1]
    assert (c["action"], c["data"]["false_alarm_reason"], c["role"]) == ("false_alarm", "shadow", "ramp_lead")
    with pytest.raises(WorkflowError) as e:
        rig.cmd("okafor", "/not-found F1")
    assert code(e) == (409, "already_confirmed")


def test_task_commands_are_reports_and_only_for_the_assignee(rig):
    rig.inspect()
    task = rig.task("remove")
    tid = task["task_id"]
    assert tid in rig.cmd("kim", "/tasks")[0] and rig.cmd("patel", "/tasks") == ["No open Tasks."]
    assert len(rig.cmd("dana", "/tasks")) == 2                # the supervisor sees every open Task
    with pytest.raises(WorkflowError) as e:
        rig.cmd("patel", f"/done {tid}")
    assert code(e) == (403, "not_your_task")
    rig.cmd("kim", f"/accept {tid}")
    assert rig.board.task(tid)["status"] == "accepted"
    rig.cmd("kim", f"/cant {tid} belt loader is in the way")
    assert "Kim cannot do" in rig.inbox("okafor")[-1] and "belt loader is in the way" in rig.inbox("okafor")[-1]
    kinds = [(r["kind"], r["via"]) for r in rig.board.reports(tid)]
    assert kinds == [("accepted", "command"), ("blocked", "command")]
    assert rig.finding("F2")["status"] == "open" and rig.confirmations() == []


def test_send_is_the_code_form_of_send_kim(rig):
    rig.inspect()
    with pytest.raises(WorkflowError) as e:
        rig.cmd("kim", "/send patel F2")
    assert code(e) == (403, "role_not_allowed")
    out = rig.cmd("okafor", "/send kim F1 grab the hammer by the right engine")
    task = next(t for t in rig.tasks() if t["type"] == "remove" and t["finding_label"] == "F1")
    assert task["assignee_id"] == "kim" and task["severity"] == "HOLD" and task["created_by"] == "okafor"
    assert "F1 stays open" in out[0] and "grab the hammer" in rig.inbox("kim")[-1]
    with pytest.raises(WorkflowError) as e:
        rig.cmd("okafor", "/send kim F1")
    assert code(e) == (409, "refused") and "Already assigned" in e.value.message


def test_supervisor_commands_and_help(rig):
    rig.inspect()
    assert any("/ack F1" in line for line in rig.cmd("okafor", "/help"))
    assert not any("/ack F1" in line for line in rig.cmd("kim", "/help"))
    assert len(rig.cmd("dana", "/who")) == 5
    with pytest.raises(WorkflowError) as e:
        rig.cmd("dana", "/shift okafor off")                  # he holds an open HOLD
    assert code(e) == (409, "open_hold")
    rig.cmd("dana", "/shift patel off")
    assert rig.person("patel")["shift"] == "off"
    rig.cmd("dana", "/msg kim radio check")
    assert rig.inbox("kim")[-1] == "radio check"
    with pytest.raises(WorkflowError) as e:
        rig.cmd("kim", "/shift patel on")
    assert code(e) == (403, "role_not_allowed")


# ---------------------------------------------------------------------- over HTTP, as the chat page calls it
@pytest.fixture
def client(scenes, fake_llm):
    app = create_app(store=Store(), llm=fake_llm, start_player=False, agent_mode="code", roster=ROSTER)
    with TestClient(app) as c:
        c.d, c.wf = app.state.dispatcher, app.state.workflow
        c.wf.begin_turn(TURN)
        c.wf.start_inspection("T5", kind="pre_departure", scene_id="pd-hold", background=False)
        c.d.settle()
        yield c


def join(client, who, pin):
    return {"Authorization": f"Bearer {client.post('/api/agent/join', json={'person_id': who, 'pin': pin}).json()['token']}"}


def test_chat_endpoints_inbox_cursor_tasks_proposals_and_answer(client):
    kim, okafor = join(client, "kim", "1111"), join(client, "okafor", "2222")
    box = client.get("/api/agent/inbox", headers=kim).json()
    assert set(box) == {"person", "epoch", "clock_t", "cursor", "messages", "tasks", "pending_proposals"}
    assert box["person"] == {"person_id": "kim", "name": "Kim", "role": "ramp_agent", "gates": ["T5", "T8"],
                             "shift": "on", "signed_in": True}
    (first,) = box["messages"]
    assert set(first) == {"message_id", "from", "to", "kind", "text", "task_id", "proposal_id", "at", "t"}
    assert first["from"] == "code" and first["to"] == "kim" and first["task_id"] == box["tasks"][0]["task_id"]
    task = box["tasks"][0]
    assert (task["type"], task["status"], task["finding_id"], task["severity"]) == ("remove", "assigned", "F2", "REMOVE")
    assert client.get(f"/api/agent/inbox?after={box['cursor']}", headers=kim).json()["messages"] == []

    r = client.post("/api/agent/command", json={"command": "done", "args": [task["task_id"]]}, headers=kim)
    assert r.status_code == 200 and r.json()["ok"] is True
    box = client.get(f"/api/agent/inbox?after={box['cursor']}", headers=kim).json()
    assert [m["kind"] for m in box["messages"]] == ["command", "code", "code"]       # typed, the question, the reply
    (prop,) = box["pending_proposals"]
    assert prop["kind"] == "confirm" and prop["action"]["outcome"] == "removed" and prop["expires_in_s"] > 0
    assert box["messages"][1]["proposal_id"] == prop["proposal_id"]
    assert box["tasks"][0]["status"] == "reported"
    r = client.post(f"/api/agent/proposals/{prop['proposal_id']}/answer", json={"accept": True}, headers=okafor)
    assert r.status_code == 409                                # not his question
    r = client.post(f"/api/agent/proposals/{prop['proposal_id']}/answer", json={"accept": True}, headers=kim)
    assert r.json()["lines"] == ["Recorded: F2 removed, confirmed by Kim (Ramp Agent)."]
    box = client.get("/api/agent/inbox", headers=kim).json()
    assert box["pending_proposals"] == [] and box["tasks"][0]["status"] == "closed"

    r = client.post("/api/agent/say", json={"text": "anything else for me?"}, headers=kim)
    assert r.json()["routed"] == "agent"
    assert "cannot read free text right now" in client.get("/api/agent/inbox", headers=kim).json()["messages"][-1]["text"]
    assert client.post("/api/agent/say", json={"text": " "}, headers=kim).status_code == 422
    assert client.post("/api/agent/command", json={"text": "hello"}, headers=kim).json()["error"] == "invalid_command"


def test_activity_log_is_chronological_and_filterable(client):
    okafor = join(client, "okafor", "2222")
    client.post("/api/agent/command", json={"text": "/ack F1"}, headers=okafor)
    client.post("/api/agent/command", json={"text": "/signoff T5"}, headers=okafor)          # refused: also logged
    log = client.get("/api/agent/activity").json()
    entries = log["entries"]
    assert [e["id"] for e in entries] == sorted(e["id"] for e in entries) and log["cursor"] == entries[-1]["id"]
    assert set(entries[0]) == {"id", "at", "t", "kind", "event", "gate", "turn_id", "actor", "text", "data"}
    events = [e["event"] for e in entries]
    for expected in ("inspection_completed", "task_assigned", "hold_alert", "message", "signed_in", "confirmation",
                     "command_refused"):
        assert expected in events, expected
    conf = next(e for e in entries if e["event"] == "confirmation")
    assert conf["actor"] == "Okafor" and conf["data"]["by"] == {"role": "ramp_lead", "name": "Okafor"}
    assert conf["data"]["action"] == "acknowledged" and conf["data"]["finding_id"] == "F1" and conf["at"].endswith("Z")
    t5 = client.get("/api/agent/activity?gate=T5").json()["entries"]
    assert t5 and all(e["gate"] == "T5" for e in t5)
    assert client.get("/api/agent/activity?gate=T1").json()["entries"] == []
    assert client.get(f"/api/agent/activity?turn_id={TURN['turn_id']}&after={log['cursor']}").json()["entries"] == []
    board = client.get("/api/agent/board").json()
    assert {"mode", "model", "model_available", "tasks", "roster", "timers", "activity", "cost", "clock_t"} <= set(board)
    assert board["mode"] == "code" and board["cost"]["agent_session_usd"] == 0 and len(board["roster"]) == 5


def test_existing_dashboard_endpoints_are_unchanged_by_the_dispatcher(client):
    rep = client.wf.store.latest_report(TURN["turn_id"])
    hold = next(f for f in rep["findings"] if f["severity"] == "HOLD")
    url = f"/api/inspections/{rep['inspection_id']}/findings/{hold['finding_id']}/confirm"
    assert client.post(url, json={"outcome": "acknowledged", "role": "ramp_agent", "name": "A"}).status_code == 403
    assert client.post(url, json={"outcome": "acknowledged", "role": "ramp_lead", "name": "Lena"}).status_code == 200
    client.d.settle()
    assert client.d.board.tasks()[0]["status"] == "accepted"   # the dispatcher follows what the dashboard recorded
    assert set(client.get("/api/state").json()) == {"demo", "gates", "queue"}
