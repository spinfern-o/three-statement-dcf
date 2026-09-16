"""Shared fixtures. All test data is fictional -- see tests/fixtures/."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"
INPUTS = ROOT / "inputs"


@pytest.fixture(scope="session")
def loaded():
    from model.accounts import Statement
    from model.loader import load_assumptions, load_historical, load_profile, load_valuation

    profile, source_map, periods = load_profile(FIXTURES / "company_profile.yaml")
    ledgers = load_historical(FIXTURES / "raw_historical.yaml", periods)
    assumptions, taxes, segments = load_assumptions(FIXTURES / "assumptions.yaml", periods)
    valuation_inputs = load_valuation(FIXTURES / "valuation.yaml")
    return {
        "profile": profile,
        "source_map": source_map,
        "periods": periods,
        "income": ledgers[Statement.INCOME],
        "balance": ledgers[Statement.BALANCE],
        "cashflow": ledgers[Statement.CASHFLOW],
        "assumptions": assumptions,
        "taxes": taxes,
        "segments": segments,
        "valuation_inputs": valuation_inputs,
    }


@pytest.fixture(scope="session")
def forecast(loaded):
    from model.forecast import build_forecast

    return build_forecast(
        periods=loaded["periods"],
        historical_income=loaded["income"],
        historical_balance=loaded["balance"],
        historical_cashflow=loaded["cashflow"],
        assumptions=loaded["assumptions"],
        taxes=loaded["taxes"],
        segments=loaded["segments"] or None,
    )


@pytest.fixture(scope="session")
def fcff_years(forecast):
    from model.dcf import build_fcff

    return build_fcff(forecast)


@pytest.fixture(scope="session")
def valuation(fcff_years, loaded):
    from model.dcf import run_dcf

    vi = loaded["valuation_inputs"]
    return run_dcf(
        fcff_years=fcff_years,
        cost_of_capital=vi["cost_of_capital"],
        terminal_growth=vi["terminal_growth"],
        bridge=vi["equity_bridge"],
        periods=loaded["periods"],
        diluted_shares=vi["diluted_shares"],
        shares_source=vi["shares_source"],
    )
