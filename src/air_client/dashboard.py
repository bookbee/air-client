"""A dense, ops-dashboard data grid — the one component every tab's response
summary and option editor uses to show structured API output.

The brief this replaces: a wall of `st.metric` tiles and a colourful pill
`badge()` on every field, regardless of whether that field was actually
notable. That reads as a toy — a demo, not a tool an engineer reaches for
under pressure. The replacement principle is the one real dashboards
(Datadog, Grafana) actually follow: pack several related facts onto one
dense row of plain monospace text, and reserve colour for state that is
*actually* worth a second look — a failure, a ceiling reached, a flag raised
— not for routinely differentiating "positive" from "neutral".
"""

from __future__ import annotations

import html
from collections.abc import Sequence
from typing import Any

import streamlit as st

#: A value's colour. "" is the neutral ink colour every value defaults to;
#: the rest are used only for state worth a second look — see the module
#: docstring. "muted" is for a value that is present but uninteresting
#: (e.g. `requires_human: no`), dimmer than the default so attention still
#: goes to whatever nearby value *is* colored.
Kind = str

Cell = tuple[str, str, Kind]
Row = Sequence[Cell]


def grid(
    title: str, rows: Sequence[Row] | None, *, empty: str = "No data in this response."
) -> None:
    """One bordered section: a header bar, then rows of `key value` pairs.

    Each row is a sequence of `(label, value, kind)` triples rendered inline
    on one line, wrapping only if the row genuinely does not fit — several
    small facts share a line the way a real ops panel packs them, rather than
    one fact per widget.
    """
    if not rows:
        body = f'<div class="air-grid-empty">{html.escape(empty)}</div>'
    else:
        body = "".join(_row(row) for row in rows)
    st.markdown(
        f'<div class="air-grid"><div class="air-grid-head">{html.escape(title)}</div>{body}</div>',
        unsafe_allow_html=True,
    )


def table_title(title: str) -> None:
    """The same header bar `grid()` uses, standalone — for a section whose
    body is a real `st.dataframe` rather than key/value rows, so a boxed
    stat panel and a labelled data table read as one design language instead
    of two."""
    st.markdown(
        f'<div class="air-grid-head standalone">{html.escape(title)}</div>', unsafe_allow_html=True
    )


def _row(cells: Row) -> str:
    kvs = "".join(
        f'<span class="air-grid-kv"><span class="air-grid-k">{html.escape(k)}</span>'
        f'<span class="air-grid-v {html.escape(kind)}">{html.escape(v)}</span></span>'
        for k, v, kind in cells
    )
    return f'<div class="air-grid-row">{kvs}</div>'


# ── Value formatting ─────────────────────────────────────────────────────────
#
# Small, deliberately dumb formatters so every summary renders "—" the same
# way for the same kind of absence, rather than each call site inventing its
# own fallback.


def yn(value: Any) -> str:
    return "yes" if value is True else "no" if value is False else "—"


def num(value: Any, spec: str = "") -> str:
    return format(value, spec) if isinstance(value, int | float) else "—"


def pct(value: Any) -> str:
    return f"{value:.0%}" if isinstance(value, int | float) else "—"


def text(value: Any) -> str:
    return str(value) if value not in (None, "") else "—"
