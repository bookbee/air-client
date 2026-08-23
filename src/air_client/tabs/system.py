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
from air_client.tables import arrow_safe
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


#: Capability keys rendered by a block of their own, in this order. Everything
#: else in the payload falls through to the generic table below, so a service
#: that adds a field gets a readable view without a change here.
#:
#: `environment`/`default_model` are air-llm's own spelling of what
#: air-classifier calls `env` — plain scalars, both, so without a name here
#: they would not fall through anywhere: the generic loop below only picks up
#: dict and list values, and a bare string that matches neither would silently
#: vanish from the screen rather than render badly.
_HEADLINE = ("service", "version", "env", "channel", "environment", "default_model")


def _facts(payload: dict[str, Any]) -> None:
    """Whichever of the headline identity fields this service reports.

    air-classifier and air-platform answer /v1/capabilities with different
    shapes — tiers and batch ceilings on one, channel and guardrails on the
    other — and both are read on the same screen. So the renderer follows the
    payload rather than one service's schema.
    """
    present = [(key, payload[key]) for key in _HEADLINE if key in payload]
    present += [
        (key, payload[key]) for key in ("max_batch_items", "max_text_chars") if key in payload
    ]
    if not present:
        return
    for column, (key, value) in zip(st.columns(len(present)), present, strict=True):
        column.metric(key.replace("_", " ").title(), str(value))


def _flat_block(label: str, value: dict[str, Any]) -> None:
    """A one-level map — guardrails, streaming, session, turn — as a table."""
    section(label.replace("_", " ").title())
    # One column, mixed types — booleans, ints and strings all land in `value`.
    # Arrow rejects that, so every cell is rendered as text on the way in.
    st.dataframe(
        arrow_safe(
            [
                {
                    "setting": k.replace("_", " "),
                    "value": _detail(v) if isinstance(v, dict) else json.dumps(v),
                }
                for k, v in value.items()
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def _provider_map_block(payload: dict[str, Any]) -> None:
    """`providers: {name: bool}` — air-llm's own shape, on both `/v1/ready` and
    `/v1/capabilities`.

    Neither the components/dependencies loop below (a *list* of dicts) nor the
    capabilities fallthrough at the bottom of `_capabilities_summary` (which
    renders an unfamiliar dict as an opaque key/value table) reads this as
    anything more specific than that — and which providers are actually
    reachable is the one thing worth a glance here.
    """
    providers = payload.get("providers")
    if not isinstance(providers, dict) or not providers:
        return
    section("Providers")
    st.dataframe(
        arrow_safe([{"provider": name, "reachable": ok} for name, ok in providers.items()]),
        hide_index=True,
        width="stretch",
    )
    down = [name for name, ok in providers.items() if ok is False]
    if down:
        st.warning("Unreachable: " + ", ".join(down))


def _capabilities_summary(payload: Any) -> None:
    if not isinstance(payload, dict):
        return

    _facts(payload)

    tiers = payload.get("tiers")
    if isinstance(tiers, list) and tiers:
        section("Tiers")
        st.dataframe(
            arrow_safe(
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
                ]
            ),
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

    _provider_map_block(payload)

    handled = {
        *_HEADLINE,
        "max_batch_items",
        "max_text_chars",
        "tiers",
        "supported_languages",
        "providers",
    }
    for key, value in payload.items():
        if key in handled:
            continue
        if isinstance(value, dict) and value:
            _flat_block(key, value)
        elif isinstance(value, list) and value and all(not isinstance(v, dict) for v in value):
            section(key.replace("_", " ").title())
            st.write(", ".join(f"`{item}`" for item in value))


def _readiness_summary(payload: Any) -> None:
    """Readiness across all three services' shapes.

    air-classifier answers `status` + `components`; air-platform answers `ready`
    + `dependencies` and adds its own identity; air-llm answers `status` +
    `providers` (a flat name→reachable map). All three are read on this screen,
    so the renderer takes whichever fields it finds rather than one service's
    field names.
    """
    if not isinstance(payload, dict):
        return

    facts: list[tuple[str, str]] = []
    if "status" in payload:
        facts.append(("Status", str(payload["status"])))
    if "ready" in payload:
        facts.append(("Ready", "yes" if payload["ready"] else "no"))
    facts += [
        (key.replace("_", " ").title(), str(payload[key]))
        for key in ("service", "version", "checked_at")
        if key in payload
    ]
    if facts:
        for column, (label, value) in zip(st.columns(len(facts)), facts, strict=True):
            column.metric(label, value)

    _provider_map_block(payload)

    for key in ("components", "dependencies"):
        rows = payload.get(key)
        if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
            section(key.title())
            st.dataframe(arrow_safe(rows), hide_index=True, width="stretch")
            not_ready = [
                str(r.get("name") or r.get("service") or "?")
                for r in rows
                if r.get("ready") is False or r.get("reachable") is False
            ]
            if not_ready:
                st.warning("Not ready: " + ", ".join(not_ready))


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
            # Deliberately always text: an int here and "network error" there is
            # the mixed column that makes Arrow raise on every rerun.
            "status": f"{e.status_code}" if e.error is None else "network error",
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
    st.dataframe(arrow_safe(rows), hide_index=True, width="stretch")


def render(
    classifier: Connection, customer: Connection, business: Connection, llm: Connection
) -> None:
    """Draw the system tab for all three services."""
    st.markdown(
        "Liveness, readiness and the tier inventory for whichever environment the "
        "sidebar is pointed at. Check here first when a request behaves oddly — a "
        "rung that is enabled but unavailable explains most surprises."
    )

    section("air-classifier")
    _probe_panel(classifier, "system-classifier")

    st.divider()

    section("air-llm")
    _probe_panel(llm, "system-llm")

    st.divider()

    section("air-platform")
    st.caption(
        "The same probes against the platform base URL. `/v1/capabilities` answers "
        "per channel — guardrails, routes and quotas are profile-specific — so the "
        "channel here is the key the probe is sent with."
    )
    channel = st.radio(
        "Channel",
        ["customer", "business"],
        horizontal=True,
        key="system-platform-channel",
        label_visibility="collapsed",
    )
    # Slot keyed by channel, not a fixed name: otherwise flipping the radio
    # without re-probing would show the previous channel's stored response
    # under the newly selected one's label — the same collision `target_bar`'s
    # own probe cache avoids by keying on `connection.label`, not `.service`.
    _probe_panel(customer if channel == "customer" else business, f"system-platform-{channel}")

    st.divider()
    _history_panel()
