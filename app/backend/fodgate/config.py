"""Paths and environment settings. Everything is read at call time so tests can override the environment."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]          # app/backend
REPO_ROOT = Path(__file__).resolve().parents[3]            # repository root (holds .env)

ANGLES = ["NOSE", "ENG-L", "ENG-R", "CARGO", "AFT", "WIDE"]
DEFAULT_GATES = ["T1", "T2", "T4", "T5", "T8"]

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
ALLOWED_MODELS = (HAIKU, SONNET)                           # Opus is never used (PL-7)

SCHEMA_VERSION = "0.1"


def data_dir() -> Path:
    return Path(os.environ.get("FOD_DATA_DIR") or REPO_ROOT / "app" / "data").resolve()


def var_dir() -> Path:
    p = Path(os.environ.get("FOD_VAR_DIR") or REPO_ROOT / "app" / "var").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_dir() -> Path:
    p = var_dir() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def crops_dir() -> Path:
    p = var_dir() / "crops"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return var_dir() / "fod.sqlite"


def frontend_dist() -> Path:
    return REPO_ROOT / "app" / "frontend" / "dist"


def rules_path() -> Path:
    """The rule set in the data directory, falling back to the repository copy (e.g. for fixture data dirs)."""
    p = data_dir() / "rules" / "fod-rules.json"
    return p if p.exists() else REPO_ROOT / "app" / "data" / "rules" / "fod-rules.json"


def decision_model() -> str:
    m = os.environ.get("FOD_DECISION_MODEL") or HAIKU
    if m not in ALLOWED_MODELS:
        raise ValueError(f"FOD_DECISION_MODEL must be one of {ALLOWED_MODELS}, got {m!r}")
    return m


def escalation() -> str:
    v = (os.environ.get("FOD_ESCALATION") or "off").lower()
    if v not in ("off", "sonnet"):
        raise ValueError("FOD_ESCALATION must be 'off' or 'sonnet'")
    return v


def llm_cache_on() -> bool:
    return (os.environ.get("FOD_LLM_CACHE") or "on").lower() != "off"


def dino_weights() -> Path | None:
    v = os.environ.get("FOD_DINO_WEIGHTS")
    return Path(v) if v else None


def max_spend_usd() -> float | None:
    """Optional hard cap on real (uncached) API spend for this process."""
    v = os.environ.get("FOD_MAX_SPEND_USD")
    return float(v) if v else None


def load_api_key() -> bool:
    """Load ANTHROPIC_API_KEY from <repo>/.env into this process only. Returns whether a key is available.

    The value is never printed, logged or returned.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    env = REPO_ROOT / ".env"
    if not env.exists():
        return False
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith("ANTHROPIC_API_KEY=") and not line.startswith("#"):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                os.environ["ANTHROPIC_API_KEY"] = value
                return True
    return False
