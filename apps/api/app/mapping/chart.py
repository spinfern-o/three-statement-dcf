"""Item 50: the canonical chart of accounts, with definitions.

`docs/data-dictionary.md` §9.6 names this the gap that matters most:

> `definition` | text | Y | 11.3 ("map ... only when definitions align") -- the
> text a reviewer compares a raw label against
>
> **Absent.** No account has a written definition anywhere in the repository.
> This is the gap that matters most for 11.3: a reviewer approving a mapping
> has no canonical text to compare the company's label against.

So this file is mostly prose, and that is the point. A reviewer looking at
"Selling, general and administrative" and asked whether it is
`operating_expenses` needs something to compare it *to*. Without that, 11.3's
"only when definitions align" is an instruction with nothing on one side of
the alignment.

**The codes come from `model/accounts.py`, not from here.** There is one chart
of accounts in this repository and it is the engine's. This module adds the
metadata Section 9.6 requires -- display name, statement, parent, expected
sign, cash and flow tags, and the definition -- and a test asserts that every
engine account has a row and that no row invents an account. Two charts that
drift apart is the failure this arrangement exists to prevent.

Three divergences from Section 9.6, each deliberate:

1. **`statement_types` is a tuple, not a single enum.** `net_income` appears on
   both the income statement and the cash flow statement -- 41 statement slots
   over 40 codes. That is not a modelling error, it is the linkage check #5
   reconciles, and flattening it would hide the one relationship worth seeing.

2. **`operating_or_financing` has a `not_applicable` value** that 9.6's
   four-value enum lacks. `total_assets` is not operating, investing,
   financing or non-operating, and forcing one of the four onto it would be
   inventing a fact about it.

3. **`components` replaces `parent_code_optional`**, taken from
   `accounts.DERIVED`. A child list with signs is strictly more information
   than a parent pointer -- the data dictionary says so -- and `parent_code`
   is derived from it below rather than stored twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from model import accounts


class StatementType(str, Enum):
    INCOME = "income"
    BALANCE = "balance"
    CASHFLOW = "cashflow"


class ExpectedSign(str, Enum):
    """10.16, 11.8. What sign a correctly mapped value should carry.

    This is the convention `model/accounts.py` states once in prose --
    `POSITIVE_AND_SUBTRACTED` and `EXPECTED_NEGATIVE` -- turned into a
    per-account field that something can actually check.
    """

    POSITIVE = "positive"
    NEGATIVE = "negative"
    EITHER = "either"


class CashTag(str, Enum):
    """11.9, 12.3.b. Only meaningful for a cash-flow adjustment."""

    CASH = "cash"
    NON_CASH = "non_cash"
    NOT_APPLICABLE = "not_applicable"


class FlowTag(str, Enum):
    """11.9. On the balance sheet this is the working-capital membership."""

    OPERATING = "operating"
    INVESTING = "investing"
    FINANCING = "financing"
    NON_OPERATING = "non_operating"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class NormalizedLineItem:
    """Section 9.6. One canonical line, and what it means."""

    canonical_code: str
    display_name: str
    statement_types: tuple[StatementType, ...]
    definition: str
    expected_sign: ExpectedSign
    cash_or_non_cash: CashTag
    operating_or_financing: FlowTag

    @property
    def is_subtotal(self) -> bool:
        return self.canonical_code in accounts.DERIVED

    @property
    def components(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(added, subtracted), or ((), ()) for a line that is not derived."""
        return accounts.DERIVED.get(self.canonical_code, ((), ()))

    @property
    def parent_code(self) -> str | None:
        """The subtotal this line feeds, if exactly one does. 9.6, 11.6."""
        parents = [
            code
            for code, (plus, minus) in accounts.DERIVED.items()
            if self.canonical_code in plus or self.canonical_code in minus
        ]
        return parents[0] if len(parents) == 1 else None

    def describe(self) -> str:
        statements = "/".join(s.value for s in self.statement_types)
        return f"{self.canonical_code} ({statements}) -- {self.display_name}"


def _item(code, name, statements, sign, cash, flow, definition) -> NormalizedLineItem:
    return NormalizedLineItem(
        canonical_code=code,
        display_name=name,
        statement_types=tuple(statements),
        definition=" ".join(definition.split()),
        expected_sign=sign,
        cash_or_non_cash=cash,
        operating_or_financing=flow,
    )


IS = (StatementType.INCOME,)
BS = (StatementType.BALANCE,)
CF = (StatementType.CASHFLOW,)
BOTH = (StatementType.INCOME, StatementType.CASHFLOW)

P, N, E = ExpectedSign.POSITIVE, ExpectedSign.NEGATIVE, ExpectedSign.EITHER
CASH_, NONCASH, NOCASH = CashTag.CASH, CashTag.NON_CASH, CashTag.NOT_APPLICABLE
OP, INV, FIN, NONOP, NOFLOW = (
    FlowTag.OPERATING,
    FlowTag.INVESTING,
    FlowTag.FINANCING,
    FlowTag.NON_OPERATING,
    FlowTag.NOT_APPLICABLE,
)

CHART: tuple[NormalizedLineItem, ...] = (
    # --- income statement -------------------------------------------------
    _item(
        accounts.REVENUE,
        "Revenue",
        IS,
        P,
        NOCASH,
        OP,
        """
        Net sales or revenue from contracts with customers for the period,
        after returns, allowances and trade discounts, and before any expense.
        Interest income, investment income and gains on disposal are NOT
        revenue -- they belong in other income and expense. A filer reporting
        several revenue categories that sum to a total: map the total, or map
        the categories as an aggregate and show the sum (11.5).""",
    ),
    _item(
        accounts.COGS,
        "Cost of goods sold",
        IS,
        P,
        NOCASH,
        OP,
        """
        The cost of producing the goods or delivering the services sold in the
        period: direct materials, direct labour, and manufacturing or delivery
        overhead. Stored POSITIVE and subtracted. 'Cost of revenue' and 'cost
        of sales' are this line. Selling, general and administrative cost is
        NOT -- that is operating expenses. STEP 5 forbids inventing this line:
        a filer that does not separate it has not reported it.""",
    ),
    _item(
        accounts.GROSS_PROFIT,
        "Gross profit",
        IS,
        E,
        NOCASH,
        OP,
        """
        Revenue less cost of goods sold. Map a REPORTED gross profit line here
        and it becomes a validation target (11.7), not an addend -- the engine
        derives the same figure from its components and compares the two
        without preferring either. Leave it absent if the filing does not
        present it.""",
    ),
    _item(
        accounts.OPERATING_EXPENSES,
        "Operating expenses",
        IS,
        P,
        NOCASH,
        OP,
        """
        Operating cost other than cost of goods sold: selling, general and
        administrative; research and development; marketing; and the
        restructuring or impairment charges the filer presents within
        operating income. Stored POSITIVE and subtracted. A filer presenting
        several such categories maps them as an aggregate (11.5), because the
        chart has one line for all of them (12.1.d is not implemented).""",
    ),
    _item(
        accounts.EBIT,
        "Operating income (EBIT)",
        IS,
        E,
        NOCASH,
        OP,
        """
        Gross profit less operating expenses. Also labelled 'income from
        operations' or 'operating profit'. Excludes interest and tax. Where a
        filer presents an operating income that includes items this chart
        treats as non-operating, map the reported line and record the
        difference in the note rather than adjusting it silently.""",
    ),
    _item(
        accounts.INTEREST_EXPENSE,
        "Interest expense",
        IS,
        P,
        NOCASH,
        NONOP,
        """
        Interest and other financing cost on borrowings for the period, net of
        capitalised interest, as presented. Stored POSITIVE and subtracted.
        Interest INCOME belongs in other income and expense. Where the filer
        presents one net interest line, map the net figure here and record the
        netting in the note -- rule 1.8 is about not mixing bases silently,
        and a netted line disclosed as netted is not a silent mix.""",
    ),
    _item(
        accounts.OTHER_INCOME_EXPENSE,
        "Other income (expense), net",
        IS,
        E,
        NOCASH,
        NONOP,
        """
        Non-operating income and expense presented between operating income
        and pre-tax income: interest income, foreign-exchange gains and
        losses, equity-method results, gains and losses on disposal. Signed as
        presented -- income positive, expense negative. This is a residual
        line: the engine will derive a subtotal without it, treating absence
        as 'nothing else happened'.""",
    ),
    _item(
        accounts.PRETAX_INCOME,
        "Income before income taxes",
        IS,
        E,
        NOCASH,
        NOFLOW,
        """
        Operating income plus other income and expense, less interest expense.
        A reported line maps here as a validation target (11.7).""",
    ),
    _item(
        accounts.TAXES,
        "Income tax expense",
        IS,
        P,
        NOCASH,
        NONOP,
        """
        Income tax expense for the period -- current and deferred combined as
        the filer presents them. Stored POSITIVE and subtracted. Payroll,
        sales, property and excise taxes are operating cost and are NOT this
        line; mapping a payroll tax line here understates the operating cost
        base and inflates the effective tax rate the forecast uses.""",
    ),
    _item(
        accounts.NET_INCOME,
        "Net income",
        BOTH,
        E,
        NOCASH,
        NOFLOW,
        """
        Profit after tax attributable to the reporting entity. Appears on both
        the income statement and as the first line of operating cash flow;
        that duplication is deliberate and is what the net-income linkage
        check reconciles. Where income attributable to non-controlling
        interests is presented separately, map the figure attributable to the
        PARENT and record the choice -- the equity bridge subtracts minority
        interest separately, and taking the consolidated figure here would
        subtract it twice.""",
    ),
    # --- balance sheet ----------------------------------------------------
    _item(
        accounts.CASH,
        "Cash and cash equivalents",
        BS,
        P,
        NOCASH,
        NOFLOW,
        """
        Currency, demand deposits, and investments with an original maturity
        of three months or less. RESTRICTED cash and short-term investments
        with longer maturities are not this line -- map them to other current
        assets and say why. Cash is excluded from working capital by
        construction, which is why its flow tag is not applicable: the cash
        flow statement produces the ending balance, and the balance sheet
        receives it.""",
    ),
    _item(
        accounts.ACCOUNTS_RECEIVABLE,
        "Accounts receivable, net",
        BS,
        P,
        NOCASH,
        OP,
        """
        Trade receivables from customers for goods delivered or services
        performed, net of the allowance for credit losses. Non-trade
        receivables -- tax refunds, amounts due from related parties -- belong
        in other current assets, because the days-sales-outstanding driver
        divides this line by revenue and a non-trade balance has no revenue
        behind it.""",
    ),
    _item(
        accounts.INVENTORY,
        "Inventories",
        BS,
        P,
        NOCASH,
        OP,
        """
        Raw materials, work in progress and finished goods held for sale, at
        the lower of cost and net realisable value. The days-inventory driver
        divides this by cost of goods sold, so a filer with no separate cost
        of goods sold line gives this driver nothing to work from.""",
    ),
    _item(
        accounts.OTHER_CURRENT_ASSETS,
        "Other current assets",
        BS,
        P,
        NOCASH,
        OP,
        """
        Every current asset the chart does not name: prepaid expenses,
        contract assets, short-term investments, restricted cash, non-trade
        receivables, current deferred tax assets. Counted in operating working
        capital.""",
    ),
    _item(
        accounts.PPE_NET,
        "Property, plant and equipment, net",
        BS,
        P,
        NOCASH,
        INV,
        """
        Property, plant and equipment at cost less accumulated depreciation.
        The PP&E schedule rolls this forward as opening + capex -
        depreciation, so a balance containing anything capex and depreciation
        do not touch will break that reconciliation. Right-of-use assets are a
        common such item: map them to other non-current assets and record the
        choice.""",
    ),
    _item(
        accounts.OTHER_NONCURRENT_ASSETS,
        "Other non-current assets",
        BS,
        P,
        NOCASH,
        INV,
        """
        Every non-current asset the chart does not name: goodwill,
        intangibles, right-of-use assets, equity-method investments,
        non-current deferred tax assets. The chart has NO goodwill or
        intangibles line (12.2.e), so an entity with material goodwill needs
        the chart extended before its model means much. Record that on the
        mapping rather than burying it here.""",
    ),
    _item(
        accounts.TOTAL_ASSETS,
        "Total assets",
        BS,
        P,
        NOCASH,
        NOFLOW,
        """
        The reported total. A validation target (11.7), never an addend: the
        balance check compares this against the sum of the asset lines and
        reports the difference rather than plugging it.""",
    ),
    _item(
        accounts.ACCOUNTS_PAYABLE,
        "Accounts payable",
        BS,
        P,
        NOCASH,
        OP,
        """
        Trade payables to suppliers for goods and services received. Accrued
        expenses and accrued compensation belong in other current
        liabilities.""",
    ),
    _item(
        accounts.OTHER_CURRENT_LIABILITIES,
        "Other current liabilities",
        BS,
        P,
        NOCASH,
        OP,
        """
        Every current liability the chart does not name: accrued compensation,
        accrued expenses, deferred revenue, current tax payable, the current
        portion of lease liabilities. The CURRENT PORTION OF LONG-TERM DEBT
        belongs in debt, not here -- it is interest-bearing, the equity bridge
        subtracts it, and leaving it in working capital both understates net
        debt and puts a financing movement inside the working-capital
        driver.""",
    ),
    _item(
        accounts.DEBT,
        "Debt",
        BS,
        P,
        NOCASH,
        FIN,
        """
        Interest-bearing borrowings, current and non-current combined: loans,
        notes, bonds, finance leases, and -- per decision 2.4.j -- disclosed
        lease liabilities. This is the line the enterprise-to-equity bridge
        subtracts, so anything mapped here reduces equity value directly.""",
    ),
    _item(
        accounts.OTHER_NONCURRENT_LIABILITIES,
        "Other non-current liabilities",
        BS,
        P,
        NOCASH,
        NOFLOW,
        """
        Every non-current liability the chart does not name: deferred tax
        liabilities, pension and post-retirement obligations, provisions,
        non-current deferred revenue. Not counted in working capital and not
        counted as debt -- if an item here is interest-bearing it belongs in
        debt instead.""",
    ),
    _item(
        accounts.TOTAL_LIABILITIES,
        "Total liabilities",
        BS,
        P,
        NOCASH,
        NOFLOW,
        """
        The reported total of all liabilities, current and non-current. A
        validation target (11.7), never an addend: the check compares it
        against the sum of the mapped liability lines and reports the
        difference. Note that many filings present 'total liabilities and
        equity' instead, which is the balance-sheet footing and is NOT this
        line -- mapping that figure here overstates liabilities by the whole
        of equity.""",
    ),
    _item(
        accounts.COMMON_EQUITY,
        "Common equity",
        BS,
        E,
        NOCASH,
        FIN,
        """
        Contributed capital and every equity reserve other than retained
        earnings: common stock at par, additional paid-in capital, treasury
        stock (negative), accumulated other comprehensive income. Can be
        negative where treasury stock exceeds contributed capital.""",
    ),
    _item(
        accounts.RETAINED_EARNINGS,
        "Retained earnings",
        BS,
        E,
        NOCASH,
        FIN,
        """
        Cumulative profit retained: opening balance plus net income less
        dividends. The retained-earnings linkage check rolls this forward, so
        a balance that also absorbs items the chart routes elsewhere -- a
        treasury stock retirement, say -- will break that reconciliation and
        should be recorded on the mapping.""",
    ),
    _item(
        accounts.TOTAL_EQUITY,
        "Total equity",
        BS,
        E,
        NOCASH,
        NOFLOW,
        """
        The reported total. A validation target (11.7), never an addend.
        Non-controlling interests presented within total equity are not in
        this chart's equity lines; record the treatment, because the equity
        bridge subtracts minority interest separately.""",
    ),
    # --- cash flow statement ----------------------------------------------
    _item(
        accounts.DEPRECIATION_AMORTIZATION,
        "Depreciation and amortisation",
        CF,
        P,
        NONCASH,
        OP,
        """
        Depreciation of property, plant and equipment and amortisation of
        intangibles charged in the period, added back in operating cash flow
        because no cash left. STEP 19 forbids assuming this equals capex; they
        are independent lines and a model that ties them together has stopped
        reading the filing.""",
    ),
    _item(
        accounts.STOCK_BASED_COMP,
        "Stock-based compensation",
        CF,
        P,
        NONCASH,
        OP,
        """
        Share-based payment expense recognised in the period and added back as
        non-cash. Decision 2.4.k: expensed in operating income, added back
        here, credited to common equity. It is NOT removed from free cash flow
        as a real cost -- that is a defensible alternative treatment and it is
        not the reported one.""",
    ),
    _item(
        accounts.CHANGE_IN_NWC,
        "Change in net working capital",
        CF,
        E,
        CASH_,
        OP,
        """
        The period's movement in operating working capital -- receivables,
        inventory, other operating current assets, payables and other
        operating current liabilities -- as its CASH EFFECT: a source of cash
        positive, a use of cash negative. Cash and debt are excluded by
        construction. Where the filer presents each working-capital movement
        on its own line, map them as an aggregate and show the sum.""",
    ),
    _item(
        accounts.OTHER_OPERATING,
        "Other operating activities",
        CF,
        E,
        CASH_,
        OP,
        """
        Every other operating item: deferred taxes, provisions, other non-cash
        adjustments, and operating items the filer presents separately. A
        residual line -- the engine derives operating cash flow without it,
        treating absence as 'nothing else happened'.""",
    ),
    _item(
        accounts.CFO,
        "Cash flow from operations",
        CF,
        E,
        CASH_,
        OP,
        """
        The reported subtotal. A validation target (11.7): the engine sums the
        operating lines and compares.""",
    ),
    _item(
        accounts.CAPEX,
        "Capital expenditure",
        CF,
        N,
        CASH_,
        INV,
        """
        Cash paid for property, plant, equipment and capitalised software.
        Stored NEGATIVE, because it is an outflow summed into investing cash
        flow. A filer presenting it as a positive 'purchases of property and
        equipment' has printed the magnitude; the sign convention is this
        chart's, and the mapping records the flip.""",
    ),
    _item(
        accounts.ACQUISITIONS,
        "Acquisitions, net of cash acquired",
        CF,
        N,
        CASH_,
        INV,
        """
        Cash paid for business combinations, net of cash acquired. Stored
        NEGATIVE. A residual line for derivation purposes.""",
    ),
    _item(
        accounts.OTHER_INVESTING,
        "Other investing activities",
        CF,
        E,
        CASH_,
        INV,
        """
        Every other investing item: purchases and maturities of investments,
        proceeds from disposals, loans made and repaid. Signed as its cash
        effect. A residual line.""",
    ),
    _item(
        accounts.CFI,
        "Cash flow from investing",
        CF,
        E,
        CASH_,
        INV,
        """
        The reported net cash used in or provided by investing activities. A
        validation target (11.7): the engine sums capital expenditure,
        acquisitions and other investing items and compares. Usually negative
        for a company that is investing; a positive figure means disposals or
        maturing investments exceeded purchases, which is worth a note.""",
    ),
    _item(
        accounts.DEBT_ISSUANCE,
        "Proceeds from borrowings",
        CF,
        P,
        CASH_,
        FIN,
        """
        Cash received from new borrowings. POSITIVE. Where a filer presents
        one net movement in debt, map the net figure to issuance or repayment
        according to its sign and record the netting -- the debt schedule
        rolls forward on both lines and a netted figure in one of them is
        still the right total.""",
    ),
    _item(
        accounts.DEBT_REPAYMENT,
        "Repayment of borrowings",
        CF,
        N,
        CASH_,
        FIN,
        """
        Cash paid to repay borrowings, including scheduled amortisation and
        early redemptions. Stored NEGATIVE. A filer presenting it as a
        positive 'repayments of long-term debt' has printed the magnitude;
        the sign convention is this chart's and the mapping records the flip.
        The debt schedule rolls the balance forward on this line and on
        proceeds, so a movement netted into one of them is still the right
        total as long as the netting is recorded.""",
    ),
    _item(
        accounts.SHARE_REPURCHASES,
        "Share repurchases",
        CF,
        N,
        CASH_,
        FIN,
        """
        Cash paid to repurchase the entity's own shares. Stored NEGATIVE.
        Reduces common equity, not retained earnings, in this chart.""",
    ),
    _item(
        accounts.DIVIDENDS,
        "Dividends paid",
        CF,
        N,
        CASH_,
        FIN,
        """
        Cash dividends paid to shareholders. Stored NEGATIVE. Reduces retained
        earnings, which is what the retained-earnings linkage check tests.""",
    ),
    _item(
        accounts.OTHER_FINANCING,
        "Other financing activities",
        CF,
        E,
        CASH_,
        FIN,
        """
        Every other financing item: proceeds from share issuance, principal
        payments on lease liabilities, distributions to non-controlling
        interests. A residual line.""",
    ),
    _item(
        accounts.CFF,
        "Cash flow from financing",
        CF,
        E,
        CASH_,
        FIN,
        """
        The reported net cash used in or provided by financing activities. A
        validation target (11.7): the engine sums borrowing proceeds and
        repayments, share repurchases, dividends and other financing items and
        compares. This is the third of the three subtotals in the cash
        roll-forward, so an error here surfaces as a balance sheet whose cash
        does not close.""",
    ),
)

BY_CODE: dict[str, NormalizedLineItem] = {item.canonical_code: item for item in CHART}


def line_item(code: str) -> NormalizedLineItem:
    """Look one up, or say what the options are. 11.1."""
    try:
        return BY_CODE[code]
    except KeyError:
        raise KeyError(
            f"{code!r} is not a canonical line item. The chart holds "
            f"{len(BY_CODE)} codes; see apps/api/app/mapping/chart.py. "
            f"11.1 says do not force every company to use every canonical "
            f"line -- it does not say invent a line."
        ) from None


def for_statement(statement: StatementType) -> tuple[NormalizedLineItem, ...]:
    return tuple(item for item in CHART if statement in item.statement_types)


def ancestors(code: str) -> frozenset[str]:
    """Every subtotal `code` feeds, transitively. 11.6's double-count test."""
    found: set[str] = set()
    frontier = [code]
    while frontier:
        current = frontier.pop()
        for subtotal, (plus, minus) in accounts.DERIVED.items():
            if (current in plus or current in minus) and subtotal not in found:
                found.add(subtotal)
                frontier.append(subtotal)
    return frozenset(found)


def in_sum_relationship(a: str, b: str) -> bool:
    """True when one of these two is counted inside the other. 11.6."""
    if a == b:
        return False
    return b in ancestors(a) or a in ancestors(b)
