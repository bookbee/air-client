"""The response pane, shared by every tab.

Postman's split: a status line you can read at a glance, then the body, the
headers, and the request that produced them. The optional ``summary`` callback
is what makes a tab feel purpose-built — it renders the decoded domain object
above the raw JSON, and everything below stays identical everywhere.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import streamlit as st

from air_client.http import Exchange, display_headers, to_curl
from air_client.theme import note

SummaryRenderer = Callable[[Any], None]


def _pill(exchange: Exchange) -> tuple[str, str]:
    if exchange.error is not None:
        return "err", "NETWORK ERROR"
    code = exchange.status_code or 0
    label = f"{code} {exchange.reason}".strip()
    if code < 400:
        return "ok", label
    return ("warn" if code < 500 else "err"), label


def _status_bar(exchange: Exchange) -> None:
    kind, label = _pill(exchange)
    path = urlparse(exchange.url).path or exchange.url

    bits = [
        f'<span class="air-meta"><strong>{html.escape(exchange.method)}</strong> '
        f"{html.escape(path)}</span>",
        f'<span class="air-pill {kind}">{html.escape(label)}</span>',
        f'<span class="air-meta">round trip <strong>{exchange.elapsed_ms:.0f} ms</strong></span>',
    ]
    server_ms = exchange.server_latency_ms
    if server_ms is not None:
        bits.append(f'<span class="air-meta">service <strong>{server_ms:.0f} ms</strong></span>')
    request_id = exchange.request_id
    if request_id:
        bits.append(f'<span class="air-meta">{html.escape(request_id)}</span>')

    st.markdown(f'<div class="air-statusbar">{"".join(bits)}</div>', unsafe_allow_html=True)


def _problem_detail(payload: Any) -> None:
    """Render an RFC 7807 ProblemDetail, which is how the services report errors."""
    if not isinstance(payload, dict):
        return
    title = payload.get("title")
    if not isinstance(title, str):
        return

    lines = [f"**{title}**"]
    detail = payload.get("detail")
    if isinstance(detail, str) and detail:
        lines.append(detail)
    st.error("  \n".join(lines))

    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        st.markdown("Field errors:")
        st.dataframe(
            [
                {
                    "field": e.get("field", ""),
                    "message": e.get("message", ""),
                    "code": e.get("code", ""),
                }
                for e in errors
                if isinstance(e, dict)
            ],
            hide_index=True,
            width="stretch",
        )


def render(
    exchange: Exchange,
    *,
    key: str,
    summary: SummaryRenderer | None = None,
) -> None:
    """Draw the full response pane for one exchange."""
    _status_bar(exchange)

    if exchange.error is not None:
        st.error(exchange.error)
        with st.expander("Request that failed"):
            st.code(to_curl(exchange), language="bash")
        return

    if not exchange.ok:
        _problem_detail(exchange.response_json)

    tab_names = ["Response", "Headers", "Request"]
    show_summary = summary is not None and exchange.ok and exchange.response_json is not None
    if show_summary:
        tab_names.insert(0, "Summary")

    tabs = st.tabs(tab_names)
    cursor = 0

    if show_summary:
        with tabs[0]:
            assert summary is not None
            summary(exchange.response_json)
        cursor = 1

    with tabs[cursor]:
        if exchange.response_json is not None:
            st.json(exchange.response_json, expanded=2)
            st.download_button(
                "Download JSON",
                data=json.dumps(exchange.response_json, indent=2, ensure_ascii=False),
                file_name=f"{key}-response.json",
                mime="application/json",
                key=f"{key}-download",
            )
        elif exchange.response_text:
            st.code(exchange.response_text, language="text")
        else:
            note("The service returned an empty body.")

    with tabs[cursor + 1]:
        st.markdown("**Response headers**")
        st.dataframe(
            [{"header": k, "value": v} for k, v in sorted(exchange.response_headers.items())],
            hide_index=True,
            width="stretch",
        )
        st.markdown("**Request headers**")
        st.dataframe(
            [
                {"header": k, "value": v}
                for k, v in sorted(display_headers(exchange.request_headers).items())
            ],
            hide_index=True,
            width="stretch",
        )

    with tabs[cursor + 2]:
        reveal = st.checkbox(
            "Reveal API key",
            key=f"{key}-reveal",
            help="Off by default so the snippet is safe to paste into a ticket.",
        )
        st.code(to_curl(exchange, reveal_secrets=reveal), language="bash")
        if exchange.request_body is not None:
            st.markdown("**Request body as sent**")
            st.json(exchange.request_body, expanded=2)
