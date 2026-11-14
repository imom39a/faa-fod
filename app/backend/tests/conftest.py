"""Shared fixtures: a temporary data / var directory, tiny synthetic scenes and a fake LLM transport.

No test calls the Claude API. Synthetic frames are 960x540 textured backgrounds with small squares pasted in
as debris; the reference frame is the clean background with a little sensor noise.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fodgate import config, llm as llm_mod
from fodgate.llm import LLM
from fodgate.synthetic import (ENVELOPE, ERL, H, TIER, W, Brain, background, make_scene, noisy,  # noqa: F401
                               paste)

REPO_RULES = config.REPO_ROOT / "app" / "data" / "rules" / "fod-rules.json"


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    data, var = tmp_path / "data", tmp_path / "var"
    (data / "rules").mkdir(parents=True)
    (data / "scenes").mkdir()
    shutil.copy(REPO_RULES, data / "rules" / "fod-rules.json")
    monkeypatch.setenv("FOD_DATA_DIR", str(data))
    monkeypatch.setenv("FOD_VAR_DIR", str(var))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    for k in ("FOD_DECISION_MODEL", "FOD_ESCALATION", "FOD_DINO_WEIGHTS", "FOD_LLM_CACHE", "FOD_MAX_SPEND_USD"):
        monkeypatch.delenv(k, raising=False)
    llm_mod.reset_process_state()
    yield
    llm_mod.reset_process_state()


@pytest.fixture
def data_dir() -> Path:
    return config.data_dir()


@pytest.fixture
def brain() -> Brain:
    return Brain()


@pytest.fixture
def fake_llm(brain) -> LLM:
    return LLM(transport=brain)
