"""The console's skin, in light and dark.

The brief is Postman/Insomnia, not a landing page: one accent colour, flat
surfaces, status carried by a single unmissable pill, information density over
whitespace, and a typeface split — Inter for chrome, JetBrains Mono for
anything a developer copies verbatim (URLs, keys, JSON). This module is the
whole of it — every colour the console uses is declared here once, as a CSS
custom property, in two palettes.

Four things shape the implementation:

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
* **Density and typeface are mode-independent.** The root font-size trim, the
  Inter/JetBrains Mono split, and every padding/radius reduction live in
  :data:`_STATIC` rather than :data:`_CHROME`, because they apply the same way
  whether the palette came from an explicit choice or from Streamlit's own
  ``prefers-color-scheme`` handling in auto mode.
"""

from __future__ import annotations

from typing import Final

import streamlit as st

MODES: Final[tuple[str, ...]] = ("auto", "light", "dark")

_STATE_KEY: Final[str] = "theme_mode"

# ── Typeface ──────────────────────────────────────────────────────────────────
#
# Inter for UI chrome (labels, buttons, headings) and JetBrains Mono for
# anything holding an identifier, a URL or a payload — base URLs, API keys,
# JSON bodies, request/response text — the Postman/Insomnia convention of
# treating "things a developer copies and pastes" as code, not prose. Each has
# the console's original system stack behind it as a fallback, so a machine
# with no internet access degrades to exactly the old look instead of a missing
# font showing tofu or the browser default serif.
_FONT_UI: Final[str] = (
    "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
)
_FONT_MONO: Final[str] = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

#: Must precede every other rule in the stylesheet — an `@import` anywhere else
#: in the block is dropped by the CSS spec, not merely deprioritised.
_FONT_IMPORT: Final[str] = (
    "@import url('https://fonts.googleapis.com/css2"
    "?family=Inter:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;500;600"
    "&display=swap');"
)

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

_STATIC: Final[str] = f"""
  /* A ~6% root trim — every rem-based measurement in this file, and most of
     Streamlit's own, shrinks with it. This one line does more of the "compact"
     work than any individual padding tweak below; the per-component paddings
     tighten what does not scale off it (fixed-px chrome, dataframe internals). */
  :root {{ font-size: 15px; }}

  .stApp {{ font-family: {_FONT_UI}; }}
  /* URLs, keys, JSON bodies, request/response text — anything a developer
     copies verbatim reads as code, not prose, in every appearance mode
     (unlike the background/colour overrides below, which only apply when an
     explicit Light/Dark choice overrides Streamlit's own theme). */
  input, textarea, [data-baseweb="input"], [data-baseweb="textarea"],
  [data-baseweb="base-input"], .stCodeBlock, code, pre, [data-testid="stJson"] {{
      font-family: {_FONT_MONO}; }}
  .stButton > button, [data-testid="stButton"] > button {{
      font-family: {_FONT_UI}; font-weight: 600; border-radius: 7px;
      padding: .3rem .9rem; }}

  /* Streamlit's own inter-widget rhythm is the single biggest source of
     "spaced out" — tightened here rather than per-tab, so every form benefits. */
  [data-testid="stVerticalBlock"] {{ gap: .55rem; }}

  /* Fluid: fill the window, but keep a gutter and stop lines becoming
     unreadable ribbons on an ultrawide. The top padding is deliberate — it
     clears Streamlit's fixed toolbar so the page header is never underneath
     it. Padding tightens on narrow screens rather than content being clipped.
     Cut roughly a third from the original figures: this was built spacious by
     default and reads as a control panel, not a landing page, once it isn't. */
  .block-container {{ padding: 3.3rem 1.6rem 2.2rem; max-width: 1800px; }}
  @media (max-width: 900px) {{ .block-container {{ padding: 3.1rem .85rem 1.6rem; }} }}

  /* The page header. Sits in normal flow, never sticky: a floating band is the
     one thing guaranteed to end up on top of the title it is meant to label. */
  .air-header {{ padding: 0 0 .4rem 0; margin: 0 0 .7rem 0;
      border-bottom: 1px solid var(--air-line); }}
  .air-title {{ font-size: 1.35rem; font-weight: 600; color: var(--air-ink);
               letter-spacing: -0.2px; margin: 0 0 .15rem 0; line-height: 1.2; }}
  .air-subtitle {{ color: var(--air-muted); font-size: .86rem; margin: 0; }}

  /* Tabs read as a Google-style underlined nav rather than boxes. */
  .stTabs [data-baseweb="tab-list"] {{ gap: .3rem; border-bottom: 1px solid var(--air-line); }}
  .stTabs [data-baseweb="tab"] {{ height: 38px; padding: 0 .9rem;
      background: transparent; font-weight: 500; color: var(--air-muted); }}
  .stTabs [aria-selected="true"] {{ color: var(--air-blue); }}

  /* ── Target bar ─────────────────────────────────────────────────────────── */
  .air-target {{ border: 1px solid var(--air-line); border-left-width: 4px;
      border-radius: 8px; padding: .45rem .7rem; background: var(--air-surface);
      margin: 0 0 .7rem 0; }}
  .air-target.local {{ border-left-color: var(--air-blue); }}
  .air-target.remote {{ border-left-color: var(--air-amber);
      background: var(--air-surface-warn); }}
  .air-target-head {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: .5rem;
      margin-bottom: .35rem; font-size: .92rem; color: var(--air-ink); }}
  .air-target-label {{ font-size: .68rem; font-weight: 700; letter-spacing: 1px;
      color: var(--air-muted); }}
  .air-target-warn {{ font-size: .78rem; color: var(--air-muted); }}
  .air-target.remote .air-target-warn {{ color: var(--air-amber); font-weight: 600; }}
  .air-target-row {{ display: flex; align-items: center; flex-wrap: wrap; gap: .45rem;
      padding: .16rem 0; font-size: .82rem; color: var(--air-muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .air-target-service {{ min-width: 8.5rem; color: var(--air-ink); font-weight: 600; }}
  .air-target-url {{ color: var(--air-ink); }}
  .air-target-probe {{ display: inline-flex; align-items: center; gap: .35rem; }}

  .air-chip {{ display: inline-block; padding: .05rem .45rem; border-radius: 4px;
      font-size: .68rem; font-weight: 700; letter-spacing: .6px;
      font-family: system-ui, sans-serif; }}
  .air-chip.local {{ background: var(--air-chip-local-bg); color: var(--air-blue); }}
  .air-chip.remote {{ background: var(--air-chip-remote-bg); color: var(--air-amber); }}
  .air-chip.unset {{ background: var(--air-neg-bg); color: var(--air-red); }}
  .air-chip.key {{ background: var(--air-pos-bg); color: var(--air-green); }}
  .air-chip.nokey {{ background: var(--air-neg-bg); color: var(--air-red); }}

  .air-dot {{ width: .5rem; height: .5rem; border-radius: 999px; display: inline-block; }}
  .air-dot.ok {{ background: var(--air-green); }}
  .air-dot.err {{ background: var(--air-red); }}
  .air-dot.unknown {{ background: var(--air-line); }}

  /* ── Route cards ────────────────────────────────────────────────────────── */
  .air-route {{ border: 1px solid var(--air-line); border-radius: 8px;
      padding: .5rem .7rem; height: 100%; background: var(--air-bg); }}
  .air-route.on {{ border-color: var(--air-blue); background: var(--air-chip-local-bg); }}
  .air-route-path {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: .82rem; font-weight: 600; color: var(--air-blue); }}
  .air-route-what {{ font-size: .82rem; color: var(--air-ink); margin-top: .2rem; }}
  .air-route-adds {{ font-size: .78rem; color: var(--air-muted); margin-top: .25rem; }}

  /* The status line: method, pill, timings. */
  .air-statusbar {{ display: flex; align-items: center; flex-wrap: wrap; gap: .5rem;
      padding: .5rem .7rem; border: 1px solid var(--air-line); border-radius: 8px;
      background: var(--air-surface); margin: .4rem 0 .7rem 0; }}
  .air-pill {{ display: inline-block; padding: .16rem .62rem; border-radius: 999px;
      font-size: .78rem; font-weight: 600; letter-spacing: .2px;
      color: var(--air-pill-ink); }}
  .air-pill.ok {{ background: var(--air-green); }}
  .air-pill.warn {{ background: var(--air-amber); }}
  .air-pill.err {{ background: var(--air-red); }}
  .air-meta {{ color: var(--air-muted); font-size: .82rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .air-meta strong {{ color: var(--air-ink); font-weight: 600; }}

  /* Inline labels for sentiment/urgency verdicts. */
  .air-badge {{ display: inline-block; padding: .2rem .68rem; border-radius: 999px;
      font-size: .82rem; font-weight: 600; border: 1px solid transparent; }}
  .air-badge.positive {{ background: var(--air-pos-bg); color: var(--air-green);
      border-color: var(--air-pos-line); }}
  .air-badge.negative {{ background: var(--air-neg-bg); color: var(--air-red);
      border-color: var(--air-neg-line); }}
  .air-badge.neutral  {{ background: var(--air-neu-bg); color: var(--air-muted);
      border-color: var(--air-neu-line); }}
  .air-badge.mixed    {{ background: var(--air-mix-bg); color: var(--air-amber);
      border-color: var(--air-mix-line); }}
  .air-badge.unknown  {{ background: var(--air-neu-bg); color: var(--air-muted);
      border-color: var(--air-neu-line); border-style: dashed; }}

  .air-section {{ font-size: .74rem; font-weight: 600; letter-spacing: .8px;
      text-transform: uppercase; color: var(--air-muted); margin: .9rem 0 .35rem 0; }}

  /* A quiet note for things that are not errors but need saying. */
  .air-note {{ border-left: 3px solid var(--air-line); padding: .1rem 0 .1rem .7rem;
      color: var(--air-muted); font-size: .86rem; margin: .3rem 0 .7rem 0; }}

  /* ── Data grid — dashboard.py's one component for structured API output ──
     A bordered stat panel: a header bar, then dense rows of `key value`
     pairs in monospace. Colour is reserved for state actually worth a second
     look (dashboard.py's Kind), not for routinely differentiating every
     label — the opposite instinct from `.air-badge` above, deliberately. */
  .air-grid {{ border: 1px solid var(--air-line); border-radius: 6px;
      overflow: hidden; margin: 0 0 .6rem 0; background: var(--air-bg); }}
  .air-grid-head {{ background: var(--air-surface); padding: .3rem .65rem;
      font-size: .68rem; font-weight: 700; letter-spacing: .8px;
      text-transform: uppercase; color: var(--air-muted);
      border-bottom: 1px solid var(--air-line); }}
  /* `.standalone` labels a table section that has no `.air-grid` box of its
     own around it — same typography, its own rounded top so it still reads
     as a panel header sitting directly above the `st.dataframe` it titles. */
  .air-grid-head.standalone {{ border: 1px solid var(--air-line); border-bottom: none;
      border-radius: 6px 6px 0 0; margin: .6rem 0 0 0; }}
  .air-grid-row {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 1.3rem;
      padding: .38rem .65rem; border-bottom: 1px solid var(--air-line); }}
  .air-grid-row:last-child {{ border-bottom: none; }}
  .air-grid-empty {{ padding: .5rem .65rem; color: var(--air-muted);
      font-size: .82rem; font-style: italic; }}
  .air-grid-kv {{ display: inline-flex; align-items: baseline; gap: .4rem; white-space: nowrap; }}
  .air-grid-k {{ font-family: {_FONT_MONO}; font-size: .72rem; color: var(--air-muted); }}
  .air-grid-v {{ font-family: {_FONT_MONO}; font-size: .82rem; font-weight: 600;
      color: var(--air-ink); }}
  .air-grid-v.ok {{ color: var(--air-green); }}
  .air-grid-v.warn {{ color: var(--air-amber); }}
  .air-grid-v.err {{ color: var(--air-red); }}
  .air-grid-v.muted {{ color: var(--air-muted); font-weight: 400; }}

  /* Monospace anywhere a payload or identifier appears. */
  .stCodeBlock, code {{ font-size: .82rem; }}
  section[data-testid="stSidebar"] {{ border-right: 1px solid var(--air-line); }}
  section[data-testid="stSidebar"] .block-container {{ padding-top: 1rem; }}
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
    """Emit the stylesheet for ``mode``.

    ``_FONT_IMPORT`` has to lead the block — an ``@import`` anywhere else in the
    stylesheet is simply dropped by the CSS spec, not deprioritised.
    """
    chrome = "" if mode == "auto" else _CHROME
    st.markdown(
        f"<style>{_FONT_IMPORT}{_roots(mode)}{chrome}{_STATIC}</style>", unsafe_allow_html=True
    )


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
