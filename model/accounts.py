"""Controlled account vocabulary for the standardized statements.

STEP 5 is explicit: "If the company does not report a line such as COGS or
gross profit separately, do not invent it." So every account here is
OPTIONAL by construction. The statement classes hold a sparse mapping of
account -> Figure, and absence is a legitimate, preserved state that
propagates into the checks rather than being filled with zero.

`DERIVED` records which accounts can be computed from others. When a
company reports both a derived line and its components, STEP 9's
verification compares them instead of picking one.
"""

from __future__ import annotations

from enum import Enum


class Statement(str, Enum):
    INCOME = "income_statement"
    BALANCE = "balance_sheet"
    CASHFLOW = "cash_flow_statement"


# --- Income statement (STEP 5) -------------------------------------------
REVENUE = "revenue"
COGS = "cogs"
GROSS_PROFIT = "gross_profit"
# 12.1.d: operating expenses by disclosed category. `operating_expenses` stays
# the line EBIT is built from; these are the two categories nearly every filer
# discloses, and a filer that discloses them derives the total from them.
SGA = "selling_general_administrative"
RESEARCH_DEVELOPMENT = "research_development"
OTHER_OPERATING_EXPENSES = "other_operating_expenses"
OPERATING_EXPENSES = "operating_expenses"
EBITDA = "ebitda"
EBIT = "ebit"
INTEREST_INCOME = "interest_income"
INTEREST_EXPENSE = "interest_expense"
OTHER_INCOME_EXPENSE = "other_income_expense"
PRETAX_INCOME = "pretax_income"
TAXES = "taxes"
NET_INCOME = "net_income"
# 12.1.l: "including attribution when disclosed". Reported lines, never a
# derivation of `net_income` -- an account may be derived only one way, and
# net income is already pre-tax income less taxes. The attribution is checked
# against net income instead, which is what "when disclosed" asks for.
NET_INCOME_TO_PARENT = "net_income_to_parent"
NET_INCOME_TO_MINORITY = "net_income_to_minority"

INCOME_ACCOUNTS = (
    REVENUE,
    COGS,
    GROSS_PROFIT,
    SGA,
    RESEARCH_DEVELOPMENT,
    OTHER_OPERATING_EXPENSES,
    OPERATING_EXPENSES,
    EBITDA,
    EBIT,
    INTEREST_INCOME,
    INTEREST_EXPENSE,
    OTHER_INCOME_EXPENSE,
    PRETAX_INCOME,
    TAXES,
    NET_INCOME,
    NET_INCOME_TO_PARENT,
    NET_INCOME_TO_MINORITY,
)

# --- Balance sheet (STEP 6) ----------------------------------------------
CASH = "cash"
ACCOUNTS_RECEIVABLE = "accounts_receivable"
INVENTORY = "inventory"
OTHER_CURRENT_ASSETS = "other_current_assets"
PPE_NET = "ppe_net"
GOODWILL = "goodwill"
INTANGIBLES = "intangibles"
OTHER_NONCURRENT_ASSETS = "other_noncurrent_assets"
TOTAL_ASSETS = "total_assets"

ACCOUNTS_PAYABLE = "accounts_payable"
OTHER_CURRENT_LIABILITIES = "other_current_liabilities"
DEBT = "debt"
LEASE_LIABILITIES = "lease_liabilities"
OTHER_NONCURRENT_LIABILITIES = "other_noncurrent_liabilities"
TOTAL_LIABILITIES = "total_liabilities"

COMMON_EQUITY = "common_equity"
RETAINED_EARNINGS = "retained_earnings"
# 12.2.k. Non-controlling interest sits inside equity under both IFRS (IAS 1.54)
# and US GAAP (ASC 810-10-45-16), so total equity includes it and A = L + E
# holds without a fourth section.
MINORITY_INTEREST = "minority_interest"
TOTAL_EQUITY = "total_equity"

ASSET_ACCOUNTS = (
    CASH,
    ACCOUNTS_RECEIVABLE,
    INVENTORY,
    OTHER_CURRENT_ASSETS,
    PPE_NET,
    GOODWILL,
    INTANGIBLES,
    OTHER_NONCURRENT_ASSETS,
)
LIABILITY_ACCOUNTS = (
    ACCOUNTS_PAYABLE,
    OTHER_CURRENT_LIABILITIES,
    DEBT,
    LEASE_LIABILITIES,
    OTHER_NONCURRENT_LIABILITIES,
)
EQUITY_ACCOUNTS = (COMMON_EQUITY, RETAINED_EARNINGS, MINORITY_INTEREST)

BALANCE_ACCOUNTS = (
    ASSET_ACCOUNTS
    + (TOTAL_ASSETS,)
    + LIABILITY_ACCOUNTS
    + (TOTAL_LIABILITIES,)
    + EQUITY_ACCOUNTS
    + (TOTAL_EQUITY,)
)

# Operating working-capital membership (STEP 17). Cash, debt and other
# financing balances are deliberately excluded from NWC.
OPERATING_CURRENT_ASSETS = (ACCOUNTS_RECEIVABLE, INVENTORY, OTHER_CURRENT_ASSETS)
OPERATING_CURRENT_LIABILITIES = (ACCOUNTS_PAYABLE, OTHER_CURRENT_LIABILITIES)
EXCLUDED_FROM_NWC = (CASH, DEBT)

# --- Cash flow statement (STEP 7) ----------------------------------------
# 12.1.e asks for D&A "with source and classification". `depreciation_amortization`
# stays the line the cash flow statement is built from -- most filers report it
# combined -- and the two components below are separately reportable, deriving
# the combined line when a filer splits them. Keeping the combined line as the
# cash-flow term is what stops a filer who reports both from being counted
# twice.
DEPRECIATION = "depreciation"
AMORTIZATION = "amortization"
DEPRECIATION_AMORTIZATION = "depreciation_amortization"
STOCK_BASED_COMP = "stock_based_compensation"
CHANGE_IN_NWC = "change_in_nwc"
OTHER_OPERATING = "other_operating"
CFO = "cash_flow_from_operations"

CAPEX = "capex"
ACQUISITIONS = "acquisitions"
DISPOSALS = "disposals"
OTHER_INVESTING = "other_investing"
CFI = "cash_flow_from_investing"

DEBT_ISSUANCE = "debt_issuance"
DEBT_REPAYMENT = "debt_repayment"
SHARE_ISSUANCE = "share_issuance"
SHARE_REPURCHASES = "share_repurchases"
DIVIDENDS = "dividends"
OTHER_FINANCING = "other_financing"
CFF = "cash_flow_from_financing"

# 12.3.l and 12.3.m. The FX line is why 12.4.f's cash roll-forward is stated
# as "plus FX/other cash effects" rather than as CFO + CFI + CFF: for a filer
# with foreign operations the three subtotals do not tie to the change in cash
# without it, and before this the difference had nowhere to go.
FX_EFFECT_ON_CASH = "fx_effect_on_cash"
NET_CHANGE_IN_CASH = "net_change_in_cash"

OPERATING_ITEMS = (
    NET_INCOME,
    DEPRECIATION_AMORTIZATION,
    STOCK_BASED_COMP,
    CHANGE_IN_NWC,
    OTHER_OPERATING,
)
INVESTING_ITEMS = (CAPEX, ACQUISITIONS, DISPOSALS, OTHER_INVESTING)
FINANCING_ITEMS = (
    DEBT_ISSUANCE,
    DEBT_REPAYMENT,
    SHARE_ISSUANCE,
    SHARE_REPURCHASES,
    DIVIDENDS,
    OTHER_FINANCING,
)
#: The three subtotals plus the FX line, which is 12.4.f's roll-forward.
CASH_MOVEMENTS = (CFO, CFI, CFF, FX_EFFECT_ON_CASH)
CASHFLOW_ACCOUNTS = (
    (DEPRECIATION, AMORTIZATION)
    + OPERATING_ITEMS
    + (CFO,)
    + INVESTING_ITEMS
    + (CFI,)
    + FINANCING_ITEMS
    + (CFF, FX_EFFECT_ON_CASH, NET_CHANGE_IN_CASH)
)

VALID_ACCOUNTS = {
    Statement.INCOME: frozenset(INCOME_ACCOUNTS),
    Statement.BALANCE: frozenset(BALANCE_ACCOUNTS),
    Statement.CASHFLOW: frozenset(CASHFLOW_ACCOUNTS),
}

# Accounts computable from others: derived -> (positive terms, negative terms).
# Used by STEP 9 to cross-check reported against derived, never to overwrite.
DERIVED: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    GROSS_PROFIT: ((REVENUE,), (COGS,)),
    # 12.1.d. A filer disclosing categories and no total derives the total; one
    # reporting the total and no categories supplies it directly. Both shapes
    # occur in this repository's own fixtures, which is how the rule that
    # a reported subtotal stays available as an input got written.
    OPERATING_EXPENSES: ((SGA, RESEARCH_DEVELOPMENT, OTHER_OPERATING_EXPENSES), ()),
    # 12.1.f: "EBITDA only when the precise bridge is visible." The bridge is
    # EBIT plus D&A, and D&A is NOT optional in it -- an absent D&A means the
    # bridge is not visible, so EBITDA is not derived rather than being derived
    # as equal to EBIT. That is the whole of 12.1.f in one entry.
    EBITDA: ((EBIT, DEPRECIATION_AMORTIZATION), ()),
    EBIT: ((GROSS_PROFIT,), (OPERATING_EXPENSES,)),
    PRETAX_INCOME: ((EBIT, INTEREST_INCOME, OTHER_INCOME_EXPENSE), (INTEREST_EXPENSE,)),
    NET_INCOME: ((PRETAX_INCOME,), (TAXES,)),
    TOTAL_ASSETS: (ASSET_ACCOUNTS, ()),
    TOTAL_LIABILITIES: (LIABILITY_ACCOUNTS, ()),
    TOTAL_EQUITY: (EQUITY_ACCOUNTS, ()),
    # 12.1.e, the same shape: split when disclosed, combined when not.
    DEPRECIATION_AMORTIZATION: ((DEPRECIATION, AMORTIZATION), ()),
    CFO: (OPERATING_ITEMS, ()),
    CFI: (INVESTING_ITEMS, ()),
    CFF: (FINANCING_ITEMS, ()),
    NET_CHANGE_IN_CASH: (CASH_MOVEMENTS, ()),
}

# Groups that are CHECKED against a reported total but never substituted for
# it, because the total is already derived some OTHER way.
#
# `DERIVED` records the one arithmetic that produces an account, and an account
# may have only one. Net income is pre-tax income less taxes. 12.1.l also asks
# that its attribution be shown when disclosed, and the parent and minority
# shares do sum to it -- but that sum is a second relationship, not a second
# derivation, so it is checked rather than computed.
COMPONENT_CHECKS: dict[str, tuple[str, ...]] = {
    # 12.1.l: net income "including attribution when disclosed". Net income is
    # already derived as pre-tax income less taxes, and an account may be
    # derived only one way, so the attribution is a check rather than a second
    # derivation of the same line.
    NET_INCOME: (NET_INCOME_TO_PARENT, NET_INCOME_TO_MINORITY),
}


# Sign convention, stated once so it is never ambiguous in a formula:
# every account is stored with the sign it carries in the arithmetic above.
# COGS, operating expenses, interest expense and taxes are stored POSITIVE
# and subtracted. CapEx, debt repayment, buybacks and dividends are stored
# NEGATIVE, because they are cash outflows summed into their subtotal.
POSITIVE_AND_SUBTRACTED = (COGS, OPERATING_EXPENSES, INTEREST_EXPENSE, TAXES)

RESIDUAL_LINES = frozenset(
    {
        OTHER_INCOME_EXPENSE,
        OTHER_OPERATING,
        OTHER_INVESTING,
        OTHER_FINANCING,
        OTHER_OPERATING_EXPENSES,
        ACQUISITIONS,
        DISPOSALS,
    }
)

# Lines the specification itself qualifies with "when applicable" (12.2.i,
# 12.2.k) or that a whole class of filer genuinely does not have. A company
# with no acquisition history has no goodwill; one that leases nothing has no
# lease liability; one with no subsidiaries has no minority interest. Treating
# their absence as blocking would make total assets underivable for most
# filings, which is the opposite of what rule 1.3 protects.
#
# **This is safe only because 12.4.i catches the other case.** A filer that DOES
# report goodwill and whose goodwill was left unmapped derives a total assets
# that differs from the reported one by exactly the goodwill, and the
# reconciliation reports that difference with its amount and source trail. The
# optionality does not hide an unmapped line; it stops an inapplicable line
# from blocking a filing that never had it.
#
# Nothing here may be a line whose absence could pass unnoticed. Each is either
# reconciled against a reported subtotal or has no subtotal to hide inside.
WHEN_APPLICABLE = frozenset(
    {
        GOODWILL,
        INTANGIBLES,
        LEASE_LIABILITIES,
        MINORITY_INTEREST,
        INTEREST_INCOME,
        AMORTIZATION,
        SHARE_ISSUANCE,
        FX_EFFECT_ON_CASH,
        SGA,
        RESEARCH_DEVELOPMENT,
    }
)

# Terms a subtotal may be derived WITHOUT. These are residual "and anything
# else" lines and the "when applicable" lines above: a filing that omits them
# is saying nothing else happened, so treating them as zero inside a subtotal
# reports the company's position rather than inventing one. Every other absent
# account blocks derivation, because there absence means the figure is
# genuinely unknown -- which is STEP 5's distinction between a line the company
# does not report and a line worth zero.
OPTIONAL_IN_DERIVATION = RESIDUAL_LINES | WHEN_APPLICABLE
EXPECTED_NEGATIVE = (
    CAPEX,
    ACQUISITIONS,
    DEBT_REPAYMENT,
    SHARE_REPURCHASES,
    DIVIDENDS,
)


def validate_account(statement: Statement, name: str) -> str:
    if name not in VALID_ACCOUNTS[statement]:
        known = ", ".join(sorted(VALID_ACCOUNTS[statement]))
        raise KeyError(
            f"{name!r} is not a recognized {statement.value} account.\n"
            f"Recognized accounts: {known}\n"
            "Map the company's reported line into one of these (STEP 5-7) "
            "rather than adding an ad-hoc account name."
        )
    return name
