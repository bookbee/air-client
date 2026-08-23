"""The air-llm tab: the single `/v1/inference` surface, chat and embeddings alike.

air-llm is the AIR platform's central LLM gateway — one unified inference API in
front of Ollama, Anthropic, OpenAI and Gemini, with provider routing/failover,
cost accounting and response caching, reached directly by every AIR consumer
(never brokered through air-infra). It ships with no UI of its own — its own
plan docs list that as a deliberate v1 non-goal — so this tab is the only place
most developers will see a raw response from it before wiring a real
integration.

One request shape does both `task`s the service supports, and — unlike
air-classifier's and air-platform's `options` sub-object — every field below
sits at the top level of the request body:

* `chat` — `messages`, a list of `{role, content}` turns. The service is
  stateless per call: there is no `session_id` and no server-side
  conversation, unlike air-platform's `/v1/chat`. A multi-turn exchange means
  resending the whole transcript, which is what the "Advanced" messages JSON
  box below is for.
* `embeddings` — `input`, a list of strings, one vector back per entry.

Neither task streams. There is no SSE or websocket route anywhere in the
service — every call is one JSON request, one JSON response — so this tab uses
the same synchronous `http.send()` every other tab does.
"""

from __future__ import annotations

import html
import json
from typing import Any

import streamlit as st

from air_client import dashboard
from air_client.components import response_view, target_bar
from air_client.connection import Connection
from air_client.currency import format_cost
from air_client.dashboard import num, text, yn
from air_client.http import build_headers, join_url, send
from air_client.state import current, parse_json_object, remember
from air_client.theme import note, section

TASKS: tuple[str, str] = ("chat", "embeddings")


def _endpoint_card() -> None:
    st.markdown(
        '<div class="air-route on">'
        '<div class="air-route-path">POST /v1/inference</div>'
        '<div class="air-route-what">One entry point for both chat and embeddings — '
        "<code>task</code> picks which. Stateless per call: there is no session id, so a "
        "multi-turn exchange means resending the whole <code>messages</code> array.</div>"
        '<div class="air-route-adds">chat returns: content, usage, cost_usd, cached, '
        "refusal, finish_reason<br>"
        "embeddings returns: one vector per input string</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _parse_messages(raw: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    """A JSON array of `{role, content}` turns, or the parse/shape error."""
    if not raw.strip():
        return None, None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return (
            None,
            f"messages is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})",
        )
    if not isinstance(value, list) or not value:
        return None, "messages must be a non-empty JSON array."
    if not all(
        isinstance(item, dict)
        and isinstance(item.get("role"), str)
        and isinstance(item.get("content"), str)
        for item in value
    ):
        return None, 'every element of messages must be an object with string "role" and "content".'
    return value, None


def _chat_fields(prefix: str) -> tuple[list[dict[str, Any]], list[str]]:
    """A single required message, or — toggled on — a hand-built transcript."""
    errors: list[str] = []
    advanced = st.checkbox(
        "Advanced: paste a full messages array",
        key=f"{prefix}-advanced",
        help=(
            "air-llm keeps no conversation state — there is no session id — so a real "
            "multi-turn exchange means resending the whole transcript. Use this to hand-build "
            "one; leave it unticked for a single-turn call."
        ),
    )
    if advanced:
        raw = st.text_area(
            "messages  ·  JSON array of {role, content} objects",
            key=f"{prefix}-messages-json",
            height=160,
            placeholder=(
                '[\n  {"role": "user", "content": "What is my order status?"},\n'
                '  {"role": "assistant", "content": "Could you share the order id?"},\n'
                '  {"role": "user", "content": "SUP-4821"}\n]'
            ),
        )
        messages, error = _parse_messages(raw)
        if error:
            errors.append(error)
        elif messages is None:
            errors.append("messages is required.")
        return messages or [], errors

    text = st.text_area(
        "message  ·  required",
        key=f"{prefix}-message",
        height=120,
        placeholder="Where is my order?",
    )
    if not text.strip():
        errors.append("message is required.")
    return ([{"role": "user", "content": text}] if text.strip() else []), errors


def _embeddings_fields(prefix: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    raw = st.text_area(
        "input  ·  one string per line",
        key=f"{prefix}-lines",
        height=140,
        placeholder="Great value for money.\nArrived broken.",
    )
    items = [line.strip() for line in raw.splitlines() if line.strip()]
    if not items:
        errors.append("Supply at least one line of input.")
    return items, errors


def _optional_fields(prefix: str, *, task: str) -> dict[str, Any]:
    """Tick-to-send rows, same idiom as every other tab — but merged flat into
    the body, not nested under an `options` key, since `InferenceRequest` has
    no such sub-object."""
    fields: dict[str, Any] = {}

    with st.expander("Options — tick a row to send it, leave clear to use the service default"):
        row = st.columns([1, 2])
        if row[0].checkbox("model", key=f"{prefix}-on-model"):
            model = row[1].text_input(
                "Alias, provider:model, or a bare model name",
                key=f"{prefix}-model",
                placeholder="ollama:llama3.2:3b",
                label_visibility="collapsed",
            ).strip()
            if model:
                fields["model"] = model
        else:
            row[1].caption("Default: the deployment's own default model — see the System tab.")

        if task == "chat":
            row = st.columns([1, 2])
            if row[0].checkbox("max_tokens", key=f"{prefix}-on-max-tokens"):
                fields["max_tokens"] = row[1].number_input(
                    "Max output tokens",
                    min_value=1,
                    max_value=32000,
                    value=1024,
                    key=f"{prefix}-max-tokens",
                    label_visibility="collapsed",
                )
            else:
                row[1].caption("Default: the provider's own ceiling.")

            row = st.columns([1, 2])
            if row[0].checkbox("temperature", key=f"{prefix}-on-temp"):
                fields["temperature"] = row[1].number_input(
                    "Sampling temperature",
                    min_value=0.0,
                    max_value=2.0,
                    value=0.7,
                    step=0.1,
                    key=f"{prefix}-temp",
                    label_visibility="collapsed",
                )
            else:
                row[1].caption("Default: the provider's own default.")

            row = st.columns([1, 2])
            if row[0].checkbox("json_schema + schema_name", key=f"{prefix}-on-schema"):
                schema_raw = row[1].text_area(
                    "json_schema  ·  the answer must satisfy this JSON Schema",
                    key=f"{prefix}-schema",
                    height=100,
                    label_visibility="collapsed",
                    placeholder='{"type": "object", "properties": {"count": {"type": "integer"}}}',
                )
                name = row[1].text_input(
                    "schema_name",
                    key=f"{prefix}-schema-name",
                    placeholder="order_summary",
                )
                schema, error = parse_json_object(schema_raw, label="json_schema")
                if error:
                    st.warning(error)
                if schema is not None:
                    fields["json_schema"] = schema
                if name.strip():
                    fields["schema_name"] = name.strip()
            else:
                row[1].caption("Default: unset — free-form text output.")

        row = st.columns([1, 2])
        if row[0].checkbox("cache_prefix", key=f"{prefix}-on-cache"):
            fields["cache_prefix"] = row[1].checkbox(
                "Let the provider cache the stable prefix of this call",
                value=True,
                key=f"{prefix}-cache",
            )
        else:
            row[1].caption("Default: true.")

    return fields


def _send_row(prefix: str, url: str, connection: Connection, errors: list[str]) -> bool:
    left, right = st.columns([1, 4])
    clicked = left.button(
        "Send", type="primary", key=f"{prefix}-send", width="stretch", disabled=bool(errors)
    )
    marker = "REMOTE" if connection.is_remote else "LOCAL"
    right.markdown(
        f'<div class="air-meta" style="padding-top:.55rem">POST {html.escape(url)} '
        f'<span class="air-chip {connection.location}">{marker}</span></div>',
        unsafe_allow_html=True,
    )
    for message in errors:
        st.warning(message)
    return clicked


def _inference_summary(payload: Any) -> None:
    if not isinstance(payload, dict):
        return

    refusal = bool(payload.get("refusal"))
    cached = bool(payload.get("cached"))
    dashboard.grid(
        "Verdict",
        [
            [
                ("task", text(payload.get("task")), ""),
                ("provider", text(payload.get("provider")), ""),
                ("model", text(payload.get("model")), ""),
                ("cached", yn(cached), ""),
                ("refusal", yn(refusal), "err" if refusal else "muted"),
                ("finish_reason", text(payload.get("finish_reason")), ""),
            ]
        ],
    )

    content = payload.get("content")
    if isinstance(content, str) and content.strip():
        with st.chat_message("assistant"):
            st.markdown(content)
    if refusal:
        st.warning("`refusal: true` — the provider declined to answer.")

    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list) and embeddings:
        first = embeddings[0]
        dims = len(first) if isinstance(first, list) else 0
        dashboard.grid("Embeddings", [[("vectors", f"{len(embeddings)} x {dims} dims", "")]])
        with st.expander("Raw vectors"):
            st.json(embeddings)

    usage = payload.get("usage")
    if isinstance(usage, dict) and usage:
        cost = payload.get("cost_usd")
        dashboard.grid(
            "Usage & cost",
            [
                [
                    ("prompt_tokens", num(usage.get("prompt_tokens")), ""),
                    ("completion_tokens", num(usage.get("completion_tokens")), ""),
                    ("total_tokens", num(usage.get("total_tokens")), ""),
                    ("cache_read_tokens", num(usage.get("cache_read_tokens")), ""),
                    (
                        "cost",
                        format_cost(cost) if isinstance(cost, int | float) else "—",
                        "" if isinstance(cost, int | float) and cost > 0 else "muted",
                    ),
                ]
            ],
        )


def _policy_probe(connection: Connection) -> None:
    """GET /v1/admin/policy — what this key is actually scoped to.

    Rendered as raw JSON rather than a bespoke summary: `PolicyDoc`'s exact
    shape is an admin-only implementation detail worth showing verbatim rather
    than guessing at a friendlier layout for.
    """
    section("Your key's policy")
    st.caption(
        "`GET /v1/admin/policy` — resources, actions and rate limit your key is scoped to. "
        "Requires the `admin_read` scope; most caller keys will get a 403 here."
    )
    disabled = not connection.base_url.strip()
    if st.button("Check my policy", key="llm-policy-check", disabled=disabled):
        exchange = send(
            "GET",
            join_url(connection.base_url, "/v1/admin/policy"),
            headers=build_headers(connection.api_key),
            timeout=connection.timeout,
            verify=connection.verify,
        )
        remember("llm-policy", exchange)

    stored = current("llm-policy")
    if stored is not None:
        response_view.render(stored, key="llm-policy")


def render(connection: Connection) -> None:
    """Draw the whole LLM tab."""
    st.markdown(
        "One endpoint, two tasks. `POST /v1/inference` serves chat and embeddings alike — "
        "`task` picks which — across whichever provider the deployment's routing config "
        "prefers, with failover between them on a per-attempt deadline."
    )
    target_bar.caption(connection)

    _endpoint_card()
    st.divider()

    prefix = "llm"
    task = st.radio(
        "Task",
        list(TASKS),
        horizontal=True,
        key=f"{prefix}-task",
        label_visibility="collapsed",
    )

    if task == "chat":
        messages, errors = _chat_fields(prefix)
    else:
        items, errors = _embeddings_fields(prefix)

    extras = _optional_fields(prefix, task=task)

    body: dict[str, Any] = {"task": task}
    if task == "chat":
        body["messages"] = messages
    else:
        body["input"] = items
    body.update(extras)

    if not connection.base_url.strip():
        errors.append("No air-llm base URL set in the sidebar.")

    with st.expander("Request body preview"):
        st.code(json.dumps(body, indent=2, ensure_ascii=False), language="json")

    url = join_url(connection.base_url, "/v1/inference")
    if _send_row(prefix, url, connection, errors):
        with st.spinner(f"Calling air-llm on {connection.target}…"):
            exchange = send(
                "POST",
                url,
                headers=build_headers(connection.api_key),
                json_body=body,
                timeout=connection.timeout,
                verify=connection.verify,
            )
        remember(prefix, exchange)

    stored = current(prefix)
    if stored is not None:
        section("Response")
        response_view.render(stored, key=prefix, summary=_inference_summary)
    else:
        note("No call sent yet this session.")

    st.divider()
    _policy_probe(connection)
