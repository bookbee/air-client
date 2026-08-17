"""Health, readiness and capabilities.

The first question when a request misbehaves is nearly always "is the thing even
up, and which tiers are actually loaded?". `/v1/capabilities` answers the second
directly — without a local Ollama the ladder silently stops at t1, and this is
where you see that rather than inferring it from a trace.

It answers a third question too, and on a shared environment that is often the
important one: *which build am I testing*. Version, tier inventory and batch
ceiling all come from the environment you are pointed at, not from this repo, so
a QA result is only meaningful next to the capabilities that produced it.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from air_client.components import response_view, target_bar
from air_client.connection import Connection
from air_client.http import build_headers, join_url, send
from air_client.state import current, history, remember
from air_client.theme import section

PROBES = {
    "Health": "/v1/health",
    "Readiness": "/v1/ready",
    "Capabilities": "/v1/capabilities",
}


def _detail(value: Any) -> str:
    """Flatten a tier's ``detail`` object into one readable cell.

    It arrives as a small map — `scorer_kind`, `onnx_loaded`, the languages a
    rung covers — and a table cell holding a raw dict is both unreadable and
    unsortable, so it becomes `key=value` pairs instead.
    """
    if isinstance(value, dict):
        return ", ".join(
            f"{key}={json.dumps(item) if isinstance(item, list | dict) else item}"
            for key, item in value.items()
        )
    return str(value) if value else ""


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
                    "detail": _detail(t.get("detail")),
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


def _run_probe(connection: Connection, slot: str, name: str, path: str) -> None:
    exchange = send(
        "GET",
        join_url(connection.base_url, path),
        headers=build_headers(connection.api_key),
        timeout=connection.timeout,
        verify=connection.verify,
    )
    remember(slot, exchange)
    st.session_state[f"{slot}-probe-name"] = name


def _probe_panel(connection: Connection, slot: str) -> None:
    """The probe buttons for one service, plus whatever the last one returned."""
    target_bar.caption(connection)

    disabled = not connection.base_url.strip()
    cols = st.columns(len(PROBES) + 3)
    for index, (name, path) in enumerate(PROBES.items()):
        cols[index].button(
            name,
            key=f"{slot}-probe-{name}",
            width="stretch",
            disabled=disabled,
            on_click=_run_probe,
            args=(connection, slot, name, path),
        )
    if disabled:
        st.caption(":red[No base URL set for this service in the sidebar.]")

    stored = current(slot)
    if stored is not None:
        response_view.render(
            stored,
            key=slot,
            summary=_probe_summary(str(st.session_state.get(f"{slot}-probe-name", "Health"))),
        )


def _rows() -> list[dict[str, Any]]:
    return [
        {
            "method": e.method,
            "url": e.url,
            "status": e.status_code if e.error is None else "network error",
            "ms": round(e.elapsed_ms),
            "request id": e.request_id or "",
        }
        for e in history()
    ]


def _history_panel() -> None:
    section("Recent calls")
    rows = _rows()
    if not rows:
        st.caption("Nothing sent yet this session.")
        return

    st.caption(
        "Every call this session made, newest first, whichever target it went to — "
        "the full URL is the record of where."
    )
    cols = st.columns([1, 1, 4])
    cols[0].button(
        "Clear history",
        key="clear-history",
        width="stretch",
        on_click=lambda: st.session_state.update({"history": []}),
    )
    cols[1].download_button(
        "Download log",
        data=json.dumps(rows, indent=2),
        file_name="air-console-history.json",
        mime="application/json",
        key="download-history",
        width="stretch",
        help="Attach it to a defect report so the exact URLs and request ids travel with it.",
    )
    st.dataframe(rows, hide_index=True, width="stretch")


def render(classifier: Connection, platform: Connection) -> None:
    """Draw the system tab for both services."""
    st.markdown(
        "Liveness, readiness and the tier inventory for whichever environment the "
        "sidebar is pointed at. Check here first when a request behaves oddly — a "
        "rung that is enabled but unavailable explains most surprises."
    )

    section("air-classifier")
    _probe_panel(classifier, "system-classifier")

    st.divider()

    section("air-platform")
    st.caption(
        "The same probes against the platform base URL. They will fail until the "
        "service exists — that is expected."
    )
    _probe_panel(platform, "system-platform")

    st.divider()
    _history_panel()
