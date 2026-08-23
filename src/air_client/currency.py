"""USD → INR display for cost figures.

Every AIR service bills and reports cost in USD — that is the currency every
provider actually charges in — so a rupee figure anywhere in this console is a
display convenience laid on top of that number, never a second source of
truth. There is no live FX feed here: the rate is a fixed default unless the
sidebar's own control overrides it for the session, and it is labelled as an
approximation everywhere it appears rather than presented as authoritative.
"""

from __future__ import annotations

import streamlit as st

#: Illustrative only, not fetched live. Adjust it for the session in the
#: sidebar's Currency control, or change the seed with
#: `AIR_CLIENT__USD_TO_INR_RATE` in `.env`.
DEFAULT_USD_TO_INR_RATE = 87.0

_STATE_KEY = "usd_to_inr_rate"


def rate() -> float:
    """The session's current USD→INR rate — the sidebar control's value, or the default."""
    value = st.session_state.get(_STATE_KEY)
    return float(value) if isinstance(value, int | float) and value > 0 else DEFAULT_USD_TO_INR_RATE


def format_cost(amount: float, *, precision: int = 5) -> str:
    """`$0.00042 · ~₹0.04` for one cost figure — USD first, since that is what is billed."""
    return f"${amount:.{precision}f} · ~₹{amount * rate():,.2f}"
