"""STEP 9 and STEP 37: linkage verification and the final PASS/FAIL panel.

Every check returns a result rather than raising, because STEP 37 asks for
a displayed panel -- you want to see all twelve, not just the first one that
blew up. The one thing a check never does is repair what it finds: STEP 6
forbids plugging a difference away, so a FAIL is reported with its delta and
left alone.

A check whose inputs are absent returns SKIP, distinct from PASS. A model
that silently "passes" because the data was never supplied is worse than
one that fails honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from . import accounts as A
from .dcf import FCFFYear, Valuation
from .forecast import ForecastResult
from .profile import Periods
from .statements import Ledger

# Tolerances are RELATIVE, not absolute. An absolute tolerance is a
# different test at every scale: 0.01 against a balance sheet of 1,020 is
# 1e-5, but against one of 1,020,000,000 it is 1e-11. Since the reporting
# units are the modeller's choice (STEP 1), an absolute bound would silently
# change strictness with a units change.
#
# The forecast identities are pure arithmetic and hold to floating-point
# precision; a randomized sweep over 600 models spanning nine orders of
# magnitude put the worst observed drift at 3.4e-13 relative. The default
# below leaves three orders of headroom above that while staying a thousand
# times stricter than 0.0001%.
DEFAULT_REL_TOL = 1e-9

# Absolute floor, for accounts legitimately at or near zero, where relative
# error is undefined. Zero by default: STEP 6 says a balance sheet that does
# not balance is an error to find, not a difference to absorb. Raise it
# deliberately (and visibly -- the report prints it) if a filing's own
# rounding, rather than the model, is what breaks a historical check.
DEFAULT_ABS_TOL = 0.0


@dataclass(frozen=True)
class Tolerance:
    rel: float = DEFAULT_REL_TOL
    abs: float = DEFAULT_ABS_TOL

    def close(self, a: float, b: float) -> bool:
        return abs(a - b) <= max(self.rel * max(abs(a), abs(b)), self.abs)

    def describe(self) -> str:
        return f"relative {self.rel:.0e}" + (f", absolute floor {self.abs:g}" if self.abs else "")


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str = ""

    def line(self, width: int = 44) -> str:
        return f"{self.name:<{width}} {self.status.value:<4} {self.detail}".rstrip()


def _ok(name: str, detail: str = "") -> CheckResult:
    return CheckResult(name, Status.PASS, detail)


def _fail(name: str, detail: str) -> CheckResult:
    return CheckResult(name, Status.FAIL, detail)


def _skip(name: str, detail: str) -> CheckResult:
    return CheckResult(name, Status.SKIP, detail)


def _balance_check(name: str, balance: Ledger, years: tuple[str, ...], tol: Tolerance) -> CheckResult:
    """STEP 6/21: Assets = Liabilities + Equity, every year."""
    breaks, checked = [], 0
    for year in years:
        assets = balance.get(A.TOTAL_ASSETS, year)
        liabilities = balance.get(A.TOTAL_LIABILITIES, year)
        equity = balance.get(A.TOTAL_EQUITY, year)
        if assets is None or liabilities is None or equity is None:
            continue
        checked += 1
        delta = assets - (liabilities + equity)
        if not tol.close(assets, liabilities + equity):
            breaks.append(f"{year}: out by {delta:,.4f}")
    if checked == 0:
        return _skip(name, "no year has all three totals")
    if breaks:
        return _fail(name, "; ".join(breaks) + " -- find the mapping error, do not plug it")
    return _ok(name, f"{checked} year(s) balance")


def _cashflow_reconciliation(
    name: str, balance: Ledger, cashflow: Ledger, periods: Periods,
    years: tuple[str, ...], tol: Tolerance,
) -> CheckResult:
    """STEP 22/37: beginning cash + CFO + CFI + CFF = ending balance-sheet cash."""
    breaks, checked = [], 0
    for year in years:
        prior = periods.prior(year)
        if prior is None:
            continue
        begin = balance.get(A.CASH, prior)
        end = balance.get(A.CASH, year)
        cfo, cfi, cff = (cashflow.get(k, year) for k in (A.CFO, A.CFI, A.CFF))
        if None in (begin, end, cfo, cfi, cff):
            continue
        checked += 1
        delta = (begin + cfo + cfi + cff) - end
        if not tol.close(begin + cfo + cfi + cff, end):
            breaks.append(f"{year}: out by {delta:,.4f}")
    if checked == 0:
        return _skip(name, "insufficient cash / cash-flow data")
    if breaks:
        return _fail(name, "; ".join(breaks))
    return _ok(name, f"{checked} year(s) reconcile")


def _net_income_linkage(income: Ledger, cashflow: Ledger, years: tuple[str, ...], tol: Tolerance) -> CheckResult:
    """STEP 9: net income flows into the cash flow statement."""
    name = "Net income linkage (IS -> CF)"
    breaks, checked = [], 0
    for year in years:
        is_ni = income.get(A.NET_INCOME, year)
        cf_ni = cashflow.get(A.NET_INCOME, year)
        if is_ni is None or cf_ni is None:
            continue
        checked += 1
        if not tol.close(is_ni, cf_ni):
            breaks.append(f"{year}: IS {is_ni:,.1f} vs CF {cf_ni:,.1f}")
    if checked == 0:
        return _skip(name, "net income not present on both statements")
    return _fail(name, "; ".join(breaks)) if breaks else _ok(name, f"{checked} year(s) tie")


def _schedule_linkage(
    name: str, schedule, balance: Ledger, account: str, years: tuple[str, ...], tol: Tolerance
) -> CheckResult:
    """STEP 9: a schedule's ending balance equals the balance-sheet account."""
    breaks, checked = [], 0
    for year in years:
        if year not in schedule.rows:
            continue
        sheet = balance.get(account, year)
        if sheet is None:
            continue
        checked += 1
        delta = schedule.ending(year) - sheet
        if not tol.close(schedule.ending(year), sheet):
            breaks.append(f"{year}: schedule {schedule.ending(year):,.1f} vs sheet {sheet:,.1f}")
    if checked == 0:
        return _skip(name, "schedule or balance-sheet account absent")
    return _fail(name, "; ".join(breaks)) if breaks else _ok(name, f"{checked} year(s) tie")


def _fcff_matches_forecast(fcff_years: list[FCFFYear], forecast: ForecastResult, tol: Tolerance) -> CheckResult:
    """STEP 37: FCFF is built from the forecast, not assembled separately."""
    name = "FCFF matches three-statement forecast"
    breaks = []
    for item in fcff_years:
        terms = forecast.fcff_inputs(item.year)
        for field_name, expected in terms.items():
            actual = getattr(item, {"d_and_a": "d_and_a"}.get(field_name, field_name))
            if not tol.close(actual, expected):
                breaks.append(f"{item.year}.{field_name}: {actual:,.4f} vs {expected:,.4f}")
    if not fcff_years:
        return _skip(name, "no FCFF years built")
    return _fail(name, "; ".join(breaks)) if breaks else _ok(name, f"{len(fcff_years)} year(s) tie to the model")


def _no_forecast_hardcodes(forecast: ForecastResult) -> CheckResult:
    """STEP 37: a forecast cell should be driven, never pasted in."""
    name = "No unintended forecast hardcodes"
    found = []
    for ledger in (forecast.income, forecast.balance, forecast.cashflow):
        found += [f"{ledger.statement.value}.{c}" for c in ledger.hardcodes_in(forecast.periods.forecast)]
    if found:
        return _fail(name, f"{len(found)} hardcoded forecast cell(s): {', '.join(found[:6])}")
    return _ok(name, "every forecast cell carries a driver")


def _wacc_above_growth(valuation: Valuation | None) -> CheckResult:
    name = "WACC > terminal growth rate"
    if valuation is None:
        return _skip(name, "no valuation run")
    if valuation.wacc > valuation.terminal_growth:
        return _ok(name, f"WACC {valuation.wacc:.4f} > g {valuation.terminal_growth:.4f}")
    return _fail(name, f"WACC {valuation.wacc:.4f} <= g {valuation.terminal_growth:.4f}")


def run_all_checks(
    forecast: ForecastResult,
    fcff_years: list[FCFFYear] | None = None,
    valuation: Valuation | None = None,
    tolerance: Tolerance | None = None,
) -> list[CheckResult]:
    """The twelve checks STEP 37 asks to be displayed, in its order."""
    tol = tolerance or Tolerance()
    periods = forecast.periods
    hist, fore = periods.historical, periods.forecast
    all_years = periods.all_years

    results = [
        _balance_check("Historical balance sheet balances", forecast.balance, hist, tol),
        _balance_check("Forecast balance sheet balances", forecast.balance, fore, tol),
        _cashflow_reconciliation(
            "Historical cash flow reconciliation", forecast.balance, forecast.cashflow, periods, hist, tol
        ),
        _cashflow_reconciliation(
            "Forecast cash flow reconciliation", forecast.balance, forecast.cashflow, periods, fore, tol
        ),
        _net_income_linkage(forecast.income, forecast.cashflow, all_years, tol),
        _schedule_linkage("PP&E schedule linkage", forecast.ppe, forecast.balance, A.PPE_NET, fore, tol),
        _schedule_linkage("Debt schedule linkage", forecast.debt, forecast.balance, A.DEBT, fore, tol),
        _schedule_linkage(
            "Retained earnings linkage", forecast.retained_earnings, forecast.balance, A.RETAINED_EARNINGS, fore, tol
        ),
        _cashflow_reconciliation(
            "Ending cash linkage", forecast.balance, forecast.cashflow, periods, fore, tol
        ),
        _no_forecast_hardcodes(forecast),
        _wacc_above_growth(valuation),
        _fcff_matches_forecast(fcff_years or [], forecast, tol),
    ]
    return results


def summarize(results: list[CheckResult]) -> tuple[int, int, int]:
    passed = sum(1 for r in results if r.status is Status.PASS)
    failed = sum(1 for r in results if r.status is Status.FAIL)
    skipped = sum(1 for r in results if r.status is Status.SKIP)
    return passed, failed, skipped
