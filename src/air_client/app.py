"""Entry point for the AIR console.

Run with `make run`, or directly:

    streamlit run src/air_client/app.py
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
from air_client.components import sidebar
from air_client.config import load_defaults
from air_client.tabs import chat, sentiment, system


def main() -> None:
    st.set_page_config(
        page_title="AIR Console",
        page_icon="◆",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    theme.inject()
    theme.header(
        "AIR Console",
        "A developer's bench for the AIR services — send a request, read the response.",
    )

    defaults = load_defaults()
    classifier_conn, platform_conn = sidebar.render(defaults)

    sentiment_tab, chat_tab, system_tab = st.tabs(["Sentiment", "Chat", "System"])

    with sentiment_tab:
        sentiment.render(classifier_conn)
    with chat_tab:
        chat.render(platform_conn)
    with system_tab:
        system.render(classifier_conn, platform_conn)


main()
