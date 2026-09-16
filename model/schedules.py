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

from .provenance import ProvenanceError


@dataclass
class RollForwardRow:
    year: str
    beginning: float
    additions: dict[str, float] = field(default_factory=dict)
    reductions: dict[str, float] = field(default_factory=dict)

    @property
    def ending(self) -> float:
        return self.beginning + sum(self.additions.values()) - sum(self.reductions.values())

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
        beginning: float,
        additions: dict[str, float] | None = None,
        reductions: dict[str, float] | None = None,
    ) -> RollForwardRow:
        if self._order:
            prior = self.rows[self._order[-1]]
            if abs(prior.ending - beginning) > 0.01:
                raise ProvenanceError(
                    f"{self.name}: {year} beginning balance {beginning:,.1f} does not equal "
                    f"{prior.year} ending balance {prior.ending:,.1f}. The schedule must chain "
                    "(STEP 8); a break here is an error, not something to average over."
                )
        row = RollForwardRow(year, beginning, dict(additions or {}), dict(reductions or {}))
        self.rows[year] = row
        self._order.append(year)
        return row

    def ending(self, year: str) -> float:
        if year not in self.rows:
            raise KeyError(f"{self.name}: no row for {year}")
        return self.rows[year].ending

    def beginning(self, year: str) -> float:
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
    accounts_receivable: float
    inventory: float
    other_current_assets: float
    accounts_payable: float
    other_current_liabilities: float

    @property
    def operating_current_assets(self) -> float:
        return self.accounts_receivable + self.inventory + self.other_current_assets

    @property
    def operating_current_liabilities(self) -> float:
        return self.accounts_payable + self.other_current_liabilities

    @property
    def nwc(self) -> float:
        """Operating NWC: excludes cash, debt and other financing balances."""
        return self.operating_current_assets - self.operating_current_liabilities


class WorkingCapitalSchedule:
    def __init__(self) -> None:
        self.rows: dict[str, WorkingCapitalRow] = {}
        self._order: list[str] = []

    def add(self, row: WorkingCapitalRow) -> None:
        self.rows[row.year] = row
        self._order.append(row.year)

    def nwc(self, year: str) -> float:
        return self.rows[year].nwc

    def change_in_nwc(self, year: str, prior_year: str | None) -> float:
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


def days_to_balance(driver_amount: float, days: float, days_in_year: int = 365) -> float:
    """AR = Revenue x DSO / 365, Inventory = COGS x Days / 365, AP = COGS x DPO / 365."""
    if days < 0:
        raise ProvenanceError(f"Days assumption must be non-negative, got {days}")
    return driver_amount * days / days_in_year


@dataclass
class TaxSchedule:
    """STEP 16: state which rate the model uses, and why."""

    basis: str  # "statutory" | "historical_effective" | "normalized_effective"
    rate_by_year: dict[str, float]

    VALID = ("statutory", "historical_effective", "normalized_effective")

    def __post_init__(self) -> None:
        if self.basis not in self.VALID:
            raise ProvenanceError(
                f"STEP 16 requires the tax basis to be stated as one of {self.VALID}, got {self.basis!r}"
            )
        for year, rate in self.rate_by_year.items():
            if not 0.0 <= rate < 1.0:
                raise ProvenanceError(f"Tax rate for {year} must be a decimal in [0, 1), got {rate!r}")

    def rate(self, year: str) -> float:
        if year not in self.rate_by_year:
            raise ProvenanceError(f"No tax rate supplied for {year} (STEP 16)")
        return self.rate_by_year[year]
