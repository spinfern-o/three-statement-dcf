"""Items 97-108: the forecast, driven from a scenario's approved assumptions.

Nothing here forecasts anything. `model/forecast.py` implements all twenty-one
of Section 15's steps and has an independent benchmark behind it; this phase
turns a *scenario* into the engine's inputs, runs it, and reports the checks
per scenario. So the tests are about the boundary, not the arithmetic:

  - that 14.1 is enforced BEFORE the engine is touched, so a reviewer sees
    eleven missing drivers at once rather than one traceback at a time;
  - that a Draft never crosses;
  - that the scenario travels with the result (9.12, 15.20);
  - that two scenarios give two different forecasts;
  - and that every check runs for every scenario and period (15.20).

The arithmetic is checked once, against figures computed by hand from the
fixture, so that a change in the boundary that silently altered a number would
still be caught.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.assumptions.drivers import BY_CODE
from apps.api.app.assumptions.scenarios import BASE, Scenario, ScenarioSet, base_scenario
from apps.api.app.assumptions.schema import Assumption, Evidence, SourceType, Status
from apps.api.app.forecast.build import (
    ForecastError,
    build_scenario_forecast,
    forecast_ledger,
    forecast_periods,
)
from apps.api.app.forecast.checks import (
    VALUATION_CHECKS,
    check_every_scenario,
    check_scenario,
)
from model import accounts
from model.accounts import Statement
from model.checks import Status as CheckStatus

D = Decimal


def assumption(code, value, status=Status.APPROVED):
    unit = BY_CODE[code].unit
    fields = dict(
        code=code,
        name=code.replace("_", " "),
        value=D(value),
        unit=unit,
        owner="larry",
        reviewer="larry",
        status=status,
        rationale="entered for this test, with a stated source",
    )
    if unit == "days":
        fields.update(
            source_type=SourceType.HISTORICAL_DRIVER,
            evidence=Evidence(measured_over=("2025A",)),
        )
    else:
        fields.update(
            source_type=SourceType.COMPANY_GUIDANCE,
            evidence=Evidence(document_id="doc-1", page=31, date="2026-02-14"),
        )
    return Assumption(**fields)


#: Every required driver, at the rates the filing itself implies.
DRIVERS = {
    "revenue_growth": "0.08",
    "cogs_pct_revenue": "0.60",  # 1,200,000 / 2,000,000
    "opex_pct_revenue": "0.24",  #   480,000 / 2,000,000
    "depreciation_pct_beginning_ppe": "0.1412",  #   120,000 /   850,000
    "capex_pct_revenue": "0.085",  #   170,000 / 2,000,000
    "dso": "58.4",  #   320,000 / 2,000,000 x 365
    "inventory_days": "73",  #   240,000 / 1,200,000 x 365
    "dpo": "60.8",  #   200,000 / 1,200,000 x 365
    "other_current_assets_pct_revenue": "0.02",  #    40,000 / 2,000,000
    "other_current_liabilities_pct_revenue": "0.045",  #    90,000 / 2,000,000
    "interest_rate_on_debt": "0.04",  #    24,000 /   600,000
    "tax_rate": "0.25",  #    74,000 /   296,000
}


@pytest.fixture(scope="module")
def approved():
    return ScenarioSet(
        (base_scenario("larry"),),
        tuple(assumption(code, value) for code, value in DRIVERS.items()),
    )


@pytest.fixture(scope="module")
def forecast(forecast_built, approved):
    return build_scenario_forecast(forecast_built, approved, BASE)


# --- items 97: the periods (15.1, 15.2) -------------------------------------


def test_the_forecast_begins_the_year_after_the_last_actual(forecast_built):
    periods = forecast_periods(forecast_built)
    assert periods.historical == ("2024A", "2025A")
    assert periods.forecast == ("2026E", "2027E", "2028E", "2029E", "2030E")
    assert periods.last_actual == "2025A"


def test_every_period_is_labelled_actual_or_estimate(forecast):
    """15.2. `Periods` refuses anything else, so this pins the convention."""
    assert all(year.endswith("A") for year in forecast.periods.historical)
    assert all(year.endswith("E") for year in forecast.periods.forecast)


# --- the 14.1 gate runs before the engine is touched ------------------------


def test_a_scenario_missing_drivers_is_refused_before_the_engine_runs(forecast_built):
    """The engine names one missing driver per traceback. The gate names all."""
    thin = ScenarioSet(
        (base_scenario("larry"),),
        (assumption("revenue_growth", "0.08"), assumption("tax_rate", "0.25")),
    )
    with pytest.raises(ForecastError) as caught:
        build_scenario_forecast(forecast_built, thin, BASE)
    message = str(caught.value)
    assert "may not calculate yet (14.1)" in message
    for code in ("dso", "inventory_days", "dpo", "interest_rate_on_debt"):
        assert code in message, f"{code} is missing and the refusal does not say so"


def test_a_draft_driver_never_reaches_the_engine(forecast_built, approved):
    """14.1. A Draft is not an answer, and an unsourced number in a valuation
    is exactly what the status system exists to prevent."""
    drafted = approved.with_assumption(assumption("dso", "58.4", status=Status.DRAFT))
    with pytest.raises(ForecastError, match="Draft"):
        build_scenario_forecast(forecast_built, drafted, BASE)


def test_a_filing_without_the_balances_the_forecast_anchors_on_is_refused(built):
    """`three_statements.pdf` reports no other-noncurrent lines, and STEP 5
    forbids substituting zero. The refusal names the line and the step."""
    approved_set = ScenarioSet(
        (base_scenario("larry"),),
        tuple(assumption(code, value) for code, value in DRIVERS.items()),
    )
    with pytest.raises(ForecastError) as caught:
        build_scenario_forecast(built, approved_set, BASE)
    message = str(caught.value)
    assert "other_noncurrent_assets" in message
    assert "do not substitute zero" in message


# --- items 98-107: the forecast itself, checked by hand ---------------------

#: 2026E, computed by hand from the filing and the drivers above.
#:   revenue     2,000,000 x 1.08                      = 2,160,000
#:   cogs        2,160,000 x 0.60                      = 1,296,000
#:   gross       2,160,000 - 1,296,000                 =   864,000
#:   opex        2,160,000 x 0.24                      =   518,400
#:   ebit          864,000 -   518,400                 =   345,600
#:   interest      550,000 x 0.04  (on BEGINNING debt) =    22,000
#:   pretax        345,600 -    22,000                 =   323,600
#:   tax           323,600 x 0.25                      =    80,900
#:   net income    323,600 -    80,900                 =   242,700
GOLDEN_2026 = {
    accounts.REVENUE: "2160000",
    accounts.COGS: "1296000",
    accounts.GROSS_PROFIT: "864000",
    accounts.OPERATING_EXPENSES: "518400",
    accounts.EBIT: "345600",
    accounts.INTEREST_EXPENSE: "22000",
    accounts.PRETAX_INCOME: "323600",
    accounts.TAXES: "80900",
    accounts.NET_INCOME: "242700",
}


@pytest.mark.parametrize("account", sorted(GOLDEN_2026))
def test_the_first_forecast_year_of_the_income_statement(forecast, account):
    ledger = forecast_ledger(forecast, Statement.INCOME)
    assert ledger.get(account, "2026E") == D(GOLDEN_2026[account])


def test_interest_is_charged_on_beginning_debt(forecast):
    """STEP 19 and 13.4 must be the same measurement, or the rate is wrong.

    Debt opens 2026E at the 2025A balance of 550,000, and 4% of it is 22,000.
    Charging on the closing balance would give a different number every year.
    """
    income = forecast_ledger(forecast, Statement.INCOME)
    balance = forecast_ledger(forecast, Statement.BALANCE)
    assert balance.get(accounts.DEBT, "2025A") == D("550000")
    assert income.get(accounts.INTEREST_EXPENSE, "2026E") == D("22000")
    assert "beginning debt" in income.cell(accounts.INTEREST_EXPENSE, "2026E").basis


def test_depreciation_is_charged_on_opening_ppe_not_on_capex(forecast):
    """STEP 18: depreciation and CapEx are forecast separately, and neither
    may default to the other. 900,000 x 0.1412 = 127,080."""
    cashflow = forecast_ledger(forecast, Statement.CASHFLOW)
    assert cashflow.get(accounts.DEPRECIATION_AMORTIZATION, "2026E") == D("127080")
    assert cashflow.get(accounts.CAPEX, "2026E") == D("-183600")  # 2,160,000 x 0.085


def test_every_forecast_cell_carries_a_driver_and_none_is_a_hardcode(forecast):
    """STEP 37 / 17.20, which only means anything on a real forecast.

    A forecast-year cell is either `forecast` -- produced by a driver -- or
    `derived`, computed from other cells in the same year. What it must never
    be is `reported`: that is a figure pasted into a projected year, which is
    exactly what `hardcodes_in` looks for. Either way it carries a basis, so
    14.5 holds: no assumption is hidden inside a formula.
    """
    for statement in Statement:
        ledger = forecast_ledger(forecast, statement)
        assert ledger.hardcodes_in(forecast.periods.forecast) == []
        for year in forecast.periods.forecast:
            for account in ledger.accounts_present(year):
                cell = ledger.cell(account, year)
                assert cell.origin in ("forecast", "derived"), (
                    f"{account} {year} is {cell.origin} in a projected year"
                )
                assert cell.basis, f"{account} {year} has no stated basis (14.5)"


def test_the_historical_years_are_still_reported_in_the_same_ledger(forecast):
    """15.19's cash link and STEP 37's hardcode check both need one object."""
    balance = forecast_ledger(forecast, Statement.BALANCE)
    assert balance.get(accounts.CASH, "2025A") == D("180000")
    assert balance.cell(accounts.CASH, "2025A").origin == "reported"


# --- the boundary carries what Section 14 added -----------------------------


def test_every_driver_reaches_the_engine_with_its_evidence(forecast):
    """STEP 10 asks for a visible source. Losing it here would make the
    engine's own report thinner than the screen that fed it."""
    assert len(forecast.drivers) >= len(DRIVERS) - 1  # tax_rate goes via the schedule
    assert forecast.unused == (), f"declared and never read: {forecast.unused}"


def test_the_tax_basis_is_stated(forecast):
    """STEP 16: say which rate the model uses, and why."""
    assert forecast.tax_basis in ("statutory", "historical_effective", "normalized_effective")
    assert forecast.tax_source, "the basis must name where the rate came from"


def test_a_historically_sourced_tax_rate_is_labelled_as_such(forecast_built, approved):
    """The basis follows the source type, rather than being typed twice."""
    historical = approved.with_assumption(
        Assumption(
            code="tax_rate",
            name="Effective tax rate",
            value=D("0.25"),
            unit="ratio",
            source_type=SourceType.HISTORICAL_DRIVER,
            evidence=Evidence(measured_over=("2024A", "2025A")),
            rationale="the effective rate measured from the 13.6 tax schedule",
            owner="larry",
            reviewer="larry",
            status=Status.APPROVED,
        )
    )
    built = build_scenario_forecast(forecast_built, historical, BASE)
    assert built.tax_basis == "historical_effective"


def test_the_scenario_travels_with_the_result(forecast):
    """9.12 records a CalculatedValue against its scenario_id."""
    assert forecast.scenario_id == BASE


# --- item 108: every scenario and every period (15.20) ----------------------


def test_every_check_passes_on_a_forecast_that_ties(forecast):
    checks = check_scenario(forecast)
    assert checks.failed == (), checks.describe()
    assert checks.skipped == (), "no forecast check should be unable to run here"
    assert checks.is_forecast_ready
    assert "11 passed, 0 failed, 0 skipped" in checks.summarize()


def test_the_valuation_checks_are_deferred_not_counted_against_the_forecast(forecast):
    """A forecast is not unfinished because Phase 11 does not exist yet."""
    checks = check_scenario(forecast)
    assert {r.name for r in checks.deferred} == VALUATION_CHECKS
    assert "awaiting a valuation" in checks.summarize()


def test_the_deferred_set_cannot_silently_grow(forecast):
    """If the engine adds a valuation check, this fails rather than the
    readiness gate quietly excluding one more thing."""
    checks = check_scenario(forecast)
    skipping = {r.name for r in checks.results if r.status is CheckStatus.SKIP}
    assert skipping == VALUATION_CHECKS, (
        f"these checks skip with no valuation and are not in VALUATION_CHECKS: "
        f"{sorted(skipping - VALUATION_CHECKS)}"
    )


def test_two_scenarios_give_two_forecasts_and_both_are_checked(forecast_built, approved):
    """15.20's "every scenario", which a single-scenario panel hides."""
    variant = approved.with_scenario(
        Scenario(id="downside", name="Downside", parent_id=BASE, created_by="larry")
    ).override(
        "downside",
        "revenue_growth",
        D("0.02"),
        owner="larry",
        rationale="the low end of the guided range",
    )
    # An override is a new number, so it arrives as a Draft and the gate stops
    # the scenario until somebody reviews it. That is the workflow working, not
    # an obstacle to route around.
    variant = _approve(variant, "downside", "revenue_growth")

    base = build_scenario_forecast(forecast_built, variant, BASE)
    downside = build_scenario_forecast(forecast_built, variant, "downside")

    assert base.result.income.get(accounts.REVENUE, "2026E") == D("2160000")
    assert downside.result.income.get(accounts.REVENUE, "2026E") == D("2040000")

    readiness = check_every_scenario((base, downside))
    assert readiness.is_forecast_ready
    assert {item.scenario_id for item in readiness.by_scenario} == {BASE, "downside"}
    assert readiness.for_scenario("downside").is_forecast_ready


def test_an_override_arrives_as_a_draft_and_stops_its_scenario(forecast_built, approved):
    """14.7 gives an override its lineage; 14.1 still makes it earn a status."""
    variant = approved.with_scenario(
        Scenario(id="downside", name="Downside", parent_id=BASE, created_by="larry")
    ).override(
        "downside",
        "revenue_growth",
        D("0.02"),
        owner="larry",
        rationale="the low end of the guided range",
    )
    assert variant.resolve("downside")["revenue_growth"].assumption.status is Status.DRAFT
    with pytest.raises(ForecastError, match="Draft"):
        build_scenario_forecast(forecast_built, variant, "downside")
    # The base scenario is untouched by its variant's unfinished business.
    assert build_scenario_forecast(forecast_built, variant, BASE).scenario_id == BASE


def _approve(scenarios, scenario_id, code):
    """Take one assumption through review to approval, as the workflow requires."""
    from apps.api.app.assumptions.workflow import transition

    current = scenarios.resolve(scenario_id)[code].assumption
    reviewed, _ = transition(
        current,
        Status.REVIEWED,
        actor="larry",
        reason="checked against the guided range",
        reviewer="larry",
    )
    approved_item, _ = transition(
        reviewed, Status.APPROVED, actor="larry", reason="accepted for this scenario"
    )
    return scenarios.with_assumption(approved_item)


def test_one_failing_scenario_withholds_the_label_from_the_whole_model(forecast_built, approved):
    """A model whose Base balances and whose Downside does not is not ready."""
    base = build_scenario_forecast(forecast_built, approved, BASE)
    readiness = check_every_scenario((base,), not_built={"downside": "revenue_growth was Rejected"})
    assert not readiness.is_forecast_ready
    assert "downside could not be forecast" in readiness.describe()


def test_the_readiness_verdict_says_severity_is_unassigned(forecast):
    """F-4. A reader has to know that "critical" is being read as "all"."""
    readiness = check_every_scenario((forecast,))
    assert readiness.severity_is_unassigned
    assert "assigns a severity to none" in readiness.describe()
