"""The workflow's negative instructions, as executable tests.

Each test names the step it enforces. These are the tests that matter most:
the engine's value is that it stops, and a refusal that silently stopped
working would be invisible in the output of a passing model.
"""

from __future__ import annotations

import pytest

from model.assumptions import Assumption, Assumptions, Basis, Conflict
from model.dcf import CostOfCapital, EquityBridge, FCFFYear, run_dcf
from model.profile import CompanyProfile, Periods, Units
from model.numeric import D
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
    sources = {k: "stated" for k in CostOfCapital.REQUIRED_SOURCES}
    with pytest.raises(ProvenanceError, match="market_value_equity"):
        CostOfCapital("0.042", "1.1", "0.055", "0.055", "0.24", "0", "1000", sources)


def test_step31_wacc_must_exceed_terminal_growth(loaded):
    """STEP 31: 'The model must satisfy: WACC > Terminal Growth Rate.'"""
    periods = Periods(("2024A", "2025A"), ("2026E",))
    sources = {k: "stated" for k in CostOfCapital.REQUIRED_SOURCES}
    coc = CostOfCapital("0.042", "1.1", "0.055", "0.055", "0.24", "4000", "1000", sources)
    years = [FCFFYear("2026E", D("200"), D("0.24"), D("80"), D("100"), D("15"))]
    with pytest.raises(ProvenanceError, match="must exceed"):
        run_dcf(years, coc, terminal_growth=D("0.50"), bridge=EquityBridge("0", "0"), periods=periods)


def test_step35_share_count_requires_a_source():
    """STEP 35: state the source and date for diluted shares outstanding."""
    periods = Periods(("2024A", "2025A"), ("2026E",))
    sources = {k: "stated" for k in CostOfCapital.REQUIRED_SOURCES}
    coc = CostOfCapital("0.042", "1.1", "0.055", "0.055", "0.24", "4000", "1000", sources)
    years = [FCFFYear("2026E", D("200"), D("0.24"), D("80"), D("100"), D("15"))]
    with pytest.raises(ProvenanceError, match="source and date"):
        run_dcf(years, coc, D("0.025"), EquityBridge("0", "0"), periods, diluted_shares=D("100"), shares_source="")
