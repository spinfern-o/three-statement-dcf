"""The engine computes what the workflow says it should, on the fixture."""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

import model.accounts as A
from model.numeric import D
from model.checks import Status, run_all_checks
from model.statements import Ledger


# --- STEP 5-7: standardization --------------------------------------------
def test_absent_line_stays_absent(loaded):
    """STEP 5: an unreported line is None, never 0.0."""
    income = loaded["income"]
    assert income.get(A.COGS, "2025A") == D("580")
    # The fixture reports no gross_profit line; it is DERIVED, not transcribed.
    assert income.origin_of(A.GROSS_PROFIT, "2025A") == "derived"
    assert income.get(A.GROSS_PROFIT, "2025A") == D("420")


def test_derived_cascade(loaded):
    """revenue -> gross profit -> EBIT -> pretax -> net income."""
    income = loaded["income"]
    assert income.get(A.EBIT, "2025A") == D("170")
    assert income.get(A.PRETAX_INCOME, "2025A") == D("140")
    assert income.get(A.NET_INCOME, "2025A") == D("106.4")


def test_reported_subtotals_agree_with_components(loaded):
    """STEP 9: where both exist, they must tie."""
    for key in ("income", "balance", "cashflow"):
        assert loaded[key].cross_check() == [], f"{key} has a reported/derived disagreement"


def test_cross_check_detects_a_contradiction():
    """A wrong subtotal is surfaced, not corrected (STEP 6)."""
    from model.accounts import Statement
    from model.provenance import Figure, Source

    ledger = Ledger(Statement.INCOME, ("2025A",))
    src = Source("10-K", 40, "line")
    for account, value in [(A.REVENUE, "1000"), (A.COGS, "580"), (A.GROSS_PROFIT, "500")]:
        ledger.set_reported(account, "2025A", Figure(value, "2025A", src))
    breaks = ledger.cross_check()
    assert len(breaks) == 1
    assert breaks[0].account == A.GROSS_PROFIT
    assert breaks[0].delta == D("80")
    # and it is left alone
    assert ledger.get(A.GROSS_PROFIT, "2025A") == D("500")


# --- STEP 13-22: the forecast ---------------------------------------------
def test_revenue_compounds_from_the_last_actual(forecast, loaded):
    base = loaded["income"].get(A.REVENUE, "2025A")
    growth = loaded["assumptions"].get("revenue_growth", "2026E")
    assert forecast.income.get(A.REVENUE, "2026E") == base * (D(1) + growth)


def test_ebit_excludes_financing(forecast):
    """STEP 15: keep EBIT separate from interest."""
    for year in forecast.periods.forecast:
        revenue = forecast.income.get(A.REVENUE, year)
        cogs = forecast.income.get(A.COGS, year)
        opex = forecast.income.get(A.OPERATING_EXPENSES, year)
        assert forecast.income.get(A.EBIT, year) == revenue - cogs - opex


def test_depreciation_is_not_capex(forecast):
    """STEP 18: 'Do not assume Depreciation = CapEx.'"""
    for year in forecast.periods.forecast:
        dep = forecast.cashflow.get(A.DEPRECIATION_AMORTIZATION, year)
        capex = abs(forecast.cashflow.get(A.CAPEX, year))
        assert dep != capex


def test_ppe_schedule_rolls_forward(forecast, loaded):
    """Ending PP&E = Beginning + CapEx - Depreciation - Disposals."""
    prior = loaded["balance"].get(A.PPE_NET, "2025A")
    for year in forecast.periods.forecast:
        row = forecast.ppe.rows[year]
        assert row.beginning == prior
        expected = row.beginning + row.additions["CapEx"] - row.reductions["Depreciation"] - row.reductions["Disposals"]
        assert row.ending == expected
        assert forecast.balance.get(A.PPE_NET, year) == row.ending
        prior = row.ending


def test_interest_is_linked_to_the_debt_schedule(forecast, loaded):
    """STEP 19: do not forecast interest independently of debt."""
    rate = loaded["assumptions"].get("interest_rate_on_debt", "2026E")
    for year in forecast.periods.forecast:
        beginning_debt = forecast.debt.beginning(year)
        assert forecast.income.get(A.INTEREST_EXPENSE, year) == beginning_debt * rate


def test_working_capital_is_built_account_by_account(forecast, loaded):
    """STEP 17: AR from DSO, inventory from days, AP from DPO."""
    assumptions = loaded["assumptions"]
    for year in forecast.periods.forecast:
        row = forecast.working_capital.rows[year]
        revenue = forecast.income.get(A.REVENUE, year)
        cogs = forecast.income.get(A.COGS, year)
        assert row.accounts_receivable == revenue * assumptions.get("dso", year) / D(365)
        assert row.inventory == cogs * assumptions.get("inventory_days", year) / D(365)
        assert row.accounts_payable == cogs * assumptions.get("dpo", year) / D(365)
        # NWC excludes cash and debt
        assert row.nwc == row.operating_current_assets - row.operating_current_liabilities


def test_nwc_excludes_cash_and_debt(forecast):
    """STEP 17: 'Normally exclude: Cash, Debt, Other financing balances.'"""
    year = forecast.periods.forecast[0]
    row = forecast.working_capital.rows[year]
    cash = forecast.balance.get(A.CASH, year)
    debt = forecast.balance.get(A.DEBT, year)
    assert cash > 0 and debt > 0
    assert row.nwc != row.nwc + cash
    assert all(acct not in (A.CASH, A.DEBT) for acct in A.OPERATING_CURRENT_ASSETS + A.OPERATING_CURRENT_LIABILITIES)


def test_balance_sheet_balances_every_forecast_year(forecast):
    """STEP 21, and the real test of STEP 6's no-plug rule."""
    for year in forecast.periods.forecast:
        assets = forecast.balance.get(A.TOTAL_ASSETS, year)
        liabilities = forecast.balance.get(A.TOTAL_LIABILITIES, year)
        equity = forecast.balance.get(A.TOTAL_EQUITY, year)
        assert assets == liabilities + equity, f"{year} out of balance"


def test_ending_cash_comes_from_the_cash_flow_statement(forecast):
    """STEP 22: ending cash must equal the projected balance sheet cash."""
    periods = forecast.periods
    for year in periods.forecast:
        prior = periods.prior(year)
        begin = forecast.balance.get(A.CASH, prior)
        flows = sum((forecast.cashflow.get(k, year) for k in (A.CFO, A.CFI, A.CFF)), D(0))
        assert forecast.balance.get(A.CASH, year) == begin + flows


def test_retained_earnings_rolls_forward(forecast):
    for year in forecast.periods.forecast:
        row = forecast.retained_earnings.rows[year]
        net_income = forecast.income.get(A.NET_INCOME, year)
        assert row.additions["Net Income"] == net_income
        assert forecast.balance.get(A.RETAINED_EARNINGS, year) == row.ending


def test_every_forecast_cell_has_a_driver(forecast):
    """STEP 37: no unintended forecast hardcodes."""
    for ledger in (forecast.income, forecast.balance, forecast.cashflow):
        assert ledger.hardcodes_in(forecast.periods.forecast) == []
        for year in forecast.periods.forecast:
            for account in ledger.accounts_present(year):
                cell = ledger.cell(account, year)
                assert cell.origin in ("forecast", "derived")
                assert cell.basis, f"{account} {year} has no stated basis"


# --- STEP 23-35: valuation ------------------------------------------------
def test_fcff_formula(fcff_years):
    """FCFF = EBIT x (1 - t) + D&A - CapEx - Change in NWC."""
    for item in fcff_years:
        expected = item.ebit * (D(1) - item.tax_rate) + item.d_and_a - item.capex - item.change_in_nwc
        assert item.fcff == expected


def test_fcff_is_read_back_out_of_the_model(fcff_years, forecast):
    """STEP 37: FCFF matches the three-statement forecast."""
    for item in fcff_years:
        terms = forecast.fcff_inputs(item.year)
        assert item.ebit == terms["ebit"]
        assert item.d_and_a == terms["d_and_a"]
        assert item.capex == terms["capex"]
        assert item.change_in_nwc == terms["change_in_nwc"]


def test_capm_and_wacc(loaded):
    coc = loaded["valuation_inputs"]["cost_of_capital"]
    assert coc.cost_of_equity == D("0.042") + D("1.10") * D("0.055")
    assert coc.after_tax_cost_of_debt == D("0.055") * (D(1) - D("0.24"))
    expected = coc.weight_equity * coc.cost_of_equity + coc.weight_debt * coc.after_tax_cost_of_debt
    assert coc.wacc == expected
    assert coc.weight_equity + coc.weight_debt == D(1)


def test_discounting_and_terminal_value(valuation, fcff_years):
    """STEP 29-32."""
    for item in valuation.discounted:
        assert item.discount_factor == D(1) / (D(1) + valuation.wacc) ** item.period
        assert item.present_value == item.fcff * item.discount_factor
    assert [d.period for d in valuation.discounted] == [1, 2, 3, 4, 5]

    assert valuation.terminal_fcff == fcff_years[-1].fcff * (D(1) + valuation.terminal_growth)
    assert valuation.terminal_value == (
        valuation.terminal_fcff / (valuation.wacc - valuation.terminal_growth)
    )
    assert valuation.pv_terminal_value == valuation.terminal_value / (D(1) + valuation.wacc) ** 5


def test_enterprise_and_equity_value(valuation):
    """STEP 33-35."""
    assert valuation.enterprise_value == valuation.pv_explicit + valuation.pv_terminal_value
    assert valuation.equity_value == (
        valuation.enterprise_value + valuation.bridge.cash - valuation.bridge.debt
    )
    assert valuation.implied_share_price == valuation.equity_value / valuation.diluted_shares


def test_bridge_lists_every_item_even_at_zero(valuation):
    """STEP 34: 'Do not silently ignore these items.'"""
    labels = [label for label, _ in valuation.bridge.lines()]
    for expected in ("Minority interest", "Preferred stock", "Pension obligations"):
        assert any(expected in label for label in labels)


def test_private_company_has_no_share_price(fcff_years, loaded):
    """STEP 35 applies to a public company; absent shares, no price is invented."""
    from model.dcf import run_dcf

    vi = loaded["valuation_inputs"]
    result = run_dcf(fcff_years, vi["cost_of_capital"], vi["terminal_growth"],
                     vi["equity_bridge"], loaded["periods"], diluted_shares=None)
    assert result.implied_share_price is None
    assert result.equity_value > 0


# --- STEP 36-37 -----------------------------------------------------------
def test_sensitivity_grid(loaded, fcff_years):
    """STEP 36: vary WACC and terminal growth; flag, don't drop, WACC <= g."""
    from model.sensitivity import sensitivity_grid

    vi = loaded["valuation_inputs"]
    grid = sensitivity_grid(
        fcff_years, vi["cost_of_capital"], vi["equity_bridge"], loaded["periods"],
        wacc_values=[D("0.06"), D("0.08")], growth_values=[D("0.02"), D("0.07")],
        diluted_shares=vi["diluted_shares"], shares_source=vi["shares_source"],
    )
    assert len(grid) == 2 and len(grid[0]) == 2
    # WACC 0.06 vs g 0.07 violates STEP 31 and is reported as such
    assert grid[0][1].enterprise_value is None
    assert "STEP 31" in grid[0][1].note
    # value falls as WACC rises, at constant g
    assert grid[1][0].enterprise_value < grid[0][0].enterprise_value


def test_all_checks_pass_on_a_sound_model(forecast, fcff_years, valuation):
    results = run_all_checks(forecast, fcff_years, valuation)
    assert len(results) == 12
    failures = [r.line() for r in results if r.status is not Status.PASS]
    assert failures == [], f"expected all 12 to pass: {failures}"


def test_a_broken_balance_sheet_fails_rather_than_being_plugged(forecast, fcff_years, valuation):
    """STEP 6: 'Do not use a plug simply to force the model to balance.'"""
    import copy

    broken = copy.deepcopy(forecast)
    year = broken.periods.forecast[0]
    broken.balance.set_forecast(A.CASH, year, broken.balance.get(A.CASH, year) + D("50"), "deliberate corruption")
    broken.balance.set_derived(A.TOTAL_ASSETS, year, broken.balance.get(A.TOTAL_ASSETS, year) + D("50"), "corrupted")

    results = run_all_checks(broken, fcff_years, valuation)
    by_name = {r.name: r for r in results}
    assert by_name["Forecast balance sheet balances"].status is Status.FAIL
    assert "50" in by_name["Forecast balance sheet balances"].detail
    assert by_name["Forecast cash flow reconciliation"].status is Status.FAIL


def test_a_missing_input_skips_rather_than_passes(forecast, fcff_years, valuation):
    """A check that cannot run reports SKIP. A silent PASS would be worse."""
    import copy
    from model.accounts import Statement
    from model.statements import Ledger

    stripped = copy.deepcopy(forecast)
    stripped.balance = Ledger(Statement.BALANCE, stripped.periods.all_years)  # empty
    results = {r.name: r for r in run_all_checks(stripped, fcff_years, valuation)}
    assert results["Historical balance sheet balances"].status is Status.SKIP
    assert results["PP&E schedule linkage"].status is Status.SKIP
