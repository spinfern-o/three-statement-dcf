"""The workflow's negative instructions, as executable tests.

Each test names the step it enforces. These are the tests that matter most:
the engine's value is that it stops, and a refusal that silently stopped
working would be invisible in the output of a passing model.
"""

from __future__ import annotations

import pytest

from model.assumptions import Assumption, Assumptions, Basis, Conflict
from model.dcf import CostOfCapital, EquityBridge, FCFFYear, run_dcf
from model.numeric import D
from model.profile import CompanyProfile, Periods, Units
from model.provenance import Figure, ProvenanceError, Source
from model.schedules import TaxSchedule, debt_schedule


def test_step4_figure_requires_line_item():
    """STEP 4: every hardcoded figure records its reported line-item name."""
    with pytest.raises(ProvenanceError, match="line_item"):
        Source(document="10-K", page=42, line_item="")


def test_step4_figure_requires_numeric_value():
    src = Source("10-K", 42, "Total revenues")
    with pytest.raises(ProvenanceError):
        Figure(None, "2025A", src)


def test_a_float_cannot_enter_the_calculation_path():
    """Specification 1.15 and 4.4: no binary floating point in the engine.

    A float is refused rather than converted, because converting one
    preserves its error instead of removing it.
    """
    src = Source("10-K", 42, "Total revenues")
    with pytest.raises(ProvenanceError, match="float"):
        Figure(1234.5, "2025A", src)


def test_step1_units_must_be_declared():
    """STEP 1: dollars vs thousands vs millions is a 1000x error if guessed."""
    with pytest.raises(ProvenanceError, match="units"):
        CompanyProfile("Co", "FY2025", "Dec 31", "USD", "millions", True)


def test_step3_no_invented_historical_years():
    """STEP 3: 'Do not invent missing historical years.'"""
    with pytest.raises(ProvenanceError):
        Periods(("2023A", "2025A"), ("2026E",))  # 2024A silently absent


def test_step12_forecast_must_follow_last_actual():
    """A gap between actual and forecast would skip a year of compounding."""
    with pytest.raises(ProvenanceError, match="compounding"):
        Periods(("2024A", "2025A"), ("2027E", "2028E"))


def test_step10_assumption_requires_source():
    """STEP 10: 'Every forecast assumption must have a visible source.'"""
    with pytest.raises(ProvenanceError, match="visible source"):
        Assumption("revenue_growth", "0.08", Basis.MODEL_ASSUMPTION, "   ")


def test_step10_undeclared_driver_is_an_error_not_a_zero():
    """A driver nobody set is a question to answer, never a default."""
    assumptions = Assumptions()
    with pytest.raises(ProvenanceError, match="declared"):
        assumptions.get("cogs_pct_revenue", "2026E")


def test_step10_duplicate_assumption_rejected():
    assumptions = Assumptions()
    assumptions.add(Assumption("tax_rate", "0.24", Basis.COMPANY_GUIDANCE, "10-K p.72"))
    with pytest.raises(ProvenanceError, match="Duplicate"):
        assumptions.add(Assumption("tax_rate", "0.21", Basis.MODEL_ASSUMPTION, "guess"))


def test_step11_conflict_must_choose_a_recorded_source():
    """STEP 11: explicitly choose which source the model uses."""
    with pytest.raises(ProvenanceError, match="chosen"):
        Conflict("capex", "10-K", "2026-02-01", "120", "Deck", "2026-03-15", "140",
                 chosen="A third source", rationale="because")


def test_step8_schedule_refuses_to_break_its_chain():
    """STEP 8: a roll-forward that does not chain is an error, not a rounding."""
    debt = debt_schedule()
    debt.add_year("2026E", "300", {"New Borrowing": "0"}, {"Repayment": "50"})
    with pytest.raises(ProvenanceError, match="does not equal"):
        debt.add_year("2027E", "999")


def test_step16_tax_basis_must_be_stated():
    """STEP 16: state whether the rate is statutory, historical or normalized."""
    with pytest.raises(ProvenanceError, match="STEP 16"):
        TaxSchedule(basis="whatever", rate_by_year={"2026E": "0.24"})


def test_step25_cost_of_capital_requires_sources():
    """STEP 25-27: these cannot be derived from the financial statements."""
    with pytest.raises(ProvenanceError, match="explicit source"):
        CostOfCapital("0.042", "1.1", "0.055", "0.055", "0.24", "4000", "1000", sources={})


def test_step27_market_equity_cannot_be_zero_or_negative():
    """STEP 27: do not automatically use book equity for market cap."""
    sources = dict.fromkeys(CostOfCapital.REQUIRED_SOURCES, "stated")
    with pytest.raises(ProvenanceError, match="market_value_equity"):
        CostOfCapital("0.042", "1.1", "0.055", "0.055", "0.24", "0", "1000", sources)


def test_step31_wacc_must_exceed_terminal_growth(loaded):
    """STEP 31: 'The model must satisfy: WACC > Terminal Growth Rate.'"""
    periods = Periods(("2024A", "2025A"), ("2026E",))
    sources = dict.fromkeys(CostOfCapital.REQUIRED_SOURCES, "stated")
    coc = CostOfCapital("0.042", "1.1", "0.055", "0.055", "0.24", "4000", "1000", sources)
    years = [FCFFYear("2026E", D("200"), D("0.24"), D("80"), D("100"), D("15"))]
    with pytest.raises(ProvenanceError, match="must exceed"):
        run_dcf(years, coc, terminal_growth=D("0.50"), bridge=EquityBridge("0", "0"), periods=periods)


def test_step35_share_count_requires_a_source():
    """STEP 35: state the source and date for diluted shares outstanding."""
    periods = Periods(("2024A", "2025A"), ("2026E",))
    sources = dict.fromkeys(CostOfCapital.REQUIRED_SOURCES, "stated")
    coc = CostOfCapital("0.042", "1.1", "0.055", "0.055", "0.24", "4000", "1000", sources)
    years = [FCFFYear("2026E", D("200"), D("0.24"), D("80"), D("100"), D("15"))]
    with pytest.raises(ProvenanceError, match="source and date"):
        run_dcf(years, coc, D("0.025"), EquityBridge("0", "0"), periods, diluted_shares=D("100"), shares_source="")


# --- regressions for bugs found after the Decimal port --------------------
def test_f6_tolerance_flags_accept_a_decimal_string():
    """--rel-tol / --abs-tol crashed on every use.

    argparse declared them type=float, and D() refuses floats by design
    (1.15, 4.4), so the documented override mechanism raised PrecisionError
    after printing the whole report.
    """
    import subprocess
    import sys
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parent.parent
    ok = subprocess.run(
        [sys.executable, "run_model.py", "--inputs", "tests/fixtures", "--rel-tol", "1e-8"],
        cwd=root, capture_output=True, text=True,
    )
    assert ok.returncode == 0, ok.stderr
    assert "PrecisionError" not in ok.stderr

    bad = subprocess.run(
        [sys.executable, "run_model.py", "--inputs", "tests/fixtures", "--rel-tol", "banana"],
        cwd=root, capture_output=True, text=True,
    )
    assert bad.returncode == 2, "an unparseable tolerance should exit 2, not traceback"
    assert "Traceback" not in bad.stderr


def test_f7a_shifting_wacc_refuses_rather_than_missing_its_target():
    """With beta zero no equity risk premium reaches the target WACC.

    Returning the unshifted cost of capital labelled the sensitivity cell
    with a WACC it did not have.
    """
    from decimal import Decimal

    from model.dcf import CostOfCapital
    from model.sensitivity import _shift_wacc

    sources = dict.fromkeys(CostOfCapital.REQUIRED_SOURCES, "test")
    base = CostOfCapital("0.04", "0", "0.06", "0.05", "0.25", "1000", "200", sources)
    with pytest.raises(ProvenanceError, match="beta is zero"):
        _shift_wacc(base, Decimal("0.12"))

    # a non-zero beta still hits the target exactly
    ok = CostOfCapital("0.04", "1.1", "0.06", "0.05", "0.25", "1000", "200", sources)
    assert _shift_wacc(ok, Decimal("0.12")).wacc == Decimal("0.12")


def test_f7b_report_survives_an_undefined_terminal_value_share():
    """tv_share_of_ev returns None to avoid dividing by zero (17.27).

    Its only consumer formatted it with :.1%, which raises on None -- so the
    guard turned a division error into a formatting error.
    """
    from decimal import Decimal

    from model import report
    from model.dcf import EquityBridge, Valuation
    from model.profile import Periods

    valuation = Valuation(
        Periods(("2024A", "2025A"), ("2026E",)), [], Decimal("0.02"), Decimal("0.1"),
        Decimal(0), Decimal(0), Decimal(0), Decimal(0), Decimal(0),
        EquityBridge("0", "0"), None, None,
    )
    assert valuation.tv_share_of_ev is None
    text = report.valuation_block(valuation)  # must not raise
    assert "undefined" in text


def test_f7c_dividends_reject_two_declared_methods():
    """Every other driver rejects declaring both a ratio and an amount.

    Dividends silently preferred the amount.
    """
    from model.accounts import Statement
    from model.assumptions import Assumption, Assumptions, Basis
    from model.forecast import build_forecast
    from model.profile import Periods
    from model.schedules import TaxSchedule
    from model.statements import Ledger

    periods = Periods(("2024A", "2025A"), ("2026E",))
    src = Source("FIXTURE", 1, "line")
    income = Ledger(Statement.INCOME, periods.historical)
    balance = Ledger(Statement.BALANCE, periods.historical)
    cashflow = Ledger(Statement.CASHFLOW, periods.historical)
    for year in periods.historical:
        income.set_reported("revenue", year, Figure("1000", year, src))
        income.set_reported("cogs", year, Figure("500", year, src))
        income.set_reported("operating_expenses", year, Figure("200", year, src))
        for acct, value in (
            ("cash", "100"), ("accounts_receivable", "100"), ("inventory", "50"),
            ("other_current_assets", "10"), ("ppe_net", "500"), ("other_noncurrent_assets", "40"),
            ("accounts_payable", "60"), ("other_current_liabilities", "30"),
            ("debt", "200"), ("other_noncurrent_liabilities", "10"),
            ("common_equity", "200"), ("retained_earnings", "300"),
        ):
            balance.set_reported(acct, year, Figure(value, year, src))
    for ledger in (income, balance, cashflow):
        ledger.fill_derivable()

    assumptions = Assumptions()

    def add(name, value, year=None):
        assumptions.add(Assumption(name, value, Basis.MODEL_ASSUMPTION, "test", year))

    for name, value in (
        ("revenue_growth", "0.05"), ("cogs_pct_revenue", "0.5"), ("opex_pct_revenue", "0.2"),
        ("dso", "36.5"), ("inventory_days", "36.5"), ("dpo", "36.5"),
        ("other_current_assets_pct_revenue", "0.01"),
        ("other_current_liabilities_pct_revenue", "0.03"),
        ("depreciation_pct_beginning_ppe", "0.1"), ("capex_pct_revenue", "0.1"),
        ("interest_rate_on_debt", "0.05"),
        ("dividend_payout_ratio", "0.1"), ("dividends_amount", "5"),
    ):
        add(name, value)
    taxes = TaxSchedule("statutory", {"2026E": "0.25"})

    with pytest.raises(ProvenanceError, match="both"):
        build_forecast(periods, income, balance, cashflow, assumptions, taxes)


def test_units_multiplier_values_are_pinned():
    """Unused today, load-bearing the moment 2.3.a permits a second document."""

    assert Units.DOLLARS.multiplier == 1
    assert Units.THOUSANDS.multiplier == 1_000
    assert Units.MILLIONS.multiplier == 1_000_000
