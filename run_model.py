#!/usr/bin/env python3
"""Build the model end to end and print the report.

    python3 run_model.py                      # reads ./inputs
    python3 run_model.py --inputs path/to/dir
    python3 run_model.py --sensitivity equity_value

Exit status is 1 if any STEP 37 check fails, so this is usable in CI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model import report
from model.accounts import (
    BALANCE_ACCOUNTS,
    CASHFLOW_ACCOUNTS,
    INCOME_ACCOUNTS,
    Statement,
)
from model.checks import DEFAULT_ABS_TOL, DEFAULT_REL_TOL, Status, Tolerance, run_all_checks
from model.dcf import build_fcff, run_dcf
from model.disclaimer import block as disclaimer_block
from model.forecast import build_forecast
from model.loader import load_assumptions, load_historical, load_profile, load_valuation
from model.numeric import PrecisionError
from model.provenance import ProvenanceError
from model.sensitivity import sensitivity_grid


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--inputs", type=Path, default=Path("inputs"), help="directory holding the four input files")
    parser.add_argument(
        "--rel-tol", type=str, default=None,
        help=f"relative tolerance for the STEP 37 checks, as a decimal string "
             f"(default {DEFAULT_REL_TOL:.0e})",
    )
    parser.add_argument(
        "--abs-tol", type=str, default=None,
        help="absolute floor for near-zero accounts; raise only to absorb a filing's own rounding",
    )
    parser.add_argument(
        "--sensitivity",
        choices=("implied_share_price", "equity_value", "enterprise_value"),
        default="implied_share_price",
        help="which metric the STEP 36 table reports",
    )
    args = parser.parse_args(argv)

    try:
        profile, source_map, periods = load_profile(args.inputs / "company_profile.yaml")
        ledgers = load_historical(args.inputs / "raw_historical.yaml", periods)
        assumptions, taxes, segments = load_assumptions(args.inputs / "assumptions.yaml", periods)
        valuation_inputs = load_valuation(args.inputs / "valuation.yaml")

        forecast = build_forecast(
            periods=periods,
            historical_income=ledgers[Statement.INCOME],
            historical_balance=ledgers[Statement.BALANCE],
            historical_cashflow=ledgers[Statement.CASHFLOW],
            assumptions=assumptions,
            taxes=taxes,
            segments=segments or None,
        )
        fcff_years = build_fcff(forecast)
        valuation = run_dcf(
            fcff_years=fcff_years,
            cost_of_capital=valuation_inputs["cost_of_capital"],
            terminal_growth=valuation_inputs["terminal_growth"],
            bridge=valuation_inputs["equity_bridge"],
            periods=periods,
            diluted_shares=valuation_inputs["diluted_shares"],
            shares_source=valuation_inputs["shares_source"],
        )
    except (ProvenanceError, PrecisionError) as exc:
        print(f"\nMODEL HALTED\n{report.rule()}\n{exc}\n", file=sys.stderr)
        print("The workflow stops rather than substituting a value. Fix the input and re-run.", file=sys.stderr)
        return 2

    years = periods.all_years
    print(report.profile_block(profile, source_map, periods))
    print(report.assumptions_block(assumptions))
    print(report.statement_block("INCOME STATEMENT (STEP 5, 20)", forecast.income, INCOME_ACCOUNTS, years))
    print(report.statement_block("BALANCE SHEET (STEP 6, 21)", forecast.balance, BALANCE_ACCOUNTS, years))
    print(report.statement_block("CASH FLOW STATEMENT (STEP 7, 22)", forecast.cashflow, CASHFLOW_ACCOUNTS, years))
    print(report.schedules_block(forecast))
    print(report.fcff_block(fcff_years))
    print(report.wacc_block(valuation_inputs["cost_of_capital"]))
    print(report.valuation_block(valuation))

    wacc_values = valuation_inputs["sensitivity_wacc"]
    growth_values = valuation_inputs["sensitivity_growth"]
    if wacc_values and growth_values:
        grid = sensitivity_grid(
            fcff_years=fcff_years,
            base_cost_of_capital=valuation_inputs["cost_of_capital"],
            bridge=valuation_inputs["equity_bridge"],
            periods=periods,
            wacc_values=wacc_values,
            growth_values=growth_values,
            diluted_shares=valuation_inputs["diluted_shares"],
            shares_source=valuation_inputs["shares_source"],
        )
        print(report.sensitivity_block(grid, args.sensitivity))

    # Parsed as strings, not floats: D() refuses floats (1.15, 4.4), so
    # argparse type=float made these flags raise on every use.
    try:
        tolerance = Tolerance(
            rel=DEFAULT_REL_TOL if args.rel_tol is None else args.rel_tol,
            abs=DEFAULT_ABS_TOL if args.abs_tol is None else args.abs_tol,
        )
    except (ProvenanceError, PrecisionError) as exc:
        print(f"\n{report.rule()}\n{exc}\n", file=sys.stderr)
        return 2
    results = run_all_checks(forecast, fcff_years, valuation, tolerance)
    print(report.checks_block(results, tolerance))

    # Section 25: "Do not bury this only in Terms. Show it in the model,
    # release flow, and exports." A CLI report IS the model for whoever runs
    # it, and this was the surface that had none.
    print()
    print(disclaimer_block())

    return 1 if any(r.status is Status.FAIL for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
