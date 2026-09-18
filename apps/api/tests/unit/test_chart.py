"""Item 50: the canonical chart, and its agreement with the engine.

The chart is metadata over `model/accounts.py`, not a second chart. These
tests are what keeps that true: two charts that drift apart is the failure the
arrangement exists to prevent, and drift is silent.
"""

from __future__ import annotations

import pytest

from apps.api.app.mapping.chart import (
    BY_CODE,
    CHART,
    ExpectedSign,
    FlowTag,
    StatementType,
    ancestors,
    for_statement,
    in_sum_relationship,
    line_item,
)
from model import accounts

ENGINE_CODES = (
    set(accounts.INCOME_ACCOUNTS) | set(accounts.BALANCE_ACCOUNTS) | set(accounts.CASHFLOW_ACCOUNTS)
)


def test_the_chart_covers_every_engine_account():
    assert not ENGINE_CODES - set(BY_CODE), "the engine has accounts the chart does not define"


def test_the_chart_invents_no_account():
    assert not set(BY_CODE) - ENGINE_CODES, "the chart defines accounts the engine will refuse"


@pytest.mark.parametrize("item", CHART, ids=lambda i: i.canonical_code)
def test_every_line_has_a_real_definition(item):
    """11.3 compares a raw label against this text. A restatement of the name
    is not something to compare against."""
    assert len(item.definition) > 80, f"{item.canonical_code} has a stub definition"
    assert item.display_name
    assert item.canonical_code.replace("_", " ") != item.definition.lower()


@pytest.mark.parametrize("item", CHART, ids=lambda i: i.canonical_code)
def test_every_line_declares_a_statement(item):
    assert item.statement_types


def test_net_income_is_on_two_statements():
    """41 slots over 40 codes. It is the linkage check #5 reconciles."""
    both = [i for i in CHART if len(i.statement_types) > 1]
    assert [i.canonical_code for i in both] == [accounts.NET_INCOME]


def test_statement_membership_matches_the_engine():
    for statement, codes in (
        (StatementType.INCOME, accounts.INCOME_ACCOUNTS),
        (StatementType.BALANCE, accounts.BALANCE_ACCOUNTS),
        (StatementType.CASHFLOW, accounts.CASHFLOW_ACCOUNTS),
    ):
        assert {i.canonical_code for i in for_statement(statement)} == set(codes)


def test_expected_signs_match_the_engines_stated_convention():
    """`model/accounts.py` states the convention in prose. This is that prose,
    turned into a field, and it must not disagree with it."""
    for code in accounts.POSITIVE_AND_SUBTRACTED:
        assert line_item(code).expected_sign is ExpectedSign.POSITIVE, code
    for code in accounts.EXPECTED_NEGATIVE:
        assert line_item(code).expected_sign is ExpectedSign.NEGATIVE, code


def test_operating_tags_match_the_engines_working_capital_membership():
    """STEP 17's NWC membership, declared once and now checkable."""
    operating = {
        i.canonical_code
        for i in CHART
        if i.operating_or_financing is FlowTag.OPERATING
        and StatementType.BALANCE in i.statement_types
    }
    expected = set(accounts.OPERATING_CURRENT_ASSETS) | set(accounts.OPERATING_CURRENT_LIABILITIES)
    assert operating == expected


def test_cash_and_debt_are_not_working_capital():
    """`EXCLUDED_FROM_NWC`, as a property of the chart rather than a comment."""
    for code in accounts.EXCLUDED_FROM_NWC:
        assert line_item(code).operating_or_financing is not FlowTag.OPERATING


def test_cash_flow_tags_match_the_engines_sections():
    for codes, tag in (
        (accounts.INVESTING_ITEMS, FlowTag.INVESTING),
        (accounts.FINANCING_ITEMS, FlowTag.FINANCING),
    ):
        for code in codes:
            assert line_item(code).operating_or_financing is tag, code


def test_only_the_non_cash_charges_are_tagged_non_cash():
    """9.6's cash tag, and the four lines that earn it.

    Depreciation and amortization were added when 12.1.e's split was, and they
    are non-cash for the same reason the combined line is. Nothing else may
    join them without a reason: the tag is what tells a reader which operating
    adjustments moved money.
    """
    from apps.api.app.mapping.chart import CashTag

    non_cash = {i.canonical_code for i in CHART if i.cash_or_non_cash is CashTag.NON_CASH}
    assert non_cash == {
        accounts.DEPRECIATION,
        accounts.AMORTIZATION,
        accounts.DEPRECIATION_AMORTIZATION,
        accounts.STOCK_BASED_COMP,
    }


def test_subtotals_know_their_components():
    for code in accounts.DERIVED:
        plus, minus = line_item(code).components
        assert plus or minus
        assert line_item(code).is_subtotal


def test_ancestors_are_transitive():
    """COGS is inside gross profit, which is inside EBIT, and so on up."""
    assert accounts.GROSS_PROFIT in ancestors(accounts.COGS)
    assert accounts.NET_INCOME in ancestors(accounts.COGS)
    # Net income feeds operating cash flow, which feeds the net change in
    # cash (12.3.m). Transitivity is the point of the assertion, so the
    # second hop belongs in it.
    assert ancestors(accounts.NET_INCOME) == frozenset({accounts.CFO, accounts.NET_CHANGE_IN_CASH})


def test_sum_relationship_is_symmetric_and_irreflexive():
    assert in_sum_relationship(accounts.COGS, accounts.GROSS_PROFIT)
    assert in_sum_relationship(accounts.GROSS_PROFIT, accounts.COGS)
    assert not in_sum_relationship(accounts.COGS, accounts.COGS)
    assert not in_sum_relationship(accounts.COGS, accounts.INVENTORY)


def test_an_unknown_code_says_what_the_options_are():
    """`ebitda` used to be the example here, and is now a real line (12.1.f).

    Replaced with a code the chart will not acquire: "adjusted EBITDA" is a
    figure whose bridge each filer chooses, and 12.1.f's EBITDA is the plain
    one. A test whose example becomes valid stops testing anything.
    """
    with pytest.raises(KeyError) as exc:
        line_item("adjusted_ebitda")
    assert "canonical line item" in str(exc.value)


# --- F-17: the chart now covers Section 12 ----------------------------------


def test_every_line_section_12_names_has_a_canonical_code():
    """12.1, 12.2 and 12.3, clause by clause.

    The list is written out rather than derived, because deriving it from the
    chart would assert the chart against itself. Each entry is a clause of the
    specification and the code that answers it.
    """
    answers = {
        "12.1.a": accounts.REVENUE,
        "12.1.b": accounts.COGS,
        "12.1.c": accounts.GROSS_PROFIT,
        "12.1.d": accounts.SGA,
        "12.1.e": accounts.DEPRECIATION,
        "12.1.f": accounts.EBITDA,
        "12.1.g": accounts.EBIT,
        "12.1.h": accounts.INTEREST_INCOME,
        "12.1.i": accounts.OTHER_INCOME_EXPENSE,
        "12.1.j": accounts.PRETAX_INCOME,
        "12.1.k": accounts.TAXES,
        "12.1.l": accounts.NET_INCOME_TO_PARENT,
        "12.2.a": accounts.CASH,
        "12.2.b": accounts.ACCOUNTS_RECEIVABLE,
        "12.2.c": accounts.OTHER_CURRENT_ASSETS,
        "12.2.d": accounts.PPE_NET,
        "12.2.e": accounts.GOODWILL,
        "12.2.f": accounts.OTHER_NONCURRENT_ASSETS,
        "12.2.g": accounts.ACCOUNTS_PAYABLE,
        "12.2.h": accounts.DEBT,
        "12.2.i": accounts.LEASE_LIABILITIES,
        "12.2.j": accounts.OTHER_NONCURRENT_LIABILITIES,
        "12.2.k": accounts.MINORITY_INTEREST,
        "12.2.l": accounts.COMMON_EQUITY,
        "12.3.a": accounts.NET_INCOME,
        "12.3.b": accounts.DEPRECIATION_AMORTIZATION,
        "12.3.c": accounts.CHANGE_IN_NWC,
        "12.3.d": accounts.CFO,
        "12.3.e": accounts.CAPEX,
        "12.3.f": accounts.DISPOSALS,
        "12.3.g": accounts.OTHER_INVESTING,
        "12.3.h": accounts.DEBT_ISSUANCE,
        "12.3.i": accounts.SHARE_ISSUANCE,
        "12.3.j": accounts.DIVIDENDS,
        "12.3.k": accounts.OTHER_FINANCING,
        "12.3.l": accounts.FX_EFFECT_ON_CASH,
        "12.3.m": accounts.NET_CHANGE_IN_CASH,
    }
    for clause, code in answers.items():
        item = line_item(code)  # raises if the chart lacks it
        assert item.definition.strip(), f"{clause}: {code} has no definition"


def test_every_account_has_exactly_one_chart_entry():
    """The two lists must not drift, in either direction."""
    coded = [i.canonical_code for i in CHART]
    assert len(coded) == len(set(coded)), "a code appears twice in the chart"
    every = (
        set(accounts.INCOME_ACCOUNTS)
        | set(accounts.BALANCE_ACCOUNTS)
        | set(accounts.CASHFLOW_ACCOUNTS)
    )
    assert set(coded) == every, set(coded) ^ every


def test_goodwill_is_not_in_the_intangibles_line():
    """They behave differently, and the definitions must both say so.

    Goodwill is not amortized under IFRS or US GAAP. Folding it into
    intangibles would put a balance that never amortizes into a roll-forward
    driven by amortization, and the result would be wrong by exactly the
    goodwill every year.
    """
    assert "not amortized" in line_item(accounts.GOODWILL).definition.lower()
    assert "goodwill is not here" in line_item(accounts.INTANGIBLES).definition.lower()


def test_the_lease_liability_is_not_debt():
    assert accounts.LEASE_LIABILITIES in accounts.LIABILITY_ACCOUNTS
    assert accounts.LEASE_LIABILITIES != accounts.DEBT
    assert "debt" in line_item(accounts.LEASE_LIABILITIES).definition.lower()


def test_the_minority_interest_sits_inside_equity():
    """12.2.k, and the reason A = L + E still closes without a fourth section."""
    assert accounts.MINORITY_INTEREST in accounts.EQUITY_ACCOUNTS
    plus, _ = accounts.DERIVED[accounts.TOTAL_EQUITY]
    assert accounts.MINORITY_INTEREST in plus


def test_the_when_applicable_lines_are_optional_and_the_residuals_are_separate():
    """Both are optional, and the chart keeps the two reasons apart.

    A residual line is "and anything else". A when-applicable line is one a
    whole class of filer genuinely does not have. Merging the two lists would
    lose the distinction the comments exist to preserve.
    """
    assert not (accounts.RESIDUAL_LINES & accounts.WHEN_APPLICABLE)
    assert accounts.OPTIONAL_IN_DERIVATION == (accounts.RESIDUAL_LINES | accounts.WHEN_APPLICABLE)
    for code in accounts.WHEN_APPLICABLE:
        assert code in accounts.OPTIONAL_IN_DERIVATION


def test_every_optional_line_is_a_term_of_some_subtotal():
    """What makes the optionality safe, stated as a test.

    An optional line is only safe to treat as absent-means-none because
    something reported reconciles over it: a filer that DOES report goodwill
    and leaves it unmapped produces a total assets that differs by exactly the
    goodwill, and 12.4.i reports that difference. An optional line nothing
    reconciles over would have nothing watching it, and its absence would be
    invisible rather than reconciled.

    Two things reconcile: a `DERIVED` subtotal and a `COMPONENT_CHECKS` group.
    Both count, and the second must -- `amortization` moved from the first to
    the second when combined D&A stopped being derived, and this assertion is
    what caught that it had been left unwatched in between.
    """
    watched = {term for plus, minus in accounts.DERIVED.values() for term in plus + minus} | {
        term for terms in accounts.COMPONENT_CHECKS.values() for term in terms
    }
    for code in sorted(accounts.OPTIONAL_IN_DERIVATION):
        assert code in watched, (
            f"{code} may be treated as absent-means-none, but nothing "
            f"reconciles over it, so nothing would notice if it were wrongly "
            f"left unmapped"
        )


def test_a_component_check_is_a_second_relationship_not_a_second_derivation():
    """`DERIVED` records the ONE arithmetic that produces an account.

    Net income is pre-tax income less taxes. 12.1.l also asks that its
    attribution be shown when disclosed, and the parent and minority shares do
    sum to it -- but an account may be derived only one way, so that sum is
    checked rather than computed.

    Operating expenses and combined D&A are NOT here, and the reason is worth
    keeping. They were, briefly: making them checks rather than derivations
    looked right because nearly every filer reports them directly. It broke
    the filer who does not. This repository has fixtures of both shapes -- one
    reports three operating expense categories and no total, the other a total
    and no categories -- so the total must be derivable when the categories
    are there and readable when they are not. That is `_derivable_here`, not a
    component check.
    """
    assert set(accounts.COMPONENT_CHECKS) == {accounts.NET_INCOME}
    assert accounts.NET_INCOME in accounts.DERIVED
    for total, parts in accounts.COMPONENT_CHECKS.items():
        assert parts, total
        derived_terms = set(sum(accounts.DERIVED.get(total, ((), ())), ()))
        assert not (set(parts) & derived_terms), (
            f"{total} both derives from and checks against the same term, so "
            f"the check would be comparing the figure with itself"
        )
