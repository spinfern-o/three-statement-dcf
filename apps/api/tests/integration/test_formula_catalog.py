"""Items 87 and 88: the formula engine as an independent implementation.

4.15 requires a benchmark whose primary engine and benchmark "must not call
the same helper function". `tests/test_precision.py` does that for the
forecast and the valuation, by recomputing them from the YAML with its own
Decimal construction.

This file does it for the historical derivations, and the independence is
structural rather than promised. `model/statements.py:Ledger._try_derive`
walks `accounts.DERIVED` as tuples of account names and accumulates into a
running total. `apps/api/app/formula/` parses a text expression into a syntax
tree, orders a dependency graph, and evaluates the tree node by node. The two
share the DERIVED table -- deliberately, so a component added to a subtotal
appears in both -- and share no arithmetic at all.

Where they differ is instructive and is tested: `_try_derive` treats a
residual "and anything else" line as zero when absent, silently. The formula
engine refuses an unresolved reference outright (18.14), so the policy lives
in `ledger_environment`, which supplies the zero AND records that it did. A
subtotal resting on an assumed-nil residual is then visible, which it is not
inside `_try_derive`.
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from apps.api.app.formula.calculate import calculate
from apps.api.app.formula.catalog import (
    CODES,
    computable_subset,
    derivation_formulas,
    ledger_environment,
)
from apps.api.app.formula.evaluate import Environment, evaluate
from apps.api.app.formula.units import CURRENCY, RATIO
from model import accounts
from model.accounts import Statement
from model.numeric import ZERO
from model.statements import Ledger

D = Decimal


@pytest.fixture(scope="module")
def formulas():
    return derivation_formulas()


# --- the catalogue and the chart cannot drift -------------------------------

def test_every_derived_subtotal_has_a_catalogue_row(formulas):
    """The registry is generated from `accounts.DERIVED`, so this cannot fail
    by omission -- which is the point. It fails if someone hand-edits one."""
    assert set(formulas.targets) == set(accounts.DERIVED)
    assert set(CODES) == set(accounts.DERIVED)


@pytest.mark.parametrize("account", sorted(accounts.DERIVED))
def test_the_expression_is_the_charts_own_components(formulas, account):
    plus, minus = accounts.DERIVED[account]
    definition = formulas.for_target(account)
    assert definition.inputs == frozenset(plus) | frozenset(minus)
    assert definition.rounding == "exact", (
        "a sum of currency amounts contains no division, so it is exact under "
        "4.12's second clause"
    )


def test_every_formula_carries_a_written_definition(formulas):
    """11.3's lesson, applied to the catalogue: a row nobody can read is a row
    nobody can check."""
    for definition in formulas:
        assert len(definition.definition.split()) >= 5, definition.code
        assert definition.rule, definition.code


#: 4.16 names the outputs a benchmark must compare. These are the ones this
#: file's subject -- the historical derivations -- is responsible for.
SECTION_4_16_DERIVATIONS = (
    "gross_profit", "ebit", "pretax_income", "net_income",
    "total_assets", "total_liabilities", "total_equity",
    "cash_flow_from_operations", "cash_flow_from_investing",
    "cash_flow_from_financing",
)


def test_the_4_16_list_is_covered_except_the_line_the_chart_lacks(formulas):
    """4.16 also names EBITDA, and the chart has no `ebitda` line (F-17).

    Recorded as an assertion rather than a comment so it stops being true the
    day the chart grows one.
    """
    assert set(SECTION_4_16_DERIVATIONS) <= set(formulas.targets)
    assert "ebitda" not in accounts.INCOME_ACCOUNTS, (
        "the chart now has an EBITDA line; 4.16 requires it be compared against "
        "the benchmark, so add it to this file and to the catalogue"
    )


# --- 4.15: two implementations, one answer, on a real filing ---------------

def test_the_two_implementations_agree_on_the_golden_filing(built, formulas):
    """Exactly equal, not within tolerance: both are exact decimal sums (4.12)."""
    compared = 0
    for year in built.years:
        environment, assumed_nil = ledger_environment(built.ledgers, year)
        subset = computable_subset(formulas, environment)
        model = calculate(subset, environment, strict=True)

        for target, cell in model.cells.items():
            statement = _statement_of(target)
            ledger = built.ledgers[statement]
            reported = ledger.cell(target, year)
            if reported is None or reported.origin != "reported":
                continue
            compared += 1
            assert cell.value == reported.value, (
                f"{target} {year}: the formula engine computed {cell.value} from "
                f"{cell.evaluation.substituted}, the filing reported {reported.value}"
            )
        assert set(assumed_nil) <= accounts.OPTIONAL_IN_DERIVATION

    assert compared >= 12, f"only {compared} comparisons; the filing supports more"


def _statement_of(account: str) -> Statement:
    for statement, names in (
        (Statement.INCOME, accounts.INCOME_ACCOUNTS),
        (Statement.BALANCE, accounts.BALANCE_ACCOUNTS),
        (Statement.CASHFLOW, accounts.CASHFLOW_ACCOUNTS),
    ):
        if account in names:
            return statement
    raise AssertionError(account)


def test_the_assumed_nil_residuals_are_named_rather_than_silent(built, formulas):
    """The difference between the two implementations, made visible.

    `_try_derive` applies this policy and says nothing. A subtotal resting on
    an assumed-nil residual then reads exactly like one resting on a reported
    figure, and this is the half of the system where that stops being true.
    """
    _, assumed_nil = ledger_environment(built.ledgers, built.years[-1])
    assert "other_income_expense" in assumed_nil
    assert "residual" in assumed_nil["other_income_expense"]
    assert "OPTIONAL_IN_DERIVATION" in assumed_nil["other_income_expense"]


# --- 4.17: extremes, on inputs no filing would produce ---------------------

def _ledger_pair(values: "dict[str, str]"):
    """One income-statement ledger, and the matching formula environment."""
    year = "2025A"
    ledger = Ledger(Statement.INCOME, (year,))
    for account, value in values.items():
        ledger.set_derived(account, year, D(value), "test input")
    environment = Environment()
    for account, value in values.items():
        environment.put(account, D(value), CURRENCY, origin=account)
    for residual in accounts.OPTIONAL_IN_DERIVATION:
        if residual in accounts.INCOME_ACCOUNTS and not environment.has(residual):
            environment.put(residual, ZERO, CURRENCY, origin=f"{residual} nil")
    return ledger, environment, year


#: 4.17: "extreme values, negatives, zeros, very small decimals, very large
#: values, mixed source scales, and repeating-decimal rates."
EXTREMES = {
    "ordinary": ("1250000", "750000", "300000", "18000", "45500"),
    "zeros": ("0", "0", "0", "0", "0"),
    "all negative": ("-1250000", "-750000", "-300000", "-18000", "-45500"),
    "loss making": ("100", "400", "300", "50", "0"),
    "very small": ("0.00000001", "0.00000002", "0.00000003", "0.00000004", "0.00000005"),
    "very large": ("1" + "0" * 30, "2" + "0" * 29, "3" + "0" * 28, "1", "2"),
    "mixed scale": ("1000000000000", "0.000000000001", "1", "0.5", "0.25"),
    "long decimals": (
        "123456789.123456789123456789",
        "987654.321987654321987654",
        "0.000000000000000001",
        "99999999999999999999.99999999",
        "1.000000000000000000000001",
    ),
}


@pytest.mark.parametrize("case", sorted(EXTREMES))
def test_the_two_implementations_agree_on_extreme_inputs(case, formulas):
    """4.17. Both sides are exact sums, so the required answer is equality."""
    revenue, cogs, opex, interest, taxes = EXTREMES[case]
    ledger, environment, year = _ledger_pair({
        accounts.REVENUE: revenue,
        accounts.COGS: cogs,
        accounts.OPERATING_EXPENSES: opex,
        accounts.INTEREST_EXPENSE: interest,
        accounts.TAXES: taxes,
    })
    ledger.fill_derivable()

    income_only = formulas.subset(frozenset(accounts.INCOME_ACCOUNTS))
    model = calculate(income_only, environment, strict=True)

    for target in ("gross_profit", "ebit", "pretax_income", "net_income"):
        engine = ledger.get(target, year)
        assert engine is not None, target
        assert model.value(target) == engine, (
            f"{case}/{target}: formula engine {model.value(target)} vs "
            f"Ledger._try_derive {engine}"
        )


def test_a_repeating_decimal_rate_is_carried_at_context_precision():
    """4.7 and 4.9: 50 significant digits, and no intermediate rounding."""
    # currency / currency, so the declared output unit is a ratio.
    environment = Environment().put("amount", D(1), CURRENCY).put("base", D(3), CURRENCY)
    third = evaluate("amount / base", environment, RATIO).value
    assert str(third).startswith("0.3333333333")
    # 4.12: the round trip is NOT exact for a repeating division, and the test
    # says so rather than asserting an equality that happens to hold.
    assert third * D(3) != D(1)
    assert abs(third * D(3) - D(1)) < D("1e-49")


# --- 4.15 again, on inputs a filing could not produce ----------------------

@pytest.mark.parametrize("scale", [0, 3, 6, 9, 12])
def test_a_randomized_sweep_across_nine_orders_of_magnitude(scale, formulas):
    """The identities must survive reporting scales the fixture never uses."""
    generator = random.Random(20260917 + scale)
    multiplier = D(10) ** scale

    for _ in range(25):
        values = {
            name: str(D(generator.randint(-500_000, 500_000)) * multiplier / D(100))
            for name in (
                accounts.REVENUE, accounts.COGS, accounts.OPERATING_EXPENSES,
                accounts.INTEREST_EXPENSE, accounts.TAXES,
                accounts.OTHER_INCOME_EXPENSE,
            )
        }
        ledger, environment, year = _ledger_pair(values)
        ledger.fill_derivable()
        model = calculate(
            formulas.subset(frozenset(accounts.INCOME_ACCOUNTS)), environment, strict=True
        )
        for target in ("gross_profit", "ebit", "pretax_income", "net_income"):
            assert model.value(target) == ledger.get(target, year), (
                f"scale 1e{scale}, {target}: {values}"
            )


# --- the cross-check must be able to fail ----------------------------------

def test_the_recomputation_catches_a_subtotal_that_does_not_follow(three_statements):
    """Every comparison above passes, which proves nothing on its own.

    12.4 and STEP 9 exist because a reported subtotal can disagree with its own
    components. Corrupting one here is what shows the comparison would say so.
    """
    from apps.api.app.formula.views import formula_report
    from apps.api.app.review.actions import correct_fact
    from apps.api.app.statements.build import build_statements

    fact = next(
        f for f in three_statements.facts
        if f.raw_label == "Gross profit" and f.period_label == "2025"
    )
    broken = correct_fact(
        three_statements, fact.id, "499000", actor="owner", reason="deliberately wrong"
    )
    report = formula_report(build_statements(broken, strict=False))
    year = next(y for y in report.years if y.year == "2025A")

    gross = next(c for c in year.cells if c.target == "gross_profit")
    assert gross.agrees is False
    assert gross.computed == D("500000"), "revenue - cogs is unchanged"
    assert gross.reported == D("499000")
    assert gross.difference == D("1000")
    assert report.disagreements >= 1


def test_a_corrupted_subtotal_does_not_contaminate_the_others(three_statements):
    """12.5: report the difference. Do not stop, and do not plug.

    And it stays where it is. Because every subtotal is recomputed from the
    LEAF inputs rather than from the subtotal above it, a wrong gross profit
    fails its own comparison and leaves EBIT's alone -- EBIT is computed from
    the recomputed gross profit, not the printed one. A cascade would make one
    transcription error look like four.
    """
    from apps.api.app.formula.views import formula_report
    from apps.api.app.review.actions import correct_fact
    from apps.api.app.statements.build import build_statements

    fact = next(
        f for f in three_statements.facts
        if f.raw_label == "Gross profit" and f.period_label == "2025"
    )
    broken = correct_fact(
        three_statements, fact.id, "499000", actor="owner", reason="deliberately wrong"
    )
    year = next(
        y for y in formula_report(build_statements(broken, strict=False)).years
        if y.year == "2025A"
    )
    assert len(year.cells) >= 4
    failing = [cell.target for cell in year.cells if cell.agrees is False]
    assert failing == ["gross_profit"], (
        f"one wrong figure should fail exactly one comparison, not {failing}"
    )
    ebit = next(cell for cell in year.cells if cell.target == "ebit")
    assert ebit.computed == D("200000") and ebit.agrees
