"""Entry point for the AIR console.

Run with `make run`, or directly:

    streamlit run src/air_client/app.py

The console is a local tool: it is cloned and run on the tester's own machine
and pointed at whichever AIR deployment is under test. So the first thing drawn
under the title, before any tab, is where it is currently pointing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Allow `streamlit run src/air_client/app.py` to work in a bare checkout, before
# anyone has run `pip install -e .`.
if __package__ in (None, ""):  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from air_client import theme
from air_client.components import sidebar, target_bar
from air_client.config import load_defaults
from air_client.tabs import classifier, llm, platform, system


def main() -> None:
    st.set_page_config(
        page_title="AIR Console",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    # Defaults first: the appearance mode lives in them, and the stylesheet has
    # to be injected before anything it styles is drawn.
    defaults = load_defaults()
    theme.inject(theme.resolve_mode(defaults.theme))
    theme.header(
        "AIR Console",
        "A developer's bench for the AIR services — send a request, read the response. "
        "Runs on your machine against whichever environment you select.",
    )

    classifier_conn, customer_conn, business_conn, llm_conn = sidebar.render(defaults)
    target_bar.render(classifier_conn, customer_conn, business_conn, llm_conn)

    classifier_tab, platform_tab, llm_tab, system_tab = st.tabs(
        ["Classifier", "Platform", "LLM", "System"]
    )

    with classifier_tab:
        classifier.render(classifier_conn)
    with platform_tab:
        platform.render(customer_conn, business_conn)
    with llm_tab:
        llm.render(llm_conn)
    with system_tab:
        system.render(classifier_conn, customer_conn, business_conn, llm_conn)


main()
