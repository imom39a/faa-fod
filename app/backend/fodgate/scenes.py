"""Scene data (app/data/scenes/<scene_id>/scene.json), tolerant of missing optional files and fields."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import config


class SceneNotFound(Exception):
    pass


@dataclass
class AngleSpec:
    angle: str
    image: str | None            # path relative to the scene directory
    reference: str | None
    after: str | None
    declared_usable: bool
    declared_reason: str | None
    regions: dict
    derived: str | None
    source: dict
    ground_truth: list
    observations_truth: list


@dataclass
class Scene:
    scene_id: str
    kind: str
    light: str
    description: str
    directory: Path
    angles: dict[str, AngleSpec]

    def path(self, rel: str | None) -> Path | None:
        """Absolute path of a file inside the scene directory, or None when absent / outside it."""
        if not rel:
            return None
        p = (self.directory / rel).resolve()
        if not p.is_relative_to(self.directory.resolve()) or not p.is_file():
            return None
        return p

    def ref(self, rel: str | None) -> str | None:
        return f"{self.scene_id}/{rel}" if rel else None

    def url(self, rel: str | None) -> str | None:
        return f"/images/{self.scene_id}/{rel}" if rel else None


def scenes_dir() -> Path:
    return config.data_dir() / "scenes"


def load_scene(scene_id: str) -> Scene:
    if not scene_id or "/" in scene_id or "\\" in scene_id or scene_id.startswith("."):
        raise SceneNotFound(scene_id)
    d = scenes_dir() / scene_id
    f = d / "scene.json"
    if not f.is_file():
        raise SceneNotFound(scene_id)
    raw = json.loads(f.read_text())
    angles: dict[str, AngleSpec] = {}
    raw_angles = raw.get("angles") or {}
    for name in config.ANGLES:
        a = raw_angles.get(name) or {}
        image = a.get("image")
        reason = a.get("unusable_reason")
        usable = a.get("usable", True)
        if a == {} or image is None:
            usable, reason = False, reason or "missing"
        angles[name] = AngleSpec(
            angle=name, image=image, reference=a.get("reference"), after=a.get("after"),
            declared_usable=bool(usable), declared_reason=None if usable else (reason or "blocked"),
            regions=a.get("regions") or {}, derived=a.get("derived"), source=a.get("source") or {},
            ground_truth=a.get("ground_truth") or [], observations_truth=a.get("observations_truth") or [])
    return Scene(scene_id=raw.get("scene_id", scene_id), kind=raw.get("kind", "pre_departure"),
                 light=raw.get("light", "day"), description=raw.get("description", ""), directory=d, angles=angles)


def list_scenes() -> list[str]:
    d = scenes_dir()
    return sorted(p.name for p in d.iterdir() if (p / "scene.json").is_file()) if d.is_dir() else []


def load_testset() -> list[str]:
    f = config.data_dir() / "testset.json"
    if not f.is_file():
        return list_scenes()
    return list(json.loads(f.read_text()).get("scenes", []))


def load_timeline() -> dict:
    f = config.timeline_path()
    if not f.is_file():
        return {"gates": list(config.DEFAULT_GATES), "turns": []}
    t = json.loads(f.read_text())
    t.setdefault("gates", list(config.DEFAULT_GATES))
    t.setdefault("turns", [])
    return t
