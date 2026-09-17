"""STEP 36: DCF sensitivity tables across WACC and terminal growth."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from .dcf import CostOfCapital, EquityBridge, FCFFYear, run_dcf
from .numeric import D, ZERO
from .profile import Periods
from .provenance import ProvenanceError


@dataclass(frozen=True)
class SensitivityCell:
    wacc: Decimal
    terminal_growth: Decimal
    enterprise_value: Decimal | None
    equity_value: Decimal | None
    implied_share_price: Decimal | None
    note: str = ""


def sensitivity_grid(
    fcff_years: list[FCFFYear],
    base_cost_of_capital: CostOfCapital,
    bridge: EquityBridge,
    periods: Periods,
    wacc_values: list[Decimal],
    growth_values: list[Decimal],
    diluted_shares: Decimal | None = None,
    shares_source: str | None = None,
    schedule=None,
) -> list[list[SensitivityCell]]:
    """Rows are WACC, columns are terminal growth.

    `schedule` carries 16.11's timing convention through to every cell. A grid
    discounted on a different convention from the valuation it surrounds is not
    a sensitivity of that valuation, and the difference is roughly half a year
    of discounting on every number in it.

    Combinations violating WACC > g (STEP 31) are returned as cells with a
    note rather than omitted, so the table shows why a corner is empty.
    """

    if not wacc_values or not growth_values:
        raise ProvenanceError("STEP 36 requires at least one WACC and one terminal growth value")

    wacc_values = [D(w, what="sensitivity wacc") for w in wacc_values]
    growth_values = [D(g, what="sensitivity terminal_growth") for g in growth_values]

    grid: list[list[SensitivityCell]] = []
    for w in wacc_values:
        row: list[SensitivityCell] = []
        for g in growth_values:
            if w <= g:
                row.append(SensitivityCell(w, g, None, None, None, "n/a: WACC <= g (STEP 31)"))
                continue
            shifted = _shift_wacc(base_cost_of_capital, w)
            valuation = run_dcf(
                fcff_years, shifted, g, bridge, periods, diluted_shares,
                shares_source, schedule,
            )
            row.append(
                SensitivityCell(
                    wacc=w,
                    terminal_growth=g,
                    enterprise_value=valuation.enterprise_value,
                    equity_value=valuation.equity_value,
                    implied_share_price=valuation.implied_share_price,
                )
            )
        grid.append(row)
    return grid


def _shift_wacc(base: CostOfCapital, target_wacc: Decimal) -> CostOfCapital:
    """Produce a CostOfCapital whose .wacc is exactly `target_wacc`.

    The grid varies the discount rate as a rate, which is what STEP 36 asks
    for. Rather than inventing a beta that would back into the target, the
    shift is applied to the cost of equity and labeled as such in `sources`.
    """
    we = base.weight_equity
    if we <= 0:
        raise ProvenanceError("Cannot shift WACC with zero equity weight")
    if base.beta == 0:
        # With beta zero, CAPM gives cost of equity = risk-free rate whatever
        # the equity risk premium, so no ERP reaches the target. Returning the
        # unshifted cost of capital would label the cell with a WACC it does
        # not have, which is worse than refusing (specification 1.19: never
        # present a figure as something it is not).
        raise ProvenanceError(
            f"Cannot shift WACC to {target_wacc} by solving the equity risk premium: "
            f"beta is zero, so the cost of equity is the risk-free rate regardless "
            f"of the premium. Vary the risk-free rate or supply a non-zero beta."
        )
    implied_ke = (target_wacc - base.weight_debt * base.after_tax_cost_of_debt) / we
    implied_erp = (implied_ke - base.risk_free_rate) / base.beta
    sources = dict(base.sources)
    sources["equity_risk_premium"] = (
        f"{sources.get('equity_risk_premium', '')} [sensitivity: solved so WACC = {target_wacc:.4f}]"
    ).strip()
    return replace(base, equity_risk_premium=implied_erp, sources=sources)
