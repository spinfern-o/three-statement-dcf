"""13.4's second sentence: "Interest must state whether it uses beginning,
ending, or average debt."

That sentence is the whole module. The three bases give three different rates
on the same filing, and a model that computes a historical rate one way and
forecasts with another has a silent error in every forecast year's interest
expense.

So both defensible bases are computed and labelled, and the one the engine
actually uses is marked. `model/forecast.py` charges interest on BEGINNING
debt -- "interest_rate_on_debt = ... on beginning debt (STEP 19)" -- so the
beginning-debt rate is the one that reproduces this filing's interest expense
when handed forward as an assumption. The average-debt rate is shown beside it
because it is the better description of a year with a large mid-year
drawdown, and a reviewer choosing between them should see both rather than
discover later that one was picked for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.accounts import Statement
from model.numeric import ZERO, D, quantize_for_display
from model.statements import Ledger

RATE_PLACES = 4

#: The basis `model/forecast.py` charges interest on. Named here so the two
#: cannot drift apart without a test noticing.
ENGINE_BASIS = "beginning"

TWO = D(2)


@dataclass(frozen=True)
class ImpliedRate:
    basis: str  # "beginning" | "average"
    rate: Decimal | None
    denominator: Decimal | None
    explanation: str
    unavailable_reason: str = ""

    @property
    def is_engine_basis(self) -> bool:
        return self.basis == ENGINE_BASIS

    @property
    def percent(self) -> Decimal | None:
        if self.rate is None:
            return None
        return quantize_for_display(self.rate * 100, RATE_PLACES - 2)


@dataclass(frozen=True)
class InterestYear:
    year: str
    prior_year: str
    interest_expense: Decimal | None
    beginning_debt: Decimal | None
    ending_debt: Decimal | None
    rates: tuple[ImpliedRate, ...]

    def on(self, basis: str) -> ImpliedRate | None:
        for rate in self.rates:
            if rate.basis == basis:
                return rate
        return None


def _implied(
    basis: str, expense: Decimal | None, denominator: Decimal | None, explanation: str
) -> ImpliedRate:
    if expense is None:
        return ImpliedRate(
            basis,
            None,
            denominator,
            explanation,
            unavailable_reason="the filing reports no interest expense for this period",
        )
    if denominator is None:
        return ImpliedRate(
            basis,
            None,
            None,
            explanation,
            unavailable_reason=f"the {basis} debt balance is not reported",
        )
    if denominator == ZERO:
        return ImpliedRate(
            basis,
            None,
            denominator,
            explanation,
            unavailable_reason=(f"{basis} debt is zero, so a rate against it is undefined (4.12)"),
        )
    return ImpliedRate(basis, expense / denominator, denominator, explanation)


def implied_interest_rates(ledgers: dict, years: tuple[str, ...]) -> tuple[InterestYear, ...]:
    """One row per period that has a prior period to take an opening debt from."""
    balance: Ledger = ledgers[Statement.BALANCE]
    income: Ledger = ledgers[Statement.INCOME]

    rows = []
    for index, year in enumerate(years):
        if index == 0:
            continue
        prior = years[index - 1]
        expense = income.get(accounts.INTEREST_EXPENSE, year)
        opening = balance.get(accounts.DEBT, prior)
        closing = balance.get(accounts.DEBT, year)
        average = None if opening is None or closing is None else (opening + closing) / TWO
        rows.append(
            InterestYear(
                year=year,
                prior_year=prior,
                interest_expense=expense,
                beginning_debt=opening,
                ending_debt=closing,
                rates=(
                    _implied(
                        "beginning",
                        expense,
                        opening,
                        f"interest expense for {year} over debt at {prior} year end. "
                        "This is the basis model/forecast.py charges interest on "
                        "(STEP 19), so it is the rate that carries forward without "
                        "changing the convention mid-model.",
                    ),
                    _implied(
                        "average",
                        expense,
                        average,
                        f"interest expense for {year} over the mean of debt at {prior} "
                        f"and {year} year end. A better description of a year with a "
                        "large mid-year drawdown or repayment, and NOT the basis the "
                        "forecast uses.",
                    ),
                ),
            )
        )
    return tuple(rows)
