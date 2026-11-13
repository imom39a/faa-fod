"""Issue #4: "not found" reports and "still there" after a HOLD is recorded as removed (LLM mocked)."""
import pytest

from fodgate.workflow import WorkflowError
from tests.conftest import make_scene
from tests.test_workflow import AGENT, LEAD, OBJ, by_sev, code, inspect, mixed, wf  # noqa: F401 (fixtures)

OTHER_AGENT = {"role": "ramp_agent", "name": "Bo Agent"}


def pending(rep, kind=None):
    return [p for p in rep.get("proposals", []) if p["status"] == "pending" and (kind is None or p["kind"] == kind)]


# ---------------------------------------------------------------------- not found: REMOVE / ADVISORY
@pytest.mark.parametrize("severity", ["REMOVE", "ADVISORY"])
def test_not_found_makes_a_proposal_and_records_nothing(wf, mixed, severity):
    iid, f = mixed["inspection_id"], by_sev(mixed, severity, None if severity == "REMOVE" else "general")
    rep = wf.report_not_found(iid, f["finding_id"], **AGENT)
    [p] = pending(rep)
    assert p["kind"] == "record_not_found_on_walk" and p["to"] == {"role": "ramp_agent", "name": "Avi Agent"}
    assert next(x for x in rep["findings"] if x["finding_id"] == f["finding_id"])["status"] == "open"
    assert wf.store.list_confirmations(iid) == []
    again = wf.report_not_found(iid, f["finding_id"], **AGENT)          # reporting twice does not stack proposals
    assert len(pending(again)) == 1


@pytest.mark.parametrize("severity", ["REMOVE", "ADVISORY"])
def test_accepting_records_not_found_on_walk_in_the_reporters_name(wf, mixed, severity):
    iid, f = mixed["inspection_id"], by_sev(mixed, severity, None if severity == "REMOVE" else "general")
    p = pending(wf.report_not_found(iid, f["finding_id"], **AGENT))[0]
    rep = wf.answer_proposal(iid, p["proposal_id"], accept=True, **AGENT)
    got = next(x for x in rep["findings"] if x["finding_id"] == f["finding_id"])
    assert got["status"] == "confirmed" and got["confirmation"]["outcome"] == "not_found_on_walk"
    assert got["confirmation"]["confirmed_by"] == {"role": "ramp_agent", "name": "Avi Agent"}
    assert [(c["action"], c["name"]) for c in wf.store.list_confirmations(iid)] == [("not_found_on_walk", "Avi Agent")]
    assert rep["proposals"][0]["status"] == "accepted"


def test_declining_leaves_the_finding_open_with_the_reporter(wf, mixed):
    iid, f = mixed["inspection_id"], by_sev(mixed, "REMOVE")
    p = pending(wf.report_not_found(iid, f["finding_id"], **AGENT))[0]
    rep = wf.answer_proposal(iid, p["proposal_id"], accept=False, **AGENT)
    assert by_sev(rep, "REMOVE")["status"] == "open" and wf.store.list_confirmations(iid) == []
    assert rep["proposals"][0]["status"] == "declined"
    with pytest.raises(WorkflowError) as e:
        wf.answer_proposal(iid, p["proposal_id"], accept=True, **AGENT)
    assert code(e) == (409, "proposal_answered")


def test_only_the_reporting_person_can_answer(wf, mixed):
    iid = mixed["inspection_id"]
    p = pending(wf.report_not_found(iid, by_sev(mixed, "REMOVE")["finding_id"], **AGENT))[0]
    for who in (OTHER_AGENT, LEAD):
        with pytest.raises(WorkflowError) as e:
            wf.answer_proposal(iid, p["proposal_id"], accept=True, **who)
        assert code(e) == (403, "not_addressed_to_you")


def test_not_found_on_walk_cannot_be_recorded_directly(wf, mixed):
    with pytest.raises(WorkflowError) as e:
        wf.confirm_finding(mixed["inspection_id"], by_sev(mixed, "REMOVE")["finding_id"],
                           outcome="not_found_on_walk", **AGENT)
    assert code(e) == (409, "use_proposal")


# ---------------------------------------------------------------------- not found: HOLD
@pytest.mark.parametrize("reporter", [AGENT, LEAD])
def test_hold_not_found_records_nothing_and_proposes_reinspection_to_the_lead(wf, mixed, reporter):
    iid, hold = mixed["inspection_id"], by_sev(mixed, "HOLD")
    rep = wf.report_not_found(iid, hold["finding_id"], **reporter)
    assert by_sev(rep, "HOLD")["status"] == "open" and wf.store.list_confirmations(iid) == []
    assert pending(rep, "record_not_found_on_walk") == []                # never a not-found proposal for a HOLD
    [p] = pending(rep, "reinspect_angle")
    assert p["to"]["role"] == "ramp_lead" and p["reported_by"]["name"] == reporter["name"] and p["angle"] == "ENG-L"
    with pytest.raises(WorkflowError) as e:                               # a Ramp Agent cannot accept it
        wf.answer_proposal(iid, p["proposal_id"], accept=True, **AGENT)
    assert code(e) == (403, "not_addressed_to_you")


def test_no_reinspection_runs_until_the_lead_accepts(wf, mixed):
    iid, hold = mixed["inspection_id"], by_sev(mixed, "HOLD")
    rep = wf.report_not_found(iid, hold["finding_id"], **AGENT)
    turn = wf.turn_view(mixed["turn_id"])
    assert [i["inspection_id"] for i in turn["inspections"]] == [iid]    # nothing started on its own
    p = pending(rep, "reinspect_angle")[0]
    new = wf.answer_proposal(iid, p["proposal_id"], accept=True, **LEAD)
    assert new["kind"] == "on_demand" and new["parent_inspection_id"] == iid
    assert by_sev(new, "HOLD")["status"] != "confirmed"                   # re-inspecting never confirms a HOLD
    assert wf.report(iid)["proposals"][0]["result_inspection_id"] == new["inspection_id"]


def test_lead_can_decline_the_reinspection_and_keep_the_hold_open(wf, mixed):
    iid, hold = mixed["inspection_id"], by_sev(mixed, "HOLD")
    p = pending(wf.report_not_found(iid, hold["finding_id"], **AGENT), "reinspect_angle")[0]
    rep = wf.answer_proposal(iid, p["proposal_id"], accept=False, **LEAD)
    assert by_sev(rep, "HOLD")["status"] == "open" and rep["highest_open_severity"] == "HOLD"


# ---------------------------------------------------------------------- still there
def test_still_there_twice_keeps_the_hold_open_and_counts(wf, brain):
    make_scene("stuck", objects={"NOSE": [OBJ]}, after_same=("NOSE",))
    rep = inspect(wf, "stuck")
    fid = rep["findings"][0]["finding_id"]
    wf.confirm_finding(rep["inspection_id"], fid, outcome="acknowledged", **LEAD)
    first = wf.confirm_finding(rep["inspection_id"], fid, outcome="removed", **LEAD)
    [f1] = first["findings"]
    assert f1["status"] == "acknowledged" and f1["confirmation"] is None and f1["still_there_count"] == 1
    assert first["highest_open_severity"] == "HOLD" and first["verdict"] == "FINDINGS"
    assert any("still shows" in n for n in first["run_metadata"]["notes"])
    assert wf.report(rep["inspection_id"])["findings"][0]["still_there_count"] == 1
    second = wf.confirm_finding(first["inspection_id"], f1["finding_id"], outcome="removed", **LEAD)
    [f2] = second["findings"]
    assert f2["status"] == "acknowledged" and f2["still_there_count"] == 2
    events = [e for e in wf.turn_view(rep["turn_id"])["events"] if e["type"] == "hold_still_there"]
    assert [e["count"] for e in events] == [1, 2]
    assert wf.store.list_confirmations(second["inspection_id"]) == []


def test_clean_reinspection_is_not_still_there(wf, mixed, brain):
    iid, hold = mixed["inspection_id"], by_sev(mixed, "HOLD")
    wf.confirm_finding(iid, hold["finding_id"], outcome="acknowledged", **LEAD)
    new = wf.confirm_finding(iid, hold["finding_id"], outcome="removed", **LEAD)
    assert by_sev(new, "HOLD")["status"] == "confirmed" and not by_sev(new, "HOLD").get("still_there_count")
