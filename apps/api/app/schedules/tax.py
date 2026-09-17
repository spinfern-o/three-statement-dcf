"""Item 74: the tax schedule (13.6).

13.6 asks for current tax, deferred tax, cash tax, NOL usage and valuation
allowances "when relevant and available". On the face of an income statement
none of those appear: there is one tax expense line, and the split lives in
the tax footnote. This system maps the face of the statements into canonical
lines and does not yet extract footnote tables, so the split is reported as
unavailable with that reason, and what *can* be computed -- the effective rate
-- is computed.

The effective rate matters beyond this screen. STEP 16 makes the model state
which rate it uses and why, and `model/schedules.py:TaxSchedule` accepts
`historical_effective` as one of three bases. This is where that number comes
from, which is why the rates that `TaxSchedule` would reject are separated out
rather than handed over: a rate of 1.4 from a loss-making year is arithmetic,
not a forecast assumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.accounts import Statement
from model.numeric import ZERO, quantize_for_display
from model.statements import Ledger

from .base import Availability, Caveat, Schedule

#: Effective rates are shown as percentages to two decimals.
RATE_PLACES = 2


@dataclass(frozen=True)
class TaxYear:
    year: str
    pretax_income: Decimal | None
    tax_expense: Decimal | None
    effective_rate: Decimal | None
    reason: str = ""

    @property
    def effective_rate_percent(self) -> Decimal | None:
        if self.effective_rate is None:
            return None
        return quantize_for_display(self.effective_rate * 100, RATE_PLACES)

    @property
    def usable_as_assumption(self) -> bool:
        """Whether `model/schedules.py:TaxSchedule` would accept this rate.

        It requires a decimal in [0, 1). A rate outside that range is not a
        bad measurement -- it is a correct measurement of a year whose tax
        charge does not describe a going rate, and STEP 16 wants that said
        rather than smoothed.
        """
        return self.effective_rate is not None and ZERO <= self.effective_rate < 1


@dataclass(frozen=True, kw_only=True)
class TaxScheduleView(Schedule):
    years: tuple[TaxYear, ...] = ()
    #: 13.6 components this filing's face statements cannot supply.
    missing_components: tuple[str, ...] = ()

    def usable_rates(self) -> "dict[str, Decimal]":
        """Year -> effective rate, for the years STEP 16 could actually use."""
        return {y.year: y.effective_rate for y in self.years if y.usable_as_assumption}


#: 13.6's list, minus the one line the face of an income statement carries.
FOOTNOTE_COMPONENTS = (
    "current tax expense",
    "deferred tax expense",
    "cash taxes paid",
    "net operating loss usage",
    "valuation allowances",
)


def _rate(pretax: Decimal | None, tax: Decimal | None) -> "tuple[Decimal | None, str]":
    if pretax is None or tax is None:
        missing = " and ".join(
            name
            for name, value in (("pretax income", pretax), ("tax expense", tax))
            if value is None
        )
        return None, f"the filing reports no {missing} for this period"
    if pretax == ZERO:
        return None, "pretax income is zero, so an effective rate is undefined (4.12)"
    rate = tax / pretax
    if pretax < ZERO:
        return rate, (
            "pretax income is negative, so this ratio is a tax benefit rate and not "
            "an effective rate a forecast can use (STEP 16)"
        )
    return rate, ""


def tax_schedule(ledgers: dict, years: "tuple[str, ...]") -> TaxScheduleView:
    """13.6, as far as the face of the income statement reaches."""
    income: Ledger = ledgers[Statement.INCOME]

    rows = []
    for year in years:
        pretax = income.get(accounts.PRETAX_INCOME, year)
        tax = income.get(accounts.TAXES, year)
        rate, reason = _rate(pretax, tax)
        if rate is not None and not reason and not (ZERO <= rate < 1):
            reason = (
                f"an effective rate of {quantize_for_display(rate * 100, RATE_PLACES)}% "
                "is outside the [0%, 100%) range STEP 16 accepts as a forecast "
                "assumption, and is reported rather than clipped"
            )
        rows.append(TaxYear(year, pretax, tax, rate, reason))

    return TaxScheduleView(
        key="tax",
        title="Taxes",
        rule="13.6",
        availability=Availability.PARTIAL,
        reason=(
            "the effective rate is computed from the face of the income statement; "
            "the current/deferred split, cash taxes paid, NOL usage and valuation "
            "allowances are disclosed only in the tax footnote, which this system "
            "does not extract into canonical lines"
        ),
        caveats=(
            Caveat(
                "13.6",
                "`taxes` is stored positive and subtracted (model/accounts.py "
                "POSITIVE_AND_SUBTRACTED), so the effective rate is tax expense over "
                "pretax income with no sign correction. A filing that prints the "
                "charge in parentheses has already had that handled at extraction.",
            ),
            Caveat(
                "STEP 16",
                "An effective rate measured over one or two periods carries "
                "whatever was unusual in them -- a settlement, a rate change, a "
                "one-off benefit. It is one of three bases STEP 16 allows and is "
                "not automatically the right one; the statutory and normalized "
                "bases exist for exactly the years this one misreads.",
            ),
        ),
        years=tuple(rows),
        missing_components=FOOTNOTE_COMPONENTS,
    )
