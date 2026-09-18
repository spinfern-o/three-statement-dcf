"""STEP 23-35: FCFF, WACC, terminal value, and the bridge to per-share value.

FCFF is read back out of the completed three-statement forecast rather than
assembled from loose inputs, which is what STEP 37's final check ("FCFF
matches the three-statement forecast") is testing for.

Cost of capital inputs are deliberately NOT derivable from the statements.
STEP 25 says so outright for the CAPM terms, and STEP 27 warns against
using book equity as market capitalization, so `CostOfCapital` takes market
values as explicit, separately sourced inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .forecast import ForecastResult
from .numeric import ONE, ZERO, D
from .profile import Periods
from .provenance import ProvenanceError
from .timing import Schedule, Timing, build_schedule, discount_factor


@dataclass(frozen=True)
class FCFFYear:
    """STEP 24: one forecast year's free cash flow to the firm."""

    year: str
    ebit: Decimal
    tax_rate: Decimal
    d_and_a: Decimal
    capex: Decimal
    change_in_nwc: Decimal

    @property
    def nopat(self) -> Decimal:
        """STEP 16: NOPAT = EBIT x (1 - Tax Rate)."""
        return self.ebit * (ONE - self.tax_rate)

    @property
    def fcff(self) -> Decimal:
        """STEP 23: NOPAT + D&A - CapEx - Change in NWC."""
        return self.nopat + self.d_and_a - self.capex - self.change_in_nwc

    def explain(self) -> str:
        return (
            f"{self.ebit:,.1f} x (1 - {self.tax_rate:.4f}) + {self.d_and_a:,.1f} "
            f"- {self.capex:,.1f} - {self.change_in_nwc:,.1f} = {self.fcff:,.1f}"
        )


def build_fcff(forecast: ForecastResult) -> list[FCFFYear]:
    """STEP 24: repeat the FCFF calculation independently for every year."""
    out = []
    for year in forecast.periods.forecast:
        terms = forecast.fcff_inputs(year)
        out.append(
            FCFFYear(
                year=year,
                ebit=terms["ebit"],
                tax_rate=terms["tax_rate"],
                d_and_a=terms["d_and_a"],
                capex=terms["capex"],
                change_in_nwc=terms["change_in_nwc"],
            )
        )
    return out


@dataclass(frozen=True)
class CostOfCapital:
    """STEP 25-28. Every input is externally sourced and separately stated."""

    risk_free_rate: Decimal
    beta: Decimal
    equity_risk_premium: Decimal
    pretax_cost_of_debt: Decimal
    tax_rate: Decimal
    market_value_equity: Decimal
    market_value_debt: Decimal
    sources: dict[str, str] = field(default_factory=dict)

    REQUIRED_SOURCES = (
        "risk_free_rate",
        "beta",
        "equity_risk_premium",
        "pretax_cost_of_debt",
        "market_value_equity",
        "market_value_debt",
    )

    def __post_init__(self) -> None:
        for name in ("risk_free_rate", "beta", "equity_risk_premium", "pretax_cost_of_debt",
                     "tax_rate", "market_value_equity", "market_value_debt"):
            object.__setattr__(self, name, D(getattr(self, name), what=f"CostOfCapital.{name}"))
        if self.market_value_equity <= 0:
            raise ProvenanceError(
                "market_value_equity must be positive. STEP 27: use market values -- "
                "do not automatically use book equity for market capitalization."
            )
        if self.market_value_debt < 0:
            raise ProvenanceError("market_value_debt cannot be negative (STEP 27)")
        if not 0 <= self.tax_rate < 1:
            raise ProvenanceError(f"tax_rate must be a decimal in [0, 1), got {self.tax_rate!r}")
        missing = [k for k in self.REQUIRED_SOURCES if not self.sources.get(k, "").strip()]
        if missing:
            raise ProvenanceError(
                "STEP 25-27 require an explicit source for each cost-of-capital input. "
                f"Missing sources for: {', '.join(missing)}. "
                "These cannot be derived from the financial statements."
            )

    @property
    def cost_of_equity(self) -> Decimal:
        """STEP 25 (CAPM): Rf + Beta x ERP."""
        return self.risk_free_rate + self.beta * self.equity_risk_premium

    @property
    def after_tax_cost_of_debt(self) -> Decimal:
        """STEP 26: pre-tax cost of debt x (1 - tax rate)."""
        return self.pretax_cost_of_debt * (ONE - self.tax_rate)

    @property
    def total_capital(self) -> Decimal:
        return self.market_value_equity + self.market_value_debt

    @property
    def weight_equity(self) -> Decimal:
        return self.market_value_equity / self.total_capital

    @property
    def weight_debt(self) -> Decimal:
        return self.market_value_debt / self.total_capital

    @property
    def wacc(self) -> Decimal:
        """STEP 28: E/(D+E) x Ke + D/(D+E) x Kd x (1 - t)."""
        return self.weight_equity * self.cost_of_equity + self.weight_debt * self.after_tax_cost_of_debt

    def explain(self) -> str:
        return (
            f"Ke = {self.risk_free_rate:.4f} + {self.beta:.3f} x {self.equity_risk_premium:.4f} "
            f"= {self.cost_of_equity:.4f}\n"
            f"Kd(after tax) = {self.pretax_cost_of_debt:.4f} x (1 - {self.tax_rate:.4f}) "
            f"= {self.after_tax_cost_of_debt:.4f}\n"
            f"WACC = {self.weight_equity:.4f} x {self.cost_of_equity:.4f} + "
            f"{self.weight_debt:.4f} x {self.after_tax_cost_of_debt:.4f} = {self.wacc:.4f}"
        )


@dataclass(frozen=True)
class DiscountedYear:
    """STEP 29 requires these four shown separately, not collapsed."""

    year: str
    fcff: Decimal
    #: The time fraction t. A whole number under the year-end convention, and
    #: a fraction under mid-year or exact dates (16.11, 16.12). Stored as a
    #: Decimal so the three conventions share one field rather than one
    #: field each.
    period: Decimal
    discount_factor: Decimal

    @property
    def present_value(self) -> Decimal:
        return self.fcff * self.discount_factor


@dataclass(frozen=True)
class EquityBridge:
    """STEP 34. Non-operating items are listed, never silently ignored."""

    cash: Decimal
    debt: Decimal
    non_operating_investments: Decimal = ZERO
    minority_interest: Decimal = ZERO
    preferred_stock: Decimal = ZERO
    pension_obligations: Decimal = ZERO
    other_claims: Decimal = ZERO

    def __post_init__(self) -> None:
        for name in ("cash", "debt", "non_operating_investments", "minority_interest",
                     "preferred_stock", "pension_obligations", "other_claims"):
            object.__setattr__(self, name, D(getattr(self, name), what=f"EquityBridge.{name}"))

    def apply(self, enterprise_value: Decimal) -> Decimal:
        return (
            enterprise_value
            + self.cash
            - self.debt
            + self.non_operating_investments
            - self.minority_interest
            - self.preferred_stock
            - self.pension_obligations
            - self.other_claims
        )

    def lines(self) -> list[tuple[str, Decimal]]:
        return [
            ("+ Cash", self.cash),
            ("- Debt", -self.debt),
            ("+ Non-operating investments", self.non_operating_investments),
            ("- Minority interest", -self.minority_interest),
            ("- Preferred stock", -self.preferred_stock),
            ("- Pension obligations", -self.pension_obligations),
            ("- Other claims", -self.other_claims),
        ]


@dataclass
class Valuation:
    periods: Periods
    discounted: list[DiscountedYear]
    terminal_growth: Decimal
    wacc: Decimal
    terminal_fcff: Decimal
    terminal_value: Decimal
    pv_terminal_value: Decimal
    enterprise_value: Decimal
    equity_value: Decimal
    bridge: EquityBridge
    diluted_shares: Decimal | None
    shares_source: str | None

    @property
    def pv_explicit(self) -> Decimal:
        return sum((d.present_value for d in self.discounted), ZERO)

    @property
    def implied_share_price(self) -> Decimal | None:
        """STEP 35. None when the company is not public / shares not supplied."""
        if self.diluted_shares is None:
            return None
        return self.equity_value / self.diluted_shares

    @property
    def tv_share_of_ev(self) -> Decimal | None:
        """None rather than NaN when enterprise value is zero (17.27)."""
        if self.enterprise_value == 0:
            return None
        return self.pv_terminal_value / self.enterprise_value


def run_dcf(
    fcff_years: list[FCFFYear],
    cost_of_capital: CostOfCapital,
    terminal_growth: Decimal,
    bridge: EquityBridge,
    periods: Periods,
    diluted_shares: Decimal | None = None,
    shares_source: str | None = None,
    schedule: Schedule | None = None,
) -> Valuation:
    """STEP 29-35.

    `schedule` carries 16.11's timing convention. Omitted, it is built as
    year-end -- t = 1, 2, 3 -- which is STEP 29's convention and reproduces
    every discount factor this function produced before the option existed.
    A model only leaves that path by asking to.
    """

    wacc = cost_of_capital.wacc
    terminal_growth = D(terminal_growth, what="terminal_growth")
    if diluted_shares is not None:
        diluted_shares = D(diluted_shares, what="diluted_shares")

    # STEP 31: "The model must satisfy: WACC > Terminal Growth Rate."
    if wacc <= terminal_growth:
        raise ProvenanceError(
            f"WACC ({wacc:.4f}) must exceed the terminal growth rate ({terminal_growth:.4f}) "
            "(STEP 31). Below that, the perpetual-growth formula returns a negative or "
            "infinite terminal value and the valuation is meaningless."
        )
    if diluted_shares is not None:
        if diluted_shares <= 0:
            raise ProvenanceError("diluted_shares must be positive (STEP 35)")
        if not shares_source or not shares_source.strip():
            raise ProvenanceError(
                "STEP 35 requires the source and date for diluted shares outstanding."
            )

    # STEP 29 / 16.14: PV = FCFF_t / (1 + WACC)^t, with t from the schedule.
    span = schedule or build_schedule(periods.forecast, Timing.YEAR_END)
    discounted = []
    for item in fcff_years:
        t = span.fraction_for(item.year)
        discounted.append(
            DiscountedYear(
                year=item.year,
                fcff=item.fcff,
                period=t,
                discount_factor=discount_factor(wacc, t),
            )
        )

    # STEP 30-32: terminal cash flow, terminal value, and its present value.
    # 16.17: discounted on the SAME convention as the flows before it. A
    # terminal value on a different basis is a different valuation.
    terminal_fcff = fcff_years[-1].fcff * (ONE + terminal_growth)
    terminal_value = terminal_fcff / (wacc - terminal_growth)
    pv_terminal_value = terminal_value * discount_factor(wacc, span.terminal)

    # STEP 33-34
    enterprise_value = sum((d.present_value for d in discounted), ZERO) + pv_terminal_value
    equity_value = bridge.apply(enterprise_value)

    return Valuation(
        periods=periods,
        discounted=discounted,
        terminal_growth=terminal_growth,
        wacc=wacc,
        terminal_fcff=terminal_fcff,
        terminal_value=terminal_value,
        pv_terminal_value=pv_terminal_value,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        bridge=bridge,
        diluted_shares=diluted_shares,
        shares_source=shares_source,
    )
