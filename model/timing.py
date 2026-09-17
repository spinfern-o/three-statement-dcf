"""Specification 16.11-16.14: the discounting timing convention.

STEP 29 says "year-end convention" and the engine implemented exactly that: the
first forecast year discounts at t = 1, the second at t = 2. Section 16 asks for
three things that convention alone does not give.

  16.11  Select and document year-end or mid-year discounting.
  16.12  Calculate the exact time fraction from valuation date to cash-flow date.
  16.13  Calculate each discount factor using Decimal-compatible exponentiation
         with a tested precision policy.

The three are one problem. A mid-year convention puts t at 0.5, 1.5, 2.5; an
exact fraction from a valuation date puts it at whatever the calendar says; and
both mean the exponent is no longer an integer, which is where 16.13 starts.

**The precision policy, stated once.** `Decimal ** Decimal` for a non-integer
exponent is computed as `exp(t * ln(1 + WACC))`. `Decimal.ln` and `Decimal.exp`
are *correctly rounded* to the active context -- they are not approximations
with unbounded error, they are the exactly-rounded values of the true
transcendental results at 50 significant digits. So:

  - an INTEGER exponent stays exact, and goes through `numeric.power`, which
    is repeated multiplication and introduces no transcendental step at all;
  - a FRACTIONAL exponent carries at most a few units in the last place of a
    50-digit result, which is forty orders of magnitude inside the 0.0001%
    contract of 4.11.

`tests/test_timing.py` pins that: it checks `(1+w)^0.5` squared returns to
`1+w` within 1e-45, and that the integer path and the fractional path agree to
the same bound when handed the same whole number.

**Nothing here changes the engine's default.** `Timing.YEAR_END` reproduces
`Periods.discount_period` exactly -- integer t, integer exponentiation, the
same discount factors the existing tests pin. A model only leaves that path by
asking to.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from .numeric import CALCULATION_CONTEXT, D, ONE, power
from .provenance import ProvenanceError

#: 16.12's day count. 365 rather than 365.25: a leap day is a real day, and
#: the actual/actual convention below counts the days that actually elapsed,
#: so the denominator is the length of the year being crossed. Stated here
#: because 13.1.e's lesson applies to discounting too -- a day-count convention
#: left implicit is a convention nobody can check.
DAYS_IN_YEAR = D(365)


class Timing(str, Enum):
    """16.11's choice, made explicit rather than assumed."""

    #: t = 1, 2, 3 ... Cash arrives on the last day of each forecast year.
    #: STEP 29's convention, and what the engine has always done.
    YEAR_END = "year_end"
    #: t = 0.5, 1.5, 2.5 ... Cash arrives evenly through the year, so the
    #: average pound arrives halfway through it. Standard for an operating
    #: business, and it raises every present value.
    MID_YEAR = "mid_year"
    #: 16.12 in full: the actual fraction of a year between the valuation date
    #: and each cash-flow date, from the calendar.
    EXACT_DATE = "exact_date"

    @property
    def description(self) -> str:
        return {
            "year_end": (
                "Year-end: every year's cash flow is discounted as though it "
                "arrived on the last day of that year (STEP 29). The most "
                "conservative of the three, and the engine's default."
            ),
            "mid_year": (
                "Mid-year: cash is assumed to arrive evenly through each year, "
                "so the average pound arrives halfway through it. Raises every "
                "present value against the year-end convention, by roughly half "
                "a year of discounting."
            ),
            "exact_date": (
                "Exact: the real fraction of a year between the valuation date "
                "and each cash-flow date, counted from the calendar (16.12). "
                "The only one of the three that reflects a valuation date that "
                "is not a fiscal year end."
            ),
        }[self.value]


@dataclass(frozen=True)
class Schedule:
    """When each forecast year's cash flow is treated as arriving.

    `fractions` is t for each forecast year in order, and `terminal` is t for
    the terminal value -- which 16.17 requires use *the same* convention, not a
    separate one. Keeping them in one object is how that stays true.
    """

    timing: Timing
    years: "tuple[str, ...]"
    fractions: "tuple[Decimal, ...]"
    terminal: Decimal
    #: The convention in words, for the screen and the report (16.11).
    basis: str

    def fraction_for(self, year: str) -> Decimal:
        try:
            return self.fractions[self.years.index(year)]
        except ValueError:
            raise KeyError(f"{year!r} is not a forecast year in this schedule") from None

    def describe(self) -> str:
        pairs = ", ".join(
            f"{year} t={fraction}" for year, fraction in zip(self.years, self.fractions)
        )
        return f"{self.timing.value}: {pairs}, terminal t={self.terminal}"


def _year_end_date(year_label: str, fiscal_year_end: "date | None") -> date:
    """The last day of a forecast year, on the company's own fiscal calendar."""
    number = int(year_label[:4])
    if fiscal_year_end is None:
        return date(number, 12, 31)
    # A fiscal year labelled 2026 ends on the 2026 anniversary of the stated
    # year end. February 29 is carried to February 28 in a common year rather
    # than refused: the alternative is a model that cannot value a company
    # whose year ends on a leap day.
    day = fiscal_year_end.day
    if fiscal_year_end.month == 2 and day == 29:
        try:
            return date(number, 2, 29)
        except ValueError:
            return date(number, 2, 28)
    return date(number, fiscal_year_end.month, day)


def _exact_fraction(valuation_date: date, cash_flow_date: date) -> Decimal:
    """16.12: days elapsed over days in a year, as an exact Decimal.

    Actual days over a 365-day year. The result is exact -- both terms are
    integers -- and only the exponentiation that consumes it is inexact.
    """
    days = (cash_flow_date - valuation_date).days
    if days < 0:
        raise ProvenanceError(
            f"the cash flow on {cash_flow_date} falls BEFORE the valuation date "
            f"{valuation_date}. A negative time fraction would compound a future "
            "cash flow rather than discount it (16.12)."
        )
    return D(days) / DAYS_IN_YEAR


def build_schedule(
    forecast_years: "tuple[str, ...]",
    timing: Timing = Timing.YEAR_END,
    *,
    valuation_date: date | None = None,
    fiscal_year_end: date | None = None,
) -> Schedule:
    """16.11 and 16.12: when each cash flow is treated as arriving.

    `EXACT_DATE` needs a valuation date; the other two do not, because they are
    defined relative to the last actual year rather than to a calendar.
    """
    if not forecast_years:
        raise ProvenanceError("a discount schedule needs at least one forecast year")

    if timing is Timing.YEAR_END:
        fractions = tuple(D(index + 1) for index in range(len(forecast_years)))
        basis = (
            "Year-end (STEP 29): t = 1, 2, 3 ... counting from the last actual "
            "year. Integer exponents, so every discount factor is exact to the "
            "calculation context."
        )
    elif timing is Timing.MID_YEAR:
        fractions = tuple(
            D(index + 1) - D("0.5") for index in range(len(forecast_years))
        )
        basis = (
            "Mid-year: t = 0.5, 1.5, 2.5 ... Cash is assumed to arrive evenly "
            "through each year. This RAISES every present value against the "
            "year-end convention; the choice is documented rather than defaulted "
            "(16.11)."
        )
    else:
        if valuation_date is None:
            raise ProvenanceError(
                "the exact-date convention needs a valuation date to count from "
                "(16.12). Year-end and mid-year do not, because they are defined "
                "relative to the last actual year rather than to a calendar."
            )
        fractions = tuple(
            _exact_fraction(valuation_date, _year_end_date(year, fiscal_year_end))
            for year in forecast_years
        )
        ends = ", ".join(
            f"{year} on {_year_end_date(year, fiscal_year_end).isoformat()}"
            for year in forecast_years
        )
        basis = (
            f"Exact (16.12): actual days from the valuation date "
            f"{valuation_date.isoformat()} to each cash-flow date, over "
            f"{DAYS_IN_YEAR} days. Cash-flow dates: {ends}."
        )

    return Schedule(
        timing=timing,
        years=tuple(forecast_years),
        fractions=fractions,
        # 16.17: the terminal value uses the SAME convention, at the final
        # explicit period. A terminal value discounted on a different basis
        # from the flows before it is a different valuation.
        terminal=fractions[-1],
        basis=basis,
    )


def discount_factor(rate: Decimal, fraction: Decimal) -> Decimal:
    """16.13 and 16.14: 1 / (1 + rate)^t, with the precision policy stated.

    An integer `fraction` routes through `numeric.power`, which is repeated
    multiplication: no transcendental step, exact to the context. A fractional
    one is `exp(t * ln(1 + rate))`, where both `ln` and `exp` are correctly
    rounded to the context's 50 digits -- so the error is a few units in the
    last place of fifty, not an unbounded approximation.

    The split is not an optimisation. It keeps the engine's existing year-end
    results bit-for-bit what they were, so adopting Section 16's timing options
    cannot silently move a valuation that did not ask for them.
    """
    base = ONE + D(rate, what="discount rate")
    fraction = D(fraction, what="time fraction")
    if base <= 0:
        raise ProvenanceError(
            f"a discount rate of {rate} gives a non-positive base {base}, which "
            "has no real power. A rate at or below -100% is not a discount rate."
        )
    if fraction == fraction.to_integral_value():
        return ONE / power(base, int(fraction))
    with decimal.localcontext(CALCULATION_CONTEXT):
        return ONE / (fraction * base.ln()).exp()
