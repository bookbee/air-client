"""Health, readiness and capabilities.

The first question when a request misbehaves is nearly always "is the thing even
up, and which tiers are actually loaded?". `/v1/capabilities` answers the second
directly — without a local Ollama the ladder silently stops at t1, and this is
where you see that rather than inferring it from a trace.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from air_client.components import response_view
from air_client.components.sidebar import Connection
from air_client.http import build_headers, join_url, send
from air_client.state import current, history, remember
from air_client.theme import section

PROBES = {
    "Health": "/v1/health",
    "Readiness": "/v1/ready",
    "Capabilities": "/v1/capabilities",
}


def _capabilities_summary(payload: Any) -> None:
    if not isinstance(payload, dict):
        return

    cols = st.columns(4)
    cols[0].metric("Service", str(payload.get("service", "—")))
    cols[1].metric("Version", str(payload.get("version", "—")))
    cols[2].metric("Max batch items", payload.get("max_batch_items", "—"))
    cols[3].metric("Max text chars", payload.get("max_text_chars", "—"))

    tiers = payload.get("tiers")
    if isinstance(tiers, list) and tiers:
        section("Tiers")
        st.dataframe(
            [
                {
                    "tier": t.get("tier", ""),
                    "enabled": t.get("enabled"),
                    "available": t.get("available"),
                    "model version": t.get("model_version") or "—",
                    "detail": t.get("detail") or "",
                }
                for t in tiers
                if isinstance(t, dict)
            ],
            hide_index=True,
            width="stretch",
        )
        unavailable = [
            str(t.get("tier"))
            for t in tiers
            if isinstance(t, dict) and t.get("enabled") and not t.get("available")
        ]
        if unavailable:
            st.warning(
                "Enabled but unavailable: "
                + ", ".join(unavailable)
                + ". The ladder will stop below these rungs."
            )

    languages = payload.get("supported_languages")
    if isinstance(languages, list) and languages:
        section("Supported languages")
        st.write(", ".join(f"`{lang}`" for lang in languages))


def _readiness_summary(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    st.metric("Status", str(payload.get("status", "—")))
    components = payload.get("components")
    if isinstance(components, list) and components:
        section("Components")
        st.dataframe(components, hide_index=True, width="stretch")


def _probe_summary(name: str) -> Any:
    if name == "Capabilities":
        return _capabilities_summary
    if name == "Readiness":
        return _readiness_summary
    return lambda payload: st.json(payload)


def _history_panel() -> None:
    entries = history()
    section("Recent calls")
    if not entries:
        st.caption("Nothing sent yet this session.")
        return

    st.button(
        "Clear history",
        key="clear-history",
        on_click=lambda: st.session_state.update({"history": []}),
    )
    st.dataframe(
        [
            {
                "method": e.method,
                "url": e.url,
                "status": e.status_code if e.error is None else "network error",
                "ms": round(e.elapsed_ms),
                "request id": e.request_id or "",
            }
            for e in entries
        ],
        hide_index=True,
        width="stretch",
    )


def render(classifier: Connection, platform: Connection) -> None:
    """Draw the system tab for both services."""
    st.markdown(
        "Liveness, readiness and the tier inventory. Check here first when a request "
        "behaves oddly — a rung that is enabled but unavailable explains most surprises."
    )

    section("air-classifier")
    cols = st.columns(len(PROBES) + 2)
    for index, (name, path) in enumerate(PROBES.items()):
        if cols[index].button(name, key=f"probe-{name}", width="stretch"):
            with st.spinner(f"GET {path}…"):
                exchange = send(
                    "GET",
                    join_url(classifier.base_url, path),
                    headers=build_headers(classifier.api_key),
                    timeout=classifier.timeout,
                    verify=classifier.verify,
                )
            remember("system-classifier", exchange)
            st.session_state["system-probe-name"] = name

    stored = current("system-classifier")
    if stored is not None:
        response_view.render(
            stored,
            key="system-classifier",
            summary=_probe_summary(st.session_state.get("system-probe-name", "Health")),
        )

    st.divider()

    section("air-platform")
    st.caption(
        "The same probes against the platform base URL. They will fail until the "
        "service exists — that is expected."
    )
    cols = st.columns(len(PROBES) + 2)
    for index, (name, path) in enumerate(PROBES.items()):
        if cols[index].button(name, key=f"probe-platform-{name}", width="stretch"):
            with st.spinner(f"GET {path}…"):
                exchange = send(
                    "GET",
                    join_url(platform.base_url, path),
                    headers=build_headers(platform.api_key),
                    timeout=platform.timeout,
                    verify=platform.verify,
                )
            remember("system-platform", exchange)

    stored = current("system-platform")
    if stored is not None:
        response_view.render(stored, key="system-platform")

    st.divider()
    _history_panel()
