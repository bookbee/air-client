"""The "where is this going" strip, pinned under the title.

This console is run locally against remote deployments, so the single most
expensive mistake it can permit is sending a request to the wrong environment —
a QA fixture posted at staging, a local run mistaken for the shared box. The bar
therefore states the destination in full, unprompted, on every screen, and
colours anything that is not this machine.

It also holds the reachability probe, because "is it even up" is the question
that immediately follows "where am I pointing", and answering it should not
require leaving the tab you are on.
"""

from __future__ import annotations

import html
import time

import streamlit as st

from air_client.connection import Connection
from air_client.http import build_headers, join_url, send

HEALTH_PATH = "/v1/health"
_RESULTS = "probe-results"


def _probe(connection: Connection) -> dict[str, object]:
    exchange = send(
        "GET",
        join_url(connection.base_url, HEALTH_PATH),
        headers=build_headers(connection.api_key),
        timeout=min(connection.timeout, 10.0),
        verify=connection.verify,
    )
    if exchange.error is not None:
        detail = "unreachable"
    elif exchange.ok:
        detail = "healthy"
    else:
        detail = f"HTTP {exchange.status_code}"
    return {
        "ok": exchange.ok,
        "detail": detail,
        "ms": round(exchange.elapsed_ms),
        "at": time.strftime("%H:%M:%S"),
    }


def check_all(*connections: Connection) -> None:
    """Probe every connection's health endpoint and cache the verdicts."""
    st.session_state[_RESULTS] = {c.service: _probe(c) for c in connections if c.base_url.strip()}


def _reachability(connection: Connection) -> str:
    result = st.session_state.get(_RESULTS, {}).get(connection.service)
    if not isinstance(result, dict):
        return '<span class="air-dot unknown"></span><span>not checked</span>'
    kind = "ok" if result.get("ok") else "err"
    detail = html.escape(str(result.get("detail", "")))
    return (
        f'<span class="air-dot {kind}"></span>'
        f"<span>{detail} · {result.get('ms')} ms · {result.get('at')}</span>"
    )


def _row(connection: Connection) -> str:
    location = connection.location
    chip = {
        "local": '<span class="air-chip local">LOCAL</span>',
        "remote": '<span class="air-chip remote">REMOTE</span>',
    }.get(location, '<span class="air-chip unset">NOT SET</span>')

    url = html.escape(connection.base_url or "— no base URL —")
    key = (
        '<span class="air-chip key">keyed</span>'
        if connection.authenticated
        else '<span class="air-chip nokey">no key</span>'
    )
    return (
        '<div class="air-target-row">'
        f'<span class="air-target-service">{html.escape(connection.service)}</span>'
        f"{chip}"
        f'<span class="air-target-url">{url}</span>'
        f"{key}"
        f'<span class="air-target-probe">{_reachability(connection)}</span>'
        "</div>"
    )


def render(classifier: Connection, platform: Connection) -> None:
    """Draw the target bar for both services, plus the probe control."""
    remote = classifier.is_remote or platform.is_remote
    tone = "remote" if remote else "local"

    left, right = st.columns([6, 1])
    with left:
        st.markdown(
            f'<div class="air-target {tone}">'
            f'<div class="air-target-head">'
            f'<span class="air-target-label">TARGET</span>'
            f"<strong>{html.escape(classifier.target_label)}</strong>"
            + (
                '<span class="air-target-warn">requests leave this machine</span>'
                if remote
                else '<span class="air-target-warn">everything stays on this machine</span>'
            )
            + "</div>"
            f"{_row(classifier)}{_row(platform)}"
            "</div>",
            unsafe_allow_html=True,
        )
    with right:
        st.button(
            "Check both",
            key="probe-all",
            width="stretch",
            help=f"GET {HEALTH_PATH} against both base URLs and report what came back.",
            on_click=check_all,
            args=(classifier, platform),
        )


def caption(connection: Connection) -> None:
    """A one-line destination reminder, for use inside a tab."""
    location = connection.location
    marker = {"local": ":blue[⌂ LOCAL]", "remote": ":orange[⬆ REMOTE]"}.get(
        location, ":red[NOT SET]"
    )
    key = "keyed" if connection.authenticated else ":red[no key]"
    st.caption(
        f"{marker} · **{connection.service}** on `{connection.target}` · "
        f"`{connection.base_url or '—'}` · {key}"
    )
