"""Items 71 and 73, and the share-count half of item 75.

Three of Section 13's schedules cannot be built from this system's canonical
chart. Rather than render empty tables -- which claims the filing had nothing
to show -- each says what is missing, where in a filing it lives, and what
would have to change here to build it.

This is the same answer `statements/views.py:equity_statement_status` gives
for the statement of changes in equity, for the same reason: rule 1.14 makes
an unrun check a reported gap, and a blank schedule is an unrun check with the
evidence removed.

All three trace back to finding F-17 in the decision ledger: the canonical
chart is short of Section 12, and this is the second place a reviewer meets
that. The first was mapping, where a goodwill line can only be offered
`other_noncurrent_assets`.
"""

from __future__ import annotations

from .base import Availability, Schedule

INTANGIBLES_REASON = (
    "The canonical chart has no intangibles or goodwill line: both map to "
    "`other_noncurrent_assets`, which also carries deferred tax assets, "
    "investments and everything else long-lived (finding F-17). There is also no "
    "separate amortization line -- `depreciation_amortization` is one combined "
    "figure -- so neither side of 13.3's roll-forward exists. Building it means "
    "adding `goodwill`, `intangibles` and `amortization` to model/accounts.py, "
    "with the checks that go with them."
)

LEASES_REASON = (
    "13.5 asks for lease additions, payments, interest, current/non-current "
    'reclassification and the ending liability, "when material and disclosed". '
    "The chart has no lease liability or right-of-use asset line, and the "
    "movements it wants are disclosed in the lease footnote's maturity table "
    "rather than on the face of the statements. Nothing here can distinguish a "
    "company with no leases from one whose leases are folded into "
    "`other_noncurrent_liabilities`, and reporting an empty schedule would assert "
    "the first."
)

SHARE_COUNT_REASON = (
    "13.7 asks for share issuance, repurchases, stock compensation and diluted "
    "shares. The cash movements are in the common-equity roll-forward; the share "
    "COUNTS are not here at all. Basic and diluted share counts are printed under "
    "the income statement and detailed in the EPS note, and the chart has no line "
    "for either -- it holds currency amounts, and a share count is neither an "
    "amount nor a line the sign conventions in model/accounts.py apply to. A "
    "valuation needs it: equity value per share is the last division in STEP 34."
)


def _unavailable(key: str, title: str, rule: str, reason: str) -> Schedule:
    return Schedule(
        key=key,
        title=title,
        rule=rule,
        availability=Availability.UNAVAILABLE,
        reason=reason,
    )


def intangibles_schedule() -> Schedule:
    """Item 71 / 13.3."""
    return _unavailable("intangibles", "Intangibles and amortization", "13.3", INTANGIBLES_REASON)


def lease_schedule() -> Schedule:
    """Item 73 / 13.5. "When selected" -- it cannot be."""
    return _unavailable("leases", "Leases", "13.5", LEASES_REASON)


def share_count_schedule() -> Schedule:
    """The half of item 75 / 13.7 the chart cannot carry."""
    return _unavailable("share_count", "Share count and dilution", "13.7", SHARE_COUNT_REASON)
