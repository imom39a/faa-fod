import json

import pytest

from fodgate import config, pipeline, report as R
from fodgate.llm import LLM, LLMUnavailable, process_spend
from fodgate.scenes import load_scene
from tests.conftest import make_scene

OBJ = [400, 250, 416, 266]
REPORT_KEYS = {"schema_version", "rule_set_version", "inspection_id", "gate", "turn_id", "kind", "parent_inspection_id",
               "captured_at", "analysed_at", "verdict", "highest_open_severity", "missing_angles", "angles", "findings",
               "dismissed_candidates", "observations", "inspection_signoff", "run_metadata", "status"}
ANGLE_KEYS = {"angle", "image_ref", "camera_id", "crop", "status", "unusable_reason", "assessed_by",
              "source_inspection_id", "image_url", "reference_url", "width", "height", "checked_by_eye", "attribution",
              "analysis"}
FINDING_KEYS = {"finding_id", "angle", "image_ref", "bbox", "location_text", "zone_tier", "finding_type",
                "responsible_party", "category", "object_class", "size", "severity", "rule_id", "confidence",
                "description", "detected_by", "decided_by", "carried_from_inspection_id", "confirmation", "status",
                "rule", "crop_url", "reference_crop_url"}


def run(scene_id, llm, **kw):
    return pipeline.run_inspection(load_scene(scene_id), gate="T1", turn_id="turn-1", llm=llm, **kw)


# ---------------------------------------------------------------------- Verdict precedence
def _f(status="open", tier="critical"):
    return {"status": status, "zone_tier": tier, "severity": "HOLD"}


def _a(status="usable", eye=None):
    return {"angle": "NOSE", "status": status, "checked_by_eye": eye}


@pytest.mark.parametrize("findings,angles,expected", [
    ([], [_a()], "ALL_CLEAR"),
    ([], [_a(), _a("unusable")], "INCOMPLETE"),
    ([_f()], [_a()], "FINDINGS"),
    ([_f()], [_a("unusable")], "FINDINGS"),                       # FINDINGS > INCOMPLETE
    ([_f("confirmed")], [_a()], "ALL_CLEAR"),                     # carried, already closed by a Confirmation
    ([_f("confirmed")], [_a("unusable")], "INCOMPLETE"),
    ([_f("acknowledged")], [_a()], "FINDINGS"),                   # acknowledged is not cleared
    ([_f("acknowledged", "outside_boundary")], [_a()], "ALL_CLEAR"),  # reported to the airport counts as closed
    ([], [_a("unusable", {"by": {}, "at": ""})], "INCOMPLETE"),   # checked by eye does not make the cameras see
])
def test_verdict_precedence(findings, angles, expected):
    assert R.compute_verdict(findings, angles) == expected


# ---------------------------------------------------------------------- one Inspection
def test_report_shape_and_code_computed_severity(fake_llm, brain):
    make_scene("s1", objects={"ENG-L": [OBJ], "CARGO": [OBJ]})
    rep = run("s1", fake_llm)
    assert REPORT_KEYS <= set(rep)
    assert [a["angle"] for a in rep["angles"]] == config.ANGLES
    assert all(ANGLE_KEYS <= set(a) for a in rep["angles"])
    assert all(FINDING_KEYS <= set(f) for f in rep["findings"])
    assert (rep["schema_version"], rep["rule_set_version"], rep["kind"]) == ("0.1", "fod-rules v0.2", "pre_departure")
    assert rep["verdict"] == "FINDINGS" and rep["highest_open_severity"] == "HOLD" and rep["missing_angles"] == []
    assert rep["status"] == "awaiting_confirmation" and rep["inspection_signoff"] is None
    by_angle = {f["angle"]: f for f in rep["findings"]}
    assert set(by_angle) == {"ENG-L", "CARGO"}
    eng, cargo = by_angle["ENG-L"], by_angle["CARGO"]
    assert (eng["severity"], eng["rule_id"], eng["zone_tier"], eng["object_class"]) == ("HOLD", "FOD-R1", "critical", "hard")
    assert (cargo["severity"], cargo["rule_id"], cargo["zone_tier"]) == ("REMOVE", "FOD-R3", "service")
    assert eng["rule"]["id"] == "FOD-R1" and "basis" in eng["rule"]
    assert eng["detected_by"] == "local_proposer" and eng["decided_by"] == {"model": "haiku", "escalated": False}
    assert eng["status"] == "open" and eng["confirmation"] is None and eng["size"] == "S"
    assert abs(eng["bbox"][0] - OBJ[0]) < 12 and all(isinstance(v, int) for v in eng["bbox"])
    # the decision schema has no severity, zone or rule field: the model cannot set them (RU-3)
    schema_fields = set(pipeline.LLM.decide.__globals__["DECISION_SCHEMA"]["properties"]["decisions"]["items"]["properties"])
    assert not schema_fields & {"severity", "rule", "rule_id", "zone_tier"}


def test_urls_attribution_and_crops(fake_llm):
    make_scene("s1", objects={"ENG-L": [OBJ]})
    rep = run("s1", fake_llm)
    a = next(a for a in rep["angles"] if a["angle"] == "ENG-L")
    assert a["image_url"] == "/images/s1/ENG-L.jpg" and a["reference_url"] == "/images/s1/ref/ENG-L.jpg"
    assert a["image_ref"] == "s1/ENG-L.jpg" and (a["width"], a["height"]) == (960, 540)
    assert a["attribution"] == {"title": "synthetic ENG-L", "url": "https://example.invalid/x", "author": "tests",
                                "licence": "CC0", "derived": "mirror"}
    assert a["analysis"] == "change_detection" and a["source_inspection_id"] == rep["inspection_id"]
    f = rep["findings"][0]
    assert f["crop_url"].startswith(f"/images/_crops/{rep['inspection_id']}/")
    for url in (f["crop_url"], f["reference_crop_url"]):
        assert (config.crops_dir() / url.split("/_crops/")[1]).is_file()


def test_clean_scene_is_all_clear_with_safety_net_on_critical_angles_only(fake_llm, brain):
    make_scene("clean")
    rep = run("clean", fake_llm)
    assert rep["verdict"] == "ALL_CLEAR" and rep["findings"] == [] and rep["highest_open_severity"] is None
    assert sorted(c["angle"] for c in brain.of("findings")) == ["ENG-L", "ENG-R", "NOSE"]
    assert brain.of("decisions") == []                           # no Candidates, nothing to decide
    assert {c["purpose"] for c in rep["run_metadata"]["llm_calls"]} == {"safety_net"}


def test_decision_gets_current_and_reference_crops_context_and_rules(fake_llm, brain):
    make_scene("s1", objects={"CARGO": [OBJ]})
    run("s1", fake_llm)
    call = brain.of("decisions")[0]
    assert call["images"] == 3                                   # context frame + current crop + reference crop
    assert "CURRENT" in call["text"] and "REFERENCE" in call["text"] and "Context frame" in call["text"]
    assert "fod-rules v0.2" in call["system"] and "severity_matrix" in call["system"]
    assert call["model"] == "claude-haiku-5-5"


def test_rejected_candidates_are_dismissed_with_a_reason(fake_llm, brain):
    make_scene("s1", objects={"CARGO": [OBJ]})
    brain.verdict = lambda cid, angle: "not_fod"
    rep = run("s1", fake_llm)
    assert rep["verdict"] == "ALL_CLEAR" and rep["findings"] == []
    assert rep["dismissed_candidates"] == [{"angle": "CARGO", "bbox": rep["dismissed_candidates"][0]["bbox"],
                                            "reason": "verdict not_fod"}]


def test_observations_stay_out_of_the_verdict(fake_llm, brain):
    make_scene("s1", objects={"AFT": [OBJ]})
    brain.verdict = lambda cid, angle: "observation"
    rep = run("s1", fake_llm)
    assert rep["verdict"] == "ALL_CLEAR" and rep["observations"][0]["kind"] == "spill"
    assert rep["observations"][0]["angle"] == "AFT"


def test_safety_net_hit_becomes_candidate_through_the_decision_step(fake_llm, brain):
    make_scene("clean")
    brain.net_hits = {"NOSE": [[100, 100, 120, 120]]}
    rep = run("clean", fake_llm)
    assert len(brain.of("decisions")) == 1 and brain.of("decisions")[0]["angle"] == "NOSE"
    f = rep["findings"][0]
    assert (f["angle"], f["detected_by"], f["severity"], f["rule_id"]) == ("NOSE", "safety_net", "HOLD", "FOD-R2")
    assert f["bbox"] == [100, 100, 120, 120]


def test_safety_net_hit_on_an_existing_candidate_is_not_duplicated(fake_llm, brain):
    make_scene("s1", objects={"ENG-R": [OBJ]})
    brain.net_hits = {"ENG-R": [[398, 248, 418, 268]]}
    rep = run("s1", fake_llm)
    assert len(rep["findings"]) == 1 and rep["findings"][0]["detected_by"] == "local_proposer"


def test_no_reference_falls_back_to_tiled_pass_and_says_so(fake_llm, brain):
    make_scene("noref", objects={"CARGO": [OBJ]}, no_ref=("CARGO",))
    brain.net_hits = {"CARGO": [OBJ]}
    rep = run("noref", fake_llm)
    a = next(a for a in rep["angles"] if a["angle"] == "CARGO")
    assert a["analysis"] == "claude_tiled" and a["reference_url"] is None
    f = rep["findings"][0]
    assert f["detected_by"] == "claude" and f["reference_crop_url"] is None and f["severity"] == "REMOVE"
    assert any("no reference frame" in n for n in rep["run_metadata"]["notes"])
    decide = [c for c in brain.of("decisions") if c["angle"] == "CARGO"][0]
    assert decide["images"] == 2 and "no reference frame" in decide["text"]


def test_unusable_angles_local_and_declared_and_which_decided(fake_llm):
    make_scene("bad", missing=("AFT",), declared_unusable={"ENG-R": "glare"}, degrade={"NOSE": "blur"},
               objects={"CARGO": [OBJ]})
    rep = run("bad", fake_llm)
    got = {a["angle"]: (a["status"], a["unusable_reason"]) for a in rep["angles"]}
    assert got["AFT"] == ("unusable", "missing") and got["ENG-R"] == ("unusable", "glare")
    assert got["NOSE"] == ("unusable", "blur") and got["WIDE"] == ("usable", None)
    assert rep["missing_angles"] == ["NOSE", "ENG-R", "AFT"]
    assert rep["verdict"] == "FINDINGS"                          # FINDINGS takes precedence over INCOMPLETE
    decided = {u["angle"]: u["decided_by"] for u in rep["run_metadata"]["usability_checks"]}
    assert decided["ENG-R"] == "scene_declared" and decided["NOSE"] == "local_check"
    assert decided["AFT"] == "local_check+scene_declared" and decided["WIDE"] == "local_check"
    aft = next(a for a in rep["angles"] if a["angle"] == "AFT")
    assert aft["image_url"] is None and aft["analysis"] is None


def test_incomplete_when_only_an_angle_is_unusable(fake_llm):
    make_scene("glare", declared_unusable={"ENG-L": "glare"})
    rep = run("glare", fake_llm)
    assert rep["verdict"] == "INCOMPLETE" and rep["missing_angles"] == ["ENG-L"] and rep["highest_open_severity"] is None


def test_wide_envelope_routes_outside_boundary_to_airport(fake_llm, brain):
    inside, outside = [470, 400, 486, 416], [470, 90, 486, 106]
    make_scene("wide", objects={"WIDE": [inside, outside]})
    brain.category = lambda cid, angle: ("cargo_packaging", "light")
    rep = run("wide", fake_llm)
    by_tier = {f["zone_tier"]: f for f in rep["findings"]}
    assert set(by_tier) == {"general", "outside_boundary"}
    assert (by_tier["general"]["rule_id"], by_tier["general"]["severity"], by_tier["general"]["responsible_party"]) == \
        ("FOD-R4", "ADVISORY", "airline")
    assert (by_tier["outside_boundary"]["rule_id"], by_tier["outside_boundary"]["responsible_party"]) == ("FOD-R10", "airport")


def test_equipment_staging_at_pre_arrival_only(fake_llm, brain):
    make_scene("pa", kind="pre_arrival")
    brain.equipment = [[400, 350, 520, 450], [20, 220, 90, 280]]      # one inside the ERL, one outside it
    rep = run("pa", fake_llm)
    assert len(brain.of("equipment")) == 1
    staged = [f for f in rep["findings"] if f["finding_type"] == "equipment_staging"]
    assert len(staged) == 1 and staged[0]["bbox"] == [400, 350, 520, 450]
    assert (staged[0]["severity"], staged[0]["rule_id"], staged[0]["category"], staged[0]["angle"]) == \
        ("REMOVE", "FOD-R9", None, "WIDE")
    assert rep["verdict"] == "FINDINGS" and rep["highest_open_severity"] == "REMOVE"
    assert {c["purpose"] for c in rep["run_metadata"]["llm_calls"]} >= {"equipment_scan"}
    brain.calls.clear()
    make_scene("pd", kind="pre_departure")
    assert run("pd", fake_llm)["findings"] == [] and brain.of("equipment") == []


def test_equipment_candidate_inside_erl_is_staging_and_outside_is_dismissed(fake_llm, brain):
    make_scene("pa", kind="pre_arrival", objects={"WIDE": [[470, 400, 486, 416], [40, 230, 56, 246]]})
    brain.verdict = lambda cid, angle: "equipment"
    rep = run("pa", fake_llm)
    assert [f["finding_type"] for f in rep["findings"]] == ["equipment_staging"]
    assert len(rep["dismissed_candidates"]) == 1 and "normal position" in rep["dismissed_candidates"][0]["reason"]


def test_undecided_candidates_never_read_as_clear(fake_llm, brain):
    make_scene("s1", objects={"CARGO": [OBJ]})
    brain.skip_ids = {1}
    rep = run("s1", fake_llm)
    a = next(a for a in rep["angles"] if a["angle"] == "CARGO")
    assert (a["status"], a["unusable_reason"]) == ("unusable", "analysis_failed")
    assert rep["verdict"] == "INCOMPLETE" and "CARGO" in rep["missing_angles"]
    assert len([c for c in brain.of("decisions") if c["angle"] == "CARGO"]) == 2      # one retry


def test_api_stop_makes_angles_incomplete_not_clear(brain):
    def broke(**kw):
        raise LLMUnavailable("billing / credit error (HTTP 402)")
    make_scene("s1", objects={"CARGO": [OBJ]}, no_ref=("AFT",))
    rep = run("s1", LLM(transport=broke))
    got = {a["angle"]: a["unusable_reason"] for a in rep["angles"]}
    assert got["CARGO"] == "analysis_failed" and got["AFT"] == "analysis_failed"       # needed the reasoning step
    assert got["WIDE"] is None                                                         # no Candidates: local result stands
    assert rep["verdict"] == "INCOMPLETE" and rep["findings"] == []


def test_failed_safety_net_is_noted_but_local_result_stands(fake_llm, brain):
    make_scene("s1", objects={"NOSE": [OBJ]})
    brain.fail_purposes = {"findings"}
    rep = run("s1", fake_llm)
    assert next(a for a in rep["angles"] if a["angle"] == "NOSE")["status"] == "usable"
    assert len(rep["findings"]) == 1 and any("safety net" in n for n in rep["run_metadata"]["notes"])


def test_escalation_is_off_by_default_and_sonnet_behind_the_flag(brain):
    make_scene("s1", objects={"ENG-L": [OBJ], "CARGO": [OBJ]})
    brain.confidence = lambda cid, angle: "low"
    rep = run("s1", LLM(transport=brain))
    assert {c["model"] for c in brain.calls} == {"claude-haiku-5-5"}
    assert rep["run_metadata"]["timings_ms"]["sonnet"] == 0
    brain.calls.clear()
    rep = run("s1", LLM(transport=brain, escalation="sonnet", use_cache=False))
    sonnet = [c for c in brain.calls if c["model"] == "claude-sonnet-5-5"]
    assert [c["angle"] for c in sonnet] == ["ENG-L"]                                   # Critical Angles only
    eng = next(f for f in rep["findings"] if f["angle"] == "ENG-L")
    assert eng["decided_by"] == {"model": "sonnet", "escalated": True}
    assert next(f for f in rep["findings"] if f["angle"] == "CARGO")["decided_by"]["model"] == "haiku"
    assert "escalate" in {c["purpose"] for c in rep["run_metadata"]["llm_calls"]}


def test_opus_is_never_allowed(monkeypatch, brain):
    with pytest.raises(ValueError):
        LLM(transport=brain, decision_model="claude-opus-5-5")
    monkeypatch.setenv("FOD_DECISION_MODEL", "claude-opus-5-5")
    with pytest.raises(ValueError):
        LLM(transport=brain)
    with pytest.raises(ValueError):
        LLM(transport=brain, decision_model="claude-haiku-5-5").call_json(
            purpose="decide", model="claude-opus-5-5", system="", content=[], schema={"properties": {"x": {}}})


def test_cache_and_cost_accounting(brain):
    make_scene("s1", objects={"CARGO": [OBJ]})
    first = run("s1", LLM(transport=brain))
    n = len(brain.calls)
    calls = first["run_metadata"]["llm_calls"]
    assert n == len(calls) == 4 and all(not c["cached"] for c in calls)
    assert all(c["tokens_in"] == 1000 and c["tokens_out"] == 200 for c in calls)
    per_call = (1000 * 0.10 + 200 * 0.50) / 1e6
    assert calls[0]["est_cost_usd"] == pytest.approx(per_call)
    assert first["run_metadata"]["est_cost_usd"] == pytest.approx(4 * per_call)
    assert process_spend()["usd"] == pytest.approx(4 * per_call) and process_spend()["calls"] == 4
    assert len(list(config.cache_dir().glob("*.json"))) == 4
    again = run("s1", LLM(transport=brain))
    assert len(brain.calls) == n                                   # replay: nothing sent
    assert all(c["cached"] for c in again["run_metadata"]["llm_calls"])
    assert again["run_metadata"]["spent_usd"] == 0 and again["run_metadata"]["est_cost_usd"] == pytest.approx(4 * per_call)
    assert process_spend()["calls"] == 4
    assert [f["bbox"] for f in again["findings"]] == [f["bbox"] for f in first["findings"]]
    run("s1", LLM(transport=brain, use_cache=False))
    assert len(brain.calls) == 2 * n


def test_spend_cap_stops_calls(monkeypatch, brain):
    monkeypatch.setenv("FOD_MAX_SPEND_USD", "0.0000001")
    make_scene("s1", objects={"CARGO": [OBJ]})
    llm = LLM(transport=brain, use_cache=False)
    run("s1", llm)
    assert llm.available()[0] is False and "spend cap" in llm.available()[1]


def test_dry_run_proposes_candidates_without_any_call(brain):
    make_scene("s1", objects={"CARGO": [OBJ]})
    rep, details = run("s1", None, return_details=True)
    assert rep["verdict"] is None and rep["findings"] == [] and brain.calls == []
    assert rep["run_metadata"]["candidates"]["CARGO"] == 1 and len(details["CARGO"].candidates) == 1
    assert rep["run_metadata"]["llm_calls"] == []


def test_night_angle_notes_skipped_dino(fake_llm):
    make_scene("night", light="night")
    rep = run("night", fake_llm)
    assert any("DINOv2 step skipped (FOD_DINO_WEIGHTS is not set)" in n for n in rep["run_metadata"]["notes"])
    assert all(a["analysis"] == "change_detection" for a in rep["angles"])


# ---------------------------------------------------------------------- on-demand re-inspection
def test_reinspection_inherits_other_angles(fake_llm, brain):
    make_scene("s1", objects={"ENG-L": [OBJ], "CARGO": [OBJ]}, after_clean=("ENG-L",))
    parent = run("s1", fake_llm)
    brain.calls.clear()
    child = pipeline.run_inspection(load_scene("s1"), gate="T1", turn_id="turn-1", llm=fake_llm, parent=parent,
                                    angles=["ENG-L"])
    assert (child["kind"], child["parent_inspection_id"]) == ("on_demand", parent["inspection_id"])
    assert {c["angle"] for c in brain.calls} == {"ENG-L"}                       # only that Angle was analysed
    src = {a["angle"]: a["source_inspection_id"] for a in child["angles"]}
    assert src["ENG-L"] == child["inspection_id"] and src["CARGO"] == parent["inspection_id"]
    assert next(a for a in child["angles"] if a["angle"] == "ENG-L")["image_ref"] == "s1/after/ENG-L.jpg"
    cargo = next(f for f in child["findings"] if f["angle"] == "CARGO")
    assert cargo["carried_from_inspection_id"] == parent["inspection_id"]
    assert cargo["finding_id"].startswith(child["inspection_id"])
    assert cargo["crop_url"].startswith(f"/images/_crops/{parent['inspection_id']}/")
    # the HOLD was not seen in the new frame, but only a Confirmation closes a Finding: it is carried, still open
    eng = next(f for f in child["findings"] if f["angle"] == "ENG-L")
    assert eng["status"] == "open" and eng["carried_from_inspection_id"] == parent["inspection_id"]
    assert pipeline.carried_copy(child, parent["findings"][0]) is not None
    assert child["verdict"] == "FINDINGS" and child["highest_open_severity"] == "HOLD"
    assert any("not seen in the new frame" in n for n in child["run_metadata"]["notes"])


def test_reinspection_replaces_a_finding_that_is_seen_again(fake_llm):
    make_scene("s1", objects={"ENG-L": [OBJ]})                                   # no `after` frame: same image
    parent = run("s1", fake_llm)
    parent["findings"][0]["status"] = "acknowledged"
    parent["findings"][0]["acknowledged"] = {"by": {"role": "ramp_lead", "name": "Sam"}, "at": "t"}
    child = pipeline.run_inspection(load_scene("s1"), gate="T1", turn_id="turn-1", llm=fake_llm, parent=parent,
                                    angles=["ENG-L"])
    assert len(child["findings"]) == 1
    f = child["findings"][0]
    assert f["carried_from_inspection_id"] is None and f["status"] == "acknowledged"   # fresh sighting, still acknowledged
    assert pipeline.carried_copy(child, parent["findings"][0]) is None


def test_reinspection_can_turn_an_unusable_angle_usable(fake_llm):
    make_scene("s1", declared_unusable={"ENG-R": "glare"}, after_clean=("ENG-R",))
    parent = run("s1", fake_llm)
    assert parent["verdict"] == "INCOMPLETE"
    child = pipeline.run_inspection(load_scene("s1"), gate="T1", turn_id="turn-1", llm=fake_llm, parent=parent,
                                    angles=["ENG-R"])
    assert child["verdict"] == "ALL_CLEAR" and child["missing_angles"] == []
    same = pipeline.run_inspection(load_scene("s1"), gate="T1", turn_id="turn-1", llm=fake_llm, parent=parent,
                                   angles=["NOSE"])
    assert same["verdict"] == "INCOMPLETE" and same["missing_angles"] == ["ENG-R"]      # inherited as it was


def test_report_is_json_serialisable(fake_llm):
    make_scene("s1", objects={"ENG-L": [OBJ]})
    assert json.loads(json.dumps(run("s1", fake_llm)))["findings"]
