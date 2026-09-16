"""STEP 36: DCF sensitivity tables across WACC and terminal growth."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .dcf import CostOfCapital, EquityBridge, FCFFYear, run_dcf
from .profile import Periods
from .provenance import ProvenanceError


@dataclass(frozen=True)
class SensitivityCell:
    wacc: float
    terminal_growth: float
    enterprise_value: float | None
    equity_value: float | None
    implied_share_price: float | None
    note: str = ""


def sensitivity_grid(
    fcff_years: list[FCFFYear],
    base_cost_of_capital: CostOfCapital,
    bridge: EquityBridge,
    periods: Periods,
    wacc_values: list[float],
    growth_values: list[float],
    diluted_shares: float | None = None,
    shares_source: str | None = None,
) -> list[list[SensitivityCell]]:
    """Rows are WACC, columns are terminal growth.

    Combinations violating WACC > g (STEP 31) are returned as cells with a
    note rather than omitted, so the table shows why a corner is empty.
    """

    if not wacc_values or not growth_values:
        raise ProvenanceError("STEP 36 requires at least one WACC and one terminal growth value")

    grid: list[list[SensitivityCell]] = []
    for w in wacc_values:
        row: list[SensitivityCell] = []
        for g in growth_values:
            if w <= g:
                row.append(SensitivityCell(w, g, None, None, None, "n/a: WACC <= g (STEP 31)"))
                continue
            shifted = _shift_wacc(base_cost_of_capital, w)
            valuation = run_dcf(
                fcff_years, shifted, g, bridge, periods, diluted_shares, shares_source
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


def _shift_wacc(base: CostOfCapital, target_wacc: float) -> CostOfCapital:
    """Produce a CostOfCapital whose .wacc is exactly `target_wacc`.

    The grid varies the discount rate as a rate, which is what STEP 36 asks
    for. Rather than inventing a beta that would back into the target, the
    shift is applied to the cost of equity and labeled as such in `sources`.
    """
    we = base.weight_equity
    if we <= 0:
        raise ProvenanceError("Cannot shift WACC with zero equity weight")
    implied_ke = (target_wacc - base.weight_debt * base.after_tax_cost_of_debt) / we
    implied_erp = (implied_ke - base.risk_free_rate) / base.beta if base.beta else 0.0
    sources = dict(base.sources)
    sources["equity_risk_premium"] = (
        f"{sources.get('equity_risk_premium', '')} [sensitivity: solved so WACC = {target_wacc:.4f}]"
    ).strip()
    return replace(base, equity_risk_premium=implied_erp, sources=sources)
