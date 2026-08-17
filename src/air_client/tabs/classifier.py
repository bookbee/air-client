"""The air-classifier tab: all three classification routes.

air-classifier answers one question — *what is this text saying, and how sure
are we* — through a four-rung escalation ladder (`t0_rules` → `t1_classifier` →
`t2_local_llm` → `t3_cloud_llm`). Every request enters at the cheapest rung and
climbs only when the rung below is not confident enough, and the response says
how far it climbed and why.

The three routes are that same ladder, specialised:

* ``/v1/sentiment`` — the base verdict, with no assumptions about where the text
  came from.
* ``/v1/feedback`` — the same verdict plus triage: how urgent, how actionable,
  and which queue it belongs in.
* ``/v1/reviews`` — the same verdict plus aspect-level scoring, and a check of
  the prose against the star rating the author gave it.

They share one request envelope (`text` plus optional `context`, `metadata` and
`options`) and add a few domain fields each, so the form is built once and
specialised per route. Two details of the API shape drive the design here:

* Every request model sets ``additionalProperties: false``, so the console must
  send *only* fields the operator actually filled in. Blank inputs are omitted
  rather than sent as null or "".
* ``Options.model_fields_set`` is load-bearing server-side — a key that carries
  ``force_pii_redaction`` rejects an explicit ``redact_pii: false`` but happily
  accepts the same value arriving as an unspoken default. So each option gets
  an enable checkbox, and unchecked options are left out of the payload
  entirely instead of being sent at their default value.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from typing import Any

import streamlit as st

from air_client.components import response_view, summary, target_bar
from air_client.connection import Connection
from air_client.http import build_headers, join_url, send
from air_client.state import current, parse_json_object, remember
from air_client.theme import note, section

MAX_TEXT_CHARS = 20000
TIERS = ["t0_rules", "t1_classifier", "t2_local_llm", "t3_cloud_llm"]

#: The service's own default ceiling on a batch. The schema allows 1000; the
#: deployment you are pointed at almost certainly allows fewer. `/v1/capabilities`
#: on the System tab reports the real number for that environment.
DEFAULT_MAX_BATCH_ITEMS = 100


@dataclass(frozen=True, slots=True)
class Route:
    """One classification endpoint, and why you would choose it."""

    key: str
    label: str
    purpose: str
    sends: str
    returns: str


ROUTES: tuple[Route, ...] = (
    Route(
        key="sentiment",
        label="Sentiment",
        purpose="The base verdict on any text, with no assumptions about its origin.",
        sends="text, context, metadata",
        returns="label, polarity, confidence, rationale, emotions",
    ),
    Route(
        key="feedback",
        label="Feedback",
        purpose="Triage inbound product and support feedback: how loud is this, and who takes it?",
        sends="+ channel, user_segment, subject",
        returns="+ urgency, actionability, suggested_route",
    ),
    Route(
        key="reviews",
        label="Reviews",
        purpose="Read marketplace reviews per aspect, and check the prose against the stars.",
        sends="+ rating, rating_scale_max, product_id, verified_purchase",
        returns="+ aspects, rating_consistency",
    ),
)

BY_LABEL = {route.label: route for route in ROUTES}

EXAMPLES: dict[str, list[tuple[str, str]]] = {
    "sentiment": [
        ("Mixed", "The battery life is superb but the camera is a letdown."),
        ("Positive", "Honestly the best purchase I have made all year."),
        ("Negative", "It broke within a week and support never replied."),
        (
            "PII",
            "Call me on +44 7700 900123 or email sam.doe@example.com — still no refund.",
        ),
    ],
    "feedback": [
        ("Critical", "Checkout has been down for two hours. We are losing orders every minute."),
        ("Low", "Would be nice if dark mode remembered my choice between sessions."),
    ],
    "reviews": [
        ("Prose vs stars", "Arrived late and the box was crushed, but the product itself works."),
        ("Glowing", "Five stars is not enough. Setup took two minutes and it just works."),
    ],
}


def _route_cards(selected: str) -> None:
    """The three routes side by side, with the active one lit.

    Worth the vertical space: the routes differ only in what they *add* to a
    shared envelope, and that difference is invisible from the form alone.
    """
    columns = st.columns(len(ROUTES))
    for column, route in zip(columns, ROUTES, strict=True):
        with column:
            st.markdown(
                f'<div class="air-route {"on" if route.key == selected else ""}">'
                f'<div class="air-route-path">POST /v1/{route.key}</div>'
                f'<div class="air-route-what">{html.escape(route.purpose)}</div>'
                f'<div class="air-route-adds">sends {html.escape(route.sends)}<br>'
                f"returns {html.escape(route.returns)}</div>"
                "</div>",
                unsafe_allow_html=True,
            )


def _options_editor(prefix: str, *, show_aspects: bool) -> dict[str, Any]:
    """Postman-style option rows: tick to send, leave clear to inherit the default."""
    options: dict[str, Any] = {}

    with st.expander("Options — tick a row to send it, leave clear to use the service default"):
        note(
            "Unticked options are omitted from the payload entirely. That is deliberate: "
            "the service distinguishes “caller said nothing” from “caller explicitly asked "
            "for this value”, and some API keys reject the latter."
        )

        row = st.columns([1, 2])
        if row[0].checkbox("min_tier", key=f"{prefix}-on-min_tier"):
            options["min_tier"] = row[1].selectbox(
                "Force the ladder to reach at least this rung",
                TIERS,
                index=0,
                key=f"{prefix}-min_tier",
                label_visibility="collapsed",
            )
        else:
            row[1].caption("Default: unset — the ladder starts at t0_rules.")

        row = st.columns([1, 2])
        if row[0].checkbox("max_tier", key=f"{prefix}-on-max_tier"):
            options["max_tier"] = row[1].selectbox(
                "Hard ceiling",
                TIERS,
                index=3,
                key=f"{prefix}-max_tier",
                label_visibility="collapsed",
            )
        else:
            row[1].caption("Default: t3_cloud_llm. Cap at t2_local_llm to keep text on-prem.")

        row = st.columns([1, 2])
        if row[0].checkbox("latency_budget_ms", key=f"{prefix}-on-latency"):
            options["latency_budget_ms"] = row[1].number_input(
                "Latency budget (ms)",
                min_value=50,
                max_value=30000,
                value=8000,
                step=250,
                key=f"{prefix}-latency",
                label_visibility="collapsed",
            )
        else:
            row[1].caption("Default: 8000 ms.")

        row = st.columns([1, 2])
        if row[0].checkbox("max_cost_usd", key=f"{prefix}-on-cost"):
            options["max_cost_usd"] = row[1].number_input(
                "Max cost (USD)",
                min_value=0.0,
                max_value=10.0,
                value=0.05,
                step=0.01,
                format="%.4f",
                key=f"{prefix}-cost",
                label_visibility="collapsed",
            )
        else:
            row[1].caption("Default: $0.05 per request.")

        row = st.columns([1, 2])
        if row[0].checkbox("include_trace", key=f"{prefix}-on-trace"):
            options["include_trace"] = row[1].checkbox(
                "Return the escalation trace",
                value=True,
                key=f"{prefix}-trace",
            )
        else:
            row[1].caption("Default: true — the trace is what makes the ladder legible.")

        row = st.columns([1, 2])
        if row[0].checkbox("redact_pii", key=f"{prefix}-on-pii"):
            options["redact_pii"] = row[1].checkbox(
                "Redact PII before it reaches a model",
                value=True,
                key=f"{prefix}-pii",
            )
        else:
            row[1].caption("Default: true. An explicit false can be refused by your API key.")

        if show_aspects:
            row = st.columns([1, 2])
            if row[0].checkbox("aspects", key=f"{prefix}-on-aspects"):
                raw = row[1].text_input(
                    "Aspects to score, comma separated",
                    value="battery, camera, price",
                    key=f"{prefix}-aspects",
                    label_visibility="collapsed",
                )
                aspects = [a.strip() for a in raw.split(",") if a.strip()][:20]
                if aspects:
                    options["aspects"] = aspects
            else:
                row[1].caption("Default: unset — the service picks aspects itself. Max 20.")

    return options


def _envelope_fields(
    prefix: str, route: str
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """The `text`, `context` and `metadata` shared by all three endpoints."""
    errors: list[str] = []

    examples = EXAMPLES.get(route, [])
    if examples:
        cols = st.columns(len(examples) + 3)
        for index, (label, value) in enumerate(examples):
            if cols[index].button(label, key=f"{prefix}-ex-{index}", width="stretch"):
                st.session_state[f"{prefix}-text"] = value

    text = st.text_area(
        "text  ·  required",
        key=f"{prefix}-text",
        height=130,
        placeholder="The text to analyse…",
    )
    remaining = MAX_TEXT_CHARS - len(text)
    if len(text) > MAX_TEXT_CHARS:
        errors.append(f"text is {len(text)} characters; the service caps it at {MAX_TEXT_CHARS}.")
        st.caption(f":red[{-remaining} characters over the limit]")
    else:
        st.caption(f"{len(text)} / {MAX_TEXT_CHARS} characters")

    left, right = st.columns(2)
    with left:
        context_raw = st.text_area(
            "context  ·  optional JSON",
            key=f"{prefix}-context",
            height=110,
            placeholder='{"locale": "en-GB", "channel": "app"}',
            help="Situational context the service's rules can read.",
        )
    with right:
        metadata_raw = st.text_area(
            "metadata  ·  optional JSON",
            key=f"{prefix}-metadata",
            height=110,
            placeholder='{"ticket": "SUP-4821"}',
            help="Echoed back untouched; never interpreted.",
        )

    context, error = parse_json_object(context_raw, label="context")
    if error:
        errors.append(error)
    metadata, error = parse_json_object(metadata_raw, label="metadata")
    if error:
        errors.append(error)

    return text, context, metadata, errors


def _domain_fields(prefix: str, route: str) -> dict[str, Any]:
    """The handful of fields that only one endpoint accepts."""
    extras: dict[str, Any] = {}

    if route == "feedback":
        section("Feedback fields")
        cols = st.columns(3)
        channel = cols[0].text_input(
            "channel", key=f"{prefix}-channel", placeholder="app | email | support | survey"
        )
        segment = cols[1].text_input(
            "user_segment", key=f"{prefix}-segment", placeholder="enterprise"
        )
        subject = cols[2].text_input(
            "subject", key=f"{prefix}-subject", placeholder="Cannot check out"
        )
        if channel.strip():
            extras["channel"] = channel.strip()
        if segment.strip():
            extras["user_segment"] = segment.strip()
        if subject.strip():
            extras["subject"] = subject.strip()

    elif route == "reviews":
        section("Review fields")
        cols = st.columns([1, 1, 1, 1])
        send_rating = cols[0].checkbox("send rating", key=f"{prefix}-on-rating", value=True)
        rating = cols[1].number_input(
            "rating",
            min_value=0.0,
            value=2.0,
            step=0.5,
            key=f"{prefix}-rating",
            disabled=not send_rating,
        )
        scale = cols[2].number_input(
            "rating_scale_max",
            min_value=0.1,
            max_value=100.0,
            value=5.0,
            step=1.0,
            key=f"{prefix}-scale",
        )
        product = cols[3].text_input("product_id", key=f"{prefix}-product", placeholder="SKU-1234")

        cols = st.columns([1, 1, 2])
        title = cols[0].text_input("title", key=f"{prefix}-title", placeholder="Late but works")
        verified_choice = cols[1].selectbox(
            "verified_purchase", ["omit", "true", "false"], key=f"{prefix}-verified"
        )

        if send_rating:
            extras["rating"] = float(rating)
            extras["rating_scale_max"] = float(scale)
        if product.strip():
            extras["product_id"] = product.strip()
        if title.strip():
            extras["title"] = title.strip()
        if verified_choice != "omit":
            extras["verified_purchase"] = verified_choice == "true"

    return extras


def _send_row(
    prefix: str,
    label: str,
    url: str,
    connection: Connection,
    *,
    errors: list[str],
) -> bool:
    """The Send button and, beside it, the exact destination it will hit."""
    left, right = st.columns([1, 4])
    clicked = left.button(
        label, type="primary", key=f"{prefix}-send", width="stretch", disabled=bool(errors)
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


def _single_form(route: str, connection: Connection) -> None:
    prefix = f"clf-{route}-single"
    text, context, metadata, errors = _envelope_fields(prefix, route)
    extras = _domain_fields(prefix, route)
    options = _options_editor(prefix, show_aspects=route == "reviews")

    body: dict[str, Any] = {"text": text}
    body.update(extras)
    if context is not None:
        body["context"] = context
    if metadata is not None:
        body["metadata"] = metadata
    if options:
        body["options"] = options

    if not text.strip():
        errors.insert(0, "text is required.")

    with st.expander("Request body preview"):
        st.code(json.dumps(body, indent=2, ensure_ascii=False), language="json")

    url = join_url(connection.base_url, f"/v1/{route}")
    if _send_row(prefix, "Send", url, connection, errors=errors):
        with st.spinner(f"Calling air-classifier on {connection.target}…"):
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
        response_view.render(stored, key=prefix, summary=summary.render_analysis)


def _batch_form(route: str, connection: Connection) -> None:
    prefix = f"clf-{route}-batch"
    errors: list[str] = []

    mode = st.radio(
        "How do you want to supply the items?",
        ["One text per line", "Full JSON items array"],
        horizontal=True,
        key=f"{prefix}-mode",
    )

    items: list[dict[str, Any]] = []
    if mode == "One text per line":
        raw = st.text_area(
            "texts  ·  one per line",
            key=f"{prefix}-lines",
            height=170,
            placeholder="Great value for money.\nArrived broken.\nDoes the job, nothing special.",
        )
        items = [{"text": line.strip()} for line in raw.splitlines() if line.strip()]
    else:
        raw = st.text_area(
            "items  ·  JSON array of request objects",
            key=f"{prefix}-json",
            height=220,
            placeholder='[\n  {"text": "Great value."},\n  {"text": "Arrived broken.", '
            '"metadata": {"id": "r-2"}}\n]',
            help="Each element takes the same shape as a single request, minus batch options.",
        )
        if raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"items is not valid JSON: {exc.msg} (line {exc.lineno}).")
                parsed = None
            if parsed is not None:
                if not isinstance(parsed, list):
                    errors.append("items must be a JSON array.")
                elif not all(isinstance(item, dict) for item in parsed):
                    errors.append("every element of items must be a JSON object.")
                else:
                    items = parsed

    options = _options_editor(prefix, show_aspects=route == "reviews")

    if not items:
        errors.insert(0, "Supply at least one item.")
    if len(items) > DEFAULT_MAX_BATCH_ITEMS:
        st.warning(
            f"{len(items)} items. The schema allows 1000, but a deployment's own batch "
            f"ceiling defaults to {DEFAULT_MAX_BATCH_ITEMS} and rejects more. "
            "The System tab's Capabilities probe reports the limit for this target."
        )

    body: dict[str, Any] = {"items": items}
    if options:
        body["options"] = options

    st.caption(f"{len(items)} item(s) ready to send.")
    with st.expander("Request body preview"):
        st.code(json.dumps(body, indent=2, ensure_ascii=False)[:6000], language="json")

    url = join_url(connection.base_url, f"/v1/{route}/batch")
    if _send_row(prefix, "Send batch", url, connection, errors=errors):
        with st.spinner(f"Analysing {len(items)} item(s) on {connection.target}…"):
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
        response_view.render(stored, key=prefix, summary=summary.render_batch)


def render(connection: Connection) -> None:
    """Draw the whole classifier tab."""
    st.markdown(
        "Three routes onto one escalation ladder — `t0_rules` → `t1_classifier` → "
        "`t2_local_llm` → `t3_cloud_llm`. Every request enters at the cheapest rung "
        "and climbs only when the rung below is not confident enough; the response "
        "says how far it climbed and why."
    )
    target_bar.caption(connection)

    top = st.columns([2, 1])
    with top[0]:
        label = st.radio(
            "Route",
            list(BY_LABEL),
            horizontal=True,
            key="clf-route",
            label_visibility="collapsed",
        )
    with top[1]:
        mode = st.radio(
            "Mode",
            ["Single", "Batch"],
            horizontal=True,
            key="clf-mode",
            label_visibility="collapsed",
        )

    route = BY_LABEL[label].key
    _route_cards(route)
    st.divider()

    if mode == "Single":
        _single_form(route, connection)
    else:
        _batch_form(route, connection)
