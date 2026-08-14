"""Session-scoped storage for exchanges.

Streamlit re-runs the whole script on every widget interaction, so a response
rendered straight after a button press vanishes the moment you tick a checkbox.
Everything worth keeping on screen therefore lives in ``st.session_state``.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from air_client.http import Exchange

HISTORY_LIMIT = 25


def remember(slot: str, exchange: Exchange) -> None:
    """Store ``exchange`` as the current response for ``slot`` and log it."""
    st.session_state[f"exchange::{slot}"] = exchange

    history: list[Exchange] = st.session_state.setdefault("history", [])
    history.insert(0, exchange)
    del history[HISTORY_LIMIT:]


def current(slot: str) -> Exchange | None:
    value = st.session_state.get(f"exchange::{slot}")
    return value if isinstance(value, Exchange) else None


def history() -> list[Exchange]:
    value = st.session_state.get("history", [])
    return value if isinstance(value, list) else []


def clear_history() -> None:
    st.session_state["history"] = []


def parse_json_object(raw: str, *, label: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse an optional JSON object from a textarea.

    Returns ``(None, None)`` for blank input — meaning "omit this field", which
    matters because the request schemas set ``additionalProperties: false`` and
    reject stray or malformed keys outright.
    """
    if not raw.strip():
        return None, None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"{label} is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
    if not isinstance(value, dict):
        return None, f"{label} must be a JSON object, got {type(value).__name__}."
    return value, None
