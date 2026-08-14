"""A thin coat of CSS.

The brief was "a simple Google page, or Postman": generous whitespace, one
accent colour, flat surfaces, and status carried by a single unmissable pill.
The palette is pinned to a light base in `.streamlit/config.toml`, so these
colours are written literally rather than through theme variables.
"""

from __future__ import annotations

import streamlit as st

BLUE = "#1a73e8"
GREEN = "#188038"
AMBER = "#b06000"
RED = "#c5221f"
GREY = "#5f6368"
LINE = "#dadce0"

_CSS = f"""
<style>
  /* Keep the console dense: Streamlit's default top padding wastes a fold. */
  .block-container {{ padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1180px; }}

  .air-title {{ font-size: 1.55rem; font-weight: 500; color: #202124;
               letter-spacing: -0.2px; margin: 0 0 .15rem 0; }}
  .air-subtitle {{ color: {GREY}; font-size: .9rem; margin: 0 0 1.1rem 0; }}

  /* Tabs read as a Google-style underlined nav rather than boxes. */
  .stTabs [data-baseweb="tab-list"] {{ gap: .35rem; border-bottom: 1px solid {LINE}; }}
  .stTabs [data-baseweb="tab"] {{ height: 44px; padding: 0 1.05rem;
      background: transparent; font-weight: 500; color: {GREY}; }}
  .stTabs [aria-selected="true"] {{ color: {BLUE}; }}

  /* The status line: method, pill, timings. */
  .air-statusbar {{ display: flex; align-items: center; flex-wrap: wrap; gap: .55rem;
      padding: .6rem .85rem; border: 1px solid {LINE}; border-radius: 10px;
      background: #f8f9fa; margin: .5rem 0 .9rem 0; }}
  .air-pill {{ display: inline-block; padding: .16rem .62rem; border-radius: 999px;
      font-size: .78rem; font-weight: 600; letter-spacing: .2px; color: #fff; }}
  .air-pill.ok {{ background: {GREEN}; }}
  .air-pill.warn {{ background: {AMBER}; }}
  .air-pill.err {{ background: {RED}; }}
  .air-meta {{ color: {GREY}; font-size: .82rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .air-meta strong {{ color: #202124; font-weight: 600; }}

  /* Inline labels for sentiment/urgency verdicts. */
  .air-badge {{ display: inline-block; padding: .2rem .68rem; border-radius: 999px;
      font-size: .82rem; font-weight: 600; border: 1px solid transparent; }}
  .air-badge.positive {{ background: #e6f4ea; color: {GREEN}; border-color: #ceead6; }}
  .air-badge.negative {{ background: #fce8e6; color: {RED};   border-color: #f6cbc9; }}
  .air-badge.neutral  {{ background: #f1f3f4; color: {GREY};  border-color: {LINE}; }}
  .air-badge.mixed    {{ background: #fef7e0; color: {AMBER}; border-color: #feefc3; }}
  .air-badge.unknown  {{ background: #f1f3f4; color: {GREY};  border-color: {LINE};
      border-style: dashed; }}

  .air-section {{ font-size: .74rem; font-weight: 600; letter-spacing: .8px;
      text-transform: uppercase; color: {GREY}; margin: 1.15rem 0 .4rem 0; }}

  /* A quiet note for things that are not errors but need saying. */
  .air-note {{ border-left: 3px solid {LINE}; padding: .1rem 0 .1rem .7rem;
      color: {GREY}; font-size: .86rem; margin: .3rem 0 .8rem 0; }}

  /* Monospace anywhere a payload or identifier appears. */
  .stCodeBlock, code {{ font-size: .82rem; }}
  section[data-testid="stSidebar"] {{ border-right: 1px solid {LINE}; }}
  section[data-testid="stSidebar"] .block-container {{ padding-top: 1.4rem; }}
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="air-title">{title}</div><div class="air-subtitle">{subtitle}</div>',
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    st.markdown(f'<div class="air-section">{label}</div>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="air-note">{text}</div>', unsafe_allow_html=True)


def badge(text: str, kind: str) -> str:
    """Inline HTML badge. Caller decides where it lands."""
    kind = kind if kind in {"positive", "negative", "neutral", "mixed", "unknown"} else "neutral"
    return f'<span class="air-badge {kind}">{text}</span>'
