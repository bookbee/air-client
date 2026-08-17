"""The console's skin, in light and dark.

The brief was "a simple Google page, or Postman": generous whitespace, one
accent colour, flat surfaces, and status carried by a single unmissable pill.
This module is the whole of it — every colour the console uses is declared here
once, as a CSS custom property, in two palettes.

Three things shape the implementation:

* **Both palettes are first-class.** QA sessions run for hours; a console that
  only works in light is a console people squint at. Nothing below hardcodes a
  colour outside :data:`_LIGHT` and :data:`_DARK`.
* **Auto is the default and is genuinely native.** With ``mode="auto"`` the
  palette switches on ``prefers-color-scheme`` and Streamlit's own chrome
  switches with it (see ``.streamlit/config.toml``, which declares a full
  ``[theme.light]`` and ``[theme.dark]`` and pins no base). Nothing is
  overridden, so nothing can disagree.
* **An explicit choice overrides in-session.** Streamlit sends theme config only
  in its ``new_session`` message, so a running app cannot ask it to re-theme.
  Picking Light or Dark therefore paints the surfaces here instead — app,
  sidebar, header, fields, code and the dataframe grid — and sets
  ``color-scheme`` so scrollbars and native controls follow too. For a
  chrome-perfect forced mode from the start, launch with ``make run THEME=dark``.
"""

from __future__ import annotations

from typing import Final

import streamlit as st

MODES: Final[tuple[str, ...]] = ("auto", "light", "dark")

_STATE_KEY: Final[str] = "theme_mode"

# ── Palettes ──────────────────────────────────────────────────────────────────
#
# Keys are CSS custom property names minus the `--air-` prefix. Both dicts must
# carry exactly the same keys: a var that exists in one palette and not the
# other is a colour that vanishes when someone switches theme.

_LIGHT: Final[dict[str, str]] = {
    "bg": "#ffffff",
    "surface": "#f8f9fa",
    "surface-warn": "#fffaf2",
    "field": "#ffffff",
    "ink": "#202124",
    "muted": "#5f6368",
    "line": "#dadce0",
    "blue": "#1a73e8",
    "green": "#188038",
    "amber": "#b06000",
    "red": "#c5221f",
    "code-bg": "#f1f3f4",
    "pill-ink": "#ffffff",
    "pos-bg": "#e6f4ea",
    "pos-line": "#ceead6",
    "neg-bg": "#fce8e6",
    "neg-line": "#f6cbc9",
    "neu-bg": "#f1f3f4",
    "neu-line": "#dadce0",
    "mix-bg": "#fef7e0",
    "mix-line": "#feefc3",
    "chip-local-bg": "#e8f0fe",
    "chip-remote-bg": "#feefc3",
    "scheme": "light",
}

_DARK: Final[dict[str, str]] = {
    "bg": "#0e1117",
    "surface": "#171a21",
    "surface-warn": "#1e1a12",
    "field": "#1c2027",
    "ink": "#e6e8eb",
    "muted": "#9aa0a6",
    "line": "#2c313a",
    # Google's dark-mode accents: the light-mode hues fail contrast on a dark
    # surface, so each one lifts rather than being reused.
    "blue": "#8ab4f8",
    "green": "#81c995",
    "amber": "#fdd663",
    "red": "#f28b82",
    "code-bg": "#161a21",
    # A saturated accent behind white text is unreadable in dark mode; pills
    # invert instead, dark ink on a light accent.
    "pill-ink": "#0e1117",
    "pos-bg": "rgba(129,201,149,.15)",
    "pos-line": "rgba(129,201,149,.38)",
    "neg-bg": "rgba(242,139,130,.15)",
    "neg-line": "rgba(242,139,130,.38)",
    "neu-bg": "rgba(154,160,166,.14)",
    "neu-line": "#2c313a",
    "mix-bg": "rgba(253,214,99,.14)",
    "mix-line": "rgba(253,214,99,.36)",
    "chip-local-bg": "rgba(138,180,248,.18)",
    "chip-remote-bg": "rgba(253,214,99,.18)",
    "scheme": "dark",
}


def _vars(palette: dict[str, str]) -> str:
    return "".join(f"--air-{name}:{value};" for name, value in palette.items())


def _roots(mode: str) -> str:
    """The custom-property block(s) for one mode."""
    if mode == "light":
        return f":root{{{_vars(_LIGHT)}}}"
    if mode == "dark":
        return f":root{{{_vars(_DARK)}}}"
    return f":root{{{_vars(_LIGHT)}}}@media (prefers-color-scheme: dark){{:root{{{_vars(_DARK)}}}}}"


# Only emitted for an explicit Light/Dark choice. In auto mode Streamlit's own
# theme already paints these, and overriding them would be a second source of
# truth that can only ever drift.
_CHROME: Final[str] = """
  :root { color-scheme: var(--air-scheme); }

  .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
  header[data-testid="stHeader"] { background: var(--air-bg) !important; }
  .stApp { color: var(--air-ink); }

  section[data-testid="stSidebar"],
  section[data-testid="stSidebar"] > div { background: var(--air-surface) !important; }

  /* Inputs, selects and the number stepper: baseweb paints these itself. */
  input, textarea, [data-baseweb="input"], [data-baseweb="textarea"],
  [data-baseweb="select"] > div, [data-baseweb="base-input"] {
      background: var(--air-field) !important; color: var(--air-ink) !important; }

  [data-testid="stExpander"] details, [data-testid="stExpander"] summary {
      background: var(--air-surface) !important; }

  pre, code, .stCodeBlock, [data-testid="stJson"] {
      background: var(--air-code-bg) !important; }

  /* The dataframe is a canvas grid; it reads its colours from these vars only. */
  [data-testid="stDataFrame"] {
      --gdg-bg-cell: var(--air-bg); --gdg-bg-header: var(--air-surface);
      --gdg-bg-header-hovered: var(--air-surface); --gdg-text-dark: var(--air-ink);
      --gdg-text-medium: var(--air-muted); --gdg-text-light: var(--air-muted);
      --gdg-text-header: var(--air-muted); --gdg-border-color: var(--air-line);
      --gdg-horizontal-border-color: var(--air-line);
      --gdg-bg-cell-medium: var(--air-surface); --gdg-accent-color: var(--air-blue); }
"""

_STATIC: Final[str] = """
  /* Fluid: fill the window, but keep a gutter and stop lines becoming
     unreadable ribbons on an ultrawide. The top padding is deliberate — it
     clears Streamlit's fixed toolbar so the page header is never underneath
     it. Padding tightens on narrow screens rather than content being clipped. */
  .block-container { padding: 4.6rem 2.2rem 3.5rem; max-width: 1800px; }
  @media (max-width: 900px) { .block-container { padding: 4.2rem 1rem 2.5rem; } }

  /* The page header. Sits in normal flow, never sticky: a floating band is the
     one thing guaranteed to end up on top of the title it is meant to label. */
  .air-header { padding: 0 0 .5rem 0; margin: 0 0 .9rem 0;
      border-bottom: 1px solid var(--air-line); }
  .air-title { font-size: 1.6rem; font-weight: 500; color: var(--air-ink);
               letter-spacing: -0.2px; margin: 0 0 .2rem 0; line-height: 1.2; }
  .air-subtitle { color: var(--air-muted); font-size: .9rem; margin: 0; }

  /* Tabs read as a Google-style underlined nav rather than boxes. */
  .stTabs [data-baseweb="tab-list"] { gap: .35rem; border-bottom: 1px solid var(--air-line); }
  .stTabs [data-baseweb="tab"] { height: 44px; padding: 0 1.05rem;
      background: transparent; font-weight: 500; color: var(--air-muted); }
  .stTabs [aria-selected="true"] { color: var(--air-blue); }

  /* ── Target bar ─────────────────────────────────────────────────────────── */
  .air-target { border: 1px solid var(--air-line); border-left-width: 4px;
      border-radius: 10px; padding: .55rem .8rem; background: var(--air-surface);
      margin: 0 0 .9rem 0; }
  .air-target.local { border-left-color: var(--air-blue); }
  .air-target.remote { border-left-color: var(--air-amber);
      background: var(--air-surface-warn); }
  .air-target-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: .5rem;
      margin-bottom: .35rem; font-size: .92rem; color: var(--air-ink); }
  .air-target-label { font-size: .68rem; font-weight: 700; letter-spacing: 1px;
      color: var(--air-muted); }
  .air-target-warn { font-size: .78rem; color: var(--air-muted); }
  .air-target.remote .air-target-warn { color: var(--air-amber); font-weight: 600; }
  .air-target-row { display: flex; align-items: center; flex-wrap: wrap; gap: .45rem;
      padding: .16rem 0; font-size: .82rem; color: var(--air-muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .air-target-service { min-width: 8.5rem; color: var(--air-ink); font-weight: 600; }
  .air-target-url { color: var(--air-ink); }
  .air-target-probe { display: inline-flex; align-items: center; gap: .35rem; }

  .air-chip { display: inline-block; padding: .05rem .45rem; border-radius: 4px;
      font-size: .68rem; font-weight: 700; letter-spacing: .6px;
      font-family: system-ui, sans-serif; }
  .air-chip.local { background: var(--air-chip-local-bg); color: var(--air-blue); }
  .air-chip.remote { background: var(--air-chip-remote-bg); color: var(--air-amber); }
  .air-chip.unset { background: var(--air-neg-bg); color: var(--air-red); }
  .air-chip.key { background: var(--air-pos-bg); color: var(--air-green); }
  .air-chip.nokey { background: var(--air-neg-bg); color: var(--air-red); }

  .air-dot { width: .5rem; height: .5rem; border-radius: 999px; display: inline-block; }
  .air-dot.ok { background: var(--air-green); }
  .air-dot.err { background: var(--air-red); }
  .air-dot.unknown { background: var(--air-line); }

  /* ── Route cards ────────────────────────────────────────────────────────── */
  .air-route { border: 1px solid var(--air-line); border-radius: 10px;
      padding: .6rem .8rem; height: 100%; background: var(--air-bg); }
  .air-route.on { border-color: var(--air-blue); background: var(--air-chip-local-bg); }
  .air-route-path { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: .82rem; font-weight: 600; color: var(--air-blue); }
  .air-route-what { font-size: .82rem; color: var(--air-ink); margin-top: .2rem; }
  .air-route-adds { font-size: .78rem; color: var(--air-muted); margin-top: .25rem; }

  /* The status line: method, pill, timings. */
  .air-statusbar { display: flex; align-items: center; flex-wrap: wrap; gap: .55rem;
      padding: .6rem .85rem; border: 1px solid var(--air-line); border-radius: 10px;
      background: var(--air-surface); margin: .5rem 0 .9rem 0; }
  .air-pill { display: inline-block; padding: .16rem .62rem; border-radius: 999px;
      font-size: .78rem; font-weight: 600; letter-spacing: .2px;
      color: var(--air-pill-ink); }
  .air-pill.ok { background: var(--air-green); }
  .air-pill.warn { background: var(--air-amber); }
  .air-pill.err { background: var(--air-red); }
  .air-meta { color: var(--air-muted); font-size: .82rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .air-meta strong { color: var(--air-ink); font-weight: 600; }

  /* Inline labels for sentiment/urgency verdicts. */
  .air-badge { display: inline-block; padding: .2rem .68rem; border-radius: 999px;
      font-size: .82rem; font-weight: 600; border: 1px solid transparent; }
  .air-badge.positive { background: var(--air-pos-bg); color: var(--air-green);
      border-color: var(--air-pos-line); }
  .air-badge.negative { background: var(--air-neg-bg); color: var(--air-red);
      border-color: var(--air-neg-line); }
  .air-badge.neutral  { background: var(--air-neu-bg); color: var(--air-muted);
      border-color: var(--air-neu-line); }
  .air-badge.mixed    { background: var(--air-mix-bg); color: var(--air-amber);
      border-color: var(--air-mix-line); }
  .air-badge.unknown  { background: var(--air-neu-bg); color: var(--air-muted);
      border-color: var(--air-neu-line); border-style: dashed; }

  .air-section { font-size: .74rem; font-weight: 600; letter-spacing: .8px;
      text-transform: uppercase; color: var(--air-muted); margin: 1.15rem 0 .4rem 0; }

  /* A quiet note for things that are not errors but need saying. */
  .air-note { border-left: 3px solid var(--air-line); padding: .1rem 0 .1rem .7rem;
      color: var(--air-muted); font-size: .86rem; margin: .3rem 0 .8rem 0; }

  /* Monospace anywhere a payload or identifier appears. */
  .stCodeBlock, code { font-size: .82rem; }
  section[data-testid="stSidebar"] { border-right: 1px solid var(--air-line); }
  section[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
"""


def resolve_mode(default: str) -> str:
    """The active appearance mode, seeding session state on first render.

    Read before anything is drawn, because the palette has to be injected ahead
    of the widget that changes it. The sidebar's radio writes the same key, so a
    change lands here on the rerun it triggers.
    """
    mode = str(st.session_state.get(_STATE_KEY, "")).lower()
    if mode not in MODES:
        mode = default if default in MODES else "auto"
        st.session_state[_STATE_KEY] = mode
    return mode


def inject(mode: str = "auto") -> None:
    """Emit the stylesheet for ``mode``."""
    chrome = "" if mode == "auto" else _CHROME
    st.markdown(f"<style>{_roots(mode)}{chrome}{_STATIC}</style>", unsafe_allow_html=True)


def header(title: str, subtitle: str) -> None:
    """The page header: what this is, and what it is for."""
    st.markdown(
        f'<div class="air-header"><div class="air-title">{title}</div>'
        f'<div class="air-subtitle">{subtitle}</div></div>',
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
