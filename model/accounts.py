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
OPERATING_EXPENSES = "operating_expenses"
EBIT = "ebit"
INTEREST_EXPENSE = "interest_expense"
OTHER_INCOME_EXPENSE = "other_income_expense"
PRETAX_INCOME = "pretax_income"
TAXES = "taxes"
NET_INCOME = "net_income"

INCOME_ACCOUNTS = (
    REVENUE,
    COGS,
    GROSS_PROFIT,
    OPERATING_EXPENSES,
    EBIT,
    INTEREST_EXPENSE,
    OTHER_INCOME_EXPENSE,
    PRETAX_INCOME,
    TAXES,
    NET_INCOME,
)

# --- Balance sheet (STEP 6) ----------------------------------------------
CASH = "cash"
ACCOUNTS_RECEIVABLE = "accounts_receivable"
INVENTORY = "inventory"
OTHER_CURRENT_ASSETS = "other_current_assets"
PPE_NET = "ppe_net"
OTHER_NONCURRENT_ASSETS = "other_noncurrent_assets"
TOTAL_ASSETS = "total_assets"

ACCOUNTS_PAYABLE = "accounts_payable"
OTHER_CURRENT_LIABILITIES = "other_current_liabilities"
DEBT = "debt"
OTHER_NONCURRENT_LIABILITIES = "other_noncurrent_liabilities"
TOTAL_LIABILITIES = "total_liabilities"

COMMON_EQUITY = "common_equity"
RETAINED_EARNINGS = "retained_earnings"
TOTAL_EQUITY = "total_equity"

ASSET_ACCOUNTS = (
    CASH,
    ACCOUNTS_RECEIVABLE,
    INVENTORY,
    OTHER_CURRENT_ASSETS,
    PPE_NET,
    OTHER_NONCURRENT_ASSETS,
)
LIABILITY_ACCOUNTS = (
    ACCOUNTS_PAYABLE,
    OTHER_CURRENT_LIABILITIES,
    DEBT,
    OTHER_NONCURRENT_LIABILITIES,
)
EQUITY_ACCOUNTS = (COMMON_EQUITY, RETAINED_EARNINGS)

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
DEPRECIATION_AMORTIZATION = "depreciation_amortization"
STOCK_BASED_COMP = "stock_based_compensation"
CHANGE_IN_NWC = "change_in_nwc"
OTHER_OPERATING = "other_operating"
CFO = "cash_flow_from_operations"

CAPEX = "capex"
ACQUISITIONS = "acquisitions"
OTHER_INVESTING = "other_investing"
CFI = "cash_flow_from_investing"

DEBT_ISSUANCE = "debt_issuance"
DEBT_REPAYMENT = "debt_repayment"
SHARE_REPURCHASES = "share_repurchases"
DIVIDENDS = "dividends"
OTHER_FINANCING = "other_financing"
CFF = "cash_flow_from_financing"

OPERATING_ITEMS = (
    NET_INCOME,
    DEPRECIATION_AMORTIZATION,
    STOCK_BASED_COMP,
    CHANGE_IN_NWC,
    OTHER_OPERATING,
)
INVESTING_ITEMS = (CAPEX, ACQUISITIONS, OTHER_INVESTING)
FINANCING_ITEMS = (
    DEBT_ISSUANCE,
    DEBT_REPAYMENT,
    SHARE_REPURCHASES,
    DIVIDENDS,
    OTHER_FINANCING,
)
CASHFLOW_ACCOUNTS = OPERATING_ITEMS + (CFO,) + INVESTING_ITEMS + (CFI,) + FINANCING_ITEMS + (CFF,)

VALID_ACCOUNTS = {
    Statement.INCOME: frozenset(INCOME_ACCOUNTS),
    Statement.BALANCE: frozenset(BALANCE_ACCOUNTS),
    Statement.CASHFLOW: frozenset(CASHFLOW_ACCOUNTS),
}

# Accounts computable from others: derived -> (positive terms, negative terms).
# Used by STEP 9 to cross-check reported against derived, never to overwrite.
DERIVED: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    GROSS_PROFIT: ((REVENUE,), (COGS,)),
    EBIT: ((GROSS_PROFIT,), (OPERATING_EXPENSES,)),
    PRETAX_INCOME: ((EBIT, OTHER_INCOME_EXPENSE), (INTEREST_EXPENSE,)),
    NET_INCOME: ((PRETAX_INCOME,), (TAXES,)),
    TOTAL_ASSETS: (ASSET_ACCOUNTS, ()),
    TOTAL_LIABILITIES: (LIABILITY_ACCOUNTS, ()),
    TOTAL_EQUITY: (EQUITY_ACCOUNTS, ()),
    CFO: (OPERATING_ITEMS, ()),
    CFI: (INVESTING_ITEMS, ()),
    CFF: (FINANCING_ITEMS, ()),
}

# Sign convention, stated once so it is never ambiguous in a formula:
# every account is stored with the sign it carries in the arithmetic above.
# COGS, operating expenses, interest expense and taxes are stored POSITIVE
# and subtracted. CapEx, debt repayment, buybacks and dividends are stored
# NEGATIVE, because they are cash outflows summed into their subtotal.
POSITIVE_AND_SUBTRACTED = (COGS, OPERATING_EXPENSES, INTEREST_EXPENSE, TAXES)

# Terms a subtotal may be derived WITHOUT. These are residual "and anything
# else" lines: a filing that omits them is saying nothing else happened, so
# treating them as zero inside a subtotal reports the company's position
# rather than inventing one. Every other absent account blocks derivation,
# because there absence means the figure is genuinely unknown -- which is
# STEP 5's distinction between a line the company does not report and a
# line worth zero.
OPTIONAL_IN_DERIVATION = frozenset(
    {
        OTHER_INCOME_EXPENSE,
        OTHER_OPERATING,
        OTHER_INVESTING,
        OTHER_FINANCING,
        ACQUISITIONS,
    }
)
EXPECTED_NEGATIVE = (CAPEX, ACQUISITIONS, DEBT_REPAYMENT, SHARE_REPURCHASES, DIVIDENDS)


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
