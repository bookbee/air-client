"""Connection settings.

Kept in the sidebar and out of the tabs, because during development the thing
you change most often is *where* you are pointing, not what you are sending.

Two rules govern this file:

* Environment values seed the widgets once; after that the widgets are the truth.
  Streamlit would otherwise reset a field you just edited on the next rerun.
* Every widget that changes the destination announces the destination back to
  you. Nobody should have to expand anything to find out whether the next Send
  lands on their laptop or on a shared QA box.
"""

from __future__ import annotations

import streamlit as st

from air_client import theme
from air_client.config import Defaults, Target, location_of
from air_client.connection import Connection

#: Widget keys the target switcher rewrites. Session state is the single source
#: of truth for these; the widgets below are declared with `key` and no `value`
#: so that a programmatic switch and a manual edit cannot disagree.
FIELD_KEYS = (
    "classifier_base_url",
    "classifier_api_key",
    "platform_base_url",
    "platform_api_key",
)

_SEEDED = "connection-seeded"


def _fields_of(target: Target) -> dict[str, str]:
    return {
        "classifier_base_url": target.classifier_base_url,
        "classifier_api_key": target.classifier_api_key,
        "platform_base_url": target.platform_base_url,
        "platform_api_key": target.platform_api_key,
    }


def _seed(defaults: Defaults) -> None:
    """Populate session state once, on first render of the session."""
    if st.session_state.get(_SEEDED):
        return
    st.session_state["target_name"] = defaults.selected
    st.session_state.update(_fields_of(defaults.selected_target))
    st.session_state.setdefault("timeout_seconds", defaults.timeout_seconds)
    st.session_state.setdefault("verify_tls", defaults.verify_tls)
    st.session_state[_SEEDED] = True


def apply_target(defaults: Defaults, name: str) -> None:
    """Overwrite the connection fields from a named target.

    Used as a widget callback, so it runs *before* the rerun that redraws the
    widgets — which is what lets it change values a user has already typed.
    """
    target = defaults.targets.get(name)
    if target is None:
        return
    st.session_state["target_name"] = name
    st.session_state.update(_fields_of(target))
    # A fresh target has not been probed yet; stale dots are worse than none.
    st.session_state.pop("probe-results", None)


def _is_edited(defaults: Defaults) -> bool:
    """Have the live fields drifted from the target they were loaded from?"""
    target = defaults.targets.get(st.session_state.get("target_name", ""))
    if target is None:
        return False
    return any(st.session_state.get(key, "") != value for key, value in _fields_of(target).items())


def _location_caption(base_url: str) -> None:
    location = location_of(base_url)
    if location == "remote":
        st.caption(f":orange[⬆ REMOTE] · {base_url}")
    elif location == "local":
        st.caption(f":blue[⌂ LOCAL] · {base_url}")
    else:
        st.caption(":grey[no base URL set]")


def _appearance_note(mode: str) -> None:
    """Say so when an explicit choice disagrees with Streamlit's own theme.

    A running app cannot re-theme Streamlit's chrome — the theme is fixed for
    the session — so Light/Dark repaints the console's own surfaces and leaves
    alert boxes and a few widgets on whatever Streamlit resolved at start-up. On
    a machine whose OS already matches the choice nothing is out of step, so the
    warning only appears when it genuinely is.
    """
    if mode == "auto":
        st.caption("Following your operating system.")
        return
    resolved = getattr(st.context.theme, "type", None)
    if resolved is None or resolved == mode:
        return
    st.caption(
        f":orange[Streamlit's widgets are still {resolved}.] Alert boxes will not "
        f"match. `make run THEME={mode}` pins both from start-up."
    )


def render(defaults: Defaults) -> tuple[Connection, Connection]:
    """Draw the sidebar; return the classifier and platform connections."""
    _seed(defaults)

    with st.sidebar:
        st.markdown("### Target")
        names = list(defaults.targets)
        st.selectbox(
            "Environment",
            names,
            key="target_name",
            format_func=lambda name: defaults.targets[name].label,
            on_change=lambda: apply_target(defaults, st.session_state["target_name"]),
            help=(
                "Named environments come from `.env`. Switching one rewrites the "
                "URLs and keys below; editing those by hand is always allowed."
            ),
        )
        if len(names) == 1:
            st.caption(
                "Only `local` is declared. Add `AIR_CLIENT__TARGETS__<NAME>__…` "
                "entries to `.env` to switch between deployments from here."
            )

        selected = st.session_state["target_name"]
        if _is_edited(defaults):
            st.caption(f":orange[edited] · differs from `{selected}` as declared in `.env`")
            st.button(
                "Reset to .env values",
                key="reset-target",
                width="stretch",
                on_click=apply_target,
                args=(defaults, selected),
            )

        st.divider()

        st.markdown("**air-classifier**")
        st.text_input(
            "Base URL",
            key="classifier_base_url",
            help="No trailing path — the console appends /v1/… itself.",
        )
        _location_caption(str(st.session_state.get("classifier_base_url", "")))
        st.text_input(
            "X-API-Key",
            key="classifier_api_key",
            type="password",
            help=(
                "Sent as `X-API-Key`. A local checkout of air-classifier accepts "
                "`airc_local_dev_key`, which is what `local` is preloaded with."
            ),
        )
        if not str(st.session_state.get("classifier_api_key", "")).strip():
            st.caption(":red[no key set] · authenticated routes will return 401")

        st.divider()

        st.markdown("**air-platform**")
        st.text_input("Base URL", key="platform_base_url")
        _location_caption(str(st.session_state.get("platform_base_url", "")))
        st.text_input("X-API-Key", key="platform_api_key", type="password")

        st.divider()

        with st.expander("Request behaviour", expanded=False):
            st.number_input(
                "Timeout (seconds)",
                min_value=1.0,
                max_value=300.0,
                step=5.0,
                key="timeout_seconds",
                help=(
                    "A cold local model on the t2 rung can take tens of seconds; so "
                    "can a first call to a remote environment that has scaled to zero."
                ),
            )
            st.checkbox(
                "Verify TLS certificates",
                key="verify_tls",
                help="Turn off only for a self-signed staging endpoint.",
            )

        st.divider()

        st.markdown("**Appearance**")
        st.radio(
            "Theme",
            theme.MODES,
            key="theme_mode",
            horizontal=True,
            format_func=lambda mode: mode.capitalize(),
            label_visibility="collapsed",
            help=(
                "**Auto** follows your operating system, chrome included. "
                "**Light** and **Dark** override it for this session. For a forced "
                "mode from start-up, run `make run THEME=dark`."
            ),
        )
        _appearance_note(str(st.session_state["theme_mode"]))

        st.caption(
            "Nothing here is written back to disk — edits last for this browser "
            "session. Preset them in `.env`; see `.env.example`."
        )

    target = defaults.targets[st.session_state["target_name"]]
    seconds = float(st.session_state["timeout_seconds"])
    check_tls = bool(st.session_state["verify_tls"])

    return (
        Connection(
            service="air-classifier",
            target=target.name,
            target_label=target.label,
            base_url=str(st.session_state["classifier_base_url"]).strip(),
            api_key=str(st.session_state["classifier_api_key"]),
            timeout=seconds,
            verify=check_tls,
        ),
        Connection(
            service="air-platform",
            target=target.name,
            target_label=target.label,
            base_url=str(st.session_state["platform_base_url"]).strip(),
            api_key=str(st.session_state["platform_api_key"]),
            timeout=seconds,
            verify=check_tls,
        ),
    )
