"""Items 89-96: the assumption schema, scenarios, the workflow and the gate.

The interesting tests are the refusals, and there are three families of them.

The **evidence rules** (14.4.f, 14.4.g) are per source type, and each one is
there because taking the clause literally would let an unreviewable number
through: a company filing cited without a page, a beta with no observation
date, a historical driver that does not say which year it was measured over.

The **scenario rules** (14.6, 14.9) refuse a label that asserts something the
model does not contain -- an Upside identical to Base, a scenario called
"Likely case" in a system that models no distribution.

The **gate** (14.1) is the one that decides whether a forecast may run at all,
and it is tested per period rather than per code, because a driver scoped to
one of five forecast years is missing from four of them.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.assumptions.drivers import BY_CODE, DRIVERS, REQUIRED, driver
from apps.api.app.assumptions.gate import evaluate
from apps.api.app.assumptions.scenarios import (
    BASE,
    Probability,
    Scenario,
    ScenarioError,
    ScenarioSet,
    base_scenario,
)
from apps.api.app.assumptions.schema import (
    Assumption,
    AssumptionError,
    Evidence,
    SourceType,
    Status,
)
from apps.api.app.assumptions.workflow import (
    LEGAL_TRANSITIONS,
    WorkflowError,
    transition,
)

D = Decimal

FILING = Evidence(document_id="doc-1", page=31, date="2026-02-14")


def make(code="revenue_growth", value="0.08", **kwargs):
    defaults = dict(
        code=code,
        name=code.replace("_", " ").capitalize(),
        value=D(value),
        unit="ratio",
        source_type=SourceType.COMPANY_GUIDANCE,
        evidence=FILING,
        rationale="the midpoint of the guided range",
        owner="larry",
    )
    defaults.update(kwargs)
    return Assumption(**defaults)


# --- item 89: the schema (14.2, 14.3, 14.4) ---------------------------------

def test_the_five_statuses_are_exactly_14_2s():
    assert [s.value for s in Status] == [
        "Draft", "Needs Source", "Reviewed", "Approved", "Rejected"
    ]


def test_the_six_source_types_are_exactly_14_3s():
    assert [s.value for s in SourceType] == [
        "Company Guidance", "Company Filing", "External Market Data",
        "Historical Driver", "Analyst Assumption", "Scenario Override",
    ]


def test_only_draft_needs_source_and_rejected_block_a_calculation():
    """14.1. Reviewed and Approved are answers; the other three are not."""
    blocking = {s for s in Status if s.blocks_calculation}
    assert blocking == {Status.DRAFT, Status.NEEDS_SOURCE, Status.REJECTED}


@pytest.mark.parametrize(
    "missing,fragment",
    [
        (dict(code=" "), "needs a code"),
        (dict(name=" "), "needs a clear name"),
        (dict(owner=" "), "needs an owner"),
        (dict(rationale=" "), "needs a rationale"),
        (dict(unit="furlongs"), "not a declared unit"),
    ],
)
def test_every_14_4_field_is_required(missing, fragment):
    with pytest.raises(AssumptionError, match=fragment):
        make(**missing)


def test_a_float_value_is_refused_rather_than_converted():
    """4.4, at the boundary where a number enters the model.

    Constructed directly rather than through `make`, which would convert the
    float to a Decimal on the way in and test nothing.
    """
    from model.numeric import PrecisionError

    with pytest.raises(PrecisionError, match="arrived as a float"):
        Assumption(
            code="c", name="n", value=0.08, unit="ratio", owner="larry",
            rationale="because of things",
            source_type=SourceType.ANALYST_ASSUMPTION, evidence=Evidence(),
        )


# --- item 91: the evidence rules -------------------------------------------

def test_a_filing_cited_without_a_page_is_not_a_citation():
    with pytest.raises(AssumptionError, match="STEP 2 makes the page"):
        make(
            source_type=SourceType.COMPANY_FILING,
            evidence=Evidence(document_id="doc-1"),
        )


def test_market_data_without_an_observation_date_is_not_reproducible():
    with pytest.raises(AssumptionError, match="observation date"):
        make(
            source_type=SourceType.EXTERNAL_MARKET_DATA,
            evidence=Evidence(url="https://example.test/beta"),
        )


def test_market_data_without_a_url_has_no_source():
    with pytest.raises(AssumptionError, match="URL is required"):
        make(
            source_type=SourceType.EXTERNAL_MARKET_DATA,
            evidence=Evidence(date="2026-09-01"),
        )


def test_a_historical_driver_must_say_which_periods_it_measured():
    """A DSO of 59.9 days means nothing without saying 59.9 days of which year."""
    with pytest.raises(AssumptionError, match="which year"):
        make(
            code="dso", unit="days", value="59.9",
            source_type=SourceType.HISTORICAL_DRIVER,
            evidence=Evidence(),
        )
    ok = make(
        code="dso", unit="days", value="59.9",
        source_type=SourceType.HISTORICAL_DRIVER,
        evidence=Evidence(measured_over=("2025A",)),
    )
    assert "measured over 2025A" in ok.evidence.describe()


def test_guidance_must_carry_the_date_it_was_given():
    with pytest.raises(AssumptionError, match="superseded"):
        make(evidence=Evidence(document_id="doc-1", page=31))


def test_self_review_is_recorded_rather_than_refused():
    """14.4.i. This system is single-user; refusing would only invite a fiction."""
    assert make(reviewer="larry").is_self_reviewed
    assert not make(reviewer="someone else").is_self_reviewed
    assert not make().is_self_reviewed, "no reviewer is not self-review"


def test_every_source_type_maps_onto_one_of_the_engines_three_bases():
    """The fuller vocabulary must not lose STEP 10's distinction."""
    bases = {
        make(source_type=kind, **_extras_for(kind)).engine_basis
        for kind in SourceType
    }
    assert bases == {"company_guidance", "external_research", "model_assumption"}


def _extras_for(kind: SourceType) -> dict:
    """The evidence each source type's own rule demands."""
    if kind is SourceType.EXTERNAL_MARKET_DATA:
        return {"evidence": Evidence(url="https://example.test", date="2026-09-01")}
    if kind is SourceType.HISTORICAL_DRIVER:
        return {"evidence": Evidence(measured_over=("2025A",))}
    if kind is SourceType.SCENARIO_OVERRIDE:
        return {"evidence": Evidence(), "overrides": "base:revenue_growth"}
    return {"evidence": FILING}


def test_a_scenario_override_must_name_what_it_overrides():
    with pytest.raises(AssumptionError, match="inherited assumption lineage"):
        make(source_type=SourceType.SCENARIO_OVERRIDE, evidence=Evidence())


# --- item 92: scenarios (14.6, 14.7, 14.9) ----------------------------------

def test_a_set_needs_a_base_scenario():
    with pytest.raises(ScenarioError, match="needs a 'base' scenario"):
        ScenarioSet((Scenario(id="upside", name="Upside"),))


@pytest.mark.parametrize(
    "name", ["Likely case", "Expected case", "P90", "High confidence case",
             "Probable outcome", "Median case"]
)
def test_a_name_that_implies_probability_is_refused(name):
    """14.9, and 1.19 behind it: this system models no distribution."""
    with pytest.raises(ScenarioError, match=r"likelihood|distribution"):
        Scenario(id="x", name=name)


def test_a_probability_implying_name_is_allowed_once_it_is_sourced():
    """14.9's escape clause, read strictly: modelled AND sourced."""
    scenario = Scenario(
        id="x", name="Likely case",
        probability=Probability(D("0.6"), "internal forecast poll", "2026-09-01"),
    )
    assert scenario.name == "Likely case"


def test_a_probability_without_a_source_does_not_unlock_the_name():
    with pytest.raises(ScenarioError, match="explicitly modelled AND sourced"):
        Probability(D("0.6"), "", "")


def test_a_variant_that_differs_in_nothing_is_reported(base_set):
    """14.6: a named case the model does not contain is a label."""
    with_upside = base_set.with_scenario(
        Scenario(id="upside", name="Upside", parent_id=BASE)
    )
    problem = with_upside.check_differences("upside")
    assert "differs from 'base' in nothing" in problem
    assert with_upside.differences("upside") == ()


def test_an_override_keeps_its_lineage(base_set):
    """14.7."""
    scenarios = base_set.with_scenario(
        Scenario(id="upside", name="Upside", parent_id=BASE)
    ).override(
        "upside", "revenue_growth", D("0.12"),
        owner="larry", rationale="top of the guided range",
    )
    assert scenarios.check_differences("upside") == ""
    assert scenarios.differences("upside") == (("revenue_growth", D("0.08"), D("0.12")),)

    resolved = scenarios.resolve("upside")
    override = resolved["revenue_growth"]
    assert override.from_scenario == "upside"
    assert override.assumption.inherited_from == BASE
    assert override.assumption.overrides == "base:revenue_growth"
    assert override.assumption.source_type is SourceType.SCENARIO_OVERRIDE
    # The base's evidence travels with it: the evidence for the number being
    # departed from is what a reviewer needs to judge the departure.
    assert override.assumption.evidence.document_id == "doc-1"

    inherited = resolved["dso"]
    assert inherited.from_scenario == BASE and inherited.is_inherited


def test_overriding_something_the_parent_does_not_carry_is_refused(base_set):
    """It would invent a driver rather than vary one."""
    scenarios = base_set.with_scenario(Scenario(id="upside", name="Upside"))
    with pytest.raises(AssumptionError, match="invent a driver"):
        scenarios.override("upside", "made_up", D(1), owner="l", rationale="r")


def test_inheritance_cannot_be_circular():
    with pytest.raises(ScenarioError, match="circular"):
        ScenarioSet((
            base_scenario(),
            Scenario(id="a", name="A", parent_id="b"),
            Scenario(id="b", name="B", parent_id="a"),
        ))


def test_a_grandchild_resolves_through_both_parents(base_set):
    scenarios = (
        base_set
        .with_scenario(Scenario(id="upside", name="Upside", parent_id=BASE))
        .override("upside", "revenue_growth", D("0.12"), owner="l", rationale="r")
    )
    scenarios = scenarios.with_scenario(
        Scenario(id="upside_fast", name="Upside with faster collection", parent_id="upside")
    ).override("upside_fast", "dso", D("45"), owner="l", rationale="collection programme")

    assert scenarios.lineage("upside_fast") == ("upside_fast", "upside", BASE)
    resolved = scenarios.resolve("upside_fast")
    assert resolved["dso"].from_scenario == "upside_fast"
    assert resolved["revenue_growth"].from_scenario == "upside"
    assert resolved["inventory_days"].from_scenario == BASE


# --- item 95: the workflow --------------------------------------------------

def test_draft_cannot_go_straight_to_approved():
    with pytest.raises(WorkflowError, match="four statuses and a decoration"):
        transition(make(), Status.APPROVED, actor="larry", reason="looks fine")


def test_a_status_change_needs_a_reason():
    with pytest.raises(WorkflowError, match="needs a written reason"):
        transition(make(), Status.REVIEWED, actor="larry", reason="", reviewer="larry")


def test_reviewed_needs_a_named_reviewer():
    with pytest.raises(WorkflowError, match=r"named.*reviewer"):
        transition(make(), Status.REVIEWED, actor="larry", reason="checked p.31")


def test_a_no_op_transition_is_refused():
    with pytest.raises(WorkflowError, match="already Draft"):
        transition(make(), Status.DRAFT, actor="larry", reason="nothing changed")


def test_the_happy_path_records_who_and_why():
    reviewed, first = transition(
        make(), Status.REVIEWED, actor="larry", reason="checked against p.31",
        reviewer="larry",
    )
    approved, second = transition(
        reviewed, Status.APPROVED, actor="larry", reason="accepted for the base case"
    )
    assert approved.status is Status.APPROVED
    assert approved.reviewer == "larry" and approved.is_self_reviewed
    assert first.was is Status.DRAFT and first.became is Status.REVIEWED
    assert "checked against p.31" in first.describe()
    assert second.became is Status.APPROVED


def test_an_approved_assumption_is_reopened_through_draft_not_re_approved():
    """Approved -> Reviewed is not a legal move: there is nothing to review."""
    reviewed, _ = transition(
        make(), Status.REVIEWED, actor="larry", reason="checked", reviewer="larry"
    )
    approved, _ = transition(
        reviewed, Status.APPROVED, actor="larry", reason="accepted"
    )
    with pytest.raises(WorkflowError, match="cannot go from Approved to Reviewed"):
        transition(approved, Status.REVIEWED, actor="larry", reason="second look")

    reopened, change = transition(
        approved, Status.DRAFT, actor="larry", reason="guidance was updated"
    )
    assert reopened.status is Status.DRAFT
    assert change.was is Status.APPROVED


def test_every_declared_transition_is_reachable_from_its_source():
    """The diagram in the module docstring and the table cannot drift."""
    assert set(LEGAL_TRANSITIONS) == set(Status)
    for source, allowed in LEGAL_TRANSITIONS.items():
        assert source not in allowed, f"{source} may not transition to itself"


# --- item 96 and 14.1: the gate --------------------------------------------

PERIODS = ("2026E", "2027E")


def test_the_gate_names_every_missing_driver_per_period(base_set):
    result = evaluate(base_set, BASE, PERIODS)
    assert not result.may_calculate
    assert any("capex" in item for item in result.missing)
    assert any("2026E" in item for item in result.missing)


def test_a_driver_scoped_to_one_year_is_missing_from_the_others(approved_set):
    """The reason the gate walks periods rather than codes."""
    without = ScenarioSet(
        approved_set.scenarios,
        tuple(a for a in approved_set.assumptions if a.code != "revenue_growth"),
    )
    narrowed = without.with_assumption(
        make(code="revenue_growth", periods=("2026E",), status=Status.APPROVED,
             reviewer="larry")
    )
    result = evaluate(narrowed, BASE, PERIODS)
    assert any("revenue_growth for 2027E" in item for item in result.missing)
    assert not any("revenue_growth for 2026E" in item for item in result.missing)


def test_a_period_scoped_driver_shadows_the_all_years_one(approved_set):
    """STEP 14's own pattern: an all-years default, overridden where it differs.

    The engine resolves `(name, year)` before `(name, None)`; without the same
    rule here the two would race on insertion order.
    """
    both = approved_set.with_assumption(
        make(code="revenue_growth", value="0.15", periods=("2027E",),
             status=Status.APPROVED, reviewer="larry")
    )
    assert both.resolve(BASE, period="2027E")["revenue_growth"].assumption.value == D("0.15")
    assert both.resolve(BASE, period="2026E")["revenue_growth"].assumption.value == D("0.05")


def test_a_draft_driver_blocks_the_calculation(full_set):
    result = evaluate(full_set, BASE, PERIODS)
    assert not result.may_calculate
    assert result.unresolved
    assert all(status == "Draft" for _, status in result.unresolved)
    assert "not an answer yet" in result.describe()


def test_declaring_both_methodologies_is_refused(approved_set):
    """STEP 14/18: one stated methodology per line."""
    # The fixture supplies `cogs_amount`; declaring the percentage as well is
    # the ambiguity STEP 14 refuses.
    both = approved_set.with_assumption(
        make(code="cogs_pct_revenue", unit="ratio", value="0.6",
             status=Status.APPROVED, reviewer="larry")
    )
    result = evaluate(both, BASE, PERIODS)
    assert not result.may_calculate
    assert any("cogs_amount and cogs_pct_revenue" in item for item in result.ambiguous)


def test_an_approved_set_may_calculate_and_says_what_was_self_reviewed(approved_set):
    result = evaluate(approved_set, BASE, PERIODS)
    assert result.may_calculate, result.describe()
    assert result.self_reviewed
    assert "approved by their own owner" in result.describe()


def test_a_rejected_driver_blocks_even_though_it_has_a_status(approved_set):
    """14.1 read literally is satisfied by any status. Rejected is an answer of no."""
    rejected = approved_set.with_assumption(
        make(code="dso", unit="days", value="59.9", status=Status.REJECTED,
             reviewer="larry", source_type=SourceType.HISTORICAL_DRIVER,
             evidence=Evidence(measured_over=("2025A",))),
    )
    result = evaluate(rejected, BASE, PERIODS)
    assert not result.may_calculate
    assert ("dso for 2026E", "Rejected") in result.unresolved


# --- the driver table must stay a reading of the engine --------------------

def test_every_required_driver_is_read_by_the_forecast():
    import inspect

    from model import forecast

    source = inspect.getsource(forecast)
    for item in DRIVERS:
        assert f'"{item.code}"' in source, (
            f"{item.code} is in the driver table and model/forecast.py never "
            "reads it, so the 14.1 gate would demand something the forecast "
            "does not use"
        )


def test_every_structural_driver_the_forecast_requires_is_in_the_table():
    """The direction that actually matters: a gate that lets a halt through."""
    import inspect
    import re

    from model import forecast

    source = inspect.getsource(forecast)
    required = set(re.findall(r'assumptions\.get\(\s*"([a-z_]+)"', source))
    # `_pick_driver` reads its two names from parameters, so its pairs are
    # collected from the call sites instead.
    required |= set(re.findall(r'"([a-z_]+_pct_[a-z_]+|[a-z_]+_amount)"', source))
    missing = sorted(required - set(BY_CODE))
    assert not missing, (
        f"model/forecast.py requires {missing}, which the driver table does not "
        "carry: the 14.1 gate would pass a model that then halts"
    )


def test_days_drivers_are_declared_in_days_not_ratios():
    """0.164 where 59.9 was meant is a receivable four hundred times too small."""
    for code in ("dso", "inventory_days", "dpo"):
        assert driver(code).unit == "days"


def test_a_segment_scoped_driver_resolves_to_its_base_driver():
    assert driver("revenue_growth.north_america").code == "revenue_growth"


def test_the_required_set_is_deduplicated():
    """A one-of-two pair appears once, not twice."""
    assert len(REQUIRED) == len(set(REQUIRED))
    assert frozenset({"cogs_pct_revenue", "cogs_amount"}) in REQUIRED


# --- fixtures ---------------------------------------------------------------

@pytest.fixture
def base_set():
    """A base scenario with three of the eleven required drivers."""
    return ScenarioSet(
        (base_scenario("larry"),),
        (
            make(code="revenue_growth", value="0.08"),
            make(code="dso", unit="days", value="59.9",
                 source_type=SourceType.HISTORICAL_DRIVER,
                 evidence=Evidence(measured_over=("2025A",))),
            make(code="inventory_days", unit="days", value="77.9",
                 source_type=SourceType.HISTORICAL_DRIVER,
                 evidence=Evidence(measured_over=("2025A",))),
        ),
    )


def _every_required(status=Status.DRAFT, reviewer=""):
    """One assumption per required choice, taking the first member of each."""
    out = []
    for choice in REQUIRED:
        code = sorted(choice)[0]
        item = BY_CODE[code]
        kwargs = dict(code=code, unit=item.unit, status=status, reviewer=reviewer)
        if item.unit == "days":
            kwargs.update(
                value="60",
                source_type=SourceType.HISTORICAL_DRIVER,
                evidence=Evidence(measured_over=("2025A",)),
            )
        elif item.unit == "currency":
            kwargs.update(value="100000")
        else:
            kwargs.update(value="0.05")
        out.append(make(**kwargs))
    return tuple(out)


@pytest.fixture
def full_set():
    return ScenarioSet((base_scenario("larry"),), _every_required())


@pytest.fixture
def approved_set():
    return ScenarioSet(
        (base_scenario("larry"),),
        _every_required(status=Status.APPROVED, reviewer="larry"),
    )
