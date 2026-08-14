"""Decoding an analysis response into something readable at a glance.

Every air-classifier response shares one envelope; feedback and reviews bolt
extra blocks onto it. So the renderer walks the common shape first and then
picks up whichever domain extras are present, which means it handles all three
endpoints — and their batch forms — without branching on the route.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from air_client.theme import badge, note, section

_URGENCY_KIND = {
    "low": "neutral",
    "medium": "mixed",
    "high": "negative",
    "critical": "negative",
}
_ACTIONABILITY_KIND = {
    "none": "neutral",
    "informational": "neutral",
    "actionable": "mixed",
    "blocking": "negative",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _verdict(payload: dict[str, Any]) -> None:
    sentiment = _as_dict(payload.get("sentiment"))
    label = str(sentiment.get("label", "unknown"))
    polarity = sentiment.get("polarity")
    confidence = sentiment.get("confidence")

    left, mid, right = st.columns([1.4, 1, 1])
    with left:
        st.markdown("**Sentiment**")
        st.markdown(badge(label, label), unsafe_allow_html=True)
    with mid:
        st.metric(
            "Polarity",
            f"{polarity:+.2f}" if isinstance(polarity, int | float) else "—",
            help="-1 wholly negative, +1 wholly positive.",
        )
    with right:
        st.metric(
            "Confidence",
            f"{confidence:.0%}" if isinstance(confidence, int | float) else "—",
        )

    rationale = sentiment.get("rationale")
    if isinstance(rationale, str) and rationale.strip():
        st.markdown(f"> {rationale}")


def _provenance(payload: dict[str, Any]) -> None:
    """Which rung decided, and whether the answer is trustworthy."""
    cols = st.columns(4)
    cols[0].metric("Decided by", str(payload.get("decided_by", "—")))
    cols[1].metric("Degraded", "yes" if payload.get("degraded") else "no")
    cols[2].metric("Cached", "yes" if payload.get("cached") else "no")
    language = _as_dict(payload.get("language"))
    code = language.get("code")
    cols[3].metric("Language", str(code) if code else "—")

    if payload.get("degraded"):
        st.warning(
            "`degraded: true` — at least one tier failed and the verdict came from a "
            "lower rung than the ladder wanted. Check the escalation trace."
        )


def _domain_extras(payload: dict[str, Any]) -> None:
    """Feedback's routing block and reviews' rating check, when present."""
    urgency = payload.get("urgency")
    actionability = payload.get("actionability")
    route = payload.get("suggested_route")
    if urgency or actionability or route:
        section("Routing")
        cols = st.columns(3)
        with cols[0]:
            st.markdown("**Urgency**")
            st.markdown(
                badge(str(urgency), _URGENCY_KIND.get(str(urgency), "neutral")) if urgency else "—",
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown("**Actionability**")
            st.markdown(
                badge(str(actionability), _ACTIONABILITY_KIND.get(str(actionability), "neutral"))
                if actionability
                else "—",
                unsafe_allow_html=True,
            )
        with cols[2]:
            st.markdown("**Suggested route**")
            st.markdown(f"`{route}`" if route else "—")

    consistency = _as_dict(payload.get("rating_consistency"))
    if consistency:
        section("Rating consistency")
        agreement = str(consistency.get("agreement", "—"))
        delta = consistency.get("delta")
        normalised = consistency.get("normalised_rating")
        cols = st.columns(3)
        cols[0].metric("Agreement", agreement.replace("_", " "))
        cols[1].metric(
            "Delta",
            f"{delta:+.2f}" if isinstance(delta, int | float) else "—",
            help="Prose polarity minus the normalised star rating.",
        )
        cols[2].metric(
            "Normalised rating",
            f"{normalised:+.2f}" if isinstance(normalised, int | float) else "—",
            help="The author's stars mapped onto the polarity scale.",
        )
        if agreement != "agrees":
            st.info(
                f"The prose and the stars disagree ({agreement.replace('_', ' ')}) — "
                "often the most interesting rows in a review set."
            )


def _emotions_and_aspects(payload: dict[str, Any]) -> None:
    emotions = payload.get("emotions")
    if isinstance(emotions, list) and emotions:
        section("Emotions")
        st.dataframe(
            [
                {"emotion": e.get("name", ""), "score": e.get("score")}
                for e in emotions
                if isinstance(e, dict)
            ],
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
        section("Aspects")
        st.dataframe(
            [
                {
                    "aspect": a.get("name", ""),
                    "label": a.get("label", ""),
                    "confidence": a.get("confidence"),
                    "evidence": a.get("evidence", ""),
                }
                for a in aspects
                if isinstance(a, dict)
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "confidence": st.column_config.ProgressColumn(
                    "confidence", min_value=0.0, max_value=1.0, format="%.2f"
                )
            },
        )


def _trace(payload: dict[str, Any]) -> None:
    trace = payload.get("escalation_trace")
    if not isinstance(trace, list) or not trace:
        note(
            "No escalation trace in this response — `options.include_trace` was off, "
            "or the service omitted it."
        )
        return

    section("Escalation ladder")
    st.dataframe(
        [
            {
                "tier": step.get("tier", ""),
                "label": step.get("label", ""),
                "confidence": step.get("confidence"),
                "latency ms": step.get("latency_ms"),
                "ok": step.get("succeeded"),
                "escalated because": step.get("escalated_because") or "— (accepted)",
            }
            for step in trace
            if isinstance(step, dict)
        ],
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
    if safety:
        section("Safety")
        cols = st.columns(4)
        cols[0].metric("PII redacted", "yes" if safety.get("pii_redacted") else "no")
        cols[1].metric("Flagged", "yes" if safety.get("flagged") else "no")
        cols[2].metric("Truncated", "yes" if safety.get("truncated") else "no")
        findings = safety.get("pii_findings")
        count = (
            sum(int(f.get("count", 0)) for f in findings if isinstance(f, dict))
            if isinstance(findings, list)
            else 0
        )
        cols[3].metric("PII findings", count)

        if isinstance(findings, list) and findings:
            st.dataframe(
                [
                    {"kind": f.get("kind", ""), "count": f.get("count")}
                    for f in findings
                    if isinstance(f, dict)
                ],
                hide_index=True,
                width="stretch",
            )
        reason = safety.get("flag_reason")
        if isinstance(reason, str) and reason:
            st.warning(f"Flagged: {reason}")

    usage = _as_dict(payload.get("usage"))
    if usage:
        section("Usage")
        cols = st.columns(5)
        cols[0].metric("Tiers run", usage.get("tiers_run", "—"))
        cols[1].metric("Tokens in", usage.get("tokens_in", "—"))
        cols[2].metric("Tokens out", usage.get("tokens_out", "—"))
        cols[3].metric("Cache read", usage.get("cache_read_tokens", "—"))
        cost = usage.get("est_cost_usd")
        cols[4].metric("Est. cost", f"${cost:.5f}" if isinstance(cost, int | float) else "—")

    versions = _as_dict(payload.get("model_versions"))
    if versions:
        with st.expander("Model versions"):
            st.json(versions)

    metadata = _as_dict(payload.get("metadata"))
    if metadata:
        with st.expander("Metadata echoed back"):
            st.json(metadata)


def render_analysis(payload: Any) -> None:
    """Render one analysis response — sentiment, feedback or review alike."""
    payload = _as_dict(payload)
    if not payload:
        note("Nothing to summarise.")
        return

    _verdict(payload)
    _provenance(payload)
    _domain_extras(payload)
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

    cols = st.columns(4)
    cols[0].metric("Succeeded", payload.get("succeeded", "—"))
    cols[1].metric("Failed", payload.get("failed", "—"))
    latency = payload.get("latency_ms")
    cols[2].metric("Service ms", f"{latency:.0f}" if isinstance(latency, int | float) else "—")
    usage = _as_dict(payload.get("usage"))
    cost = usage.get("est_cost_usd")
    cols[3].metric("Est. cost", f"${cost:.5f}" if isinstance(cost, int | float) else "—")

    section("Items")
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
    st.dataframe(overview, hide_index=True, width="stretch")

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
