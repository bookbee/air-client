"""The air-platform tab: both channels of the conversational front door.

air-platform runs one pipeline behind two entry points, and they differ only by
profile — guardrails, output contract, audit sink, quota bucket, tool allow-list:

* ``POST /v1/chat`` — public conversational traffic, customer gateway.
* ``POST /v1/query`` — internal business queries, corporate gateway, with
  schema-validated structured output.

**The channel comes from the API key, not from a header.** That is the single
fact this tab is built around. A caller who could name its own channel could
select the weaker guardrail profile, so air-platform refuses to read it from the
request: the customer key on ``/v1/query`` is a 403 and so is the business key on
``/v1/chat``. The console therefore holds one key per channel and picks the one
that belongs to the route you chose — the pairing is not something you can get
wrong from here, which is exactly what makes the 403 informative when it does
appear against a real environment.

A turn that warrants a write returns a ``proposal`` and changes nothing;
executing it takes a second turn on the same session carrying ``confirm``. The
console offers Confirm and Decline buttons for that second call — neither
development key grants ``allow_actions``, so both 403 against a local
checkout, which is the correct, honest outcome; they exist for a remote key
that actually carries the scope.

**Streaming.** Both routes are content-negotiated — ``Accept:
text/event-stream`` gets the real turn-lifecycle stream (``turn.start``,
``stage`` per pipeline step, ``route``, ``citation``, ``proposal``,
``answer``, ``usage``, ``turn.end``), anything else gets the single JSON body
above (docs/01-hld.md §5). The "Stream via SSE" checkbox switches which one
this tab sends; either way the same summary renders, because
:func:`_fold_events` reassembles a stream's events into the identical shape
the JSON body already has.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from functools import partial
from typing import Any

import streamlit as st

from air_client import dashboard
from air_client.components import response_view, target_bar
from air_client.connection import Connection
from air_client.currency import format_cost
from air_client.dashboard import Kind, num, yn
from air_client.dashboard import text as fmt_text
from air_client.http import Exchange, build_headers, join_url, send, send_stream
from air_client.state import current, parse_json_object, remember
from air_client.tables import arrow_safe
from air_client.theme import note, section


@dataclass(frozen=True, slots=True)
class Route:
    """One entry point, and the channel whose key opens it."""

    key: str
    label: str
    path: str
    channel: str
    field: str
    purpose: str
    placeholder: str


ROUTES: tuple[Route, ...] = (
    Route(
        key="chat",
        label="Chat",
        path="/v1/chat",
        channel="customer",
        field="message",
        purpose="Public conversational traffic through the customer gateway.",
        placeholder="Where is my order?",
    ),
    Route(
        key="query",
        label="Query",
        path="/v1/query",
        channel="business",
        field="query",
        purpose="Internal business queries, with schema-validated structured output.",
        placeholder="How many orders shipped late last week?",
    ),
)

BY_LABEL = {route.label: route for route in ROUTES}

STAGE_ORDER = (
    "guardrails_in",
    "context",
    "cache",
    "classify",
    "plan",
    "gather",
    "synthesise",
    "guardrails_out",
    "persist",
)


def _route_cards(selected: str) -> None:
    columns = st.columns(len(ROUTES))
    for column, route in zip(columns, ROUTES, strict=True):
        with column:
            st.markdown(
                f'<div class="air-route {"on" if route.key == selected else ""}">'
                f'<div class="air-route-path">POST {route.path}</div>'
                f'<div class="air-route-what">{route.purpose}</div>'
                f'<div class="air-route-adds">key: <b>{route.channel}</b> channel · '
                f"body field <code>{route.field}</code></div>"
                "</div>",
                unsafe_allow_html=True,
            )


def _options_editor(prefix: str) -> dict[str, Any]:
    """TurnOptions. Unticked rows are omitted so the service's own default wins."""
    options: dict[str, Any] = {}
    with st.expander("Options — tick a row to send it, leave clear to use the service default"):
        row = st.columns([1, 2])
        if row[0].checkbox("deadline_ms", key=f"{prefix}-on-deadline"):
            options["deadline_ms"] = row[1].number_input(
                "Turn deadline (ms)",
                min_value=100,
                max_value=120000,
                value=15000,
                step=500,
                key=f"{prefix}-deadline",
                label_visibility="collapsed",
            )
        else:
            row[1].caption("Default: 15000 ms — see `turn.deadline_ms` in Capabilities.")

        row = st.columns([1, 2])
        if row[0].checkbox("max_cost_usd", key=f"{prefix}-on-cost"):
            options["max_cost_usd"] = row[1].number_input(
                "Max cost (USD)",
                min_value=0.0,
                max_value=10.0,
                value=0.25,
                step=0.05,
                format="%.4f",
                key=f"{prefix}-cost",
                label_visibility="collapsed",
            )
        else:
            row[1].caption("Default: $0.25 per turn.")

        row = st.columns([1, 2])
        if row[0].checkbox("allow_routes", key=f"{prefix}-on-routes"):
            raw = row[1].text_input(
                "Routes the planner may use, comma separated",
                value="direct",
                key=f"{prefix}-routes",
                label_visibility="collapsed",
            )
            routes = [r.strip() for r in raw.split(",") if r.strip()]
            if routes:
                options["allow_routes"] = routes
        else:
            row[1].caption("Default: unset — the planner picks. Capabilities lists what exists.")

        row = st.columns([1, 2])
        if row[0].checkbox("use_cache", key=f"{prefix}-on-cache"):
            options["use_cache"] = row[1].checkbox(
                "Serve from cache when possible", value=True, key=f"{prefix}-cache"
            )
        else:
            row[1].caption("Default: on. Turn it off to force a cold turn while testing.")

        row = st.columns([1, 2])
        if row[0].checkbox("redact_pii", key=f"{prefix}-on-pii"):
            options["redact_pii"] = row[1].checkbox(
                "Redact PII on the way in", value=True, key=f"{prefix}-pii"
            )
        else:
            row[1].caption("Default: on, per the guardrail profile of your channel.")

        row = st.columns([1, 2])
        if row[0].checkbox("include_trace", key=f"{prefix}-on-trace"):
            options["include_trace"] = row[1].checkbox(
                "Return the stage trace", value=True, key=f"{prefix}-trace"
            )
        else:
            row[1].caption("Default: true — the trace is what makes the pipeline legible.")
    return options


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


#: `TurnStatus` — air-platform's own vocabulary. `ok` is the only outcome that
#: needs no second look; the rest are all worth one, in ascending order of concern.
_STATUS_KIND: dict[str, Kind] = {"ok": "ok", "refused": "warn", "degraded": "warn", "error": "err"}


def _event_detail(event: dict[str, Any]) -> str:
    """One line worth showing next to an event's name in the timeline."""
    name = event.get("event")
    if name == "turn.start":
        return f"session={event.get('session_id')} · channel={event.get('channel')}"
    if name == "stage":
        detail = event.get("detail")
        bits = f"{event.get('stage')} · {event.get('status')} · {event.get('latency_ms')}ms"
        return f"{bits} — {detail}" if detail else bits
    if name == "route":
        routes = event.get("routes") or []
        reason = event.get("reason", "")
        return f"{', '.join(routes)} — {reason}" if routes else reason
    if name == "citation":
        citation = _as_dict(event.get("citation"))
        return str(citation.get("title") or citation.get("source_id") or "")
    if name == "proposal":
        proposal = _as_dict(event.get("proposal"))
        risk, pid = proposal.get("risk"), proposal.get("proposal_id")
        return f"{proposal.get('action')} · risk={risk} · {pid}"
    if name == "answer":
        text = event.get("text") or ""
        return text if len(text) <= 80 else f"{text[:77]}..."
    if name == "usage":
        usage = _as_dict(event.get("usage"))
        cost = usage.get("cost_usd", 0)
        return f"cost=${cost:.4f} · tokens={usage.get('total_tokens', 0)}"
    if name == "error":
        return f"{event.get('code')}: {event.get('detail')}"
    if name == "turn.end":
        return f"status={event.get('status')} · {event.get('latency_ms')}ms"
    return ""


def _event_timeline(events: list[dict[str, Any]]) -> None:
    """The raw event sequence, in arrival order — the thing a JSON-body turn
    can never show, since it collapses the whole pipeline into one response."""
    dashboard.table_title("Event timeline (SSE)")
    st.dataframe(
        arrow_safe(
            [
                {"#": i + 1, "event": event.get("event", ""), "detail": _event_detail(event)}
                for i, event in enumerate(events)
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def _fold_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reassemble a stream's events into the same shape a JSON-body TurnResult
    already has, so `_turn_summary` below reads either one identically —
    folding is the only place that needs to know the event vocabulary
    (air-platform's `constants.EventType`).

    `degraded` has no equivalent event and is deliberately absent here: the
    JSON body summarises it as one field, but the SSE contract carries the
    same information implicitly, in each `stage` event's own status/detail.
    """
    folded: dict[str, Any] = {"trace": [], "citations": [], "usage": {}}
    for event in events:
        name = event.get("event")
        if name == "turn.start":
            folded["session_id"] = event.get("session_id")
        elif name == "stage":
            folded["trace"].append(
                {
                    "stage": event.get("stage"),
                    "status": event.get("status"),
                    "latency_ms": event.get("latency_ms"),
                    "detail": event.get("detail"),
                }
            )
        elif name == "route":
            folded["routes"] = event.get("routes")
        elif name == "citation":
            citation = event.get("citation")
            if isinstance(citation, dict):
                folded["citations"].append(citation)
        elif name == "proposal":
            folded["proposal"] = event.get("proposal")
        elif name == "answer":
            folded["answer"] = event.get("text")
            folded["structured"] = event.get("structured")
            folded["grounded"] = event.get("grounded", False)
            folded["refusal"] = event.get("refusal", False)
        elif name == "usage":
            folded["usage"] = event.get("usage") or {}
        elif name == "turn.end":
            folded["status"] = event.get("status")
    return folded


def _turn_summary(payload: Any, *, prefix: str, route: Route, connection: Connection) -> None:
    """A TurnResult, read the way an operator reads it: verdict, then evidence.

    `payload` is either the JSON body directly, or — when the turn was sent
    via SSE — the whole `Exchange`, whose `events` this folds into the same
    shape before falling through to identical rendering either way.
    """
    if isinstance(payload, Exchange):
        if payload.events:
            _event_timeline(payload.events)
        payload = _fold_events(payload.events)
    if not isinstance(payload, dict):
        return

    answer = payload.get("answer")
    if isinstance(answer, str) and answer.strip():
        with st.chat_message("assistant"):
            st.markdown(answer)

    status = str(payload.get("status", "—"))
    grounded = bool(payload.get("grounded"))
    refusal = bool(payload.get("refusal"))
    routes = payload.get("routes")
    session = payload.get("session_id")

    dashboard.grid(
        "Verdict",
        [
            [
                ("status", status, _STATUS_KIND.get(status, "")),
                ("grounded", yn(grounded), "" if grounded else "muted"),
                ("refusal", yn(refusal), "err" if refusal else "muted"),
                (
                    "routes",
                    ", ".join(routes) if isinstance(routes, list) and routes else "—",
                    "",
                ),
                ("session_id", fmt_text(session), ""),
            ]
        ],
    )

    degraded = payload.get("degraded")
    if isinstance(degraded, list) and degraded:
        st.warning(
            "Degraded: "
            + ", ".join(str(d) for d in degraded)
            + ". A capability was unavailable and the turn answered without it."
        )

    structured = payload.get("structured")
    if structured is not None:
        dashboard.table_title("Structured output")
        st.json(structured)

    proposal = payload.get("proposal")
    if proposal:
        _proposal_panel(_as_dict(proposal), prefix=prefix, route=route, connection=connection)

    citations = payload.get("citations")
    if isinstance(citations, list) and citations:
        dashboard.table_title("Citations")
        st.dataframe(
            arrow_safe([c for c in citations if isinstance(c, dict)]),
            hide_index=True,
            width="stretch",
        )

    trace = payload.get("trace")
    if isinstance(trace, list) and trace:
        dashboard.table_title("Pipeline stages")
        st.dataframe(
            arrow_safe(
                [
                    {
                        "stage": step.get("stage", ""),
                        "status": step.get("status"),
                        "latency ms": step.get("latency_ms"),
                        "detail": step.get("detail") or "",
                    }
                    for step in trace
                    if isinstance(step, dict)
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    usage = _as_dict(payload.get("usage"))
    if usage:
        cost = usage.get("cost_usd")
        dashboard.grid(
            "Usage",
            [
                [
                    ("model_calls", num(usage.get("model_calls")), ""),
                    ("prompt_tokens", num(usage.get("prompt_tokens")), ""),
                    ("completion_tokens", num(usage.get("completion_tokens")), ""),
                    ("total_tokens", num(usage.get("total_tokens")), ""),
                    ("cache_hit", yn(usage.get("cache_hit")), ""),
                    (
                        "cost",
                        format_cost(cost) if isinstance(cost, int | float) else "—",
                        "" if isinstance(cost, int | float) and cost > 0 else "muted",
                    ),
                ]
            ],
        )


def _proposal_panel(
    proposal: dict[str, Any], *, prefix: str, route: Route, connection: Connection
) -> None:
    """The second half of `confirm` — executing or declining a proposed mutation.

    A turn that proposes a mutation changes nothing on its own; confirming or
    declining it is an ordinary turn on the *same* session that also carries a
    `confirm: {proposal_id, approve}` object, per `docs/02-lld.md` §8. Neither
    development key grants `allow_actions`, so both buttons below will 403
    against a local checkout — that is the correct, honest outcome, and this
    exists for a remote key that actually carries the scope.
    """
    dashboard.table_title("Proposal")
    st.info(
        "This turn proposes a mutation and changed nothing. Confirming or declining it "
        "sends a second turn on the same session carrying `confirm` — needs a key with "
        "`allow_actions`, which neither development key grants by default.",
        icon=":material/gpp_maybe:",
    )
    st.json(proposal)

    proposal_id = proposal.get("proposal_id")
    if not isinstance(proposal_id, str) or not proposal_id:
        return

    session_id = str(st.session_state.get(f"{prefix}-session", "")).strip()
    if not session_id:
        st.caption(
            "No session id captured for this turn yet — a confirmation has to land on the "
            "same session the proposal did."
        )
        return

    url = join_url(connection.base_url, route.path)
    left, right = st.columns(2)
    left.button(
        "Confirm & execute",
        key=f"{prefix}-confirm-{proposal_id}-yes",
        type="primary",
        width="stretch",
        on_click=_send_turn,
        args=(
            prefix,
            url,
            connection,
            {
                route.field: "Confirm this action.",
                "session_id": session_id,
                "confirm": {"proposal_id": proposal_id, "approve": True},
            },
        ),
    )
    right.button(
        "Decline",
        key=f"{prefix}-confirm-{proposal_id}-no",
        width="stretch",
        on_click=_send_turn,
        args=(
            prefix,
            url,
            connection,
            {
                route.field: "Decline this action.",
                "session_id": session_id,
                "confirm": {"proposal_id": proposal_id, "approve": False},
            },
        ),
    )


def _transcript() -> list[dict[str, str]]:
    turns: list[dict[str, str]] = st.session_state.setdefault("platform-transcript", [])
    return turns


def _resolve_payload(exchange: Exchange) -> dict[str, Any] | None:
    """The turn result, whichever transport produced it.

    One JSON body for a plain send; the folded shape of a stream's events for
    one made with `send_stream` — `_send_turn` below reads either identically
    once past this, the same way `_turn_summary` does.
    """
    if exchange.is_stream:
        return _fold_events(exchange.events) if exchange.events else None
    return exchange.response_json if isinstance(exchange.response_json, dict) else None


def _send_turn(
    prefix: str, url: str, connection: Connection, body: dict[str, Any], *, stream: bool = False
) -> None:
    """Perform the turn and fold the result into session state.

    Runs as a widget callback, which is what makes the session hand-off legal:
    Streamlit refuses to let a widget's state key be written after that widget
    has been instantiated, and callbacks run before any of them are. Sending
    inline would mean the returned `session_id` could never populate the box it
    belongs in — the next turn would silently start a new conversation.

    `stream` picks the transport, not the shape of what happens next: `send`
    and `send_stream` both land in one `Exchange`, and `_resolve_payload`
    below is what makes the rest of this function transport-agnostic.
    """
    headers = build_headers(connection.api_key)
    transport = send_stream if stream else send
    exchange = transport(
        "POST",
        url,
        headers=headers,
        json_body=body,
        timeout=connection.timeout,
        verify=connection.verify,
    )
    remember(prefix, exchange)

    if not exchange.ok:
        return
    result = _resolve_payload(exchange)
    if result is None:
        return
    returned = result.get("session_id")
    if isinstance(returned, str) and returned:
        st.session_state[f"{prefix}-session"] = returned

    transcript = _transcript()
    asked = body.get("message") or body.get("query")
    if isinstance(asked, str) and asked.strip():
        transcript.append({"role": "user", "content": asked})
    answer = result.get("answer")
    if isinstance(answer, str) and answer:
        transcript.append({"role": "assistant", "content": answer})


def _send_row(
    prefix: str,
    url: str,
    connection: Connection,
    errors: list[str],
    body: dict[str, Any],
    *,
    stream: bool,
) -> None:
    left, right = st.columns([1, 4])
    left.button(
        "Send",
        type="primary",
        key=f"{prefix}-send",
        width="stretch",
        disabled=bool(errors),
        on_click=_send_turn,
        args=(prefix, url, connection, body),
        kwargs={"stream": stream},
    )
    marker = "REMOTE" if connection.is_remote else "LOCAL"
    keyed = "keyed" if connection.authenticated else "NO KEY"
    stream_chip = '<span class="air-chip key">SSE</span> ' if stream else ""
    right.markdown(
        f'<div class="air-meta" style="padding-top:.55rem">POST {html.escape(url)} '
        f'<span class="air-chip {connection.location}">{marker}</span> '
        f'<span class="air-chip {"key" if connection.authenticated else "nokey"}">'
        f"{connection.channel} · {keyed}</span> {stream_chip}</div>",
        unsafe_allow_html=True,
    )
    for message in errors:
        st.warning(message)


def render(customer: Connection, business: Connection) -> None:
    """Draw the platform tab. One connection per channel, picked by the route."""
    st.markdown(
        "One pipeline, two entry points. `/v1/chat` serves the customer gateway and "
        "`/v1/query` the corporate one, returning structured output. They differ only "
        "by profile — guardrails, output contract, audit sink, quota, tool allow-list."
    )

    label = st.radio(
        "Route",
        list(BY_LABEL),
        horizontal=True,
        key="platform-route",
        label_visibility="collapsed",
    )
    route = BY_LABEL[label]
    connection = customer if route.channel == "customer" else business

    target_bar.caption(connection)
    note(
        f"`{route.path}` is pinned to the **{route.channel}** channel, so the console "
        f"sends the {route.channel} key. The other key would be a 403 here — the "
        "channel is a property of the credential, not of the request."
    )
    _route_cards(route.key)
    st.divider()

    prefix = f"platform-{route.key}"
    errors: list[str] = []

    left, right = st.columns([3, 1])
    text = left.text_area(
        f"{route.field}  ·  required",
        key=f"{prefix}-text",
        height=110,
        placeholder=route.placeholder,
    )
    session_id = right.text_input(
        "session_id  ·  optional",
        key=f"{prefix}-session",
        placeholder="blank starts a new one",
        help="A new session id is returned on the first turn; paste it back to continue.",
    )

    body: dict[str, Any] = {route.field: text}
    if session_id.strip():
        body["session_id"] = session_id.strip()

    if route.key == "query":
        schema_raw = st.text_area(
            "output_schema  ·  optional JSON Schema the answer must satisfy",
            key=f"{prefix}-schema",
            height=110,
            placeholder='{"type": "object", "properties": {"count": {"type": "integer"}}}',
        )
        schema, error = parse_json_object(schema_raw, label="output_schema")
        if error:
            errors.append(error)
        if schema is not None:
            body["output_schema"] = schema

    options = _options_editor(prefix)
    if options:
        body["options"] = options

    stream = st.checkbox(
        "Stream via SSE (Accept: text/event-stream)",
        key=f"{prefix}-stream",
        help=(
            "Exercises the real event stream — turn.start, one stage event per "
            "pipeline step, route, citation, proposal, answer, usage, turn.end — "
            "instead of the single JSON body. Same summary either way."
        ),
    )

    if not text.strip():
        errors.insert(0, f"{route.field} is required.")
    if not connection.base_url.strip():
        errors.append("No air-platform base URL set in the sidebar.")

    with st.expander("Request body preview"):
        st.code(json.dumps(body, indent=2, ensure_ascii=False), language="json")

    url = join_url(connection.base_url, route.path)
    _send_row(prefix, url, connection, errors, body, stream=stream)

    stored = current(prefix)
    if stored is not None:
        section("Response")
        response_view.render(
            stored,
            key=prefix,
            summary=partial(_turn_summary, prefix=prefix, route=route, connection=connection),
        )

    transcript = _transcript()
    if transcript:
        section("Transcript")
        st.caption(
            "This session's turns, both routes. The service keeps its own history "
            "against `session_id`; this is only the local view."
        )
        st.button(
            "Clear transcript",
            key="platform-clear",
            on_click=lambda: st.session_state.update({"platform-transcript": []}),
        )
        for turn in transcript:
            with st.chat_message(turn["role"]):
                st.markdown(turn["content"])
