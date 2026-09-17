"""Items 93 and 94: the preview that must happen BEFORE saving (14.8).

"Changing one assumption must show all affected outputs before saving."

The word carrying the requirement is *before*. A preview implemented by
saving, recalculating and offering an undo is not a preview: the model has
already moved, and if the reviewer closes the tab the change stands. So the
first test here is not about numbers at all -- it asserts that previewing
leaves the scenario set it was handed byte-for-byte unchanged.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.assumptions.impact import (
    model_for,
    preview,
    reaches,
    unread_assumptions,
)
from apps.api.app.assumptions.scenarios import BASE, Scenario, ScenarioSet, base_scenario
from apps.api.app.assumptions.schema import Assumption, Evidence, SourceType, Status
from apps.api.app.formula.evaluate import Environment
from apps.api.app.formula.registry import FormulaDefinition, FormulaSet
from apps.api.app.formula.units import CURRENCY, RATIO

D = Decimal


def definition(code, target, expression, unit="currency"):
    return FormulaDefinition(
        code=code, target=target, expression=expression, output_unit=unit,
        definition=f"{target} computed as {expression}",
    )


#: A small forecast-shaped chain: growth drives revenue, revenue drives COGS,
#: and both drive gross profit and the margin.
FORMULAS = FormulaSet((
    definition("F1", "revenue", "prior_revenue * (1 + revenue_growth)"),
    definition("F2", "cogs", "revenue * cogs_pct_revenue"),
    definition("F3", "gross_profit", "revenue - cogs"),
    definition("F4", "gross_margin", "gross_profit / revenue", unit="ratio"),
))


def assumption(code, value, unit="ratio"):
    return Assumption(
        code=code, name=code.replace("_", " "), value=D(value), unit=unit,
        source_type=SourceType.COMPANY_GUIDANCE,
        evidence=Evidence(document_id="doc-1", page=31, date="2026-02-14"),
        rationale="the midpoint of the guided range",
        owner="larry", reviewer="larry", status=Status.APPROVED,
    )


@pytest.fixture
def scenarios():
    return ScenarioSet(
        (base_scenario("larry"),),
        (assumption("revenue_growth", "0.10"), assumption("cogs_pct_revenue", "0.60")),
    )


@pytest.fixture
def environment():
    return Environment().put("prior_revenue", D("1000000"), CURRENCY, origin="2025A revenue")


def _preview(scenarios, environment, code, proposed):
    return preview(
        formulas=FORMULAS, base_environment=environment, scenarios=scenarios,
        scenario_id=BASE, code=code, proposed=D(proposed),
    )


# --- 14.8: "before saving" --------------------------------------------------

def test_previewing_changes_nothing(scenarios, environment):
    """The requirement is not that a change can be undone. It is that it has
    not yet happened."""
    before = scenarios
    _preview(scenarios, environment, "revenue_growth", "0.20")
    assert scenarios is before
    assert scenarios.version == 1
    assert scenarios.resolve(BASE)["revenue_growth"].assumption.value == D("0.10")


def test_the_preview_shows_every_affected_output(scenarios, environment):
    impact = _preview(scenarios, environment, "revenue_growth", "0.20")
    assert impact.before == D("0.10") and impact.after == D("0.20")
    # Everything downstream of revenue, transitively.
    assert set(impact.reaches) == {"revenue", "cogs", "gross_profit", "gross_margin"}
    moved = {item.target: (item.before, item.after) for item in impact.moved}
    assert moved["revenue"] == (D("1100000"), D("1200000"))
    assert moved["cogs"] == (D("660000"), D("720000"))
    assert moved["gross_profit"] == (D("440000"), D("480000"))
    assert "gross_margin" not in moved, (
        "the margin is a ratio of two figures that both scaled, so it does not "
        "move -- which is exactly the kind of thing a preview is for"
    )


def test_a_margin_moves_when_the_margin_driver_moves(scenarios, environment):
    impact = _preview(scenarios, environment, "cogs_pct_revenue", "0.55")
    moved = {item.target for item in impact.moved}
    assert moved == {"cogs", "gross_profit", "gross_margin"}
    assert "revenue" not in moved, "revenue does not depend on the cost ratio"


def test_a_change_that_moves_nothing_says_so(scenarios, environment):
    impact = _preview(scenarios, environment, "revenue_growth", "0.10")
    assert impact.changes_nothing
    assert "is unchanged" in impact.describe()


def test_previewing_an_assumption_the_scenario_does_not_carry_is_refused(
    scenarios, environment
):
    with pytest.raises(KeyError, match="not an assumption"):
        _preview(scenarios, environment, "made_up", "1")


def test_the_preview_reports_what_would_become_uncomputable(environment):
    """18.14 through 14.8: a change that makes a cell absent is an affected output."""
    scenarios = ScenarioSet(
        (base_scenario("larry"),),
        (assumption("revenue_growth", "0.10"), assumption("cogs_pct_revenue", "0.60")),
    )
    # Driving revenue to zero makes the margin a division by zero, which is
    # refused rather than reported as zero or infinity (18.13).
    impact = _preview(scenarios, environment, "revenue_growth", "-1")
    assert any(item.target == "revenue" for item in impact.moved)
    assert impact.unavailable.get("gross_margin"), (
        "the margin has no value at zero revenue, and saying so is the point"
    )


# --- item 94 on its own -----------------------------------------------------

def test_the_dependency_answer_comes_from_the_phase_8_graph():
    """A second traversal here would be a second answer to the same question."""
    assert reaches(FORMULAS, "cogs_pct_revenue") == ("cogs", "gross_margin", "gross_profit")
    assert reaches(FORMULAS, "prior_revenue") == (
        "cogs", "gross_margin", "gross_profit", "revenue"
    )


def test_an_assumption_nothing_reads_is_reported(scenarios):
    """A misspelled driver code looks exactly like this."""
    stray = scenarios.with_assumption(assumption("revenue_growht", "0.10"))
    assert unread_assumptions(FORMULAS, stray, BASE) == ("revenue_growht",)
    assert unread_assumptions(FORMULAS, scenarios, BASE) == ()


# --- previewing across a scenario ------------------------------------------

def test_a_preview_in_a_child_scenario_starts_from_what_it_inherits(
    scenarios, environment
):
    variant = scenarios.with_scenario(
        Scenario(id="upside", name="Upside", parent_id=BASE)
    ).override(
        "upside", "revenue_growth", D("0.15"),
        owner="larry", rationale="top of the guided range",
    )
    impact = preview(
        formulas=FORMULAS, base_environment=environment, scenarios=variant,
        scenario_id="upside", code="revenue_growth", proposed=D("0.18"),
    )
    assert impact.before == D("0.15"), "the child's own value, not the base's"
    moved = {item.target: item.after for item in impact.moved}
    assert moved["revenue"] == D("1180000")


def test_the_two_scenarios_calculate_to_different_models(scenarios, environment):
    variant = scenarios.with_scenario(
        Scenario(id="upside", name="Upside", parent_id=BASE)
    ).override(
        "upside", "revenue_growth", D("0.15"), owner="larry", rationale="top of range",
    )
    base_model = model_for(FORMULAS, environment, variant, BASE)
    upside_model = model_for(FORMULAS, environment, variant, "upside")
    assert base_model.value("revenue") == D("1100000")
    assert upside_model.value("revenue") == D("1150000")
    assert base_model.fingerprint != upside_model.fingerprint, (
        "9.12 records a calculated value against its scenario; two scenarios "
        "that fingerprint alike could not be told apart"
    )


def test_a_units_mismatch_between_an_assumption_and_its_formula_is_caught(environment):
    """18.12, at the seam Section 14 and Section 18 meet.

    An assumption declared in percent -- 10, meaning ten percent -- handed to a
    formula that multiplies by it is out by a factor of 100.
    """
    from apps.api.app.formula.units import UnitError

    wrong = ScenarioSet(
        (base_scenario("larry"),),
        (
            Assumption(
                code="revenue_growth", name="Revenue growth", value=D("10"),
                unit="percent", source_type=SourceType.COMPANY_GUIDANCE,
                evidence=Evidence(document_id="doc-1", page=31, date="2026-02-14"),
                rationale="ten percent, as guided", owner="larry",
            ),
            assumption("cogs_pct_revenue", "0.60"),
        ),
    )
    with pytest.raises(UnitError, match="percent"):
        model_for(FORMULAS, environment, wrong, BASE)


def test_a_ratio_declared_as_a_ratio_passes_the_same_check(scenarios, environment):
    assert model_for(FORMULAS, environment, scenarios, BASE).value("revenue") == D("1100000")
    assert RATIO.name == "ratio"
