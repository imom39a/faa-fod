"""Confirmation rules, error codes, Gate status and queue ordering (LLM mocked)."""
import pytest

from fodgate.store import Store
from fodgate.workflow import Workflow, WorkflowError, queue_item, sort_queue
from tests.conftest import make_scene

OBJ = [400, 250, 416, 266]
LEAD = {"role": "ramp_lead", "name": "Lena Lead"}
AGENT = {"role": "ramp_agent", "name": "Avi Agent"}


@pytest.fixture
def wf(fake_llm):
    w = Workflow(Store(), fake_llm)
    yield w
    w.shutdown()


def inspect(wf, scene_id, gate="T1", kind="pre_departure"):
    return wf.start_inspection(gate, kind=kind, scene_id=scene_id, background=False)


def by_sev(rep, severity, tier=None):
    return next(f for f in rep["findings"] if f["severity"] == severity and (tier is None or f["zone_tier"] == tier))


def code(excinfo):
    return excinfo.value.status, excinfo.value.code


@pytest.fixture
def mixed(wf, brain):
    """HOLD on ENG-L, REMOVE on CARGO, ADVISORY in WIDE (general) and ADVISORY outside the envelope."""
    make_scene("mixed", objects={"ENG-L": [OBJ], "CARGO": [OBJ], "WIDE": [[470, 400, 486, 416], [470, 90, 486, 106]]},
               after_clean=("ENG-L",))
    brain.category = lambda cid, angle: ("cargo_packaging", "light") if angle == "WIDE" else ("tools", "hard")
    return inspect(wf, "mixed")


# ---------------------------------------------------------------------- roles
def test_ramp_agent_is_refused_on_a_hold(wf, mixed):
    hold = by_sev(mixed, "HOLD")
    for outcome in ("acknowledged", "removed", "false_alarm", "not_found_on_walk"):
        with pytest.raises(WorkflowError) as e:
            wf.confirm_finding(mixed["inspection_id"], hold["finding_id"], outcome=outcome, **AGENT)
        assert code(e) == (403, "role_not_allowed")
    assert by_sev(wf.report(mixed["inspection_id"]), "HOLD")["status"] == "open"


def test_ramp_agent_confirms_remove_and_advisory_in_one_step(wf, mixed):
    iid = mixed["inspection_id"]
    rep = wf.confirm_finding(iid, by_sev(mixed, "REMOVE")["finding_id"], outcome="removed", **AGENT)
    f = by_sev(rep, "REMOVE")
    assert f["status"] == "confirmed" and f["confirmation"]["outcome"] == "removed"
    assert f["confirmation"]["confirmed_by"] == AGENT and f["confirmation"]["confirmed_at"]
    assert f["confirmation"]["false_alarm_reason"] is None and f["confirmation"]["after_photo_ref"] is None
    rep = wf.confirm_finding(iid, by_sev(mixed, "ADVISORY", "general")["finding_id"], outcome="false_alarm",
                             false_alarm_reason="shadow", **AGENT)
    assert by_sev(rep, "ADVISORY", "general")["confirmation"]["false_alarm_reason"] == "shadow"
    assert rep["highest_open_severity"] == "HOLD" and rep["verdict"] == "FINDINGS"   # the Verdict is not rewritten


def test_invalid_role_outcome_reason_and_name(wf, mixed):
    iid, fid = mixed["inspection_id"], by_sev(mixed, "REMOVE")["finding_id"]
    for kwargs in ({"outcome": "removed", "role": "pilot", "name": "x"},
                   {"outcome": "vanished", **AGENT},
                   {"outcome": "false_alarm", "false_alarm_reason": "aliens", **AGENT},
                   {"outcome": "removed", "role": "ramp_agent", "name": "  "}):
        with pytest.raises(WorkflowError) as e:
            wf.confirm_finding(iid, fid, **kwargs)
        assert code(e) == (422, "invalid_request")


def test_unknown_ids_are_404(wf, mixed):
    with pytest.raises(WorkflowError) as e:
        wf.confirm_finding("insp-nope", "x", outcome="removed", **AGENT)
    assert code(e) == (404, "not_found")
    with pytest.raises(WorkflowError) as e:
        wf.confirm_finding(mixed["inspection_id"], "nope", outcome="removed", **AGENT)
    assert code(e) == (404, "not_found")
    with pytest.raises(WorkflowError) as e:
        wf.reinspect(mixed["inspection_id"], "TAIL", **AGENT)
    assert code(e) == (404, "not_found")


def test_a_confirmed_finding_cannot_be_confirmed_again(wf, mixed):
    iid, fid = mixed["inspection_id"], by_sev(mixed, "REMOVE")["finding_id"]
    wf.confirm_finding(iid, fid, outcome="removed", **AGENT)
    with pytest.raises(WorkflowError) as e:
        wf.confirm_finding(iid, fid, outcome="false_alarm", **AGENT)
    assert code(e) == (409, "already_confirmed")


# ---------------------------------------------------------------------- HOLD: acknowledge, then removed + re-inspection
def test_hold_must_be_acknowledged_before_removed(wf, mixed):
    with pytest.raises(WorkflowError) as e:
        wf.confirm_finding(mixed["inspection_id"], by_sev(mixed, "HOLD")["finding_id"], outcome="removed", **LEAD)
    assert code(e) == (409, "hold_needs_acknowledge")


def test_hold_acknowledge_then_removed_clears_when_new_frame_is_clean(wf, mixed, brain):
    iid, hold = mixed["inspection_id"], by_sev(mixed, "HOLD")
    rep = wf.confirm_finding(iid, hold["finding_id"], outcome="acknowledged", **LEAD)
    f = by_sev(rep, "HOLD")
    assert f["status"] == "acknowledged" and f["confirmation"] is None and f["acknowledged"]["by"] == LEAD
    assert rep["highest_open_severity"] == "HOLD"                    # acknowledged is not cleared
    brain.calls.clear()
    new = wf.confirm_finding(iid, hold["finding_id"], outcome="removed", possible_source="tool roll", **LEAD)
    assert new["inspection_id"] != iid and new["kind"] == "on_demand" and new["parent_inspection_id"] == iid
    assert {c["angle"] for c in brain.calls} == {"ENG-L"}            # re-inspection of that Angle only
    assert next(a for a in new["angles"] if a["angle"] == "ENG-L")["image_ref"] == "mixed/after/ENG-L.jpg"
    # the Confirmation is on the original Finding and on the copy the new Inspection carries
    for rpt in (wf.report(iid), new):
        f = next(f for f in rpt["findings"] if f["angle"] == "ENG-L")
        assert f["status"] == "confirmed" and f["confirmation"]["outcome"] == "removed"
        assert f["confirmation"]["confirmed_by"] == LEAD and f["confirmation"]["possible_source"] == "tool roll"
        assert f["confirmation"]["after_photo_ref"] == "mixed/after/ENG-L.jpg"
    assert new["highest_open_severity"] == "REMOVE"                  # the other Findings were inherited, still open
    assert wf.report(iid)["highest_open_severity"] == "REMOVE"


def test_hold_removed_then_all_clear(wf, brain):
    make_scene("hold", objects={"NOSE": [OBJ]}, after_clean=("NOSE",))
    rep = inspect(wf, "hold")
    fid = rep["findings"][0]["finding_id"]
    wf.confirm_finding(rep["inspection_id"], fid, outcome="acknowledged", **LEAD)
    new = wf.confirm_finding(rep["inspection_id"], fid, outcome="removed", **LEAD)
    assert new["verdict"] == "ALL_CLEAR" and new["highest_open_severity"] is None
    assert wf.signoff(new["inspection_id"], **LEAD)["status"] == "confirmed"


def test_hold_stays_open_when_the_object_is_still_there(wf, brain):
    make_scene("stuck", objects={"NOSE": [OBJ]})                     # no `after` frame: the new frame shows it again
    rep = inspect(wf, "stuck")
    fid = rep["findings"][0]["finding_id"]
    wf.confirm_finding(rep["inspection_id"], fid, outcome="acknowledged", **LEAD)
    new = wf.confirm_finding(rep["inspection_id"], fid, outcome="removed", **LEAD)
    assert new["inspection_id"] != rep["inspection_id"] and new["verdict"] == "FINDINGS"
    assert [f["status"] for f in new["findings"]] == ["acknowledged"] and new["findings"][0]["confirmation"] is None
    assert new["highest_open_severity"] == "HOLD"
    assert wf.report(rep["inspection_id"])["findings"][0]["status"] == "acknowledged"   # nothing was recorded


def test_hold_false_alarm_needs_no_reinspection_and_no_acknowledge(wf, mixed, brain):
    brain.calls.clear()
    rep = wf.confirm_finding(mixed["inspection_id"], by_sev(mixed, "HOLD")["finding_id"], outcome="false_alarm",
                             false_alarm_reason="marking", **LEAD)
    assert rep["inspection_id"] == mixed["inspection_id"] and brain.calls == []
    assert by_sev(rep, "HOLD")["confirmation"]["false_alarm_reason"] == "marking"
    assert rep["highest_open_severity"] == "REMOVE"


# ---------------------------------------------------------------------- confirm-all
def test_confirm_all_marks_remove_and_advisory_removed_but_never_a_hold(wf, mixed):
    rep = wf.confirm_all(mixed["inspection_id"], **AGENT)
    for f in rep["findings"]:
        if f["severity"] == "HOLD":
            assert f["status"] == "open" and f["confirmation"] is None
        else:
            assert f["status"] == "confirmed" and f["confirmation"]["outcome"] == "removed"
            assert f["confirmation"]["confirmed_by"] == AGENT
    assert rep["highest_open_severity"] == "HOLD"
    assert len(wf.store.list_confirmations(mixed["inspection_id"])) == 3


# ---------------------------------------------------------------------- sign-off
def test_signoff_blocked_by_open_findings_then_allowed(wf, mixed):
    iid = mixed["inspection_id"]
    with pytest.raises(WorkflowError) as e:
        wf.signoff(iid, **LEAD)
    assert code(e) == (409, "open_findings")
    wf.confirm_all(iid, **AGENT)
    with pytest.raises(WorkflowError) as e:
        wf.signoff(iid, **LEAD)                                       # the HOLD is still open
    assert code(e) == (409, "open_findings")
    wf.confirm_finding(iid, by_sev(mixed, "HOLD")["finding_id"], outcome="false_alarm", **LEAD)
    rep = wf.signoff(iid, **LEAD)
    assert rep["status"] == "confirmed" and rep["inspection_signoff"]["by"] == LEAD and rep["inspection_signoff"]["at"]
    with pytest.raises(WorkflowError) as e:
        wf.signoff(iid, **LEAD)
    assert code(e) == (409, "already_signed_off")


def test_outside_boundary_counts_as_closed_once_reported(wf, brain):
    make_scene("out", objects={"WIDE": [[470, 90, 486, 106]]})
    rep = inspect(wf, "out")
    f = rep["findings"][0]
    assert f["zone_tier"] == "outside_boundary" and f["rule_id"] == "FOD-R10"
    with pytest.raises(WorkflowError) as e:
        wf.signoff(rep["inspection_id"], **AGENT)
    assert code(e) == (409, "open_findings")
    rep = wf.confirm_finding(rep["inspection_id"], f["finding_id"], outcome="acknowledged", **AGENT)
    assert rep["highest_open_severity"] is None                       # reported: no longer open
    assert wf.signoff(rep["inspection_id"], **AGENT)["status"] == "confirmed"


def test_outside_boundary_removed_with_possible_source(wf):
    make_scene("out", objects={"WIDE": [[470, 90, 486, 106]]})
    rep = inspect(wf, "out")
    rep = wf.confirm_finding(rep["inspection_id"], rep["findings"][0]["finding_id"], outcome="removed",
                             possible_source="reported to Ramp 1 control", **AGENT)
    assert rep["findings"][0]["confirmation"]["possible_source"] == "reported to Ramp 1 control"
    assert wf.signoff(rep["inspection_id"], **AGENT)["inspection_signoff"]


def test_signoff_blocked_by_unusable_angle_until_checked_by_eye(wf):
    make_scene("glare", declared_unusable={"ENG-R": "glare"})
    rep = inspect(wf, "glare")
    iid = rep["inspection_id"]
    assert rep["verdict"] == "INCOMPLETE"
    with pytest.raises(WorkflowError) as e:
        wf.signoff(iid, **LEAD)
    assert code(e) == (409, "unusable_angles")
    with pytest.raises(WorkflowError) as e:
        wf.checked_by_eye(iid, "ENG-R", **AGENT)                      # Ramp Lead only
    assert code(e) == (403, "role_not_allowed")
    with pytest.raises(WorkflowError) as e:
        wf.checked_by_eye(iid, "NOSE", **LEAD)                        # a usable Angle has nothing to check
    assert code(e) == (409, "angle_usable")
    rep = wf.checked_by_eye(iid, "ENG-R", **LEAD)
    a = next(a for a in rep["angles"] if a["angle"] == "ENG-R")
    assert a["checked_by_eye"]["by"] == LEAD and a["status"] == "unusable"   # still recorded as not seen by camera
    assert rep["verdict"] == "INCOMPLETE" and rep["missing_angles"] == ["ENG-R"]
    assert wf.signoff(iid, **LEAD)["status"] == "confirmed"


def test_unusable_angle_reinspected_usable_allows_signoff(wf):
    make_scene("glare", declared_unusable={"ENG-R": "glare"}, after_clean=("ENG-R",))
    rep = inspect(wf, "glare")
    new = wf.reinspect(rep["inspection_id"], "ENG-R", **AGENT)        # any role may ask for a re-inspection
    assert new["kind"] == "on_demand" and new["verdict"] == "ALL_CLEAR" and new["missing_angles"] == []
    assert wf.signoff(new["inspection_id"], **AGENT)["status"] == "confirmed"
    with pytest.raises(WorkflowError) as e:
        wf.signoff(rep["inspection_id"], **LEAD)                      # the earlier Inspection is still incomplete
    assert code(e) == (409, "unusable_angles")


def test_reinspect_cannot_clear_a_hold_without_the_ramp_lead(wf, mixed):
    new = wf.reinspect(mixed["inspection_id"], "ENG-L", **AGENT)      # the `after` frame is clean
    hold = by_sev(new, "HOLD")
    assert hold["status"] == "open" and hold["carried_from_inspection_id"] == mixed["inspection_id"]
    with pytest.raises(WorkflowError) as e:
        wf.signoff(new["inspection_id"], **AGENT)
    assert code(e) == (409, "open_findings")


def test_actions_refused_while_inspecting(wf):
    make_scene("s1")
    ph = wf._placeholder(gate="T1", turn_id="t", kind="pre_departure", scene_id="s1", parent_id=None)
    wf.store.save_report(ph)
    assert ph["status"] == "inspecting" and ph["verdict"] is None
    for call in (lambda: wf.signoff(ph["inspection_id"], **LEAD),
                 lambda: wf.confirm_all(ph["inspection_id"], **LEAD),
                 lambda: wf.reinspect(ph["inspection_id"], "NOSE", **LEAD)):
        with pytest.raises(WorkflowError) as e:
            call()
        assert code(e) == (409, "inspection_in_progress")


# ---------------------------------------------------------------------- Gate status and queue
def turn(gate, turn_id, pushback):
    return {"turn_id": turn_id, "gate": gate, "flight": "DL1", "aircraft_type": "A321",
            "events": [{"t": 0, "type": "stand_prep"}, {"t": pushback, "type": "scheduled_pushback"}]}


def test_gate_status_through_a_turn(wf):
    make_scene("clean")
    make_scene("hold", objects={"NOSE": [OBJ]})
    gates, queue = wf.state()
    assert [g["gate"] for g in gates] == ["T1", "T2", "T4", "T5", "T8"] and queue == []
    assert all(g["status"] == "idle" and g["turn"] is None and g["verdict"] is None for g in gates)

    wf.begin_turn(turn("T1", "T1-A", 600))
    g = wf.gate_state("T1")[0]
    assert g["status"] == "awaiting_pre_arrival" and g["turn"]["phase"] == "stand_prep"
    assert g["turn"]["minutes_to_pushback"] == 10.0 and g["turn"]["latest_inspection_id"] is None

    rep = inspect(wf, "clean", kind="pre_arrival")
    g, item = wf.gate_state("T1")
    assert (g["status"], g["verdict"], g["highest_open_severity"]) == ("awaiting_confirmation", "ALL_CLEAR", None)
    assert g["turn"]["phase"] == "pre_arrival" and g["turn"]["latest_inspection_id"] == rep["inspection_id"]
    assert item["reason"] == "signoff" and item["severity"] is None      # ALL CLEAR is advisory until signed off

    wf.signoff(rep["inspection_id"], **AGENT)
    g, item = wf.gate_state("T1")
    assert g["status"] == "confirmed_clear" and item is None

    wf.block_in("T1-A")
    assert wf.gate_state("T1")[0]["status"] == "on_stand"

    rep = inspect(wf, "hold", kind="pre_departure")
    g, item = wf.gate_state("T1")
    assert (g["status"], g["verdict"], g["highest_open_severity"]) == ("awaiting_confirmation", "FINDINGS", "HOLD")
    assert g["turn"]["phase"] == "pre_departure" and item["reason"] == "hold" and item["severity"] == "HOLD"
    assert wf.try_depart("T1-A") is False                                # not shown as departed while unconfirmed
    wf.confirm_finding(rep["inspection_id"], rep["findings"][0]["finding_id"], outcome="false_alarm", **LEAD)
    wf.signoff(rep["inspection_id"], **LEAD)
    assert wf.try_depart("T1-A") is True
    g, item = wf.gate_state("T1")
    assert g["status"] == "departed" and g["turn"]["minutes_to_pushback"] is None and item is None


def test_gate_shows_inspecting_and_hold_even_when_incomplete(wf):
    make_scene("both", objects={"NOSE": [OBJ]}, declared_unusable={"AFT": "blocked"})
    wf.begin_turn(turn("T2", "T2-A", 300))
    ph = wf._placeholder(gate="T2", turn_id="T2-A", kind="pre_departure", scene_id="both", parent_id=None)
    wf.store.save_report(ph)
    g, item = wf.gate_state("T2")
    assert g["status"] == "inspecting" and g["verdict"] is None and item is None
    wf._run(ph, wf._scene("both"), parent=None, angles=None, generation=wf._generation)
    g, item = wf.gate_state("T2")
    assert g["verdict"] == "FINDINGS" and g["highest_open_severity"] == "HOLD" and item["reason"] == "hold"


def test_queue_reasons(wf):
    rep = {"inspection_id": "i", "highest_open_severity": None, "findings": [], "angles": []}
    assert queue_item("T1", "t", rep, 5)["reason"] == "signoff"
    rep["angles"] = [{"angle": "AFT", "status": "unusable", "checked_by_eye": None}]
    assert queue_item("T1", "t", rep, 5)["reason"] == "incomplete"
    rep["findings"] = [{"status": "open", "severity": "REMOVE", "zone_tier": "service", "angle": "AFT", "description": "d"}]
    rep["highest_open_severity"] = "REMOVE"
    item = queue_item("T1", "t", rep, 5)
    assert (item["reason"], item["severity"], item["text"]) == ("findings", "REMOVE", "1 Finding to confirm")
    assert set(item) == {"gate", "turn_id", "inspection_id", "reason", "severity", "minutes_to_pushback", "text"}


def test_queue_order_holds_first_then_time_to_pushback(wf):
    def q(gate, severity, minutes):
        return {"gate": gate, "severity": severity, "minutes_to_pushback": minutes}
    ordered = sort_queue([q("T1", "REMOVE", 2), q("T2", "HOLD", 30), q("T4", None, 1), q("T5", "HOLD", 4),
                          q("T8", "ADVISORY", None)])
    assert [i["gate"] for i in ordered] == ["T5", "T2", "T4", "T1", "T8"]


def test_queue_order_end_to_end(wf):
    make_scene("hold", objects={"NOSE": [OBJ]})
    make_scene("remove", objects={"CARGO": [OBJ]})
    make_scene("clean")
    for gate, scene, pushback in (("T1", "remove", 120), ("T2", "hold", 900), ("T4", "clean", 60), ("T5", "hold", 300)):
        wf.begin_turn(turn(gate, f"{gate}-A", pushback))
        inspect(wf, scene, gate=gate)
    _, queue = wf.state()
    assert [(i["gate"], i["reason"]) for i in queue] == [("T5", "hold"), ("T2", "hold"), ("T4", "signoff"), ("T1", "findings")]
    assert [i["minutes_to_pushback"] for i in queue] == [5.0, 15.0, 1.0, 2.0]


def test_manual_trigger_errors_and_ad_hoc_turn(wf):
    make_scene("clean")
    for args, expected in ((("T9", "pre_arrival", "clean"), (404, "not_found")),
                           (("T1", "walkaround", "clean"), (422, "invalid_request")),
                           (("T1", "pre_arrival", "nope"), (404, "not_found")),
                           (("T1", "pre_arrival", None), (422, "invalid_request"))):
        with pytest.raises(WorkflowError) as e:
            wf.start_inspection(args[0], kind=args[1], scene_id=args[2], background=False)
        assert code(e) == expected
    rep = inspect(wf, "clean", gate="T8", kind="pre_arrival")
    view = wf.turn_view(rep["turn_id"])
    assert view["flight"] == "MANUAL" and view["latest_inspection_id"] == rep["inspection_id"]
    assert [e["type"] for e in view["events"]][:2] == ["stand_prep", "inspection_started"]
    assert view["inspections"][0]["inspection_id"] == rep["inspection_id"]


def test_store_keeps_findings_and_confirmations(wf, mixed):
    iid = mixed["inspection_id"]
    assert len(wf.store.list_findings(iid)) == 4
    wf.confirm_finding(iid, by_sev(mixed, "REMOVE")["finding_id"], outcome="not_found_on_walk", **AGENT)
    log = wf.store.list_confirmations(iid)
    assert [(c["action"], c["role"], c["name"]) for c in log] == [("not_found_on_walk", "ramp_agent", "Avi Agent")]
    assert {f["status"] for f in wf.store.list_findings(iid)} == {"open", "confirmed"}
    wf.reset()
    assert wf.store.get_report(iid) is None and wf.store.list_confirmations() == [] and wf.store.count_turns() == 0


def test_failed_manual_trigger_leaves_no_turn_behind(wf):
    with pytest.raises(WorkflowError):
        wf.start_inspection("T1", kind="pre_arrival", scene_id=None, background=False)
    assert wf.store.count_turns() == 0 and wf.gate_state("T1")[0]["status"] == "idle"


def test_timeline_is_picked_up_when_it_appears_later(wf, data_dir):
    import json
    assert wf.timeline["turns"] == [] and wf.gates == ["T1", "T2", "T4", "T5", "T8"]
    (data_dir / "demo").mkdir()
    (data_dir / "demo" / "timeline.json").write_text(json.dumps({"gates": ["T1", "T2", "T4", "T5", "T8"], "turns": [
        turn("T1", "T1-A", 100)]}))
    assert [t["turn_id"] for t in wf.timeline["turns"]] == ["T1-A"]
