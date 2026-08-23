"""Making a table safe to hand to Arrow.

Streamlit serialises every dataframe through pyarrow, which needs one type per
column. Real API payloads do not oblige: a status is ``200`` on success and
``"network error"`` when the socket never opened; a dependency's ``reachable``
is ``true`` for one entry and ``null`` for the one that is not configured.

Arrow raises on those columns. Streamlit then recovers by coercing the frame —
so the table still renders, and a full traceback lands in the log on *every*
rerun that draws it. The output looks fine and the log looks broken, which is
the worst of both.

The fix belongs here rather than at each call site: a column whose values do not
share one kind is rendered as text, once, before Arrow ever sees it.
"""

from __future__ import annotations

import json
from typing import Any


def _kind(value: Any) -> str | None:
    """The Arrow-relevant family of one cell. ``None`` is compatible with any."""
    if value is None:
        return None
    if isinstance(value, bool):
        # Checked before int: bool is a subclass of it, and Arrow types them apart.
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "str"
    return "other"


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def arrow_safe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``rows`` with every mixed-kind column rendered as text.

    Uniform columns are left exactly as they are, so numbers stay sortable and
    booleans keep their tick boxes. Only the columns that would actually break
    are flattened.
    """
    if not rows:
        return rows

    columns: dict[str, set[str]] = {}
    for row in rows:
        for key, value in row.items():
            kind = _kind(value)
            if kind is not None:
                columns.setdefault(key, set()).add(kind)

    unsafe = {key for key, kinds in columns.items() if len(kinds) > 1 or kinds == {"other"}}
    if not unsafe:
        return rows
    return [
        {key: _text(value) if key in unsafe else value for key, value in row.items()}
        for row in rows
    ]
