import json
from types import SimpleNamespace

import pytest

from fodgate import assistant, pipeline
from fodgate.scenes import load_scene
from fodgate.workflow import WorkflowError
from tests.conftest import make_scene


@pytest.fixture
def report(fake_llm, brain):
    make_scene("s", objects={"ENG-L": [[400, 250, 416, 266]], "WIDE": [[470, 90, 486, 106]]},
               declared_unusable={"AFT": "blur"})
    return pipeline.run_inspection(load_scene("s"), gate="T1", turn_id="t", llm=fake_llm)


def msg(stop, *blocks):
    return SimpleNamespace(stop_reason=stop, content=list(blocks), usage=SimpleNamespace(input_tokens=100, output_tokens=20))


def tool_use(i, name, **inp):
    return SimpleNamespace(type="tool_use", id=f"tu_{i}", name=name, input=inp)


def test_tools_are_exactly_the_five_read_only_ones():
    assert assistant.TOOL_NAMES == ["get_report", "get_finding", "get_rule", "list_unusable_angles",
                                    "draft_outside_boundary_report"]
    for t in assistant.TOOLS:
        assert t["strict"] is True and t["input_schema"]["additionalProperties"] is False
        assert not any(w in t["name"] for w in ("confirm", "set", "update", "sign", "clear", "delete"))


def test_tools_read_the_report_and_never_change_it(report):
    before = json.dumps(report, sort_keys=True)
    tools = assistant.Tools(report, {"flight": "DL1432"})
    summary = tools.get_report()
    assert summary["verdict"] == "FINDINGS" and len(summary["findings"]) == 2
    hold = next(f for f in report["findings"] if f["severity"] == "HOLD")
    assert tools.get_finding(hold["finding_id"])["rule"]["id"] == "FOD-R1"
    assert tools.get_rule("fod-r10")["id"] == "FOD-R10"
    assert tools.list_unusable_angles() == [{"angle": "AFT", "unusable_reason": "blur", "checked_by_eye": None}]
    draft = tools.draft_outside_boundary_report("airport_operations", [])
    assert draft.startswith("To: Airport Operations") and "FOD-R10" in draft and "T1" in draft and "DL1432" in draft
    assert "A person must review it" in draft and tools.draft == draft
    assert tools.call("get_rule", {"rule_id": "FOD-R99"})[1] is True
    assert tools.call("confirm_finding", {"finding_id": hold["finding_id"]}) == ("Unknown tool confirm_finding", True)
    assert tools.call("get_finding", {"finding_id": "nope"})[1] is True
    assert json.dumps(report, sort_keys=True) == before


def test_draft_says_so_when_nothing_is_outside_the_envelope(report):
    report = dict(report, findings=[f for f in report["findings"] if f["zone_tier"] != "outside_boundary"])
    tools = assistant.Tools(report)
    assert "nothing to report" in tools.draft_outside_boundary_report("ramp_1_control", []) and tools.draft is None


def test_agent_loop_runs_tools_and_returns_the_contract_shape(report):
    seen = []

    def create(**kw):
        seen.append(kw)
        if len(seen) == 1:
            return msg("tool_use", SimpleNamespace(type="thinking", thinking="", signature="sig"),
                       tool_use(1, "list_unusable_angles"), tool_use(2, "get_rule", rule_id="FOD-R99"),
                       tool_use(3, "draft_outside_boundary_report", recipient="ramp_1_control", finding_ids=[]))
        return msg("end_turn", SimpleNamespace(type="text", text=json.dumps(
            {"reply": "AFT is blurred; re-inspect it.", "suggested_reinspect_angles": ["AFT", "ENG-L"]})))

    out = assistant.answer(report=report, message="What should I re-inspect?", llm=None, create=create)
    assert out["reply"] == "AFT is blurred; re-inspect it."
    assert out["suggested_reinspect_angles"] == ["ENG-L", "AFT"]              # canonical Angle order
    assert out["draft_report"].startswith("To: Ramp 1 control")
    assert out["usage"]["tokens_in"] == 200 and out["usage"]["purpose"] == "workflow"
    first, second = seen
    assert first["model"] == "claude-haiku-5-5" and [t["name"] for t in first["tools"]] == assistant.TOOL_NAMES
    assert first["output_config"]["format"]["type"] == "json_schema" and "tool_choice" not in first
    # the assistant turn goes back unchanged (thinking block included) and all tool results in one user message
    assert second["messages"][1]["content"][0].type == "thinking"
    results = second["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2", "tu_3"]
    assert [r["is_error"] for r in results] == [False, True, False]


def test_agent_falls_back_to_plain_text_and_filters_bad_angles(report):
    out = assistant.answer(report=report, message="hi", llm=None,
                           create=lambda **kw: msg("end_turn", SimpleNamespace(type="text", text="plain words")))
    assert out == {"reply": "plain words", "suggested_reinspect_angles": [], "draft_report": None, "usage": out["usage"]}
    out = assistant.answer(report=report, message="hi", llm=None, create=lambda **kw: msg(
        "end_turn", SimpleNamespace(type="text", text=json.dumps({"reply": "x", "suggested_reinspect_angles": ["TAIL", "NOSE"]}))))
    assert out["suggested_reinspect_angles"] == ["NOSE"]


def test_agent_stops_after_max_turns_and_needs_a_configured_api(report):
    out = assistant.answer(report=report, message="hi", llm=None,
                           create=lambda **kw: msg("tool_use", tool_use(1, "get_report")))
    assert "could not finish" in out["reply"]
    with pytest.raises(WorkflowError) as e:
        assistant.answer(report=report, message="hi", llm=None)
    assert (e.value.status, e.value.code) == (503, "assistant_unavailable")
