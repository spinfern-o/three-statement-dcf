"""Items 79-86: units, evaluation, the graph, and recalculation.

The tests worth reading here are the negative ones. An evaluator that produces
the right number on good input is the easy half; what Section 18 actually asks
for is an evaluator that refuses the wrong input loudly, and a recalculation
that does LESS work than a full one while giving the same answer.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.formula import units as u
from apps.api.app.formula.calculate import calculate, environment_from, recalculate
from apps.api.app.formula.evaluate import (
    DivisionByZeroRefused,
    Environment,
    EvaluationError,
    MissingInput,
    evaluate,
)
from apps.api.app.formula.graph import CycleError, DependencyGraph
from apps.api.app.formula.registry import (
    FormulaDefinition,
    FormulaSet,
    RegistryError,
    calculation_fingerprint,
)

D = Decimal


def formula(code, target, expression, unit="currency", version=1):
    return FormulaDefinition(
        code=code,
        target=target,
        expression=expression,
        output_unit=unit,
        version=version,
        definition=f"{target} as {expression}",
    )


def money(**values):
    return environment_from({k: (D(v), u.CURRENCY) for k, v in values.items()})


# --- item 82: units (18.12) -------------------------------------------------


def test_currency_and_shares_cannot_be_added():
    with pytest.raises(u.UnitError, match="cannot add"):
        u.add(u.CURRENCY, u.SHARES)


def test_a_percent_and_a_ratio_cannot_be_added_although_both_are_dimensionless():
    """The error dimensions alone would miss, and it is a factor of 100."""
    with pytest.raises(u.UnitError, match="factor of 100"):
        u.add(u.RATIO, u.PERCENT)


@pytest.mark.parametrize("other", [u.CURRENCY, u.RATIO, u.SHARES])
def test_a_percent_refuses_to_be_multiplied_or_divided(other):
    with pytest.raises(u.UnitError, match="percent"):
        u.multiply(u.PERCENT, other)
    with pytest.raises(u.UnitError, match="percent"):
        u.divide(other, u.PERCENT)


def test_currency_squared_has_no_meaning_and_is_refused():
    with pytest.raises(u.UnitError, match="no declared unit carries"):
        u.multiply(u.CURRENCY, u.CURRENCY)


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (u.CURRENCY, u.RATIO, "currency"),
        (u.RATIO, u.CURRENCY, "currency"),
        (u.RATIO, u.RATIO, "ratio"),
    ],
)
def test_scaling_by_a_dimensionless_quantity_keeps_the_dimension(left, right, expected):
    assert u.multiply(left, right).name == expected


@pytest.mark.parametrize(
    "left,right,expected",
    [
        (u.CURRENCY, u.CURRENCY, "ratio"),
        (u.CURRENCY, u.SHARES, "currency_per_share"),
    ],
)
def test_division_subtracts_dimensions(left, right, expected):
    assert u.divide(left, right).name == expected


def test_the_declared_unit_is_verified_not_inferred():
    """`currency / currency` could be a margin or a multiple. Only intent knows."""
    environment = money(a="10", b="5")
    assert evaluate("a / b", environment, u.RATIO).value == D(2)
    assert evaluate("a / b", environment, u.MULTIPLE).value == D(2)
    with pytest.raises(u.UnitError, match="declares"):
        evaluate("a / b", environment, u.CURRENCY)


def test_an_undeclared_unit_name_is_refused():
    with pytest.raises(u.UnitError, match="not a declared unit"):
        u.unit_for("furlongs")


# --- items 81, 83: evaluation and its refusals ------------------------------


def test_a_missing_input_is_not_zero():
    """18.14, stated as the difference it makes."""
    with pytest.raises(MissingInput, match="It is not zero"):
        evaluate("revenue - cogs", money(revenue="100"))


def test_a_missing_input_suggests_a_path_with_the_same_leaf_name():
    with pytest.raises(MissingInput, match="Did you mean"):
        evaluate("cogs", money(**{"income_statement.cogs": "5"}))


def test_division_by_zero_names_the_expression_that_was_zero():
    with pytest.raises(DivisionByZeroRefused, match=r"\(a - b\)"):
        evaluate("c / (a - b)", money(a="5", b="5", c="1"))


def test_a_fractional_exponent_is_refused_rather_than_rounded():
    """4.12: only integer exponentiation is exact in decimal arithmetic."""
    with pytest.raises(EvaluationError, match="not an integer"):
        evaluate("a ^ 0.5", money(a="4"))


def test_a_negative_exponent_on_zero_is_a_division_by_zero():
    with pytest.raises(DivisionByZeroRefused):
        evaluate("a ^ -1", money(a="0"))


def test_the_trace_carries_the_formula_and_the_exact_inputs():
    """18.10 and 18.11, which is what makes a calculated cell reviewable."""
    result = evaluate(
        "(revenue - cogs) / revenue", money(revenue="1250000", cogs="750000"), u.RATIO
    )
    assert result.formula == "((revenue - cogs) / revenue)"
    assert result.substituted == "((1,250,000 - 750,000) / 1,250,000)"
    assert result.inputs == {"revenue": D("1250000"), "cogs": D("750000")}
    assert result.value == D("0.4")
    assert "= 0.4" in result.explain()


def test_the_substituted_trace_is_the_exact_input_not_a_display_value():
    """18.11 says exact. A trace that rounds cannot be checked by hand."""
    result = evaluate("a + b", money(a="1234.56789", b="0.00001"))
    assert "1,234.56789" in result.substituted
    assert result.value == D("1234.56790")


def test_a_bare_number_may_scale_a_currency_and_may_not_be_added_to_one():
    environment = money(revenue="100")
    assert evaluate("revenue * 2", environment, u.CURRENCY).value == D(200)
    with pytest.raises(u.UnitError):
        evaluate("revenue + 2", environment)


def test_min_and_max_require_one_unit_across_every_argument():
    environment = Environment().put("a", D(1), u.CURRENCY).put("b", D(2), u.SHARES)
    with pytest.raises(u.UnitError):
        evaluate("min(a, b)", environment)


def test_the_environment_is_a_mapping_not_an_object():
    """18.3: resolution cannot reach a method, because there is no object."""
    environment = money(a="1")
    assert environment.has("a") and not environment.has("keys")
    with pytest.raises(MissingInput):
        evaluate("keys", environment)


# --- items 79, 80: the graph ------------------------------------------------

CHAIN = FormulaSet(
    (
        formula("A", "gross_profit", "revenue - cogs"),
        formula("B", "ebit", "gross_profit - operating_expenses"),
        formula("C", "pretax", "ebit - interest_expense"),
    )
)


def test_the_order_puts_every_formula_after_what_it_reads():
    order = DependencyGraph(CHAIN).order()
    assert order == ("gross_profit", "ebit", "pretax")


def test_the_order_is_deterministic_across_runs():
    """18.7 needs it: an order that varies makes a fingerprint vary."""
    wide = FormulaSet(tuple(formula(f"C{i}", f"t{i}", "revenue - cogs") for i in range(12)))
    orders = {DependencyGraph(wide).order() for _ in range(5)}
    assert len(orders) == 1


def test_required_inputs_are_what_the_graph_does_not_produce():
    assert DependencyGraph(CHAIN).required_inputs == frozenset(
        {"revenue", "cogs", "operating_expenses", "interest_expense"}
    )


def test_a_cycle_is_named_before_anything_is_evaluated():
    """18.6. The three-statement circularity, which is not hypothetical."""
    circular = FormulaSet(
        (
            formula("A", "interest_expense", "debt * rate"),
            formula("B", "net_income", "ebit - interest_expense"),
            formula("C", "debt", "opening_debt + net_income"),
        )
    )
    with pytest.raises(CycleError) as caught:
        DependencyGraph(circular).order()
    message = str(caught.value)
    assert "debt -> interest_expense -> net_income -> debt" in message
    assert "beginning debt" in message, "the message names the usual way out"


def test_a_self_reference_is_refused_when_the_formula_is_defined():
    with pytest.raises(RegistryError, match="refers to itself"):
        formula("A", "cash", "cash + 1")


def test_two_formulas_cannot_compute_the_same_target():
    with pytest.raises(RegistryError, match="has no definition"):
        FormulaSet((formula("A", "ebit", "a - b"), formula("B", "ebit", "c - d")))


def test_a_code_cannot_be_reused():
    with pytest.raises(RegistryError, match="used twice"):
        FormulaSet((formula("A", "x", "a"), formula("A", "y", "b")))


# --- item 85: incremental recalculation (18.8) ------------------------------


def test_only_the_descendants_of_a_change_are_recalculated():
    first = calculate(
        CHAIN,
        money(
            revenue="1250000",
            cogs="750000",
            operating_expenses="300000",
            interest_expense="18000",
        ),
    )
    second = recalculate(
        first,
        money(
            revenue="1250000",
            cogs="750000",
            operating_expenses="310000",
            interest_expense="18000",
        ),
        ("operating_expenses",),
    )

    assert second.recalculated == ("ebit", "pretax")
    assert second.carried_over == ("gross_profit",)
    # Equal values would not prove it was not recomputed. Identity does.
    assert second.cells["gross_profit"] is first.cells["gross_profit"]
    assert second.value("ebit") == D("190000")
    assert second.changed_from_previous() == ("ebit", "pretax")


def test_recalculation_gives_the_same_answer_as_calculating_from_scratch():
    """18.8 is an optimisation, and an optimisation that changes a number is a bug."""
    before = money(revenue="100", cogs="40", operating_expenses="30", interest_expense="5")
    after = money(revenue="130", cogs="40", operating_expenses="30", interest_expense="5")
    incremental = recalculate(calculate(CHAIN, before), after, ("revenue",))
    complete = calculate(CHAIN, after)
    assert {t: c.value for t, c in incremental.cells.items()} == {
        t: c.value for t, c in complete.cells.items()
    }
    assert incremental.fingerprint == complete.fingerprint


def test_the_prior_model_is_preserved():
    """18.9."""
    first = calculate(
        CHAIN, money(revenue="100", cogs="40", operating_expenses="30", interest_expense="5")
    )
    second = recalculate(
        first,
        money(revenue="200", cogs="40", operating_expenses="30", interest_expense="5"),
        ("revenue",),
    )
    assert second.previous is first
    assert second.version == 2
    assert first.value("gross_profit") == D(60), "the old model still reads as it did"
    assert second.value("gross_profit") == D(160)


# --- item 84: fingerprints (18.7) -------------------------------------------


def test_the_same_inputs_over_the_same_formulas_hash_the_same():
    inputs = dict(revenue="100", cogs="40", operating_expenses="30", interest_expense="5")
    assert (
        calculate(CHAIN, money(**inputs)).fingerprint
        == calculate(CHAIN, money(**inputs)).fingerprint
    )


def test_one_changed_input_changes_the_fingerprint():
    base = dict(revenue="100", cogs="40", operating_expenses="30", interest_expense="5")
    moved = dict(base, cogs="40.0000001")
    assert (
        calculate(CHAIN, money(**base)).fingerprint != calculate(CHAIN, money(**moved)).fingerprint
    )


def test_a_changed_formula_version_changes_the_fingerprint():
    other = FormulaSet(
        (
            formula("A", "gross_profit", "revenue - cogs", version=2),
            formula("B", "ebit", "gross_profit - operating_expenses"),
            formula("C", "pretax", "ebit - interest_expense"),
        )
    )
    inputs = dict(revenue="100", cogs="40", operating_expenses="30", interest_expense="5")
    assert (
        calculate(CHAIN, money(**inputs)).fingerprint
        != calculate(other, money(**inputs)).fingerprint
    )


def test_trailing_zeros_are_a_different_calculation():
    """4.14: the precision a figure was reported to is a fact about it."""
    assert calculation_fingerprint(CHAIN, {"a": D("1.0")}) != calculation_fingerprint(
        CHAIN, {"a": D("1")}
    )


def test_reformatting_a_definition_does_not_change_the_fingerprint():
    """An editorial change must not make a stored calculation look stale."""
    a = formula("A", "x", "revenue - cogs")
    b = FormulaDefinition(
        code="A",
        target="x",
        expression="revenue  -  cogs",
        output_unit="currency",
        definition="a completely different sentence",
        rule="STEP 99",
    )
    assert a.fingerprint == b.fingerprint


# --- 18.14 through a whole model -------------------------------------------


def test_an_uncomputable_cell_stays_absent_and_takes_its_dependents_with_it():
    """Not zero, and not a partial subtotal. The same rule as STEP 5."""
    partial = calculate(CHAIN, money(revenue="100", cogs="40"), strict=False)
    assert partial.value("gross_profit") == D(60)
    assert "ebit" in partial.unavailable
    assert "pretax" in partial.unavailable
    assert "operating_expenses" in partial.unavailable["ebit"]
    # The dependent refuses for its own reason, not by inheriting a zero.
    assert "ebit" in partial.unavailable["pretax"]


def test_strict_refuses_rather_than_reporting_a_gap():
    with pytest.raises(MissingInput):
        calculate(CHAIN, money(revenue="100", cogs="40"), strict=True)


def test_a_unit_error_is_refused_even_when_gaps_are_tolerated():
    """A missing input is a fact about the filing; a unit error is a defect."""
    broken = FormulaSet(
        (
            FormulaDefinition(
                code="A",
                target="nonsense",
                expression="revenue * revenue",
                output_unit="currency",
                definition="deliberately wrong",
            ),
        )
    )
    with pytest.raises(u.UnitError):
        calculate(broken, money(revenue="100"), strict=False)


def test_a_division_by_zero_is_a_data_state_not_a_defect():
    """4.12: a measure against zero is UNDEFINED, which is a state a figure
    can legitimately be in.

    `gross_profit / revenue` is a correct formula, and a company with no
    revenue has no gross margin. Not strict, that is reported with its reason;
    strict, it refuses, because an export must not move on a figure nobody has.
    """
    margin = FormulaSet(
        (
            FormulaDefinition(
                code="M",
                target="gross_margin",
                expression="gross_profit / revenue",
                output_unit="ratio",
                definition="gross profit over revenue",
            ),
        )
    )
    environment = money(gross_profit="0", revenue="0")

    tolerant = calculate(margin, environment, strict=False)
    assert tolerant.value("gross_margin") is None
    assert "division by zero" in tolerant.unavailable["gross_margin"]

    with pytest.raises(DivisionByZeroRefused):
        calculate(margin, environment, strict=True)
