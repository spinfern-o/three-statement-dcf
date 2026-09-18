"""Item 73, and the share-count half of item 75.

Two of Section 13's schedules cannot be built from this system's canonical
chart. Rather than render empty tables -- which claims the filing had nothing
to show -- each says what is missing, where in a filing it lives, and what
would have to change here to build it.

This is the same answer `statements/views.py:equity_statement_status` gives
for the statement of changes in equity, for the same reason: rule 1.14 makes
an unrun check a reported gap, and a blank schedule is an unrun check with the
evidence removed.

**13.3 used to be here and is not any more.** Closing finding F-17 gave the
chart `intangibles` and a separate `amortization` line, so the roll-forward
has both of its sides and lives in `rollforward.py` with the others. What is
left here is the two that a longer chart does not fix:

  13.5 leases    needs movements the face statements do not carry.
  13.7 shares    needs a quantity, and this chart holds amounts.

The second is the more interesting one, and it is worth being precise that it
is NOT a chart-length problem. A share count is not a currency amount; none of
the sign conventions in `model/accounts.py` apply to it, and nothing in the
three statements sums over it.
"""

from __future__ import annotations

from .base import Availability, Schedule

LEASES_REASON = (
    "13.5 asks for lease additions, payments, interest, current/non-current "
    'reclassification and the ending liability, "when material and disclosed". '
    "The chart now carries `lease_liabilities` (12.2.i), so the ENDING BALANCE "
    "exists and a company with no leases is distinguishable from one whose "
    "leases sit inside `other_noncurrent_liabilities` -- that half was finding "
    "F-17 and is closed. Every MOVEMENT is still missing, and not because the "
    "chart is short: additions, payments and the interest component are "
    "disclosed in the lease footnote's maturity table rather than on the face "
    "of the statements, which is where this system extracts from. A "
    "roll-forward with a balance and no movements explains nothing, so it is "
    "reported as unavailable rather than rendered as a table whose every row "
    "reads 'unexplained'. Building it needs footnote extraction, not more "
    "canonical lines."
)

SHARE_COUNT_REASON = (
    "13.7 asks for share issuance, repurchases, stock compensation and diluted "
    "shares. The cash movements are in the common-equity roll-forward; the share "
    "COUNTS are not here at all. Basic and diluted share counts are printed under "
    "the income statement and detailed in the EPS note, and the chart has no line "
    "for either -- it holds currency amounts, and a share count is neither an "
    "amount nor a line the sign conventions in model/accounts.py apply to. "
    "Lengthening the chart does not fix this one, which is why it survived the "
    "extension that closed F-17: a share count needs its own kind of line, or it "
    "stays what it is today -- a valuation input supplied with its own source "
    "(STEP 35). A valuation needs it either way: equity value per share is the "
    "last division in STEP 34."
)


def _unavailable(key: str, title: str, rule: str, reason: str) -> Schedule:
    return Schedule(
        key=key,
        title=title,
        rule=rule,
        availability=Availability.UNAVAILABLE,
        reason=reason,
    )


def lease_schedule() -> Schedule:
    """Item 73 / 13.5. "When selected" -- it cannot be."""
    return _unavailable("leases", "Leases", "13.5", LEASES_REASON)


def share_count_schedule() -> Schedule:
    """The half of item 75 / 13.7 the chart cannot carry."""
    return _unavailable("share_count", "Share count and dilution", "13.7", SHARE_COUNT_REASON)
