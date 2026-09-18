"""Render the model as text, following the workflow's own output demands.

STEP 10 wants assumptions split by basis; STEP 29 wants FCFF, discount
period, discount factor and present value shown separately; STEP 37 wants a
PASS/FAIL panel. This module does that and nothing else -- no calculation
happens here.
"""

from __future__ import annotations

from decimal import Decimal

from .assumptions import Assumptions, Basis
from .checks import CheckResult, Tolerance, summarize
from .dcf import CostOfCapital, FCFFYear, Valuation
from .forecast import ForecastResult
from .numeric import quantize_for_display
from .profile import CompanyProfile, Periods, SourceMap
from .sensitivity import SensitivityCell
from .statements import Ledger

WIDTH = 78


def rule(char: str = "-") -> str:
    return char * WIDTH


def header(title: str) -> str:
    return f"\n{rule('=')}\n{title}\n{rule('=')}"


def _row(label: str, values: list[str], label_width: int = 30, col: int = 12) -> str:
    return f"{label:<{label_width}}" + "".join(f"{v:>{col}}" for v in values)


def _fmt(value: Decimal | None, places: int = 1) -> str:
    """Round for display only, through the declared boundary (4.9, 4.18).

    The stored value keeps full precision; this is the single place a
    statement figure is reduced for presentation.
    """
    return "--" if value is None else f"{quantize_for_display(value, places):,.{places}f}"


def statement_block(
    title: str, ledger: Ledger, accounts: tuple[str, ...], years: tuple[str, ...]
) -> str:
    lines = [header(title), _row("", list(years))]
    for account in accounts:
        if not any(ledger.has(account, y) for y in years):
            continue  # STEP 5: a line the company does not report stays off the page
        lines.append(_row(account, [_fmt(ledger.get(account, y)) for y in years]))
    return "\n".join(lines)


def profile_block(
    profile: CompanyProfile, source_map: SourceMap, periods: Periods
) -> str:
    lines = [header("STEP 1-3 -- IDENTIFICATION"), profile.describe()]
    missing = source_map.missing()
    if missing:
        lines.append(f"\nSTEP 2 source map INCOMPLETE -- no page recorded for: {', '.join(missing)}")
    else:
        lines.append("\nSTEP 2 source map: complete (all 12 sections located)")
    lines.append(f"Historical: {', '.join(periods.historical)}")
    lines.append(f"Forecast:   {', '.join(periods.forecast)}")
    return "\n".join(lines)


def assumptions_block(assumptions: Assumptions) -> str:
    lines = [header("STEP 10 -- ASSUMPTIONS, BY BASIS")]
    grouped = assumptions.by_basis()
    for basis in Basis:
        items = grouped[basis]
        lines.append(f"\n{basis.label} ({len(items)}):")
        if not items:
            lines.append("  (none)")
        for item in items:
            scope = item.year or "all years"
            note = f" -- {item.note}" if item.note else ""
            lines.append(f"  {item.name} [{scope}] = {item.value} -- {item.source}{note}")
    if assumptions.conflicts:
        lines.append(f"\nSTEP 11 -- SOURCE CONFLICTS RESOLVED ({len(assumptions.conflicts)}):")
        for conflict in assumptions.conflicts:
            lines.append(f"  {conflict.describe()}")
    unused = assumptions.unused()
    if unused:
        lines.append(f"\nDeclared but never used ({len(unused)}): {', '.join(unused)}")
    return "\n".join(lines)


def schedules_block(forecast: ForecastResult) -> str:
    lines = [header("STEP 8 / 17-19 -- SUPPORTING SCHEDULES")]
    for schedule in (forecast.ppe, forecast.debt, forecast.retained_earnings):
        lines.append(f"\n{schedule.name}: {schedule.formula}")
        for year, explanation in schedule.table():
            lines.append(f"  {year}  {explanation}")
    lines.append("\nWorking capital (STEP 17): NWC = operating current assets - operating current liabilities")
    wc = forecast.working_capital
    prior = None
    for year in wc.years:
        row = wc.rows[year]
        change = "" if prior is None else f"  change {wc.change_in_nwc(year, prior):>+10,.1f}"
        lines.append(
            f"  {year}  AR {row.accounts_receivable:>9,.1f}  Inv {row.inventory:>9,.1f}  "
            f"AP {row.accounts_payable:>9,.1f}  NWC {row.nwc:>10,.1f}{change}"
        )
        prior = year
    return "\n".join(lines)


def fcff_block(fcff_years: list[FCFFYear]) -> str:
    lines = [header("STEP 23-24 -- FCFF"), "FCFF = EBIT x (1 - t) + D&A - CapEx - Change in NWC", ""]
    lines.append(_row("", ["NOPAT", "D&A", "CapEx", "chg NWC", "FCFF"], 10, 12))
    for item in fcff_years:
        lines.append(
            _row(
                item.year,
                [f"{item.nopat:,.1f}", f"{item.d_and_a:,.1f}", f"{item.capex:,.1f}",
                 f"{item.change_in_nwc:,.1f}", f"{item.fcff:,.1f}"],
                10, 12,
            )
        )
    return "\n".join(lines)


def wacc_block(cost_of_capital: CostOfCapital) -> str:
    lines = [header("STEP 25-28 -- COST OF CAPITAL"), cost_of_capital.explain(), "", "Sources:"]
    for key in CostOfCapital.REQUIRED_SOURCES:
        lines.append(f"  {key}: {cost_of_capital.sources.get(key, '(none)')}")
    return "\n".join(lines)


def valuation_block(valuation: Valuation) -> str:
    lines = [header("STEP 29-35 -- DISCOUNTING AND VALUE")]
    lines.append(_row("", ["FCFF", "period", "factor", "PV"], 10, 14))
    for item in valuation.discounted:
        lines.append(
            _row(item.year, [f"{item.fcff:,.1f}", str(item.period),
                             f"{item.discount_factor:.4f}", f"{item.present_value:,.1f}"], 10, 14)
        )
    lines += [
        "",
        f"Sum of PV of explicit FCFF        {valuation.pv_explicit:>16,.1f}",
        f"Terminal FCFF (STEP 30)           {valuation.terminal_fcff:>16,.1f}",
        f"Terminal value (STEP 31)          {valuation.terminal_value:>16,.1f}",
        f"PV of terminal value (STEP 32)    {valuation.pv_terminal_value:>16,.1f}",
        rule(),
        f"ENTERPRISE VALUE (STEP 33)        {valuation.enterprise_value:>16,.1f}",
        (
            "  terminal value share of enterprise value: undefined (enterprise value is zero)"
            if valuation.tv_share_of_ev is None
            else f"  terminal value is {valuation.tv_share_of_ev:.1%} of enterprise value"
        ),
        "",
        "STEP 34 -- bridge to equity value:",
    ]
    for label, amount in valuation.bridge.lines():
        lines.append(f"  {label:<32}{amount:>16,.1f}")
    lines.append(rule())
    lines.append(f"EQUITY VALUE (STEP 34)            {valuation.equity_value:>16,.1f}")
    price = valuation.implied_share_price
    if price is None:
        lines.append("Implied share price (STEP 35): not calculated -- no diluted share count supplied")
    else:
        lines.append(f"Diluted shares                    {valuation.diluted_shares:>16,.1f}")
        lines.append(f"IMPLIED SHARE PRICE (STEP 35)     {price:>16,.2f}")
        lines.append(f"  shares source: {valuation.shares_source}")
    return "\n".join(lines)


def sensitivity_block(grid: list[list[SensitivityCell]], metric: str = "implied_share_price") -> str:
    if not grid:
        return ""
    label = {"implied_share_price": "Implied share price",
             "equity_value": "Equity value",
             "enterprise_value": "Enterprise value"}[metric]
    lines = [header(f"STEP 36 -- SENSITIVITY: {label.upper()}")]
    growths = [c.terminal_growth for c in grid[0]]
    lines.append(_row("WACC \\ g", [f"{g:.2%}" for g in growths], 12, 14))
    for row in grid:
        values = []
        for cell in row:
            value = getattr(cell, metric)
            values.append("n/a" if value is None else (f"{value:,.2f}" if metric == "implied_share_price" else f"{value:,.0f}"))
        lines.append(_row(f"{row[0].wacc:.2%}", values, 12, 14))
    return "\n".join(lines)


def checks_block(results: list[CheckResult], tolerance: Tolerance | None = None) -> str:
    passed, failed, skipped = summarize(results)
    lines = [header("STEP 37 -- FINAL MODEL CHECKS")]
    if tolerance is not None:
        lines.append(f"judged at {tolerance.describe()}\n")
    for result in results:
        lines.append(result.line())
    lines.append(rule())
    lines.append(f"{passed} PASS   {failed} FAIL   {skipped} SKIP")
    if failed:
        lines.append(
            "\nA FAIL is an extraction or mapping error to find, not a number to plug (STEP 6)."
        )
    if skipped:
        lines.append(
            "A SKIP means the check could not run because its inputs were absent. "
            "It is not a pass."
        )
    return "\n".join(lines)
