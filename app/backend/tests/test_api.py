"""API contract shapes and error codes over HTTP (TestClient; LLM mocked)."""
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from fodgate import config
from fodgate.api import create_app
from fodgate.store import Store
from tests.conftest import make_scene
from tests.test_pipeline import ANGLE_KEYS, FINDING_KEYS, REPORT_KEYS

OBJ = [400, 250, 416, 266]
LEAD = {"role": "ramp_lead", "name": "Lena Lead"}
AGENT = {"role": "ramp_agent", "name": "Avi Agent"}
GATE_STATUSES = {"idle", "awaiting_pre_arrival", "inspecting", "awaiting_confirmation", "confirmed_clear", "on_stand",
                 "departed"}


@pytest.fixture
def timeline(data_dir):
    make_scene("pa-clean", kind="pre_arrival")
    make_scene("pd-hold", objects={"ENG-L": [OBJ], "CARGO": [OBJ]}, after_clean=("ENG-L",))
    make_scene("pd-glare", declared_unusable={"ENG-R": "glare"}, after_clean=("ENG-R",))
    (data_dir / "demo").mkdir()
    (data_dir / "demo" / "timeline.json").write_text(json.dumps({
        "gates": ["T1", "T2", "T4", "T5", "T8"],
        "turns": [{"turn_id": "T1-DL1432", "gate": "T1", "flight": "DL1432", "aircraft_type": "A321", "events": [
            {"t": 0, "type": "stand_prep"},
            {"t": 20, "type": "inspection", "kind": "pre_arrival", "scene_id": "pa-clean"},
            {"t": 60, "type": "block_in"},
            {"t": 180, "type": "inspection", "kind": "pre_departure", "scene_id": "pd-hold"},
            {"t": 300, "type": "scheduled_pushback"}]}]}))


def fake_assistant_create(**kw):
    """Scripted Claude for the assistant: first call asks for tools, second call answers."""
    if not any(m["role"] == "user" and isinstance(m["content"], list) for m in kw["messages"]):
        return SimpleNamespace(stop_reason="tool_use", usage=SimpleNamespace(input_tokens=900, output_tokens=60), content=[
            SimpleNamespace(type="tool_use", id="tu_1", name="get_report", input={}),
            SimpleNamespace(type="tool_use", id="tu_2", name="draft_outside_boundary_report",
                            input={"recipient": "ramp_1_control", "finding_ids": []})])
    return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=1500, output_tokens=120), content=[
        SimpleNamespace(type="text", text=json.dumps({"reply": "The HOLD on ENG-L cites FOD-R1.",
                                                      "suggested_reinspect_angles": ["ENG-L"]}))])


@pytest.fixture
def client(timeline, fake_llm):
    app = create_app(store=Store(), llm=fake_llm, start_player=False, assistant_create=fake_assistant_create)
    with TestClient(app) as c:
        c.player = app.state.player
        yield c


def wait_done(client, inspection_id, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        rep = client.get(f"/api/inspections/{inspection_id}").json()
        if rep["status"] != "inspecting":
            return rep
        time.sleep(0.05)
    raise AssertionError("Inspection did not finish")


def inspect(client, gate, kind, scene_id=None):
    body = {"kind": kind} | ({"scene_id": scene_id} if scene_id else {})
    r = client.post(f"/api/gates/{gate}/inspect", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "inspecting"
    return wait_done(client, r.json()["inspection_id"])


def err(r):
    body = r.json()
    assert set(body) == {"error", "message"} and body["message"]
    return r.status_code, body["error"]


def test_state_shape(client):
    s = client.get("/api/state").json()
    assert set(s) == {"demo", "gates", "queue"}
    assert s["demo"] == {"playing": False, "speed": 1, "t": 0.0, "duration": 300.0}
    assert [g["gate"] for g in s["gates"]] == ["T1", "T2", "T4", "T5", "T8"]
    assert all(set(g) == {"gate", "status", "verdict", "highest_open_severity", "turn"} for g in s["gates"])
    assert all(g["status"] == "idle" for g in s["gates"]) and s["queue"] == []


def test_rules_endpoint(client):
    r = client.get("/api/rules").json()
    assert r == json.loads(config.rules_path().read_text()) and r["version"] == "fod-rules v0.2"


def test_manual_inspection_report_turn_and_export(client):
    rep = inspect(client, "T2", "pre_departure", "pd-hold")
    assert REPORT_KEYS <= set(rep) and rep["status"] == "awaiting_confirmation" and rep["gate"] == "T2"
    assert all(ANGLE_KEYS <= set(a) for a in rep["angles"]) and all(FINDING_KEYS <= set(f) for f in rep["findings"])
    assert rep["verdict"] == "FINDINGS" and rep["highest_open_severity"] == "HOLD"
    assert set(rep["run_metadata"]) >= {"local_models", "llm_calls", "timings_ms"}
    assert set(rep["run_metadata"]["timings_ms"]) == {"local", "haiku", "sonnet", "total"}
    assert set(rep["run_metadata"]["llm_calls"][0]) >= {"model", "purpose", "tokens_in", "tokens_out", "est_cost_usd"}

    turn = client.get(f"/api/turns/{rep['turn_id']}").json()
    assert set(turn) >= {"turn_id", "gate", "flight", "aircraft_type", "phase", "minutes_to_pushback",
                         "latest_inspection_id", "inspections", "events"}
    assert [i["inspection_id"] for i in turn["inspections"]] == [rep["inspection_id"]]
    assert [e["type"] for e in turn["events"]] == ["stand_prep", "inspection_started", "inspection_completed"]

    export = client.get(f"/api/inspections/{rep['inspection_id']}/export")
    assert export.status_code == 200 and export.json() == rep
    assert f'filename="{rep["inspection_id"]}.json"' in export.headers["content-disposition"]

    s = client.get("/api/state").json()
    t2 = next(g for g in s["gates"] if g["gate"] == "T2")
    assert (t2["status"], t2["verdict"], t2["highest_open_severity"]) == ("awaiting_confirmation", "FINDINGS", "HOLD")
    assert set(t2["turn"]) == {"turn_id", "flight", "aircraft_type", "phase", "minutes_to_pushback", "latest_inspection_id"}
    assert s["queue"][0]["reason"] == "hold" and s["queue"][0]["inspection_id"] == rep["inspection_id"]
    assert set(s["queue"][0]) == {"gate", "turn_id", "inspection_id", "reason", "severity", "minutes_to_pushback", "text"}


def test_images_and_crops_are_served(client):
    rep = inspect(client, "T2", "pre_departure", "pd-hold")
    a = rep["angles"][0]
    for url in (a["image_url"], a["reference_url"], rep["findings"][0]["crop_url"], rep["findings"][0]["reference_crop_url"]):
        r = client.get(url)
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert err(client.get("/images/pd-hold/nope.jpg")) == (404, "not_found")
    assert err(client.get("/images/pd-hold/scene.json")) == (404, "not_found")
    assert client.get("/images/pd-hold/..%2F..%2Frules%2Ffod-rules.json").status_code == 404


def test_full_confirmation_flow_with_error_codes(client):
    rep = inspect(client, "T1", "pre_departure", "pd-hold")
    iid = rep["inspection_id"]
    hold = next(f for f in rep["findings"] if f["severity"] == "HOLD")
    base = f"/api/inspections/{iid}"
    confirm = f"{base}/findings/{hold['finding_id']}/confirm"

    assert err(client.post(confirm, json={"outcome": "acknowledged", **AGENT})) == (403, "role_not_allowed")
    assert err(client.post(confirm, json={"outcome": "removed", **LEAD})) == (409, "hold_needs_acknowledge")
    assert err(client.post(f"{base}/signoff", json=LEAD)) == (409, "open_findings")
    assert err(client.post(confirm, json={"outcome": "removed"})) == (422, "invalid_request")       # no role / name
    assert err(client.post(confirm, json={"outcome": "gone", **LEAD})) == (422, "invalid_request")
    assert err(client.post(f"{base}/findings/nope/confirm", json={"outcome": "removed", **LEAD})) == (404, "not_found")
    assert err(client.post("/api/inspections/nope/signoff", json=LEAD)) == (404, "not_found")
    assert err(client.post(f"{base}/angles/NOSE/checked-by-eye", json=AGENT)) == (403, "role_not_allowed")

    r = client.post(f"{base}/findings/confirm-all", json=AGENT)
    assert r.status_code == 200 and r.json()["highest_open_severity"] == "HOLD"
    r = client.post(confirm, json={"outcome": "acknowledged", **LEAD})
    assert r.status_code == 200 and next(f for f in r.json()["findings"] if f["severity"] == "HOLD")["status"] == "acknowledged"
    r = client.post(confirm, json={"outcome": "removed", **LEAD})
    new = r.json()
    assert r.status_code == 200 and new["kind"] == "on_demand" and new["parent_inspection_id"] == iid
    assert new["verdict"] == "ALL_CLEAR" and new["highest_open_severity"] is None and new["status"] == "awaiting_confirmation"
    assert client.get(base).json()["findings"][0]["confirmation"]["outcome"] == "removed"

    r = client.post(f"/api/inspections/{new['inspection_id']}/signoff", json=LEAD)
    assert r.status_code == 200 and r.json()["status"] == "confirmed" and r.json()["inspection_signoff"]["by"] == LEAD
    t1 = next(g for g in client.get("/api/state").json()["gates"] if g["gate"] == "T1")
    assert t1["status"] == "confirmed_clear" and client.get("/api/state").json()["queue"] == []
    turn = client.get(f"/api/turns/{rep['turn_id']}").json()
    assert [i["kind"] for i in turn["inspections"]] == ["pre_departure", "on_demand"]


def test_not_found_endpoints(client):
    rep = inspect(client, "T1", "pre_departure", "pd-hold")
    iid = rep["inspection_id"]
    base = f"/api/inspections/{iid}"
    remove = next(f for f in rep["findings"] if f["severity"] == "REMOVE")
    hold = next(f for f in rep["findings"] if f["severity"] == "HOLD")

    confirm = f"{base}/findings/{remove['finding_id']}/confirm"
    assert err(client.post(confirm, json={"outcome": "not_found_on_walk", **AGENT})) == (409, "use_proposal")

    r = client.post(f"{base}/findings/{remove['finding_id']}/not-found", json=AGENT)
    assert r.status_code == 200
    [p] = [p for p in r.json()["proposals"] if p["status"] == "pending"]
    answer = f"{base}/proposals/{p['proposal_id']}/answer"
    assert err(client.post(answer, json={"accept": True, **LEAD})) == (403, "not_addressed_to_you")
    assert err(client.post(answer, json=AGENT)) == (422, "invalid_request")                  # accept is required
    r = client.post(answer, json={"accept": True, **AGENT})
    got = next(f for f in r.json()["findings"] if f["finding_id"] == remove["finding_id"])
    assert got["confirmation"]["outcome"] == "not_found_on_walk"
    assert err(client.post(answer, json={"accept": True, **AGENT})) == (409, "proposal_answered")

    r = client.post(f"{base}/findings/{hold['finding_id']}/not-found", json=AGENT)
    h = next(f for f in r.json()["findings"] if f["finding_id"] == hold["finding_id"])
    assert h["status"] == "open" and h["confirmation"] is None
    [p] = [p for p in r.json()["proposals"] if p["status"] == "pending"]
    assert p["kind"] == "reinspect_angle" and p["to"]["role"] == "ramp_lead"
    assert err(client.post(f"{base}/proposals/nope/answer", json={"accept": True, **LEAD})) == (404, "not_found")


def test_unusable_angle_flow(client):
    rep = inspect(client, "T4", "pre_departure", "pd-glare")
    base = f"/api/inspections/{rep['inspection_id']}"
    assert rep["verdict"] == "INCOMPLETE" and rep["missing_angles"] == ["ENG-R"]
    assert err(client.post(f"{base}/signoff", json=LEAD)) == (409, "unusable_angles")
    assert err(client.post(f"{base}/angles/TAIL/reinspect", json=AGENT)) == (404, "not_found")
    r = client.post(f"{base}/angles/ENG-R/checked-by-eye", json=LEAD)
    assert r.status_code == 200
    assert next(a for a in r.json()["angles"] if a["angle"] == "ENG-R")["checked_by_eye"]["by"] == LEAD
    new = client.post(f"{base}/angles/ENG-R/reinspect", json=AGENT).json()
    assert new["kind"] == "on_demand" and new["verdict"] == "ALL_CLEAR" and new["missing_angles"] == []
    assert client.post(f"{base}/signoff", json=LEAD).status_code == 200


def test_manual_trigger_errors(client):
    assert err(client.post("/api/gates/T9/inspect", json={"kind": "pre_arrival", "scene_id": "pa-clean"})) == (404, "not_found")
    assert err(client.post("/api/gates/T1/inspect", json={"kind": "pre_arrival", "scene_id": "nope"})) == (404, "not_found")
    assert err(client.post("/api/gates/T1/inspect", json={"kind": "sideways", "scene_id": "pa-clean"})) == (422, "invalid_request")
    assert err(client.post("/api/gates/T1/inspect", json={})) == (422, "invalid_request")
    assert err(client.get("/api/turns/nope")) == (404, "not_found")
    assert err(client.get("/api/nothing/here")) == (404, "not_found")


def test_demo_controls_and_scripted_turn(client):
    assert err(client.post("/api/demo/speed", json={"speed": 3})) == (422, "invalid_request")
    s = client.post("/api/demo/speed", json={"speed": 10}).json()
    assert s["demo"]["speed"] == 10
    s = client.post("/api/demo/play").json()
    assert s["demo"]["playing"] is True and set(s) == {"demo", "gates", "queue"}
    client.player.advance(0.1)                                           # t = 1 demo second
    t1 = client.get("/api/state").json()["gates"][0]
    assert t1["status"] == "awaiting_pre_arrival" and t1["turn"]["flight"] == "DL1432"
    assert t1["turn"]["minutes_to_pushback"] == pytest.approx(5.0, abs=0.1)
    client.player.advance(2.0)                                           # t = 21: pre-arrival Inspection starts
    s = client.get("/api/state").json()
    iid = s["gates"][0]["turn"]["latest_inspection_id"]
    assert iid and s["gates"][0]["status"] in ("inspecting", "awaiting_confirmation")
    assert s["gates"][0]["status"] in GATE_STATUSES
    rep = wait_done(client, iid)
    assert rep["kind"] == "pre_arrival" and rep["verdict"] == "ALL_CLEAR" and rep["turn_id"] == "T1-DL1432"
    s = client.post("/api/demo/pause").json()
    assert s["demo"]["playing"] is False and s["demo"]["t"] == pytest.approx(21.0, abs=0.01)
    assert s["queue"][0]["reason"] == "signoff"
    # manual trigger without scene_id uses the Turn's scripted scene for that kind
    assert inspect(client, "T1", "pre_departure")["scene_id"] == "pd-hold"

    cached = len(list(config.cache_dir().glob("*.json")))
    assert cached > 0
    s = client.post("/api/demo/reset").json()
    assert s["demo"] == {"playing": False, "speed": 10, "t": 0.0, "duration": 300.0}
    assert all(g["status"] == "idle" for g in s["gates"]) and s["queue"] == []
    assert err(client.get(f"/api/inspections/{iid}")) == (404, "not_found")          # the database was cleared
    assert len(list(config.cache_dir().glob("*.json"))) == cached                   # the LLM cache was kept


def test_demo_runs_to_departure_only_after_signoff(client):
    client.post("/api/demo/speed", json={"speed": 10})
    client.post("/api/demo/play")
    client.player.advance(2.1)                                           # past the pre-arrival Inspection
    first = wait_done(client, client.get("/api/state").json()["gates"][0]["turn"]["latest_inspection_id"])
    client.post(f"/api/inspections/{first['inspection_id']}/signoff", json=AGENT)
    client.player.advance(5.0)                                           # t = 71: block-in
    assert client.get("/api/state").json()["gates"][0]["status"] == "on_stand"
    client.player.advance(30.0)                                          # end of the timeline
    s = client.get("/api/state").json()
    assert s["demo"]["t"] == 300.0 and s["demo"]["playing"] is False
    rep = wait_done(client, s["gates"][0]["turn"]["latest_inspection_id"])
    assert rep["kind"] == "pre_departure" and rep["verdict"] == "FINDINGS"
    client.player.advance(0.1)
    g = client.get("/api/state").json()["gates"][0]
    assert g["status"] == "awaiting_confirmation" and g["turn"]["minutes_to_pushback"] == 0.0   # not departed
    base = f"/api/inspections/{rep['inspection_id']}"
    for f in rep["findings"]:
        assert client.post(f"{base}/findings/{f['finding_id']}/confirm",
                           json={"outcome": "false_alarm", "false_alarm_reason": "other", **LEAD}).status_code == 200
    client.post(f"{base}/signoff", json=LEAD)
    client.player.advance(0.1)
    turn = client.get("/api/turns/T1-DL1432").json()
    assert turn["phase"] == "departed" and client.get("/api/state").json()["gates"][0]["status"] == "departed"
    assert [e["type"] for e in turn["events"] if e["type"] in ("stand_prep", "block_in", "departed")] == \
        ["stand_prep", "block_in", "departed"]


def test_assistant_endpoint(client):
    rep = inspect(client, "T2", "pre_departure", "pd-hold")
    r = client.post("/api/assistant", json={"inspection_id": rep["inspection_id"], "message": "Why is ENG-L a HOLD?"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"reply", "suggested_reinspect_angles", "draft_report"}
    assert body["reply"] == "The HOLD on ENG-L cites FOD-R1." and body["suggested_reinspect_angles"] == ["ENG-L"]
    assert body["draft_report"] is None                                  # nothing outside the envelope in this scene
    assert client.get(f"/api/inspections/{rep['inspection_id']}").json() == rep   # the assistant changed nothing
    assert err(client.post("/api/assistant", json={"inspection_id": "nope", "message": "hi"})) == (404, "not_found")
    assert err(client.post("/api/assistant", json={"inspection_id": rep["inspection_id"], "message": " "})) == \
        (422, "invalid_request")


def test_health_never_exposes_the_key(client):
    body = client.get("/api/health").text
    assert "test-key-not-real" not in body and '"llm_available":true' in body
