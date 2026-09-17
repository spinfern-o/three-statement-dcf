"""Item 51: mapping proposals.

11.10: "Record whether each mapping is system-proposed or human-approved."
11.11: "Require human approval of all mappings before the historical model is
labeled Verified."

So this module's entire job is to make a *suggestion*. Nothing here approves
anything, nothing here is applied without a person agreeing, and the score it
attaches is an ordering aid, not a confidence in the sense of a probability.

Three things keep it honest:

**It never proposes what it cannot justify.** Every candidate carries the rule
that produced it, in words, and the reviewer sees that rule beside the
proposal. "matched 'cost of sales' in the label" is checkable; a bare
suggestion is not.

**It says nothing rather than guessing.** A label the rules do not recognise
gets no proposal and a note saying so. `Total current assets` is the standing
example: the chart has no line for it, the temptation is to file it under
`total_assets`, and doing that would put a subtotal of part of the balance
sheet where the whole one belongs. Rule 1.3 -- never silently map an ambiguous
line -- is the whole reason this returns an empty tuple so readily.

**The statement narrows the field.** A fact extracted from a table captioned
"CONSOLIDATED BALANCE SHEETS" cannot be `revenue`, whatever its label says, and
using that removes most of the ways a label-matcher embarrasses itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.numeric import D

from .chart import ExpectedSign, StatementType, line_item
from .sets import SignNormalization

#: An exact match on the whole label, the strongest evidence a label offers.
EXACT = D("0.95")
#: A distinctive phrase appearing in the label.
STRONG = D("0.85")
#: A keyword that usually means this line but sometimes does not.
WEAK = D("0.60")

#: Below this, a proposal is shown with a warning rather than pre-selected.
WEAK_THRESHOLD = D("0.75")


@dataclass(frozen=True)
class Candidate:
    """One suggestion, and the reason for it."""

    code: str
    score: Decimal
    rule: str
    sign_normalization: SignNormalization = SignNormalization.AS_PRINTED

    @property
    def is_weak(self) -> bool:
        return self.score < WEAK_THRESHOLD

    def describe(self) -> str:
        flip = " (sign flipped)" if self.sign_normalization is SignNormalization.NEGATED else ""
        return f"{self.code} {self.score} -- {self.rule}{flip}"


def _rule(code, pattern, score, description):
    return (code, re.compile(pattern, re.IGNORECASE), score, description)


#: Labels that must NOT produce a proposal, checked before anything else. Each
#: is a line a naive matcher files under the wrong canonical code.
BLOCKED = (
    (
        re.compile(r"(?i)^total\s+current\s+(assets|liabilities)\b"),
        "the chart has no current-total line. Mapping it to the statement "
        "total would put a subtotal of part of the balance sheet where the "
        "whole one belongs",
    ),
    (
        re.compile(r"(?i)^total\s+(non-?current|long-?term)\s+(assets|liabilities)\b"),
        "the chart has no non-current-total line",
    ),
    (
        re.compile(r"(?i)^total\s+liabilities\s+and\s+(stockholders'?|shareholders'?)?\s*equity\b"),
        "this is the balance-sheet footing, equal to total assets. It is not "
        "total liabilities, and mapping it there would overstate liabilities "
        "by the whole of equity",
    ),
    (
        re.compile(r"(?i)^(net\s+)?(increase|decrease|change)\s+in\s+cash\b"),
        "the chart has no net-change-in-cash line: the cash roll-forward "
        "produces it from the three subtotals, and mapping it in would make it "
        "an input to the check that is supposed to test it",
    ),
    (
        re.compile(r"(?i)cash\s+(and\s+cash\s+equivalents\s+)?at\s+(the\s+)?(beginning|end)\b"),
        "an opening or closing cash line on the cash flow statement is the "
        "roll-forward's own output, not an input to it",
    ),
    (
        re.compile(r"(?i)\bper\s+share\b|\bearnings\s+per\s+share\b|\bweighted[- ]average\s+(number\s+of\s+)?shares\b"),
        "a per-share figure or a share count is not a statement line in this "
        "chart. Diluted shares are a valuation input (STEP 35), supplied with "
        "their own source",
    ),
    (
        re.compile(r"(?i)^(supplemental|non-?cash)\s+(disclosure|information|investing)"),
        "a supplemental disclosure sits outside the three statements",
    ),
)

#: (canonical code, pattern, score, the rule in words). Order does not matter;
#: every rule is tried and the best score per code wins.
RULES = (
    # --- income statement -------------------------------------------------
    _rule(accounts.REVENUE, r"^(net\s+)?(sales|revenues?)$", EXACT, "the whole label is a revenue line"),
    _rule(accounts.REVENUE, r"revenue\s+from\s+contracts\s+with\s+customers", EXACT, "matched the IFRS 15 / ASC 606 revenue caption"),
    _rule(accounts.REVENUE, r"^(total\s+)?(net\s+)?(sales|revenues?)\b", STRONG, "the label begins with a revenue term"),
    _rule(accounts.REVENUE, r"\bturnover\b", STRONG, "matched 'turnover', the UK term for revenue"),

    _rule(accounts.COGS, r"^cost\s+of\s+(goods\s+sold|sales|revenue|services)", EXACT, "matched a cost-of-sales caption"),
    _rule(accounts.COGS, r"\bcost\s+of\s+(goods|sales|revenue)\b", STRONG, "matched 'cost of sales' in the label"),

    _rule(accounts.GROSS_PROFIT, r"^gross\s+(profit|margin|income)$", EXACT, "the whole label is a gross profit line"),

    _rule(accounts.OPERATING_EXPENSES, r"^(selling,?\s+general\s+and\s+administrative|sg&a)", EXACT, "matched the SG&A caption"),
    _rule(accounts.OPERATING_EXPENSES, r"^research\s+and\s+development", EXACT, "matched the R&D caption"),
    _rule(accounts.OPERATING_EXPENSES, r"^(total\s+)?operating\s+(expenses|costs)", EXACT, "matched a total operating expense caption"),
    _rule(accounts.OPERATING_EXPENSES, r"\b(restructuring|impairment|amortisation\s+of\s+acquired)", STRONG, "an operating charge presented within operating income"),
    _rule(accounts.OPERATING_EXPENSES, r"\b(marketing|distribution|administrative)\s+(expense|cost)", STRONG, "an operating expense category"),

    _rule(accounts.EBIT, r"^(operating\s+(income|profit)|income\s+from\s+operations)$", EXACT, "the whole label is an operating income line"),

    _rule(accounts.INTEREST_EXPENSE, r"^interest\s+expense", EXACT, "matched an interest expense caption"),
    _rule(accounts.INTEREST_EXPENSE, r"^(finance|financing)\s+costs?$", STRONG, "matched the IFRS finance-cost caption"),

    _rule(accounts.OTHER_INCOME_EXPENSE, r"^(other|non-?operating)\s+(income|expense)", EXACT, "matched an other-income caption"),
    _rule(accounts.OTHER_INCOME_EXPENSE, r"^interest\s+income", STRONG, "interest income is non-operating in this chart"),
    _rule(accounts.OTHER_INCOME_EXPENSE, r"\b(foreign\s+(exchange|currency)|equity\s+in\s+earnings|gain\s+on\s+(sale|disposal))", STRONG, "a non-operating gain or loss"),

    _rule(accounts.PRETAX_INCOME, r"income\s+before\s+(income\s+)?tax", EXACT, "matched a pre-tax income caption"),
    _rule(accounts.PRETAX_INCOME, r"^(profit|earnings)\s+before\s+tax", EXACT, "matched a pre-tax income caption"),

    _rule(accounts.TAXES, r"^(income|corporate)\s+tax(es|ation)?\s+(expense|provision|charge)", EXACT, "matched an income tax expense caption"),
    _rule(accounts.TAXES, r"^provision\s+for\s+income\s+tax", EXACT, "matched the US provision-for-income-taxes caption"),
    _rule(accounts.TAXES, r"^(income\s+)?tax(es)?$", WEAK, "the label is just 'tax' -- confirm it is INCOME tax and not payroll, sales or property tax, which are operating cost"),

    _rule(accounts.NET_INCOME, r"^net\s+(income|earnings|profit)", EXACT, "matched a net income caption"),
    _rule(accounts.NET_INCOME, r"^(profit|loss)\s+for\s+the\s+(year|period)", EXACT, "matched the IFRS profit-for-the-period caption"),

    # --- balance sheet ----------------------------------------------------
    _rule(accounts.CASH, r"^cash\s+and\s+cash\s+equivalents", EXACT, "matched the cash and equivalents caption"),
    _rule(accounts.CASH, r"^cash$", STRONG, "the whole label is 'cash'"),

    _rule(accounts.ACCOUNTS_RECEIVABLE, r"^(accounts|trade)\s+receivable", EXACT, "matched a trade receivables caption"),
    _rule(accounts.ACCOUNTS_RECEIVABLE, r"^receivables", STRONG, "matched 'receivables' -- confirm these are TRADE receivables"),

    _rule(accounts.INVENTORY, r"^inventor(y|ies)", EXACT, "matched an inventories caption"),
    _rule(accounts.INVENTORY, r"^stock$", WEAK, "'stock' is inventory in UK usage and share capital in US usage -- confirm which"),

    _rule(accounts.OTHER_CURRENT_ASSETS, r"^other\s+current\s+assets", EXACT, "the whole label names the other-current-asset line"),
    _rule(accounts.OTHER_CURRENT_ASSETS, r"^(other|prepaid|prepayments)", STRONG, "matched an other-current-asset caption"),
    _rule(accounts.OTHER_CURRENT_ASSETS, r"\b(short-?term\s+investments|restricted\s+cash|contract\s+assets)", STRONG, "an item this chart routes to other current assets"),

    _rule(accounts.PPE_NET, r"^property,?\s+(plant\s+and\s+)?equipment", EXACT, "matched a property, plant and equipment caption"),
    _rule(accounts.PPE_NET, r"^(fixed|tangible)\s+assets", STRONG, "matched the UK/IFRS tangible assets caption"),

    # An EXACT rule, because `^other` alone proposes OTHER_CURRENT_ASSETS and
    # wins on nothing but ordering. A non-current balance mapped to a current
    # line moves working capital by its whole amount, and the balance sheet
    # still balances -- so nothing downstream catches it.
    _rule(accounts.OTHER_NONCURRENT_ASSETS, r"^other\s+(non-?current|long-?term)\s+assets", EXACT, "the label says NON-current, which the generic 'other' rule would miss"),
    _rule(accounts.OTHER_NONCURRENT_ASSETS, r"^(goodwill|intangible)", STRONG, "the chart has no goodwill or intangibles line (12.2.e); it routes here, and that is worth recording on the mapping"),
    _rule(accounts.OTHER_NONCURRENT_ASSETS, r"\b(right-?of-?use|deferred\s+tax\s+assets?|equity[- ]method\s+investments?)", STRONG, "a non-current asset this chart routes to the residual line"),

    _rule(accounts.TOTAL_ASSETS, r"^total\s+assets$", EXACT, "the whole label is total assets"),

    _rule(accounts.ACCOUNTS_PAYABLE, r"^(accounts|trade)\s+payable", EXACT, "matched a trade payables caption"),

    _rule(accounts.OTHER_CURRENT_LIABILITIES, r"^other\s+current\s+liabilit", EXACT, "the whole label names the other-current-liability line"),
    _rule(accounts.OTHER_CURRENT_LIABILITIES, r"^(accrued|deferred\s+revenue|contract\s+liabilit)", STRONG, "an item this chart routes to other current liabilities"),

    _rule(accounts.DEBT, r"^(long-?term\s+)?(debt|borrowings|loans)", EXACT, "matched a borrowings caption"),
    _rule(accounts.DEBT, r"\b(notes\s+payable|current\s+portion\s+of\s+long-?term\s+debt|finance\s+lease\s+liabilit|lease\s+liabilit)", STRONG, "interest-bearing, so it belongs in debt (decision 2.4.j for leases)"),

    _rule(accounts.OTHER_NONCURRENT_LIABILITIES, r"^other\s+(non-?current|long-?term)\s+liabilit", EXACT, "the label says NON-current; the same trap as other non-current assets"),
    _rule(accounts.OTHER_NONCURRENT_LIABILITIES, r"\b(deferred\s+tax\s+liabilit|pension|post-?retirement|provisions)", STRONG, "a non-current liability this chart routes to the residual line"),

    _rule(accounts.TOTAL_LIABILITIES, r"^total\s+liabilities$", EXACT, "the whole label is total liabilities"),

    _rule(accounts.COMMON_EQUITY, r"^(common|ordinary)\s+stock|^share\s+capital|^additional\s+paid-?in\s+capital|^treasury\s+stock|accumulated\s+other\s+comprehensive", EXACT, "a contributed-capital or reserve line"),

    _rule(accounts.RETAINED_EARNINGS, r"^(retained\s+earnings|accumulated\s+(deficit|profits))", EXACT, "matched a retained earnings caption"),

    _rule(accounts.TOTAL_EQUITY, r"^total\s+(stockholders'?|shareholders'?|owners'?)?\s*equity$", EXACT, "the whole label is total equity"),

    # --- cash flow statement ----------------------------------------------
    _rule(accounts.DEPRECIATION_AMORTIZATION, r"^depreciation", EXACT, "matched a depreciation caption"),
    _rule(accounts.DEPRECIATION_AMORTIZATION, r"^amorti[sz]ation", STRONG, "matched an amortisation caption"),

    _rule(accounts.STOCK_BASED_COMP, r"(stock|share)-?based\s+(compensation|payment)", EXACT, "matched a share-based payment caption"),

    _rule(accounts.CHANGE_IN_NWC, r"changes?\s+in\s+(operating\s+)?(working\s+capital|assets\s+and\s+liabilities)", EXACT, "matched a working-capital movement caption"),

    _rule(accounts.CFO, r"^(net\s+)?cash\s+(provided\s+by|from|used\s+in)\s+operating", EXACT, "matched the operating cash flow subtotal"),

    _rule(accounts.CAPEX, r"(purchases?|acquisitions?|additions?)\s+of\s+(property|plant|equipment|fixed\s+assets)", EXACT, "matched a capital expenditure caption"),
    _rule(accounts.CAPEX, r"^capital\s+expenditures?", EXACT, "the whole label is capital expenditure"),

    _rule(accounts.ACQUISITIONS, r"acquisitions?\s+(of\s+)?(business|subsidiar)|business\s+combinations?", EXACT, "matched a business-combination caption"),

    _rule(accounts.CFI, r"^(net\s+)?cash\s+(provided\s+by|from|used\s+in)\s+investing", EXACT, "matched the investing cash flow subtotal"),

    _rule(accounts.DEBT_ISSUANCE, r"^proceeds\s+from\s+(the\s+)?(issuance\s+of\s+)?(debt|borrowings|notes|long-?term)", EXACT, "matched a borrowing-proceeds caption"),

    _rule(accounts.DEBT_REPAYMENT, r"(repayments?|payments?)\s+(of|on)\s+(debt|borrowings|notes|long-?term)", EXACT, "matched a debt-repayment caption"),

    _rule(accounts.SHARE_REPURCHASES, r"(repurchases?|buy-?backs?)\s+of\s+(common\s+)?(stock|shares)", EXACT, "matched a share-repurchase caption"),

    _rule(accounts.DIVIDENDS, r"^dividends?\s+(paid|to)", EXACT, "matched a dividends-paid caption"),
    _rule(accounts.DIVIDENDS, r"^dividends?$", STRONG, "the whole label is 'dividends' -- confirm it is dividends PAID, not declared"),

    _rule(accounts.CFF, r"^(net\s+)?cash\s+(provided\s+by|from|used\s+in)\s+financing", EXACT, "matched the financing cash flow subtotal"),
)


def blocked_reason(label: str) -> str | None:
    """Why this label gets no proposal, if it is one of the known traps."""
    clean = " ".join((label or "").split())
    for pattern, reason in BLOCKED:
        if pattern.search(clean):
            return reason
    return None


def infer_sign(code: str, value: Decimal | None) -> SignNormalization:
    """11.8. Does the chart's convention differ from what was printed?

    A filing printing an expense in parentheses has printed it negative; this
    chart stores operating expenses, cost of sales, interest and tax POSITIVE
    and subtracts them. The flip is recorded on the mapping rather than
    applied silently, which is what 11.8 asks for.
    """
    if value is None or value == 0:
        return SignNormalization.AS_PRINTED
    expected = line_item(code).expected_sign
    if expected is ExpectedSign.POSITIVE and value < 0:
        return SignNormalization.NEGATED
    if expected is ExpectedSign.NEGATIVE and value > 0:
        return SignNormalization.NEGATED
    return SignNormalization.AS_PRINTED


def propose(
    label: str,
    *,
    statement: StatementType | None = None,
    value: Decimal | None = None,
    limit: int = 3,
) -> tuple[Candidate, ...]:
    """Rank the canonical lines this label might be. May return nothing.

    `statement` narrows the field to the lines that statement can carry. It
    comes from the table's caption, and passing it removes most of the ways a
    label-matcher embarrasses itself -- "cash" on an income statement is not
    the balance-sheet cash line.
    """
    if blocked_reason(label):
        return ()

    clean = " ".join((label or "").split())
    if not clean:
        return ()

    best: dict[str, tuple[Decimal, str]] = {}
    for code, pattern, score, description in RULES:
        if statement is not None and statement not in line_item(code).statement_types:
            continue
        if not pattern.search(clean):
            continue
        if code not in best or score > best[code][0]:
            best[code] = (score, description)

    candidates = [
        Candidate(
            code=code,
            score=score,
            rule=description,
            sign_normalization=infer_sign(code, value),
        )
        for code, (score, description) in best.items()
    ]
    candidates.sort(key=lambda c: (-c.score, c.code))
    return tuple(candidates[:limit])


def explain_no_proposal(label: str, statement: StatementType | None = None) -> str:
    """What to tell a reviewer when nothing matched. Rule 1.3."""
    reason = blocked_reason(label)
    if reason:
        return f"No proposal, deliberately: {reason}."
    where = f" on the {statement.value} statement" if statement else ""
    return (
        f"No rule recognises {label!r}{where}. Rule 1.3 forbids mapping an "
        f"ambiguous line silently, so nothing is suggested -- map it yourself "
        f"against the canonical definitions, or reject it if it is not a "
        f"statement line."
    )
