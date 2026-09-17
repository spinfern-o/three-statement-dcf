"""Item 111: the WACC input and source panel (16.6-16.10, STEP 25-27).

Every number in a WACC is a fact about a date and about a market, and **not one
of them can be derived from the filing**. A risk-free rate is a yield somebody
observed; a beta is a regression somebody ran over a window somebody chose; an
equity risk premium is an estimate somebody published. The engine already
refuses to construct a `CostOfCapital` without a source string per input, which
is the right instinct and a weak enforcement: "Bloomberg" satisfies it.

So these are Section 14 assumptions, and the evidence rules do the work.
`SourceType.EXTERNAL_MARKET_DATA` requires a URL **and** an observation date,
because the same field observed a month later is a different number, and a
valuation nobody can reproduce is a valuation nobody can check. Decision 2.3.e
forbids external retrieval, so the system never fetches any of this -- the
reviewer supplies the number and says where they got it.

The market-value inputs carry a second trap that STEP 27 names outright: **do
not automatically use book equity for market capitalization.** The engine
refuses a non-positive market equity and cannot tell book from market, so the
note on that row says it in words where a reviewer will read it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..assumptions.schema import SourceType


@dataclass(frozen=True)
class MarketInput:
    """One cost-of-capital or valuation input, and why it needs a source."""

    code: str
    name: str
    unit: str
    rule: str
    why_sourced: str
    #: The source types that make sense for it. A beta is market data; a
    #: terminal growth rate is usually a stated analyst judgement.
    expected: "tuple[SourceType, ...]"
    required: bool = True
    note: str = ""


MARKET = SourceType.EXTERNAL_MARKET_DATA
ANALYST = SourceType.ANALYST_ASSUMPTION
FILING = SourceType.COMPANY_FILING

#: 16.6 to 16.10, plus the terminal growth rate 16.15 needs.
MARKET_INPUTS = (
    MarketInput(
        "risk_free_rate", "Risk-free rate", "ratio", "16.6",
        "A government yield on a stated date and a stated maturity. It moves "
        "daily, so the date is part of the number.",
        (MARKET,),
        note="Match the maturity to the horizon being discounted, and say which.",
    ),
    MarketInput(
        "beta", "Beta", "ratio", "16.6",
        "A regression over a window somebody chose, against an index somebody "
        "chose, possibly adjusted. None of those choices is recoverable from "
        "the number.",
        (MARKET,),
        note="Record whether it is raw or adjusted, levered or unlevered, and "
             "over what window -- two betas for one company routinely differ by "
             "more than the equity risk premium.",
    ),
    MarketInput(
        "equity_risk_premium", "Equity risk premium", "ratio", "16.6",
        "A published estimate, not an observation. Different publishers differ "
        "by more than a percentage point, which is more than most modelling "
        "decisions are worth.",
        (MARKET, ANALYST),
    ),
    MarketInput(
        "pretax_cost_of_debt", "Pre-tax cost of debt", "ratio", "16.7",
        "Either a yield on the company's own traded debt or a spread over the "
        "risk-free rate for its rating. Both are dated observations.",
        (MARKET, FILING),
        note="The historical implied rate on beginning debt is in the 13.4 "
             "schedule, and is a different thing: what the company HAS paid, "
             "not what it would pay now.",
    ),
    MarketInput(
        "market_value_equity", "Market value of equity", "currency", "16.8",
        "A price times a share count, both on the valuation date.",
        (MARKET,),
        note="STEP 27: do NOT use book equity. The engine cannot tell the two "
             "apart -- both are positive numbers -- so this is the one place "
             "the distinction has to be made by a person.",
    ),
    MarketInput(
        "market_value_debt", "Market value of debt", "currency", "16.8",
        "Book value is the usual proxy and is a choice, not a fact.",
        (MARKET, FILING),
        note="If book value is being used as the proxy, say so in the rationale "
             "-- that is the decision, and it is invisible in the number.",
    ),
    MarketInput(
        "terminal_growth", "Terminal growth rate", "ratio", "16.15",
        "A perpetual growth rate. Above long-run nominal GDP it asserts the "
        "company eventually becomes the economy.",
        (ANALYST, MARKET),
        note="16.16 blocks the calculation when it reaches the WACC, because "
             "the formula returns a negative or infinite value there.",
    ),
)

#: 16.19's bridge, beyond the cash and debt the balance sheet supplies.
BRIDGE_INPUTS = (
    MarketInput(
        "non_operating_investments", "Non-operating investments", "currency", "16.19",
        "An asset the FCFF does not generate, so its value is added separately.",
        (FILING,), required=False,
    ),
    MarketInput(
        "minority_interest", "Minority interest", "currency", "16.19",
        "A claim on the enterprise held by somebody else.",
        (FILING,), required=False,
        note="The chart has no minority_interest line (F-17), so this cannot be "
             "read off the balance sheet and must be entered with its page.",
    ),
    MarketInput(
        "preferred_stock", "Preferred stock", "currency", "16.19",
        "A capital class senior to common equity (16.10).",
        (FILING,), required=False,
    ),
    MarketInput(
        "pension_obligations", "Unfunded pension obligations", "currency", "16.19",
        "A claim ranking ahead of equity, disclosed in the pension note.",
        (FILING,), required=False,
    ),
    MarketInput(
        "other_claims", "Other approved claims", "currency", "16.19",
        "16.19's residual line, which must be explicitly approved rather than "
        "used as a plug.",
        (FILING, ANALYST), required=False,
    ),
    MarketInput(
        "diluted_shares", "Diluted shares outstanding", "shares", "16.20",
        "The denominator of the last division in a valuation. 16.20 permits a "
        "per-share value ONLY when it is verified.",
        (FILING,), required=False,
        note="The chart carries no share count (F-17), so there is nothing to "
             "cross-check this against: it rests entirely on its own citation.",
    ),
)

BY_CODE = {item.code: item for item in MARKET_INPUTS + BRIDGE_INPUTS}

#: 16.19's line the chart cannot supply at all.
LEASE_LIABILITIES_NOTE = (
    "16.19 lists lease liabilities \"if policy treats them as debt\". Decision "
    "2.4.j does treat them as debt, and the chart has no lease liability line "
    "(F-17): a company's leases are either inside `other_noncurrent_liabilities` "
    "or not disclosed on the face at all. So this bridge line cannot be built, "
    "and it is reported rather than silently taken as nil -- a company with "
    "material leases is over-valued by their whole amount if it is."
)


def required_codes() -> "frozenset[str]":
    return frozenset(item.code for item in MARKET_INPUTS if item.required)
