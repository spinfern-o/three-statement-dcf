"""One display precision, for every screen and every export.

Found by item 143, which compares an export against the *rendered page*. Until
this module existed the same figure was displayed three different ways:

    statements.html   {{ cell.value }}        full stored precision, no separators
    schedules.html    {:,}                    separators, full precision
    forecast.html     {:,.0f}                 separators, whole units
    valuation.html    {:,.0f}                 separators, whole units

21.8 requires an export to equal the website "at the same display precision",
and that requirement cannot be met against a website that does not agree with
itself. Neither can a reader compare a forecast line to the historical line
above it when one is rounded and the other carries eighteen decimal places.

**The policy, stated once.** Currency displays with thousands separators at
whole units. These filings report in thousands or millions; a fractional
currency unit on a statement line is a division residual, not information, and
4.18 exists precisely so that display may drop it while the stored value keeps
it. Percentages display to one decimal place, ratios to four, days to one.

**4.19 is the other half and is not optional**: "label every displayed rounded
value with a tooltip showing its full stored value". `exact` is what that
tooltip shows, and `is_rounded` says whether one is owed -- a value that
displays losslessly does not need a tooltip claiming it was rounded.

Both the templates and `exports/gather.py` call these, so 21.8 holds by
construction: the export and the page cannot disagree without one of them
calling a different function, which is a change a reader of this module will
see.
"""

from __future__ import annotations

from decimal import Decimal

from model.numeric import quantize_for_display

#: What a screen shows where there is no value. Never "0" and never blank:
#: rule 1.3 makes absent a distinct state, and a blank cell reads as an
#: oversight rather than as a fact about the filing.
ABSENT = "—"  # em dash

#: Decimal places per unit kind. One place for a percentage matches
#: `statements/views.py:PERCENT_PLACES`, which has shown growth that way since
#: Phase 6 -- changing it here would move numbers nobody asked to move.
PLACES = {
    "currency": 0,
    "percent": 1,
    "ratio": 4,
    "days": 1,
    "integer": 0,
    # A discount factor needs more than a rate does: at four places the
    # factors for two adjacent years in a low-WACC model print the same, and a
    # reader checking a present value by hand cannot reproduce it.
    "factor": 6,
}


def exact(value: Decimal | None) -> str:
    """The full stored value, for 4.19's tooltip. Never rounded."""
    return "" if value is None else str(value)


def is_rounded(value: Decimal | None, kind: str) -> bool:
    """True when displaying this value at `kind`'s precision loses something."""
    if value is None or kind not in PLACES:
        return False
    return quantize_for_display(value, PLACES[kind]) != value


def display(value: Decimal | None, kind: str = "currency") -> str:
    """One value at its unit's display precision, with separators."""
    if value is None:
        return ABSENT
    if kind not in PLACES:
        return str(value)
    places = PLACES[kind]
    rounded = quantize_for_display(value, places)
    return f"{rounded:,.{places}f}"


def money(value: Decimal | None) -> str:
    return display(value, "currency")


def percent(value: Decimal | None) -> str:
    return display(value, "percent")


def ratio(value: Decimal | None) -> str:
    return display(value, "ratio")


def days(value: Decimal | None) -> str:
    return display(value, "days")


def factor(value: Decimal | None) -> str:
    return display(value, "factor")


def tooltip(value: Decimal | None, kind: str = "currency") -> str:
    """4.19's tooltip text, or an empty string when nothing was rounded.

    Empty rather than the same number twice: a tooltip that repeats what is
    already on screen teaches a reader that tooltips are noise, and the next
    one -- the one that does carry a hidden figure -- goes unread.
    """
    if not is_rounded(value, kind):
        return ""
    return f"Full stored value: {exact(value)} (4.19)"


#: Registered on the Jinja environment so a template cannot reach a different
#: formatter by accident.
FILTERS = {
    "money": money,
    "percent": percent,
    "ratio": ratio,
    "days": days,
    "factor": factor,
    "display": display,
    "exact": exact,
    "tooltip": tooltip,
}
