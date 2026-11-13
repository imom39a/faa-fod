"""The FOD rule set in code (spec/fod-rules.md v0.2, machine-readable copy in fod-rules.json).

Severity, zone tier and rule ID are always computed here, never taken from the model (RU-3).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from . import config

SEVERITY_ORDER = {"HOLD": 0, "REMOVE": 1, "ADVISORY": 2}
ENGINE_ANGLES = ("ENG-L", "ENG-R")

Polygon = Sequence[Sequence[float]]
Box = Sequence[float]


class RuleSet:
    def __init__(self, data: dict):
        self.data = data
        self.version: str = data["version"]
        self.angle_zone_tier: dict[str, str] = data["angle_zone_tier"]
        self.categories: dict[str, dict] = data["categories"]
        self.matrix: dict[str, dict[str, str]] = data["severity_matrix"]
        self.rule_for: dict[str, str] = data["rule_for"]
        self.roles: dict[str, list[str]] = data["roles"]
        self._rules = {r["id"]: r for r in data["rules"]}

    # ------------------------------------------------------------------ lookups
    def rule(self, rule_id: str) -> dict | None:
        r = self._rules.get(rule_id)
        return None if r is None else {"id": r["id"], "text": r["text"], "basis": r["basis"]}

    def critical_angles(self) -> list[str]:
        return [a for a, t in self.angle_zone_tier.items() if t == "critical"]

    # ------------------------------------------------------------------ zone tier
    def zone_tier(self, angle: str, bbox: Box | None = None, envelope: Polygon | None = None) -> str:
        """Zone tier of a Finding. Non-WIDE Angles carry their own tier. In WIDE, an object whose centre lies
        outside the gate safety envelope polygon is `outside_boundary`; with no polygon it is `general`."""
        tier = self.angle_zone_tier[angle]
        if angle == "WIDE" and envelope and bbox is not None:
            if not point_in_polygon(box_centre(bbox), envelope):
                return "outside_boundary"
        return tier

    # ------------------------------------------------------------------ object class
    def object_class(self, category: str, hint: str | None = None) -> str:
        """Object class from the category default, adjusted by the model's hard/light hint only where the rule
        set allows it: bag tags (luggage parts) count as light; metal catering items count as hard."""
        if category not in self.categories:
            category = "unidentified"
        default = self.categories[category]["default_class"]
        if category == "luggage_parts" and hint == "light":
            return "light"
        if category == "catering_flightline" and hint == "hard":
            return "hard"
        return default

    # ------------------------------------------------------------------ severity and rule
    def severity(self, object_class: str, zone_tier: str) -> str:
        return self.matrix[object_class][zone_tier]

    def rule_id(self, angle: str, zone_tier: str, finding_type: str = "fod") -> str:
        if finding_type == "equipment_staging":
            return self.rule_for["equipment_staging"]
        if zone_tier == "outside_boundary":
            return self.rule_for["outside_boundary"]
        if zone_tier == "critical":
            return self.rule_for["critical_engine" if angle in ENGINE_ANGLES else "critical_nose"]
        return self.rule_for[zone_tier]

    def also_rules(self, category: str | None) -> list[str]:
        return [self.rule_for["unidentified_also"]] if category == "unidentified" else []

    def equipment_staging_severity(self) -> str:
        return self._rules[self.rule_for["equipment_staging"]].get("severity", "REMOVE")

    def classify(self, *, angle: str, bbox: Box, category: str, hint: str | None = None,
                 envelope: Polygon | None = None) -> dict:
        """Everything code decides about a FOD Finding."""
        if category not in self.categories:
            category = "unidentified"
        tier = self.zone_tier(angle, bbox, envelope)
        oc = self.object_class(category, hint)
        rid = self.rule_id(angle, tier)
        rule = self.rule(rid) | {"also": self.also_rules(category)}
        return {"finding_type": "fod", "category": category, "object_class": oc, "zone_tier": tier,
                "severity": self.severity(oc, tier), "rule_id": rid, "rule": rule,
                "responsible_party": "airport" if tier == "outside_boundary" else "airline"}

    def classify_equipment_staging(self, *, angle: str, bbox: Box, envelope: Polygon | None = None) -> dict:
        tier = self.zone_tier(angle, bbox, envelope)
        rid = self.rule_id(angle, tier, "equipment_staging")
        return {"finding_type": "equipment_staging", "category": None, "object_class": None, "zone_tier": tier,
                "severity": self.equipment_staging_severity(), "rule_id": rid,
                "rule": self.rule(rid) | {"also": []}, "responsible_party": "airline"}

    # ------------------------------------------------------------------ roles
    def role_may_confirm(self, role: str, severity: str) -> bool:
        return severity in self.roles.get(role, [])


# ---------------------------------------------------------------------- geometry
def box_centre(b: Box) -> tuple[float, float]:
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def point_in_polygon(pt: Sequence[float], poly: Polygon) -> bool:
    """Ray casting; points on an edge count as inside."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        # on-edge check
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if abs(cross) < 1e-9 and min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2):
            return True
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def is_equipment_staging(kind: str, angle: str, bbox: Box, erl: Polygon | None) -> bool:
    """FOD-R9: at pre-arrival, GSE inside the equipment restraint line area (WIDE polygon) is an
    equipment-staging Finding. The ground-contact point (bottom centre of the box) or the box centre must lie
    inside the ERL polygon."""
    if kind != "pre_arrival" or angle != "WIDE" or not erl:
        return False
    cx, cy = box_centre(bbox)
    return point_in_polygon((cx, bbox[3]), erl) or point_in_polygon((cx, cy), erl)


def highest_severity(severities: Sequence[str]) -> str | None:
    sev = [s for s in severities if s in SEVERITY_ORDER]
    return min(sev, key=SEVERITY_ORDER.__getitem__) if sev else None


def size_class(bbox: Box) -> str:
    """S / M / L from the longest box side in pixels. Recorded only; never used to drop a Finding (RU-4)."""
    long_px = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
    return "S" if long_px < 32 else "M" if long_px < 96 else "L"


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> RuleSet:
    return RuleSet(json.loads(Path(path).read_text()))


def load_rules(path: Path | None = None) -> RuleSet:
    p = Path(path or config.rules_path())
    return _load(str(p), p.stat().st_mtime)
