"""Start-up defaults for the console.

Read once from the environment (and a `.env` beside the repo root, if present)
purely to seed the sidebar. Nothing here is authoritative at runtime — the
sidebar owns the live connection settings, because the entire point of this
console is changing them without a restart.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_PREFIX = "AIR_CLIENT__"

# Mirrors air-classifier's own local default, which is still spelled
# AIR_SENTIMENT__APP__PORT=8080 — that repo was renamed but its internals,
# including the settings prefix, have not been.
DEFAULT_CLASSIFIER_BASE_URL = "http://127.0.0.1:8080"
# air-platform has no service yet; 8081 just avoids colliding with the classifier.
DEFAULT_PLATFORM_BASE_URL = "http://127.0.0.1:8081"


def _load_dotenv() -> None:
    """Fold a sibling `.env` into os.environ without adding a dependency.

    Only `KEY=value` lines are honoured, and existing environment variables
    always win — an explicit export should beat a stale file.
    """
    path = Path(__file__).resolve().parents[2] / ".env"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _get(name: str, default: str, *, legacy: str | None = None) -> str:
    """Read one setting.

    ``legacy`` names a superseded key that is still honoured, so a `.env`
    written before the air-sentiment → air-classifier rename keeps working
    instead of silently falling back to the default.
    """
    value = os.environ.get(f"{ENV_PREFIX}{name}")
    if (value is None or not value.strip()) and legacy is not None:
        value = os.environ.get(f"{ENV_PREFIX}{legacy}")
    return value.strip() if value and value.strip() else default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"{ENV_PREFIX}{name}")
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(f"{ENV_PREFIX}{name}")
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Defaults:
    """Seed values for the sidebar."""

    classifier_base_url: str
    classifier_api_key: str
    platform_base_url: str
    platform_api_key: str
    timeout_seconds: float
    verify_tls: bool


def load_defaults() -> Defaults:
    _load_dotenv()
    return Defaults(
        classifier_base_url=_get(
            "CLASSIFIER_BASE_URL", DEFAULT_CLASSIFIER_BASE_URL, legacy="SENTIMENT_BASE_URL"
        ),
        classifier_api_key=_get("CLASSIFIER_API_KEY", "", legacy="SENTIMENT_API_KEY"),
        platform_base_url=_get("PLATFORM_BASE_URL", DEFAULT_PLATFORM_BASE_URL),
        platform_api_key=_get("PLATFORM_API_KEY", ""),
        timeout_seconds=_get_float("TIMEOUT_SECONDS", 60.0),
        verify_tls=_get_bool("VERIFY_TLS", True),
    )
