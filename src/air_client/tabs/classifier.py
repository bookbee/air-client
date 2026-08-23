"""The air-classifier tab: the single `/v1/classify` surface.

air-classifier answers one question — *what is this text saying, and how sure
are we* — through a four-rung escalation ladder (`t0_rules` → `t1_classifier` →
`t2_local_llm` → `t3_cloud_llm`). Every request enters at the cheapest rung and
climbs only when the rung below is not confident enough, and the response says
how far it climbed and why.

This used to be three routes (`/v1/sentiment`, `/v1/feedback`, `/v1/reviews`),
each adding a few request fields and a few response fields to a shared
envelope. They are gone: `POST /v1/classify` now accepts every field any of the
three ever did — `channel`/`user_segment`/`subject` from feedback,
`rating`/`product_id`/etc. from reviews — all optional, all read only where
they are relevant, and returns every field any of them ever produced. A caller
choosing between three response contracts on one service was always the same
confusion three endpoints were, so this tab now drives one form, not three.

Two details of the request shape drive the design here, unchanged from before:

* The request model sets ``additionalProperties: false``, so the console must
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

#: Scenario examples spanning the range one endpoint now covers — no longer
#: grouped by route, since there is only one to send them to.
EXAMPLES: tuple[tuple[str, str], ...] = (
    ("Mixed", "The battery life is superb but the camera is a letdown."),
    ("Positive", "Honestly the best purchase I have made all year."),
    ("Negative", "It broke within a week and support never replied."),
    ("Critical", "Checkout has been down for two hours. We are losing orders every minute."),
    ("Prose vs stars", "Arrived late and the box was crushed, but the product itself works."),
    (
        "PII",
        "Call me on +44 7700 900123 or email sam.doe@example.com — still no refund.",
    ),
)


@dataclass(frozen=True, slots=True)
class TierProbe:
    """One case written to land on exactly the named tier, and why it does.

    Straight from air-classifier's own README, "Sample texts, one confident
    case per tier" — keep this in sync with that table if it changes.
    """

    tier: str
    label: str
    text: str
    why: str
    #: Only the t0_rules rating shortcut needs this; every other probe leaves
    #: it unset, which is itself part of reproducing the case exactly.
    rating: float | None = None


#: Two confident cases per tier — the same texts the README pins with
#: `options.min_tier`/`max_tier` set to the tier named, so a working response
#: really did come from that rung and nowhere else. A pinned tier that cannot
#: serve returns 503 rather than quietly falling back, which is what makes
#: this a probe of the tier rather than just an example of text it might land on.
TIER_PROBES: tuple[TierProbe, ...] = (
    TierProbe(
        "t0_rules",
        "Lexicon shortcut",
        "absolutely terrible",
        "Short, unambiguous lexicon term — clears the 0.95 shortcut floor with no model involved.",
    ),
    TierProbe(
        "t0_rules",
        "Rating shortcut",
        "Arrived on time.",
        "An extreme, unambiguous star rating on short prose is its own shortcut.",
        rating=5.0,
    ),
    TierProbe(
        "t1_classifier",
        "Clear polarity",
        "Genuinely delighted with this purchase, it works beautifully.",
        "Clear single polarity, conventional phrasing — no T0 shortcut fits, no ambiguity "
        "needs an LLM.",
    ),
    TierProbe(
        "t1_classifier",
        "Non-English",
        "Der Akku ist gut, aber die Kamera enttäuscht.",
        "Same shape, non-English — the classifier is multilingual, T0's lexicon is not.",
    ),
    TierProbe(
        "t2_local_llm",
        "Sarcasm",
        "Battery lasts forever, if by forever you mean until lunchtime.",
        "A bag-of-terms classifier cannot see the reversal; needs real language understanding.",
    ),
    TierProbe(
        "t2_local_llm",
        "Genuine mix",
        "The screen is gorgeous but the battery dies by lunchtime.",
        "Praise and complaint in one sentence, which must come back mixed, not averaged to "
        "neutral.",
    ),
    TierProbe(
        "t3_cloud_llm",
        "Subtle irony",
        "Well, at least the box it arrived in was sturdy.",
        "Irony subtle enough that a 3B local model is itself unconfident and escalates.",
    ),
    TierProbe(
        "t3_cloud_llm",
        "Polite but damning",
        "Support replied within minutes, every single time, to tell me they could not help.",
        "Structurally polite, substantively damning — genuine ambiguity between literal and "
        "intended sentiment.",
    ),
)


def _tier_probes(prefix: str) -> None:
    """Force the ladder onto one named rung, reproducing the README's own cases.

    Sets `text` (and, for one case, `rating`) plus `options.min_tier`/`max_tier`
    pinned to the tier named — never the trace or cost/latency options, which do
    not decide which rung answers and may be a deliberate choice already made
    below. Runs before every other widget in the single form is instantiated
    this script pass, which is what lets a plain session-state write land in
    time to seed them.
    """
    with st.expander("Tier probes — pin the ladder to one rung, from the README", expanded=False):
        note(
            "Each button sets the text (and pins `options.min_tier`/`max_tier` to the tier "
            "named) so the verdict cannot have come from anywhere else — a pinned tier that "
            "cannot serve returns `503` rather than quietly falling back."
        )
        columns = st.columns(4)
        for column, tier in zip(columns, TIERS, strict=True):
            with column:
                st.caption(f"`{tier}`")
                for index, probe in enumerate(TIER_PROBES):
                    if probe.tier != tier:
                        continue
                    if st.button(
                        probe.label,
                        key=f"{prefix}-probe-{tier}-{index}",
                        width="stretch",
                    ):
                        st.session_state[f"{prefix}-text"] = probe.text
                        st.session_state[f"{prefix}-on-min_tier"] = True
                        st.session_state[f"{prefix}-min_tier"] = probe.tier
                        st.session_state[f"{prefix}-on-max_tier"] = True
                        st.session_state[f"{prefix}-max_tier"] = probe.tier
                        st.session_state[f"{prefix}-on-rating"] = probe.rating is not None
                        if probe.rating is not None:
                            st.session_state[f"{prefix}-rating"] = probe.rating


def _endpoint_card() -> None:
    """What `/v1/classify` sends and returns, at a glance.

    One card rather than three: the routes are gone, but the shape of "what
    varies" is still worth showing, because the response fields split into
    always-present ones and ones that only appear when the ladder reached an
    LLM tier — a distinction easy to misread as a bug the first time you see it.
    """
    st.markdown(
        '<div class="air-route on">'
        '<div class="air-route-path">POST /v1/classify · POST /v1/classify/batch</div>'
        '<div class="air-route-what">One entry point for any text — plain sentiment, '
        "product feedback, a marketplace review, or anything in between. The text and "
        "the fields you supply are what decide which of those it looks like, not which "
        "endpoint you called.</div>"
        '<div class="air-route-adds">always returns: sentiment, urgency, routing, '
        "requires_human, actionability, emotions<br>"
        "only when the ladder reaches an LLM tier: tone, topics, intent, aspects<br>"
        "only when you supply <code>rating</code>: rating_consistency</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _options_editor(prefix: str) -> dict[str, Any]:
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
            row[1].caption(
                "Default: unset — the service picks aspects itself when the text has any. Max 20."
            )

    return options


def _envelope_fields(
    prefix: str,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """The `text`, `context` and `metadata` every request carries."""
    errors: list[str] = []

    cols = st.columns(len(EXAMPLES) + 1)
    for index, (label, value) in enumerate(EXAMPLES):
        if cols[index].button(label, key=f"{prefix}-ex-{index}", width="stretch"):
            st.session_state[f"{prefix}-text"] = value

    text = st.text_area(
        "text  ·  required",
        key=f"{prefix}-text",
        height=120,
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
            height=100,
            placeholder='{"locale": "en-GB", "channel": "app"}',
            help="Situational context the service's rules can read.",
        )
    with right:
        metadata_raw = st.text_area(
            "metadata  ·  optional JSON",
            key=f"{prefix}-metadata",
            height=100,
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


def _optional_fields(prefix: str) -> dict[str, Any]:
    """Every field `/v1/classify` accepts beyond text/context/metadata.

    Formerly split across `/feedback` and `/reviews`; both groups are always
    available now; tucked into one expander so the form stays compact when
    nobody needs them, which is most of the time.
    """
    extras: dict[str, Any] = {}

    with st.expander("Optional context — feedback & review fields, all independent"):
        section("Feedback-shaped")
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

        section("Review-shaped")
        cols = st.columns([1, 1, 1, 1])
        send_rating = cols[0].checkbox("send rating", key=f"{prefix}-on-rating")
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


def _single_form(connection: Connection) -> None:
    prefix = "clf-single"
    _tier_probes(prefix)
    text, context, metadata, errors = _envelope_fields(prefix)
    extras = _optional_fields(prefix)
    options = _options_editor(prefix)

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

    url = join_url(connection.base_url, "/v1/classify")
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


def _batch_form(connection: Connection) -> None:
    prefix = "clf-batch"
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
            height=160,
            placeholder="Great value for money.\nArrived broken.\nDoes the job, nothing special.",
        )
        items = [{"text": line.strip()} for line in raw.splitlines() if line.strip()]
    else:
        raw = st.text_area(
            "items  ·  JSON array of request objects",
            key=f"{prefix}-json",
            height=200,
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

    options = _options_editor(prefix)

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

    url = join_url(connection.base_url, "/v1/classify/batch")
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
        "One endpoint onto a four-rung escalation ladder — `t0_rules` → `t1_classifier` "
        "→ `t2_local_llm` → `t3_cloud_llm`. Every request enters at the cheapest rung "
        "and climbs only when the rung below is not confident enough; the response "
        "says how far it climbed and why."
    )
    target_bar.caption(connection)

    _endpoint_card()
    st.divider()

    mode = st.radio(
        "Mode",
        ["Single", "Batch"],
        horizontal=True,
        key="clf-mode",
        label_visibility="collapsed",
    )

    if mode == "Single":
        _single_form(connection)
    else:
        _batch_form(connection)
