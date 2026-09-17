"""Items 109-120: the DCF, and its independent benchmark.

Item 120 asks for benchmark tests, and 4.15 says the primary engine and the
benchmark must not call the same helper. So `BENCHMARK` below recomputes the
whole valuation from the forecast with plain `Decimal` arithmetic written out
longhand -- no `model.dcf`, no `model.timing`, no `model.numeric` -- and
asserts exact equality, because every operation involved is addition,
subtraction, multiplication or a terminating division.

Everything else here is about the boundary: that a valuation input without a
URL and an observation date is refused, that 16.16 blocks rather than returns
an infinity, that 16.20 withholds a per-share value, and that 16.19's bridge
lines nobody addressed are reported as taken-as-nil rather than silently zero.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.api.app.assumptions.scenarios import BASE, ScenarioSet
from apps.api.app.assumptions.schema import Assumption, Evidence, SourceType, Status
from apps.api.app.forecast.build import build_scenario_forecast
from apps.api.app.valuation.build import ValuationError, build_scenario_valuation
from apps.api.app.valuation.checks import (
    DEFAULT_TERMINAL_THRESHOLD,
    EXIT_MULTIPLE_STATUS,
    headroom,
    terminal_share,
)
from apps.api.app.valuation.inputs import LEASE_LIABILITIES_NOTE, MARKET_INPUTS
from apps.api.app.valuation.sensitivity import build_grid
from apps.api.tests.conftest import approved_scenario
from model.timing import Timing

D = Decimal


@pytest.fixture(scope="module")
def scenarios():
    return approved_scenario("larry")


@pytest.fixture(scope="module")
def forecast(forecast_built, scenarios):
    return build_scenario_forecast(forecast_built, scenarios, BASE)


@pytest.fixture(scope="module")
def valuation(forecast, scenarios):
    return build_scenario_valuation(forecast, scenarios)


# --- item 120: the independent benchmark (4.15, 4.16) -----------------------

def _benchmark(forecast, wacc_inputs, growth, cash, debt):
    """Every 4.16 valuation output, recomputed longhand.

    Deliberately shares no helper with `model/`: the arithmetic is written out
    here with the built-in operators, and the forecast's own EBIT, D&A, CapEx
    and working capital are read straight off the ledgers rather than through
    `fcff_inputs`.
    """
    from model.accounts import (
        ACCOUNTS_PAYABLE,
        ACCOUNTS_RECEIVABLE,
        CAPEX,
        DEPRECIATION_AMORTIZATION,
        EBIT,
        INVENTORY,
        OTHER_CURRENT_ASSETS,
        OTHER_CURRENT_LIABILITIES,
        Statement,
    )

    income = forecast.result.income
    cashflow = forecast.result.cashflow
    balance = forecast.result.balance
    del Statement

    def nwc(year):
        assets = sum(
            balance.get(name, year)
            for name in (ACCOUNTS_RECEIVABLE, INVENTORY, OTHER_CURRENT_ASSETS)
        )
        liabilities = sum(
            balance.get(name, year)
            for name in (ACCOUNTS_PAYABLE, OTHER_CURRENT_LIABILITIES)
        )
        return assets - liabilities

    one = D(1)
    tax = forecast.result.taxes.rate(forecast.periods.forecast[-1])
    cost_of_equity = (
        wacc_inputs["risk_free_rate"] + wacc_inputs["beta"] * wacc_inputs["equity_risk_premium"]
    )
    equity, borrowings = wacc_inputs["market_value_equity"], wacc_inputs["market_value_debt"]
    capital = equity + borrowings
    wacc = (equity / capital) * cost_of_equity + (borrowings / capital) * (
        wacc_inputs["pretax_cost_of_debt"] * (one - tax)
    )

    flows, present_values = [], []
    for index, year in enumerate(forecast.periods.forecast, start=1):
        prior = forecast.periods.prior(year)
        nopat = income.get(EBIT, year) * (one - tax)
        fcff = (
            nopat
            + cashflow.get(DEPRECIATION_AMORTIZATION, year)
            - abs(cashflow.get(CAPEX, year))
            - (nwc(year) - nwc(prior))
        )
        flows.append(fcff)
        present_values.append(fcff / (one + wacc) ** index)

    terminal_fcff = flows[-1] * (one + growth)
    terminal_value = terminal_fcff / (wacc - growth)
    pv_terminal = terminal_value / (one + wacc) ** len(flows)
    enterprise = sum(present_values) + pv_terminal
    return {
        "cost_of_equity": cost_of_equity,
        "wacc": wacc,
        "fcff": flows,
        "pv": present_values,
        "terminal_fcff": terminal_fcff,
        "terminal_value": terminal_value,
        "pv_terminal_value": pv_terminal,
        "enterprise_value": enterprise,
        "equity_value": enterprise + cash - debt,
    }


def test_the_benchmark_agrees_with_the_engine_exactly(forecast, valuation):
    """4.11's contract is 0.0001%. Both sides are exact decimal arithmetic, so
    the required answer is equality, not a tolerance."""
    from apps.api.tests.conftest import MARKET_INPUTS as SUPPLIED

    expected = _benchmark(
        forecast,
        {code: D(value) for code, (value, _) in SUPPLIED.items()},
        growth=D("0.02"),
        cash=D("180000"),
        debt=D("550000"),
    )
    engine = valuation.valuation

    assert valuation.cost_of_capital.cost_of_equity == expected["cost_of_equity"]
    assert engine.wacc == expected["wacc"]
    for index, item in enumerate(valuation.fcff_years):
        assert item.fcff == expected["fcff"][index], item.year
    for index, item in enumerate(engine.discounted):
        assert item.present_value == expected["pv"][index], item.year
    assert engine.terminal_fcff == expected["terminal_fcff"]
    assert engine.terminal_value == expected["terminal_value"]
    assert engine.pv_terminal_value == expected["pv_terminal_value"]
    assert engine.enterprise_value == expected["enterprise_value"]
    assert engine.equity_value == expected["equity_value"]


#: Checked by hand against the benchmark above, and pinned so a change
#: anywhere in the chain says which number moved.
def test_the_cost_of_capital_is_what_capm_says(valuation):
    """16.6 and 16.9. 0.042 + 1.15 x 0.055 = 0.10525."""
    coc = valuation.cost_of_capital
    assert coc.cost_of_equity == D("0.10525")
    assert coc.after_tax_cost_of_debt == D("0.05") * D("0.75")
    assert coc.total_capital == D("3050000")


def test_the_enterprise_to_equity_bridge_is_explicit(valuation):
    """16.19. Cash and debt come off the balance sheet, with a page behind them."""
    assert valuation.bridge.cash == D("180000")
    assert valuation.bridge.debt == D("550000")
    assert valuation.valuation.equity_value == (
        valuation.valuation.enterprise_value + D("180000") - D("550000")
    )


# --- item 111: the source panel ---------------------------------------------

def test_every_market_input_carries_a_url_and_an_observation_date(valuation):
    """16.6-16.10 with Section 14's evidence rules doing the enforcing.

    `CostOfCapital` requires a non-empty source string, which "Bloomberg"
    satisfies. This requires the thing a reader can go and check.
    """
    supplied = {r.code: r for r in valuation.inputs if not r.assumed_nil}
    for definition in MARKET_INPUTS:
        record = supplied[definition.code]
        assert "https://" in record.evidence, definition.code
        assert "2026-09-17" in record.evidence, definition.code
        assert record.status == "Approved"


def test_a_market_input_without_an_observation_date_never_gets_this_far(
    forecast_built, scenarios
):
    """The refusal is Section 14's, at the point the number is entered."""
    from apps.api.app.assumptions.schema import AssumptionError

    with pytest.raises(AssumptionError, match="observation date"):
        Assumption(
            code="beta", name="Beta", value=D("1.15"), unit="ratio",
            source_type=SourceType.EXTERNAL_MARKET_DATA,
            evidence=Evidence(url="https://example.test/beta"),
            rationale="a beta from somewhere", owner="larry",
        )


def test_a_missing_market_input_is_refused_and_named(forecast, scenarios):
    thin = ScenarioSet(
        scenarios.scenarios,
        tuple(a for a in scenarios.assumptions if a.code not in ("beta", "risk_free_rate")),
    )
    with pytest.raises(ValuationError) as caught:
        build_scenario_valuation(forecast, thin)
    message = str(caught.value)
    assert "beta" in message and "risk_free_rate" in message
    assert "can be derived from the filing (STEP 25-27)" in message


def test_a_draft_market_input_blocks_the_valuation(forecast, scenarios):
    from dataclasses import replace

    drafted = scenarios.with_assumption(
        replace(
            next(a for a in scenarios.assumptions if a.code == "beta"),
            status=Status.DRAFT,
        )
    )
    with pytest.raises(ValuationError, match="beta is Draft"):
        build_scenario_valuation(forecast, drafted)


def test_a_market_input_in_the_wrong_unit_is_refused(forecast, scenarios):
    """18.12 at the seam. A beta declared in currency is not a beta."""
    from dataclasses import replace

    wrong = scenarios.with_assumption(
        replace(
            next(a for a in scenarios.assumptions if a.code == "beta"),
            unit="currency",
        )
    )
    with pytest.raises(ValuationError, match="18.12"):
        build_scenario_valuation(forecast, wrong)


# --- items 112, 113: the timing convention ----------------------------------

def test_year_end_is_the_default_and_uses_whole_periods(valuation):
    assert valuation.schedule.timing is Timing.YEAR_END
    assert [item.period for item in valuation.valuation.discounted] == [
        D(1), D(2), D(3), D(4), D(5)
    ]


def test_mid_year_discounting_raises_the_valuation(forecast, scenarios, valuation):
    """16.11. The choice is documented because it moves the answer."""
    mid = build_scenario_valuation(forecast, scenarios, timing=Timing.MID_YEAR)
    assert mid.valuation.enterprise_value > valuation.valuation.enterprise_value
    assert [item.period for item in mid.valuation.discounted] == [
        D("0.5"), D("1.5"), D("2.5"), D("3.5"), D("4.5")
    ]
    assert "RAISES every present value" in mid.schedule.basis


def test_the_terminal_value_is_discounted_on_the_same_convention(forecast, scenarios):
    """16.17. A terminal value on a different basis is a different valuation."""
    mid = build_scenario_valuation(forecast, scenarios, timing=Timing.MID_YEAR)
    assert mid.schedule.terminal == D("4.5")


def test_exact_dates_need_a_valuation_date_and_then_use_the_calendar(
    forecast, scenarios
):
    """16.12."""
    from model.provenance import ProvenanceError

    with pytest.raises(ProvenanceError, match="needs a valuation date"):
        build_scenario_valuation(forecast, scenarios, timing=Timing.EXACT_DATE)

    exact = build_scenario_valuation(
        forecast, scenarios, timing=Timing.EXACT_DATE,
        valuation_date=date(2026, 6, 30), fiscal_year_end=date(2025, 12, 31),
    )
    assert exact.valuation.discounted[0].period == D(184) / D(365)
    assert "2026-06-30" in exact.schedule.basis


# --- items 115, 16.16, 16.21, 16.22 -----------------------------------------

def test_the_terminal_share_is_reported(valuation):
    """16.21. Most of a DCF's answer usually lives here."""
    share = terminal_share(valuation)
    assert share.percent == D("72.9")
    assert "72.9% of enterprise value" in share.describe()


def test_a_high_terminal_share_warns_and_does_not_fail(valuation):
    """16.22 is explicit: do not automatically fail solely because it is high."""
    strict = terminal_share(valuation, threshold=D("0.5"))
    assert strict.is_above_threshold
    assert "WARNING and not a failure" in strict.describe()
    assert "no threshold tells the two apart" in strict.describe()
    assert DEFAULT_TERMINAL_THRESHOLD == D("0.75")


def test_wacc_must_exceed_the_growth_rate(forecast, scenarios):
    """16.16 / item 115: blocked, not a negative or infinite answer."""
    from dataclasses import replace

    impossible = scenarios.with_assumption(
        replace(
            next(a for a in scenarios.assumptions if a.code == "terminal_growth"),
            value=D("0.15"),
        )
    )
    with pytest.raises(ValuationError, match="must exceed the terminal growth"):
        build_scenario_valuation(forecast, impossible)


def test_the_headroom_warns_when_the_spread_is_narrow(forecast, scenarios):
    from dataclasses import replace

    narrow = scenarios.with_assumption(
        replace(
            next(a for a in scenarios.assumptions if a.code == "terminal_growth"),
            value=D("0.08"),
        )
    )
    built = build_scenario_valuation(forecast, narrow)
    assert "under two points" in headroom(built).describe()


# --- 16.19, 16.20, 16.24, 16.25 ---------------------------------------------

def test_bridge_lines_nobody_addressed_are_reported_not_silently_zero(valuation):
    """16.19 lists them; taking one as nil without saying so is the failure."""
    assert set(valuation.assumed_nil) == {
        "non_operating_investments", "minority_interest", "preferred_stock",
        "pension_obligations", "other_claims",
    }
    nil = {r.code: r for r in valuation.inputs if r.assumed_nil}
    assert "taken as nil because nobody entered it" in nil["minority_interest"].evidence


def test_there_is_no_per_share_value_without_verified_diluted_shares(valuation):
    """16.20: "only when diluted shares are verified"."""
    assert not valuation.has_per_share
    assert valuation.valuation.implied_share_price is None
    assert "16.20 permits one only when" in valuation.per_share_status


def test_a_sourced_share_count_gives_a_per_share_value_and_says_what_rests_on_it(
    forecast, scenarios
):
    with_shares = scenarios.with_assumption(
        Assumption(
            code="diluted_shares", name="Diluted shares", value=D("50000"),
            unit="shares", source_type=SourceType.COMPANY_FILING,
            evidence=Evidence(document_id="doc-1", page=44, date="2026-02-14"),
            rationale="the diluted count under the EPS note",
            owner="larry", reviewer="larry", status=Status.APPROVED,
        )
    )
    built = build_scenario_valuation(forecast, with_shares)
    assert built.has_per_share
    assert built.valuation.implied_share_price == built.valuation.equity_value / D("50000")
    assert "rests entirely on its citation" in built.per_share_status


def test_the_exit_multiple_is_reported_as_not_implemented():
    """16.24 and 16.25. One method means nothing to average, and saying so is
    better than leaving a reader to assume a second was considered."""
    assert "Not implemented" in EXIT_MULTIPLE_STATUS
    assert "16.25" in EXIT_MULTIPLE_STATUS
    assert "no EBITDA line" in EXIT_MULTIPLE_STATUS


def test_lease_liabilities_are_reported_as_a_bridge_line_that_cannot_be_built():
    """16.19, and F-17 once more."""
    assert "2.4.j" in LEASE_LIABILITIES_NOTE
    assert "over-valued by their whole amount" in LEASE_LIABILITIES_NOTE


# --- item 119 / 16.23: the sensitivity grid ---------------------------------

def test_the_grid_is_centred_on_the_valuation_it_is_a_sensitivity_of(valuation):
    """A grid centred somewhere else is a sensitivity of a model nobody built."""
    grid = build_grid(valuation)
    assert grid.centre.enterprise_value == valuation.valuation.enterprise_value
    assert grid.base_wacc == valuation.valuation.wacc
    assert grid.base_growth == D("0.02")


def test_the_grid_states_its_step_sizes_and_its_discounting(valuation):
    """16.23: "explicit step sizes and displayed assumptions"."""
    grid = build_grid(valuation)
    assert grid.wacc_step == D("0.0025") and grid.growth_step == D("0.0025")
    assert len(grid.wacc_values) == 5 and len(grid.growth_values) == 5
    assert "Year-end" in grid.describe()


def test_the_grid_is_discounted_on_the_same_convention_as_its_valuation(
    forecast, scenarios
):
    """A grid on a different convention is a sensitivity of a different model."""
    mid = build_scenario_valuation(forecast, scenarios, timing=Timing.MID_YEAR)
    grid = build_grid(mid)
    assert grid.centre.enterprise_value == mid.valuation.enterprise_value
    assert "Mid-year" in grid.timing_basis


def test_a_corner_where_wacc_does_not_exceed_growth_shows_its_reason(valuation):
    """16.16 in the grid: empty with an explanation, never blank."""
    grid = build_grid(valuation, wacc_step=D("0.05"), growth_step=D("0.05"))
    blocked = grid.blocked
    assert blocked, "a wide enough grid must reach the WACC <= g region"
    assert all("WACC <= g" in cell.note for cell in blocked)
    assert all(cell.enterprise_value is None for cell in blocked)


def test_the_grid_moves_monotonically_with_both_axes(valuation):
    """A higher WACC lowers the value; a higher growth rate raises it."""
    grid = build_grid(valuation)
    middle = len(grid.growth_values) // 2
    column = [row[middle].enterprise_value for row in grid.rows]
    assert column == sorted(column, reverse=True), "higher WACC must lower value"
    row = [cell.enterprise_value for cell in grid.rows[len(grid.rows) // 2]]
    assert row == sorted(row), "higher terminal growth must raise value"
