"""STEP 8 / 17-19: supporting schedules.

Each schedule is a roll-forward written exactly as the workflow states it.
They exist so that the balance-sheet accounts they govern are never
forecast as a free-standing guess: PP&E comes out of the PP&E schedule,
debt out of the debt schedule, retained earnings out of the RE schedule.

STEP 18 is emphatic that depreciation and CapEx are forecast separately;
nothing here lets one default to the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .numeric import ZERO, D
from .provenance import ProvenanceError


@dataclass
class RollForwardRow:
    year: str
    beginning: Decimal
    additions: dict[str, Decimal] = field(default_factory=dict)
    reductions: dict[str, Decimal] = field(default_factory=dict)

    @property
    def ending(self) -> Decimal:
        return (
            self.beginning
            + sum(self.additions.values(), ZERO)
            - sum(self.reductions.values(), ZERO)
        )

    def explain(self) -> str:
        parts = [f"{self.beginning:,.1f}"]
        parts += [f"+ {v:,.1f} ({k})" for k, v in self.additions.items()]
        parts += [f"- {v:,.1f} ({k})" for k, v in self.reductions.items()]
        return " ".join(parts) + f" = {self.ending:,.1f}"


class RollForward:
    """Beginning -> additions -> reductions -> ending, chained across years."""

    def __init__(self, name: str, formula: str):
        self.name = name
        self.formula = formula
        self.rows: dict[str, RollForwardRow] = {}
        self._order: list[str] = []

    def add_year(
        self,
        year: str,
        beginning: Decimal,
        additions: dict[str, Decimal] | None = None,
        reductions: dict[str, Decimal] | None = None,
    ) -> RollForwardRow:
        beginning = D(beginning, what=f"{self.name} {year} beginning")
        additions = {k: D(v, what=f"{self.name} {year} {k}") for k, v in (additions or {}).items()}
        reductions = {
            k: D(v, what=f"{self.name} {year} {k}") for k, v in (reductions or {}).items()
        }
        if self._order:
            prior = self.rows[self._order[-1]]
            # Relative, for the same reason as model/checks.py: an absolute
            # bound is a different test at every reporting scale.
            if abs(prior.ending - beginning) > D("1e-9") * max(
                abs(prior.ending), abs(beginning), D(1)
            ):
                raise ProvenanceError(
                    f"{self.name}: {year} beginning balance {beginning:,.1f} does not equal "
                    f"{prior.year} ending balance {prior.ending:,.1f}. The schedule must chain "
                    "(STEP 8); a break here is an error, not something to average over."
                )
        row = RollForwardRow(year, beginning, additions, reductions)
        self.rows[year] = row
        self._order.append(year)
        return row

    def ending(self, year: str) -> Decimal:
        if year not in self.rows:
            raise KeyError(f"{self.name}: no row for {year}")
        return self.rows[year].ending

    def beginning(self, year: str) -> Decimal:
        return self.rows[year].beginning

    @property
    def years(self) -> tuple[str, ...]:
        return tuple(self._order)

    def table(self) -> list[tuple[str, str]]:
        return [(y, self.rows[y].explain()) for y in self._order]


def ppe_schedule() -> RollForward:
    """STEP 8/18: Ending PP&E = Beginning + CapEx - Depreciation - Disposals."""
    return RollForward("PP&E", "Ending PP&E = Beginning PP&E + CapEx - Depreciation - Disposals")


def debt_schedule() -> RollForward:
    """STEP 8/19: Ending Debt = Beginning + New Borrowing - Repayment."""
    return RollForward("Debt", "Ending Debt = Beginning Debt + New Borrowing - Debt Repayment")


def retained_earnings_schedule() -> RollForward:
    """STEP 8: Ending RE = Beginning RE + Net Income - Dividends."""
    return RollForward("Retained Earnings", "Ending RE = Beginning RE + Net Income - Dividends")


@dataclass
class WorkingCapitalRow:
    """STEP 17: forecast working capital account by account, never as one number."""

    year: str
    accounts_receivable: Decimal
    inventory: Decimal
    other_current_assets: Decimal
    accounts_payable: Decimal
    other_current_liabilities: Decimal

    @property
    def operating_current_assets(self) -> Decimal:
        return self.accounts_receivable + self.inventory + self.other_current_assets

    @property
    def operating_current_liabilities(self) -> Decimal:
        return self.accounts_payable + self.other_current_liabilities

    @property
    def nwc(self) -> Decimal:
        """Operating NWC: excludes cash, debt and other financing balances."""
        return self.operating_current_assets - self.operating_current_liabilities


class WorkingCapitalSchedule:
    def __init__(self) -> None:
        self.rows: dict[str, WorkingCapitalRow] = {}
        self._order: list[str] = []

    def add(self, row: WorkingCapitalRow) -> None:
        self.rows[row.year] = row
        self._order.append(row.year)

    def nwc(self, year: str) -> Decimal:
        return self.rows[year].nwc

    def change_in_nwc(self, year: str, prior_year: str | None) -> Decimal:
        """STEP 17: Change in NWC = NWC_t - NWC_(t-1).

        An increase in NWC consumes cash; the sign is applied where it is
        used (STEP 22 and STEP 23), not baked in here.
        """
        if prior_year is None:
            raise ProvenanceError(
                f"Change in NWC for {year} needs a prior year. The first modeled year must "
                "have the last actual year before it (STEP 17)."
            )
        if prior_year not in self.rows:
            raise ProvenanceError(
                f"Change in NWC for {year} requires NWC for {prior_year}, which was not built. "
                "Build the working-capital schedule for the last actual year too."
            )
        return self.rows[year].nwc - self.rows[prior_year].nwc

    @property
    def years(self) -> tuple[str, ...]:
        return tuple(self._order)


def days_to_balance(
    driver_amount: Decimal, days: Decimal, days_in_year: Decimal | int = 365
) -> Decimal:
    """AR = Revenue x DSO / 365, Inventory = COGS x Days / 365, AP = COGS x DPO / 365.

    The division is exact to the calculation context's precision; the day
    count is a policy input rather than a hidden 365 (specification 13.1.e
    requires the day-count convention be stated).
    """
    amount = D(driver_amount, what="days_to_balance driver")
    day_count = D(days, what="days assumption")
    basis = D(days_in_year, what="days_in_year")
    if day_count < 0:
        raise ProvenanceError(f"Days assumption must be non-negative, got {days}")
    if basis <= 0:
        raise ProvenanceError(f"days_in_year must be positive, got {days_in_year}")
    return amount * day_count / basis


@dataclass
class TaxSchedule:
    """STEP 16: state which rate the model uses, and why."""

    basis: str  # "statutory" | "historical_effective" | "normalized_effective"
    rate_by_year: dict[str, Decimal]

    VALID = ("statutory", "historical_effective", "normalized_effective")

    def __post_init__(self) -> None:
        if self.basis not in self.VALID:
            raise ProvenanceError(
                f"STEP 16 requires the tax basis to be stated as one of {self.VALID}, got {self.basis!r}"
            )
        coerced = {}
        for year, rate in self.rate_by_year.items():
            value = D(rate, what=f"tax rate {year}")
            if not 0 <= value < 1:
                raise ProvenanceError(
                    f"Tax rate for {year} must be a decimal in [0, 1), got {rate!r}"
                )
            coerced[year] = value
        self.rate_by_year = coerced

    def rate(self, year: str) -> Decimal:
        if year not in self.rate_by_year:
            raise ProvenanceError(f"No tax rate supplied for {year} (STEP 16)")
        return self.rate_by_year[year]
