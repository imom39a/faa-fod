import json

import pytest

from fodgate import config
from fodgate.rules import (highest_severity, is_equipment_staging, load_rules, point_in_polygon, size_class)

SQUARE = [[100, 100], [300, 100], [300, 300], [100, 300]]

# spec/fod-rules.md severity matrix (General column repeated for outside boundary, where it is "displayed")
MATRIX = {
    ("hard", "critical"): "HOLD", ("hard", "service"): "REMOVE", ("hard", "general"): "REMOVE",
    ("light", "critical"): "HOLD", ("light", "service"): "REMOVE", ("light", "general"): "ADVISORY",
    ("unidentified", "critical"): "HOLD", ("unidentified", "service"): "REMOVE", ("unidentified", "general"): "REMOVE",
    ("natural", "critical"): "HOLD", ("natural", "service"): "REMOVE", ("natural", "general"): "ADVISORY",
    ("hard", "outside_boundary"): "REMOVE", ("light", "outside_boundary"): "ADVISORY",
    ("unidentified", "outside_boundary"): "REMOVE", ("natural", "outside_boundary"): "ADVISORY",
}


@pytest.fixture
def rules():
    return load_rules()


def test_loads_rule_set_version(rules):
    assert rules.version == "fod-rules v0.2"
    assert {r for r in rules.categories} >= {"fasteners_hardware", "natural", "unidentified"}


@pytest.mark.parametrize("cell,expected", MATRIX.items())
def test_severity_matrix(rules, cell, expected):
    assert rules.severity(*cell) == expected


def test_matrix_in_code_is_the_json_copy(rules):
    raw = json.loads(config.rules_path().read_text())["severity_matrix"]
    assert all(rules.severity(oc, tier) == sev for oc, row in raw.items() for tier, sev in row.items())


@pytest.mark.parametrize("angle,tier", [("NOSE", "critical"), ("ENG-L", "critical"), ("ENG-R", "critical"),
                                        ("CARGO", "service"), ("AFT", "service"), ("WIDE", "general")])
def test_zone_tier_from_angle(rules, angle, tier):
    assert rules.zone_tier(angle) == tier


def test_zone_tier_wide_with_envelope(rules):
    assert rules.zone_tier("WIDE", [190, 190, 210, 210], SQUARE) == "general"            # centre inside
    assert rules.zone_tier("WIDE", [400, 400, 420, 420], SQUARE) == "outside_boundary"   # centre outside
    assert rules.zone_tier("WIDE", [290, 190, 330, 210], SQUARE) == "outside_boundary"   # straddles, centre out
    assert rules.zone_tier("WIDE", [400, 400, 420, 420], None) == "general"              # no polygon mapped


def test_envelope_only_applies_to_wide(rules):
    assert rules.zone_tier("ENG-L", [400, 400, 420, 420], SQUARE) == "critical"


def test_point_in_polygon_concave_and_edges():
    l_shape = [[0, 0], [10, 0], [10, 4], [4, 4], [4, 10], [0, 10]]
    assert point_in_polygon((2, 8), l_shape) and point_in_polygon((8, 2), l_shape)
    assert not point_in_polygon((8, 8), l_shape)
    assert point_in_polygon((0, 5), l_shape)       # on an edge counts as inside


@pytest.mark.parametrize("category,hint,expected", [
    ("fasteners_hardware", None, "hard"), ("fasteners_hardware", "light", "hard"),   # hint cannot soften hardware
    ("tools", "light", "hard"),
    ("luggage_parts", None, "hard"), ("luggage_parts", "light", "light"),            # bag tags count as light
    ("catering_flightline", None, "light"), ("catering_flightline", "hard", "hard"),  # cans / pens count as hard
    ("cargo_packaging", "hard", "light"),
    ("natural", "hard", "natural"), ("unidentified", "light", "unidentified"),
    ("not_a_category", None, "unidentified"), ("pavement_construction", "unsure", "hard"),
])
def test_object_class_from_category_and_hint(rules, category, hint, expected):
    assert rules.object_class(category, hint) == expected


@pytest.mark.parametrize("angle,tier,ftype,rule", [
    ("ENG-L", "critical", "fod", "FOD-R1"), ("ENG-R", "critical", "fod", "FOD-R1"), ("NOSE", "critical", "fod", "FOD-R2"),
    ("CARGO", "service", "fod", "FOD-R3"), ("AFT", "service", "fod", "FOD-R3"), ("WIDE", "general", "fod", "FOD-R4"),
    ("WIDE", "outside_boundary", "fod", "FOD-R10"), ("WIDE", "general", "equipment_staging", "FOD-R9"),
])
def test_rule_id_selection(rules, angle, tier, ftype, rule):
    assert rules.rule_id(angle, tier, ftype) == rule


def test_classify_puts_it_together(rules):
    c = rules.classify(angle="ENG-L", bbox=[10, 10, 30, 30], category="cargo_packaging", hint="light")
    assert (c["severity"], c["rule_id"], c["zone_tier"], c["object_class"], c["responsible_party"]) == \
        ("HOLD", "FOD-R1", "critical", "light", "airline")
    assert c["rule"]["text"] and c["rule"]["basis"] and c["rule"]["also"] == []
    out = rules.classify(angle="WIDE", bbox=[400, 400, 420, 420], category="cargo_packaging", envelope=SQUARE)
    assert (out["severity"], out["rule_id"], out["responsible_party"]) == ("ADVISORY", "FOD-R10", "airport")
    unk = rules.classify(angle="CARGO", bbox=[0, 0, 5, 5], category="unidentified")
    assert unk["severity"] == "REMOVE" and unk["rule"]["also"] == ["FOD-R5"]


def test_equipment_staging_fod_r9(rules):
    inside, outside = [150, 150, 250, 250], [400, 100, 500, 200]
    assert is_equipment_staging("pre_arrival", "WIDE", inside, SQUARE)
    assert not is_equipment_staging("pre_arrival", "WIDE", outside, SQUARE)
    assert not is_equipment_staging("pre_departure", "WIDE", inside, SQUARE)      # only before arrival
    assert not is_equipment_staging("pre_arrival", "CARGO", inside, SQUARE)       # regions are mapped in WIDE only
    assert not is_equipment_staging("pre_arrival", "WIDE", inside, None)
    # a tall vehicle whose wheels (bottom centre) are inside the line counts even if its centre is not
    assert is_equipment_staging("pre_arrival", "WIDE", [150, 0, 250, 120], SQUARE)
    c = rules.classify_equipment_staging(angle="WIDE", bbox=inside, envelope=SQUARE)
    assert (c["severity"], c["rule_id"], c["finding_type"], c["category"]) == ("REMOVE", "FOD-R9", "equipment_staging", None)


def test_roles(rules):
    assert rules.role_may_confirm("ramp_lead", "HOLD") and not rules.role_may_confirm("ramp_agent", "HOLD")
    assert rules.role_may_confirm("ramp_agent", "REMOVE") and rules.role_may_confirm("ramp_agent", "ADVISORY")
    assert not rules.role_may_confirm("pilot", "ADVISORY")


def test_highest_severity_and_size():
    assert highest_severity(["ADVISORY", "HOLD", "REMOVE"]) == "HOLD"
    assert highest_severity(["ADVISORY", "REMOVE"]) == "REMOVE"
    assert highest_severity([]) is None
    assert [size_class([0, 0, s, 5]) for s in (10, 40, 200)] == ["S", "M", "L"]
