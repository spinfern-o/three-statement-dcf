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


def test_only_depreciation_and_sbc_are_non_cash():
    from apps.api.app.mapping.chart import CashTag

    non_cash = {i.canonical_code for i in CHART if i.cash_or_non_cash is CashTag.NON_CASH}
    assert non_cash == {accounts.DEPRECIATION_AMORTIZATION, accounts.STOCK_BASED_COMP}


def test_subtotals_know_their_components():
    for code in accounts.DERIVED:
        plus, minus = line_item(code).components
        assert plus or minus
        assert line_item(code).is_subtotal


def test_ancestors_are_transitive():
    """COGS is inside gross profit, which is inside EBIT, and so on up."""
    assert accounts.GROSS_PROFIT in ancestors(accounts.COGS)
    assert accounts.NET_INCOME in ancestors(accounts.COGS)
    assert ancestors(accounts.NET_INCOME) == frozenset({accounts.CFO})


def test_sum_relationship_is_symmetric_and_irreflexive():
    assert in_sum_relationship(accounts.COGS, accounts.GROSS_PROFIT)
    assert in_sum_relationship(accounts.GROSS_PROFIT, accounts.COGS)
    assert not in_sum_relationship(accounts.COGS, accounts.COGS)
    assert not in_sum_relationship(accounts.COGS, accounts.INVENTORY)


def test_an_unknown_code_says_what_the_options_are():
    with pytest.raises(KeyError) as exc:
        line_item("ebitda")
    assert "canonical line item" in str(exc.value)
