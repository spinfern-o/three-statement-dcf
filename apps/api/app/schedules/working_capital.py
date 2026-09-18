"""Item 69: the historical working-capital schedule (13.1).

13.1 asks for four things: a definition of operating current assets, a
definition of operating current liabilities, the exclusion of cash, debt and
non-operating accounts, and the day-count drivers with their denominators
explained. The definitions are not invented here -- `model/accounts.py`
already fixes the membership as `OPERATING_CURRENT_ASSETS`,
`OPERATING_CURRENT_LIABILITIES` and `EXCLUDED_FROM_NWC`, so the forecast and
the history cannot drift into meaning different things by "NWC".

Two conventions have to be stated rather than assumed, because both have a
defensible alternative and the alternative gives a different number.

**Year-end balances, not averages.** DSO here is the year-end receivable over
the year's revenue. The average-balance version is arguably the better
description of how the business ran during the year, but this driver exists to
be inverted: `model/schedules.py:days_to_balance` forecasts a *closing*
balance as `Revenue x DSO / days`, so a DSO computed on averages would not
reproduce the balance sheet it came from.

**365 days.** Stated as a parameter, not written into the formula, because
13.1.e asks for the convention to be explained and some filings run a 52/53
week year where 364 is the honest denominator.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.accounts import Statement
from model.numeric import ZERO, D, quantize_for_display
from model.statements import Ledger

from .base import Availability, Caveat, Reconciliation, Schedule, ScheduleLine

#: 13.1.e. The denominator of every days driver, stated once.
DAYS_IN_YEAR = D(365)

#: Days are shown to one decimal; the underlying Decimal is exact.
DAYS_PLACES = 1


@dataclass(frozen=True)
class Driver:
    """A days-based working-capital driver, with its denominator explained."""

    name: str
    days: Decimal | None
    numerator: str
    denominator: str
    convention: str
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        if self.days is None and not self.unavailable_reason:
            raise ValueError(f"Driver {self.name!r} has no value and no reason")


@dataclass(frozen=True)
class WorkingCapitalYear:
    year: str
    assets: tuple[ScheduleLine, ...]
    liabilities: tuple[ScheduleLine, ...]
    drivers: tuple[Driver, ...]

    @staticmethod
    def _total(lines: tuple[ScheduleLine, ...]) -> Decimal | None:
        present = [line.value for line in lines if line.value is not None]
        return sum(present, ZERO) if present else None

    @property
    def operating_current_assets(self) -> Decimal | None:
        return self._total(self.assets)

    @property
    def operating_current_liabilities(self) -> Decimal | None:
        return self._total(self.liabilities)

    @property
    def nwc(self) -> Decimal | None:
        """Operating current assets less operating current liabilities.

        A total over the components this filing reports. A component it does
        not report is named in `absent` rather than treated as zero, because
        the two are only the same claim if the company genuinely has none --
        and the reconciliation against the cash flow statement is what tests
        that (STEP 5).
        """
        oca, ocl = self.operating_current_assets, self.operating_current_liabilities
        if oca is None or ocl is None:
            return None
        return oca - ocl

    @property
    def absent(self) -> tuple[str, ...]:
        return tuple(
            line.label
            for line in self.assets + self.liabilities
            if line.value is None
        )


@dataclass(frozen=True, kw_only=True)
class WorkingCapitalSchedule(Schedule):
    years: tuple[WorkingCapitalYear, ...] = ()
    days_in_year: Decimal = DAYS_IN_YEAR
    excluded: tuple[str, ...] = ()


def _lines(ledger: Ledger, year: str, names: tuple[str, ...], side: str) -> tuple[ScheduleLine, ...]:
    out = []
    for name in names:
        value = ledger.get(name, year)
        basis = f"balance_sheet.{name} at {year} year end, an operating current {side}"
        if value is None:
            out.append(
                ScheduleLine(
                    name, None, basis,
                    absent_reason=f"the filing reports no {name!r} for {year}",
                )
            )
        else:
            out.append(ScheduleLine(name, value, basis))
    return tuple(out)


def _days(
    name: str,
    balance: Decimal | None,
    balance_name: str,
    flow: Decimal | None,
    flow_name: str,
    days_in_year: Decimal,
) -> Driver:
    """balance / flow x days. Undefined against an absent or zero denominator."""
    convention = (
        f"{balance_name} at year end divided by the full-year {flow_name}, times "
        f"{days_in_year} days (13.1.e). Year-end rather than average balances, so "
        "the driver reproduces the balance sheet it came from when inverted."
    )
    numerator = f"{balance_name} (year-end balance)"
    denominator = f"{flow_name} (full year)"
    if balance is None:
        return Driver(
            name, None, numerator, denominator, convention,
            unavailable_reason=f"the filing reports no {balance_name}",
        )
    if flow is None:
        return Driver(
            name, None, numerator, denominator, convention,
            unavailable_reason=f"the filing reports no {flow_name} to divide by",
        )
    if flow == ZERO:
        return Driver(
            name, None, numerator, denominator, convention,
            unavailable_reason=(
                f"{flow_name} is zero, so days against it are undefined (4.12)"
            ),
        )
    return Driver(
        name,
        quantize_for_display(balance / flow * days_in_year, DAYS_PLACES),
        numerator,
        denominator,
        convention,
    )


def working_capital_schedule(
    ledgers: dict, years: tuple[str, ...], days_in_year: Decimal = DAYS_IN_YEAR
) -> WorkingCapitalSchedule:
    """13.1, built for every period the filing reports."""
    balance: Ledger = ledgers[Statement.BALANCE]
    income: Ledger = ledgers[Statement.INCOME]
    cashflow: Ledger = ledgers[Statement.CASHFLOW]

    rows: list[WorkingCapitalYear] = []
    for year in years:
        assets = _lines(balance, year, accounts.OPERATING_CURRENT_ASSETS, "asset")
        liabilities = _lines(
            balance, year, accounts.OPERATING_CURRENT_LIABILITIES, "liability"
        )
        revenue = income.get(accounts.REVENUE, year)
        cogs = income.get(accounts.COGS, year)
        drivers = (
            _days(
                "DSO", balance.get(accounts.ACCOUNTS_RECEIVABLE, year),
                "accounts receivable", revenue, "revenue", days_in_year,
            ),
            _days(
                "Inventory days", balance.get(accounts.INVENTORY, year),
                "inventory", cogs, "cost of goods sold", days_in_year,
            ),
            _days(
                "DPO", balance.get(accounts.ACCOUNTS_PAYABLE, year),
                "accounts payable", cogs, "cost of goods sold", days_in_year,
            ),
        )
        rows.append(WorkingCapitalYear(year, assets, liabilities, drivers))

    # 13.8: the period-over-period change against the cash flow statement's
    # own working-capital line. The sign is the interesting part: an increase
    # in net working capital CONSUMES cash, so the cash flow figure is the
    # negative of the balance-sheet change.
    reconciliations = []
    by_year = {row.year: row for row in rows}
    for index, year in enumerate(years):
        if index == 0:
            continue
        prior = years[index - 1]
        this_nwc, prior_nwc = by_year[year].nwc, by_year[prior].nwc
        computed = None
        if this_nwc is not None and prior_nwc is not None:
            computed = -(this_nwc - prior_nwc)
        note = (
            "the cash flow figure is the negative of the balance-sheet change: "
            "an increase in working capital consumes cash"
        )
        absent = by_year[year].absent + by_year[prior].absent
        if absent:
            note += ". Components absent from the balance sheet, and so missing "
            note += "from this change: " + ", ".join(sorted(set(absent)))
        reconciliations.append(
            Reconciliation(
                year=year,
                statement_line=f"cash_flow_statement.{accounts.CHANGE_IN_NWC}",
                computed=computed,
                reported=cashflow.get(accounts.CHANGE_IN_NWC, year),
                note=note,
            )
        )

    absent_anywhere = sorted({label for row in rows for label in row.absent})
    partial = bool(absent_anywhere) or any(
        d.days is None for row in rows for d in row.drivers
    )
    return WorkingCapitalSchedule(
        key="working_capital",
        title="Working capital",
        rule="13.1",
        availability=Availability.PARTIAL if partial else Availability.AVAILABLE,
        reason=(
            "built over the operating accounts this filing reports; "
            + (
                "absent from it: " + ", ".join(absent_anywhere)
                if absent_anywhere
                else "one or more days drivers has no denominator to divide by"
            )
        )
        if partial
        else "",
        caveats=(
            Caveat(
                "13.1.c",
                "Cash and debt are excluded from working capital by definition "
                "(model/accounts.py EXCLUDED_FROM_NWC), not by judgement about this "
                "filing. Cash is the DCF's output and debt is financing; including "
                "either would make the change in working capital absorb them.",
            ),
            Caveat(
                "13.1.d",
                "Every driver divides a year-end balance by a full-year flow. In a "
                "year with an acquisition, a disposal or a sharp change in trading "
                "late in the period, the resulting days figure describes neither "
                "the year nor the year end well, and should not be extrapolated "
                "without saying so.",
            ),
        ),
        reconciliations=tuple(reconciliations),
        years=tuple(rows),
        days_in_year=days_in_year,
        excluded=accounts.EXCLUDED_FROM_NWC,
    )
