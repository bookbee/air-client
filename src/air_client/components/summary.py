"""Decoding a `/v1/classify` response into something readable at a glance.

One envelope for every request now — the old `/sentiment`, `/feedback` and
`/reviews` split is gone — but the fields still fall into three groups worth
telling apart: always present (sentiment, urgency, routing, actionability,
requires_human, emotions), present only when the ladder reached an LLM tier
(tone, topics, intent, aspects), and present only when the caller supplied a
`rating` (rating_consistency). The renderer walks the always-present shape
first, then each conditional block, noting rather than hiding when a
conditional one is empty — that absence is itself informative about how far
the ladder climbed.

Every panel is one of `dashboard.py`'s dense data grids: several related
facts on one monospace row, colour reserved for state actually worth a second
look (a failure, a ceiling, a flag) rather than decorating every field.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from air_client import dashboard
from air_client.currency import format_cost
from air_client.dashboard import Kind, num, pct, text, yn
from air_client.tables import arrow_safe
from air_client.theme import note

_SENTIMENT_KIND: dict[str, Kind] = {
    "positive": "ok",
    "negative": "err",
    "mixed": "warn",
    "neutral": "",
    "unknown": "muted",
}
_URGENCY_KIND: dict[str, Kind] = {"low": "", "medium": "warn", "high": "err", "critical": "err"}
_ACTIONABILITY_KIND: dict[str, Kind] = {
    "none": "",
    "informational": "",
    "actionable": "warn",
    "blocking": "err",
}
_PRIORITY_KIND: dict[str, Kind] = {"p1": "err", "p2": "warn", "p3": "", "p4": ""}
_TONE_KIND: dict[str, Kind] = {
    "satisfied": "ok",
    "appreciative": "ok",
    "neutral": "",
    "confused": "",
    "frustrated": "warn",
    "urgent": "warn",
    "sarcastic": "warn",
    "angry": "err",
    "disappointed": "err",
    "anxious": "err",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _labeled(value: Any, kinds: dict[str, Kind]) -> tuple[str, Kind]:
    """`{label, confidence}` → one dense value string, plus its colour."""
    scored = _as_dict(value)
    label = scored.get("label")
    if not label:
        return "—", "muted"
    confidence = scored.get("confidence")
    display = f"{label} · {confidence:.0%}" if isinstance(confidence, int | float) else str(label)
    return display, kinds.get(str(label), "")


def _verdict(payload: dict[str, Any]) -> None:
    sentiment = _as_dict(payload.get("sentiment"))
    label = sentiment.get("label", "unknown")
    polarity = sentiment.get("polarity")
    confidence = sentiment.get("confidence")
    language = _as_dict(payload.get("language"))
    degraded = bool(payload.get("degraded"))

    dashboard.grid(
        "Verdict",
        [
            [
                ("label", text(label), _SENTIMENT_KIND.get(str(label), "")),
                ("polarity", f"{polarity:+.2f}" if isinstance(polarity, int | float) else "—", ""),
                ("confidence", pct(confidence), ""),
            ],
            [
                ("decided_by", text(payload.get("decided_by")), ""),
                ("degraded", yn(degraded), "err" if degraded else ""),
                ("cached", yn(payload.get("cached")), ""),
                (
                    "language",
                    f"{language.get('code', '—')} · {pct(language.get('confidence'))}",
                    "",
                ),
            ],
        ],
    )

    rationale = sentiment.get("rationale")
    if isinstance(rationale, str) and rationale.strip():
        st.caption(f"“{rationale}”")

    if degraded:
        st.warning(
            "`degraded: true` — at least one tier failed and the verdict came from a "
            "lower rung than the ladder wanted. Check the escalation trace below."
        )


def _routing_and_actionability(payload: dict[str, Any]) -> None:
    """Urgency, actionability, routing and requires_human — unconditional fields
    on `ClassificationResponse` now, heuristics computed for every verdict
    rather than only ones that arrived via the old `/feedback` route."""
    urgency_value, urgency_kind = _labeled(payload.get("urgency"), _URGENCY_KIND)
    actionability = str(payload.get("actionability") or "—")
    routing = _as_dict(payload.get("routing"))
    queue = routing.get("queue")
    priority = str(routing.get("priority") or "")
    requires_human = bool(payload.get("requires_human"))

    dashboard.grid(
        "Routing",
        [
            [
                ("urgency", urgency_value, urgency_kind),
                ("actionability", actionability, _ACTIONABILITY_KIND.get(actionability, "")),
                ("queue", text(queue), "" if queue else "muted"),
                (
                    "priority",
                    priority or "—",
                    _PRIORITY_KIND.get(priority.lower(), "") if priority else "muted",
                ),
                ("requires_human", yn(requires_human), "warn" if requires_human else "muted"),
            ]
        ],
    )


def _tone_topics_intent(payload: dict[str, Any]) -> None:
    """Tone, topics and intent — populated only when the ladder reached an LLM
    tier *and* the request wanted them filled. Absence is the common case,
    not a bug, so it is the grid's own empty state rather than a hidden panel.
    """
    tone_value, tone_kind = _labeled(payload.get("tone"), _TONE_KIND)
    intent_value, _ = _labeled(payload.get("intent"), {})
    topics = payload.get("topics")
    topic_labels = (
        ", ".join(str(t.get("label")) for t in topics if isinstance(t, dict))
        if isinstance(topics, list) and topics
        else ""
    )

    rows = (
        []
        if tone_value == "—" and intent_value == "—" and not topic_labels
        else [
            [
                ("tone", tone_value, tone_kind),
                ("intent", intent_value, "" if intent_value != "—" else "muted"),
                ("topics", topic_labels or "—", "" if topic_labels else "muted"),
            ]
        ]
    )
    dashboard.grid(
        "Tone, topics & intent",
        rows,
        empty=(
            "No tone, topics or intent — either the ladder stopped before an LLM tier, or "
            "the deciding rung was not asked to fill them."
        ),
    )


def _rating_consistency_block(payload: dict[str, Any]) -> None:
    """Reviews' rating check — only rendered when the caller supplied a rating."""
    consistency = _as_dict(payload.get("rating_consistency"))
    if not consistency:
        return

    agreement = str(consistency.get("agreement", "—"))
    delta = consistency.get("delta")
    normalised = consistency.get("normalised_rating")
    disagrees = agreement not in ("agrees", "—")

    dashboard.grid(
        "Rating consistency",
        [
            [
                ("agreement", agreement.replace("_", " "), "warn" if disagrees else ""),
                ("delta", f"{delta:+.2f}" if isinstance(delta, int | float) else "—", ""),
                (
                    "normalised_rating",
                    f"{normalised:+.2f}" if isinstance(normalised, int | float) else "—",
                    "",
                ),
            ]
        ],
    )
    if disagrees:
        st.info(
            f"The prose and the stars disagree ({agreement.replace('_', ' ')}) — often the "
            "most interesting rows in a review set."
        )


def _emotions_and_aspects(payload: dict[str, Any]) -> None:
    emotions = payload.get("emotions")
    if isinstance(emotions, list) and emotions:
        dashboard.table_title("Emotions")
        st.dataframe(
            arrow_safe(
                [
                    {"emotion": e.get("name", ""), "score": e.get("score")}
                    for e in emotions
                    if isinstance(e, dict)
                ]
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "score": st.column_config.ProgressColumn(
                    "score", min_value=0.0, max_value=1.0, format="%.2f"
                )
            },
        )

    aspects = payload.get("aspects")
    if isinstance(aspects, list) and aspects:
        dashboard.table_title("Aspects")
        st.dataframe(
            arrow_safe(
                [
                    {
                        "aspect": a.get("name", ""),
                        "label": a.get("label", ""),
                        "confidence": a.get("confidence"),
                        "evidence": a.get("evidence", ""),
                    }
                    for a in aspects
                    if isinstance(a, dict)
                ]
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "confidence": st.column_config.ProgressColumn(
                    "confidence", min_value=0.0, max_value=1.0, format="%.2f"
                )
            },
        )


def _trace(payload: dict[str, Any]) -> None:
    """The escalation ladder — one row per rung tried, with the model that
    answered folded in from `model_versions` rather than shown as a separate
    panel: it is the same fact ("what actually served this rung") read
    alongside the rest of that rung's row, not a fact on its own."""
    trace = payload.get("escalation_trace")
    if not isinstance(trace, list) or not trace:
        note(
            "No escalation trace in this response — `options.include_trace` was off, "
            "or the service omitted it."
        )
        return

    versions = _as_dict(payload.get("model_versions"))
    dashboard.table_title("Escalation ladder")
    st.dataframe(
        arrow_safe(
            [
                {
                    "tier": step.get("tier", ""),
                    "label": step.get("label", ""),
                    "confidence": step.get("confidence"),
                    "latency ms": step.get("latency_ms"),
                    "model": versions.get(str(step.get("tier")), "—"),
                    "ok": step.get("succeeded"),
                    "escalated because": step.get("escalated_because") or "— (accepted)",
                }
                for step in trace
                if isinstance(step, dict)
            ]
        ),
        hide_index=True,
        width="stretch",
        column_config={
            "confidence": st.column_config.ProgressColumn(
                "confidence", min_value=0.0, max_value=1.0, format="%.2f"
            )
        },
    )


def _safety_and_usage(payload: dict[str, Any]) -> None:
    safety = _as_dict(payload.get("safety"))
    pii_redacted = bool(safety.get("pii_redacted"))
    flagged = bool(safety.get("flagged"))
    truncated = bool(safety.get("truncated"))
    findings = safety.get("pii_findings")
    finding_count = (
        sum(int(f.get("count", 0)) for f in findings if isinstance(f, dict))
        if isinstance(findings, list)
        else 0
    )

    dashboard.grid(
        "Safety",
        [
            [
                ("pii_redacted", yn(pii_redacted), "ok" if pii_redacted else "muted"),
                ("pii_findings", str(finding_count), "warn" if finding_count else "muted"),
                ("flagged", yn(flagged), "err" if flagged else "muted"),
                ("truncated", yn(truncated), "warn" if truncated else "muted"),
            ]
        ],
    )
    if isinstance(findings, list) and findings:
        st.dataframe(
            arrow_safe(
                [
                    {"kind": f.get("kind", ""), "count": f.get("count")}
                    for f in findings
                    if isinstance(f, dict)
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    reason = safety.get("flag_reason")
    if isinstance(reason, str) and reason:
        st.warning(f"Flagged: {reason}")

    usage = _as_dict(payload.get("usage"))
    cost = usage.get("est_cost_usd")
    dashboard.grid(
        "Usage & cost",
        [
            [
                ("tiers_run", num(usage.get("tiers_run")), ""),
                ("tokens_in", num(usage.get("tokens_in")), ""),
                ("tokens_out", num(usage.get("tokens_out")), ""),
                ("cache_read_tokens", num(usage.get("cache_read_tokens")), ""),
                (
                    "cost",
                    format_cost(cost) if isinstance(cost, int | float) else "—",
                    "" if isinstance(cost, int | float) and cost > 0 else "muted",
                ),
            ]
        ],
    )

    metadata = _as_dict(payload.get("metadata"))
    if metadata:
        with st.expander("Metadata echoed back"):
            st.json(metadata)


def render_analysis(payload: Any) -> None:
    """Render one `/v1/classify` response, whatever fields it happens to carry."""
    payload = _as_dict(payload)
    if not payload:
        note("Nothing to summarise.")
        return

    _verdict(payload)
    _routing_and_actionability(payload)
    _tone_topics_intent(payload)
    _rating_consistency_block(payload)
    _emotions_and_aspects(payload)
    _trace(payload)
    _safety_and_usage(payload)


def render_batch(payload: Any) -> None:
    """Render a batch response: the roll-up, then each item on demand."""
    payload = _as_dict(payload)
    items = payload.get("items")
    if not isinstance(items, list):
        note("No items in this batch response.")
        return

    usage = _as_dict(payload.get("usage"))
    cost = usage.get("est_cost_usd")
    latency = payload.get("latency_ms")
    dashboard.grid(
        "Batch",
        [
            [
                ("succeeded", num(payload.get("succeeded")), ""),
                ("failed", num(payload.get("failed")), "err" if payload.get("failed") else ""),
                ("service_ms", f"{latency:.0f}" if isinstance(latency, int | float) else "—", ""),
                ("cost", format_cost(cost) if isinstance(cost, int | float) else "—", ""),
            ]
        ],
    )

    dashboard.table_title("Items")
    overview = []
    for item in items:
        if not isinstance(item, dict):
            continue
        result = _as_dict(item.get("result"))
        sentiment = _as_dict(result.get("sentiment"))
        error = _as_dict(item.get("error"))
        overview.append(
            {
                "#": item.get("index"),
                "ok": item.get("ok"),
                "label": sentiment.get("label", ""),
                "polarity": sentiment.get("polarity"),
                "confidence": sentiment.get("confidence"),
                "decided by": result.get("decided_by", ""),
                "error": error.get("title", ""),
            }
        )
    st.dataframe(arrow_safe(overview), hide_index=True, width="stretch")

    for item in items:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if item.get("ok"):
            result = _as_dict(item.get("result"))
            label = _as_dict(result.get("sentiment")).get("label", "?")
            with st.expander(f"Item {index} — {label}"):
                render_analysis(result)
        else:
            error = _as_dict(item.get("error"))
            with st.expander(f"Item {index} — failed"):
                st.error(error.get("title", "Unknown error"))
                st.json(error)
