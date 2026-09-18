"""Item 123: the navigation shell's items, and whether each one can be reached.

6.3.a asks for a persistent left navigation. The decision worth recording is
what it does with a screen that cannot show anything yet.

Hiding it is wrong: a reviewer who cannot see the Valuation entry does not
know a valuation exists, and 6.5.i asks empty states to explain what is
missing -- an absent link explains nothing. Enabling it is wrong too, because
a link that leads to "nothing to value yet" four times in a row teaches a
reader to stop clicking.

So every item is always present and always reachable, and one that has nothing
behind it says so in its title attribute AND carries the reason on the page it
leads to. The navigation reports; it does not gate. That is also why the
reasons here are short: the screen itself gives the full one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .status import ModelStatus


@dataclass(frozen=True)
class NavItem:
    label: str
    href: str
    #: A single character, decorative only. 6.2.e and 6.6.h: the label carries
    #: the meaning and this is `aria-hidden`, so a screen reader never meets it.
    glyph: str
    current: bool = False
    available: bool = True
    unavailable_reason: str = ""
    badge: str = ""
    badge_tone: str = "neutral"


#: The order of the work, which is also 7.1 to 7.10's order.
SECTIONS = (
    ("Source room", "", "1"),
    ("Mapping", "mapping", "2"),
    ("Statements", "statements", "3"),
    ("Schedules", "schedules", "4"),
    ("Formulas", "formulas", "5"),
    ("Assumptions", "assumptions", "6"),
    ("Forecast", "forecast", "7"),
    ("Valuation", "valuation", "8"),
    ("Diagnostics", "diagnostics", "9"),
    ("Exports", "exports", "10"),
    ("Settings", "settings", "11"),
)

#: The furthest status at which each section has something to show. A section
#: below a model's status is reachable and empty, and says why.
REQUIRES = {
    "Statements": ModelStatus.VALIDATED,
    "Schedules": ModelStatus.VALIDATED,
    "Formulas": ModelStatus.VALIDATED,
    "Forecast": ModelStatus.FORECAST_READY,
    "Valuation": ModelStatus.VALUATION_READY,
    "Exports": ModelStatus.VALIDATED,
}

# Diagnostics is deliberately absent from REQUIRES: it is reachable at every
# status, because the question it answers -- what is outstanding and why -- is
# most useful on the model that has not got anywhere yet.

REASONS = {
    "Statements": "the statements build once every fact is reviewed and mapped",
    "Exports": "an export is a claim about a model, and needs one to claim about",
    "Schedules": "the schedules are built from the statements",
    "Formulas": "the cross-check needs statements to check",
    "Forecast": "the forecast needs every required assumption to be an answer (14.1)",
    "Valuation": "the valuation needs a forecast and the cost-of-capital inputs",
}


def nav_items(
    document_id: str | None, current: str = "", status: ModelStatus | None = None
) -> tuple[NavItem, ...]:
    """The left navigation for one model, or the portfolio when there is none."""
    items = [
        NavItem(
            label="Portfolio", href="/", glyph="0",
            current=(current == "portfolio"),
        )
    ]
    if document_id is None:
        return tuple(items)

    for label, suffix, glyph in SECTIONS:
        needed = REQUIRES.get(label)
        reachable = (
            status is None or needed is None or status.rank >= needed.rank
        )
        items.append(
            NavItem(
                label=label,
                href=f"/documents/{document_id}" + (f"/{suffix}" if suffix else ""),
                glyph=glyph,
                current=(current == (suffix or "source")),
                available=reachable,
                unavailable_reason="" if reachable else REASONS.get(label, ""),
            )
        )
    return tuple(items)
