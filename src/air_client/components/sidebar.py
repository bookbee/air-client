"""Connection settings.

Kept in the sidebar and out of the tabs, because during development the thing
you change most often is *where* you are pointing, not what you are sending.
Environment values seed the widgets once; after that the widgets are the truth.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from air_client.config import Defaults


@dataclass(frozen=True, slots=True)
class Connection:
    """Everything needed to talk to one service."""

    base_url: str
    api_key: str
    timeout: float
    verify: bool


def render(defaults: Defaults) -> tuple[Connection, Connection]:
    """Draw the sidebar; return the classifier and platform connections."""
    with st.sidebar:
        st.markdown("### Connection")

        st.markdown("**air-classifier**")
        classifier_url = st.text_input(
            "Base URL",
            value=defaults.classifier_base_url,
            key="classifier_base_url",
            help="No trailing path — the console appends /v1/... itself.",
        )
        classifier_key = st.text_input(
            "X-API-Key",
            value=defaults.classifier_api_key,
            key="classifier_api_key",
            type="password",
            help=(
                "Leave blank when the service runs with "
                "AIR_SENTIMENT__SECURITY__ALLOW_UNAUTHENTICATED=true — still spelled "
                "with the old prefix, since only the repo has been renamed so far."
            ),
        )

        st.divider()

        st.markdown("**air-platform**")
        platform_url = st.text_input(
            "Base URL",
            value=defaults.platform_base_url,
            key="platform_base_url",
        )
        platform_key = st.text_input(
            "X-API-Key",
            value=defaults.platform_api_key,
            key="platform_api_key",
            type="password",
        )

        st.divider()

        with st.expander("Advanced", expanded=False):
            timeout = st.number_input(
                "Timeout (seconds)",
                min_value=1.0,
                max_value=300.0,
                value=defaults.timeout_seconds,
                step=5.0,
                key="timeout_seconds",
                help="A cold local model on the t2 rung can take tens of seconds.",
            )
            verify = st.checkbox(
                "Verify TLS certificates",
                value=defaults.verify_tls,
                key="verify_tls",
                help="Turn off only for a self-signed staging endpoint.",
            )

        st.divider()
        st.caption(
            "Settings live for this browser session only. Preset them with a "
            "`.env` file — see `.env.example`."
        )

    seconds = float(timeout)
    check_tls = bool(verify)
    return (
        Connection(
            base_url=classifier_url,
            api_key=classifier_key,
            timeout=seconds,
            verify=check_tls,
        ),
        Connection(
            base_url=platform_url,
            api_key=platform_key,
            timeout=seconds,
            verify=check_tls,
        ),
    )
