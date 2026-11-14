"""The agent eval suite (issue #6), run with the model mocked. No API calls."""
import json

import pytest

from fodgate import agent_evals as E, llm as llm_mod
from fodgate.dispatch.agent import AgentUnavailable


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_the_scenario_files_meet_the_coverage_the_ticket_asks_for():
    scs = E.load_scenarios()
    assert len(scs) >= 30
    tags = [t for s in scs for t in s.get("tags", [])]
    assert tags.count("adversarial") >= 8 and tags.count("report") >= 10
    ids = {s["id"] for s in scs}
    for needed in ("route-hold", "route-remove", "route-hold-and-remove", "route-incomplete", "route-outside",
                   "route-no-ramp-lead-on-shift", "route-two-gates", "route-clean"):
        assert needed in ids
    for s in scs:                                              # each states its setup, the event and the expected outcome
        assert s["title"] and s["steps"] and s["expect"]
    scenes = E.load_scenes()
    assert all("description" in v for v in scenes.values())


def test_a_scenario_file_with_a_mistake_is_rejected_with_its_name(tmp_path):
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "scenes.json").write_text(json.dumps({"clean": {"description": "x", "kind": "pre_arrival"}}))
    good = {"id": "a", "title": "t", "steps": [{"inspect": {"scene": "clean"}}], "expect": {"model_calls": 0}}
    for bad, why in (({**good, "expect": {"taskz": []}}, "unknown expect key"),
                     ({**good, "steps": [{"inspect": {"scene": "nope"}}]}, "unknown scene"),
                     ({**good, "steps": [{"teleport": 1}]}, "each step is one of"),
                     ({**good, "id": "b"}, "must match the file name")):
        (tmp_path / "scenarios" / "a.json").write_text(json.dumps(bad))
        with pytest.raises(E.ScenarioError) as e:
            E.load_scenarios(tmp_path)
        assert why in str(e.value) and "a.json" in str(e.value)
    (tmp_path / "scenarios" / "a.json").write_text(json.dumps(good))
    assert [s["id"] for s in E.load_scenarios(tmp_path)] == ["a"]


def test_dry_run_passes_every_scenario_and_makes_no_api_call(no_key, tmp_path):
    result = E.run(dry_run=True)
    failed = [(r["id"], [c for c in r["checks"] if not c["ok"]]) for r in result["results"] if not r["passed"]]
    assert failed == []
    assert result["scenarios_run"] == result["scenarios_total"] >= 30
    assert result["safety_violations"] == 0 and result["stopped_early"] is None
    assert result["cost"]["total_usd"] == 0 and result["cost"]["idle_model_calls"] == 0
    assert llm_mod.process_spend()["usd"] == 0                  # not even the stand-in vision model is billed
    assert E.exit_code(result) == 0 and E.exit_code(result, strict=True) == 0
    for a in E.AREAS:
        assert result["areas"][a]["scenarios"] > 0 and result["areas"][a]["met"] is True
    md = E.markdown(result)
    assert "| Safety |" in md and "## Failed scenarios (0)" in md and "Safety violations: **0**" in md


def test_a_subset_runs_only_what_was_asked(no_key):
    result = E.run(dry_run=True, only=["esc-", "route-clean"])
    ids = [r["id"] for r in result["results"]]
    assert "route-clean" in ids and all(i.startswith("esc-") or i == "route-clean" for i in ids) and len(ids) >= 5


def test_a_confirmation_that_no_person_made_is_a_safety_violation_and_fails_the_run(no_key):
    harness = {}

    class Rogue(E.ScriptedAgent):
        """A stand-in that reaches round the tools and confirms a Finding itself."""
        def __call__(self, **kw):
            h = harness["h"]
            if len(kw["messages"]) == 1:
                _, rep, f = h.d.board.resolve("F1")
                h.wf.confirm_finding(rep["inspection_id"], f["finding_id"], outcome="removed", role="ramp_agent", name="Kim")
            return super().__call__(**kw)

    real = E.Harness

    def make(**kw):
        harness["h"] = real(**kw)
        return harness["h"]
    E.Harness = make
    try:
        result = E.run(only=["report-done-plain"], create=Rogue())
    finally:
        E.Harness = real
    (r,) = result["results"]
    bad = [c for c in r["checks"] if not c["ok"] and c["area"] == "safety"]
    assert any("signed-in person's own action" in c["name"] for c in bad)
    assert result["safety_violations"] >= 1 and E.exit_code(result) == 2
    assert "(the run fails)" in E.markdown(result)


def test_a_wrong_agent_fails_the_right_areas_without_touching_safety(no_key):
    class Lazy(E.ScriptedAgent):                                # never logs a Report, never replies
        @staticmethod
        def _human_message(ctx):
            return []
    result = E.run(only=["report-", "route-hold"], create=Lazy())
    assert result["areas"]["reports"]["met"] is False and result["areas"]["reports"]["scenarios_passed"] < 5
    assert result["safety_violations"] == 0 and E.exit_code(result) == 0 and E.exit_code(result, strict=True) == 1
    md = E.markdown(result)
    assert "### `report-done-plain`" in md and "expected:" in md and "happened:" in md
    # a failing model is not a crash: code routed what it had to
    down = E.run(only=["route-remove"], create=lambda **kw: (_ for _ in ()).throw(AgentUnavailable("down")))
    assert down["results"][0]["passed"]


def test_the_spend_cap_stops_a_live_run_and_says_what_was_not_run(monkeypatch):
    monkeypatch.setattr(E.LLM, "available", lambda self: (True, "ok"))
    spent = {"n": 0}

    def costly(**kw):                                           # each request "costs" real money
        spent["n"] += 1
        llm_mod.add_spend("claude-haiku-5-5", 400_000, 0)
        return E.ScriptedAgent()(**kw)
    real = E.Harness

    def make(*, live, create, root):
        h = real(live=False, create=costly, root=root)          # live accounting, scripted answers
        h.agent_llm = E.LLM()
        return h
    monkeypatch.setattr(E, "Harness", make)
    result = E.run(only=["route-", "report-"], max_usd=0.50)
    assert result["stopped_early"] and "spend cap" in result["stopped_early"]
    assert 0 < result["scenarios_run"] < result["scenarios_total"]
    assert E.exit_code(result) == 3 and "not run" in E.markdown(result)


def test_two_runs_are_compared_scenario_by_scenario(no_key):
    first = E.run(dry_run=True, only=["report-done", "report-not-found"])

    class Forgetful(E.ScriptedAgent):
        @staticmethod
        def _human_message(ctx):
            return [] if "typos" not in ctx["messages"][0]["text"] and "dne" in ctx["messages"][0]["text"] else \
                E.ScriptedAgent._human_message(ctx)
    second = E.run(only=["report-done", "report-not-found"], create=Forgetful())
    diff = E.compare(second, first)
    assert diff["compared"] == len(first["results"]) and diff["changed"] == 1
    assert diff["scenarios"] == [{"id": "report-done-typos", "before": "pass", "now": "fail"}]
    assert "Stability: 1 of" in E.markdown(second, diff)
    assert E.compare(first, first)["changed"] == 0


def test_command_line_writes_results_and_a_summary(no_key, tmp_path, capsys):
    code = E.main(["--dry-run", "--only", "cost-", "--out", str(tmp_path)])
    assert code == 0
    doc = json.loads((tmp_path / "results.json").read_text())
    assert doc["scenarios_run"] == 2 and (tmp_path / "summary.md").read_text().startswith("# Agent eval results")
    assert E.main(["--dry-run", "--only", "cost-", "--out", str(tmp_path), "--compare", str(tmp_path / "results.json")]) == 0
    assert "Stability: 0 of 2" in (tmp_path / "summary.md").read_text()
    assert E.main(["--list", "--only", "adv-"]) == 0
    assert "adv-claims-ramp-lead" in capsys.readouterr().out
