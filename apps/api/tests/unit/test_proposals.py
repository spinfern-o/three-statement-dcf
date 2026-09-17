"""Item 51: mapping proposals, and the labels they must refuse.

The refusals matter more than the matches. A proposer that maps
"Total current assets" to `total_assets` produces a model that balances and is
wrong, which is the worst outcome available.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.mapping.chart import StatementType
from apps.api.app.mapping.proposals import (
    blocked_reason,
    explain_no_proposal,
    infer_sign,
    propose,
)
from apps.api.app.mapping.sets import SignNormalization
from model import accounts

IS, BS, CF = StatementType.INCOME, StatementType.BALANCE, StatementType.CASHFLOW


@pytest.mark.parametrize(
    "label, statement, expected",
    [
        ("Revenue", IS, accounts.REVENUE),
        ("Net sales", IS, accounts.REVENUE),
        ("Revenue from contracts with customers", IS, accounts.REVENUE),
        ("Cost of goods sold", IS, accounts.COGS),
        ("Cost of revenue", IS, accounts.COGS),
        ("Gross profit", IS, accounts.GROSS_PROFIT),
        ("Selling, general and administrative", IS, accounts.OPERATING_EXPENSES),
        ("Research and development", IS, accounts.OPERATING_EXPENSES),
        ("Operating income", IS, accounts.EBIT),
        ("Interest expense", IS, accounts.INTEREST_EXPENSE),
        ("Income before income taxes", IS, accounts.PRETAX_INCOME),
        ("Income tax expense", IS, accounts.TAXES),
        ("Provision for income taxes", IS, accounts.TAXES),
        ("Net income", IS, accounts.NET_INCOME),
        ("Cash and cash equivalents", BS, accounts.CASH),
        ("Accounts receivable, net", BS, accounts.ACCOUNTS_RECEIVABLE),
        ("Inventories", BS, accounts.INVENTORY),
        ("Property, plant and equipment, net", BS, accounts.PPE_NET),
        ("Total assets", BS, accounts.TOTAL_ASSETS),
        ("Accounts payable", BS, accounts.ACCOUNTS_PAYABLE),
        ("Long-term debt", BS, accounts.DEBT),
        ("Retained earnings", BS, accounts.RETAINED_EARNINGS),
        ("Total equity", BS, accounts.TOTAL_EQUITY),
        ("Depreciation and amortisation", CF, accounts.DEPRECIATION_AMORTIZATION),
        ("Stock-based compensation", CF, accounts.STOCK_BASED_COMP),
        ("Purchases of property and equipment", CF, accounts.CAPEX),
        ("Capital expenditures", CF, accounts.CAPEX),
        ("Dividends paid", CF, accounts.DIVIDENDS),
        ("Net cash provided by operating activities", CF, accounts.CFO),
    ],
)
def test_ordinary_labels_are_proposed(label, statement, expected):
    candidates = propose(label, statement=statement)
    assert candidates, f"nothing proposed for {label!r}"
    assert candidates[0].code == expected


@pytest.mark.parametrize(
    "label",
    [
        "Total current assets",
        "Total current liabilities",
        "Total liabilities and stockholders' equity",
        "Net increase in cash",
        "Cash and cash equivalents at beginning of year",
        "Basic earnings per share",
        "Weighted-average shares outstanding",
    ],
)
def test_the_traps_are_refused_with_a_reason(label):
    """Rule 1.3. Each of these is a line a naive matcher files somewhere wrong."""
    assert propose(label) == ()
    assert blocked_reason(label)
    assert "deliberately" in explain_no_proposal(label)


def test_a_label_nothing_recognises_says_so():
    assert propose("Widgets manufactured", statement=IS) == ()
    message = explain_no_proposal("Widgets manufactured", IS)
    assert "1.3" in message and "ambiguous" in message


def test_the_statement_narrows_the_field():
    """'Cash' on an income statement is not the balance-sheet cash line."""
    assert propose("Cash", statement=BS)
    assert propose("Cash", statement=IS) == ()


def test_a_weak_match_is_flagged_rather_than_hidden():
    candidates = propose("Taxes", statement=IS)
    assert candidates and candidates[0].code == accounts.TAXES
    assert candidates[0].is_weak
    assert "payroll" in candidates[0].rule


def test_every_candidate_carries_the_rule_that_produced_it():
    for candidate in propose("Cost of sales", statement=IS):
        assert len(candidate.rule) > 10


def test_no_proposal_is_ever_certain():
    """A proposal is a suggestion. 1.0 would say otherwise."""
    for label in ("Revenue", "Total assets", "Net income"):
        for candidate in propose(label):
            assert candidate.score < Decimal("1")


@pytest.mark.parametrize(
    "code, value, expected",
    [
        (accounts.OPERATING_EXPENSES, Decimal("-300000"), SignNormalization.NEGATED),
        (accounts.OPERATING_EXPENSES, Decimal("300000"), SignNormalization.AS_PRINTED),
        (accounts.CAPEX, Decimal("113400"), SignNormalization.NEGATED),
        (accounts.CAPEX, Decimal("-113400"), SignNormalization.AS_PRINTED),
        (accounts.REVENUE, Decimal("1250000"), SignNormalization.AS_PRINTED),
        (accounts.NET_INCOME, Decimal("-5000"), SignNormalization.AS_PRINTED),
        (accounts.REVENUE, None, SignNormalization.AS_PRINTED),
    ],
)
def test_sign_normalization_follows_the_charts_convention(code, value, expected):
    """11.8. The flip is recorded, not applied silently."""
    assert infer_sign(code, value) is expected


def test_an_expense_in_parentheses_is_proposed_with_the_flip():
    candidate = propose(
        "Selling, general and administrative", statement=IS, value=Decimal("-300000")
    )[0]
    assert candidate.sign_normalization is SignNormalization.NEGATED
