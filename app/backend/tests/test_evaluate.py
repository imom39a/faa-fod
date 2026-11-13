import json

from fodgate import config, evaluate
from tests.conftest import make_scene

OBJ = [400, 250, 416, 266]


def test_match_is_one_to_one_by_distance_or_overlap():
    truth = [{"bbox": [0, 0, 10, 10]}, {"bbox": [500, 500, 510, 510]}]
    found = [{"bbox": [3, 3, 13, 13]}, {"bbox": [5, 5, 15, 15]}, {"bbox": [900, 900, 910, 910]}]
    pairs, missed, extra = evaluate.match(truth, found, radius=20)
    assert pairs == [(0, 0)] and missed == [1] and extra == [1, 2]


def scenes(data_dir):
    make_scene("a", objects={"ENG-L": [OBJ], "CARGO": [OBJ]}, truth_class={"CARGO": ("tools", "hard", "REMOVE")})
    make_scene("b", declared_unusable={"NOSE": "glare"})
    make_scene("c")
    (data_dir / "testset.json").write_text(json.dumps({"scenes": ["a", "b", "c", "not-there"]}))


def test_full_evaluation_with_mocked_llm(data_dir, fake_llm, tmp_path):
    scenes(data_dir)
    result = evaluate.run(llm=fake_llm, out_dir=tmp_path / "eval")
    s = result["summary"]
    assert (s["objects"], s["found"], s["recall_overall"], s["recall_critical"]) == (2, 2, 1.0, 1.0)
    assert s["false_alarms_per_clean_angle"] == 0.0 and s["clean_angles"] == 15
    assert s["severity_agreement"] == 1.0 and s["severity_compared"] == 2
    assert s["unusable_angles"] == {"expected": 1, "detected": 1, "usable_angles_wrongly_unusable": 0}
    assert s["incomplete_correct"] == 1.0 and s["verdict_correct"] == 1.0 and s["inspections"] == 3
    assert s["by_derivation"]["mirrored_or_cropped"]["objects"] == 1 and s["by_derivation"]["native"]["objects"] == 1
    assert s["cost_per_inspection_mean"] > 0 and s["latency_s_mean"] > 0
    assert [i["expected_verdict"] for i in result["inspections"]] == ["FINDINGS", "INCOMPLETE", "ALL_CLEAR"]
    assert result["skipped"] == {"not-there": "scene.json not found"}
    assert {t["target"][:4]: t["met"] for t in result["targets"]} == {"NF-1": True, "NF-2": True, "NF-3": True}
    assert json.loads((tmp_path / "eval" / "results.json").read_text())["summary"] == s
    md = (tmp_path / "eval" / "summary.md").read_text()
    assert "Mirrored or cropped" in md and "NF-3 recall in Critical zones" in md and "not-there" in md


def test_misses_false_alarms_and_severity_disagreement_are_counted(data_dir, fake_llm, brain, tmp_path):
    make_scene("a", objects={"ENG-L": [OBJ]}, truth_class={"ENG-L": ("tools", "hard", "REMOVE")})   # truth disagrees
    make_scene("b", objects={"CARGO": [OBJ]})
    (data_dir / "testset.json").write_text(json.dumps({"scenes": ["a", "b"]}))
    brain.verdict = lambda cid, angle: "not_fod" if angle == "CARGO" else "fod"                       # misses CARGO
    brain.net_hits = {"NOSE": [[100, 100, 120, 120]]}                                                # a false alarm
    s = evaluate.run(llm=fake_llm, out_dir=tmp_path)["summary"]
    assert (s["found"], s["objects"], s["recall_overall"]) == (1, 2, 0.5)
    assert s["false_alarms_on_clean_angles"] == 2 and s["severity_agreement"] == 0.0
    met = {t["target"]: t["met"] for t in evaluate.targets(s, False)}
    assert met["NF-3 recall overall"] is False and met["NF-3 recall in Critical zones"] is True


def test_dry_run_and_limit_make_no_api_calls(data_dir, brain, tmp_path, capsys):
    scenes(data_dir)
    assert evaluate.main(["--dry-run", "--limit", "2", "--out", str(tmp_path)]) == 0
    result = json.loads((tmp_path / "results.json").read_text())
    assert result["dry_run"] is True and result["summary"]["inspections"] == 2 and brain.calls == []
    assert result["summary"]["recall_overall"] == 1.0 and "cost_per_inspection_mean" not in result["summary"]
    assert not list(config.cache_dir().glob("*.json"))
    assert "dry run" in capsys.readouterr().out
