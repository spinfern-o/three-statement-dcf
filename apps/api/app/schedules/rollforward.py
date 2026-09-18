"""Items 70, 72 and 75: the balance roll-forwards (13.2, 13.4, 13.7).

Each of these explains how one balance-sheet account moved between two
periods the filing reports, using only the movements the filing disclosed.

The hard design decision is what to do about the movements it did not
disclose. Every formula in Section 13 ends with a term like `+/- FX and Other
Adjustments`, and an annual report almost never puts a number beside that on
the face of the statements. The schedule could solve for it -- and then every
roll-forward ties, the reconciliation in 13.8 passes unconditionally, and the
check is worth nothing. So it does not. `computed_ending` is the beginning
balance plus what was disclosed, `reported_ending` is the balance sheet's own
figure, and `unexplained` is the difference between them, carried through to
the checks and shown to the reviewer.

The first period a filing covers has no prior period in it, so it has no
beginning balance and no roll-forward row. That is a fact about the filing,
not a gap to fill from elsewhere (STEP 3: do not invent missing historical
years).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.accounts import Statement
from model.statements import Ledger

from .base import Availability, Caveat, Reconciliation, Schedule, ScheduleLine


@dataclass(frozen=True)
class Movement:
    """One disclosed change in a balance, and what it does to that balance.

    `multiplier` is the whole sign story, stated out loud. `model/accounts.py`
    stores CapEx, dividends, buybacks and debt repayment as negative cash
    flows, so a roll-forward that wants CapEx to *increase* PP&E must negate
    it, while debt repayment -- already negative -- is added as it stands.
    Getting this wrong is a silent error of exactly twice the amount.
    """

    account: str
    statement: Statement
    multiplier: int
    label: str
    basis: str

    def __post_init__(self) -> None:
        if self.multiplier not in (1, -1):
            raise ValueError(f"Movement {self.label!r} multiplier must be +1 or -1")


@dataclass(frozen=True)
class RollForwardYear:
    """Beginning -> disclosed movements -> computed ending, for one period."""

    year: str
    prior_year: str
    beginning: ScheduleLine
    movements: tuple[ScheduleLine, ...]
    reported_ending: Decimal | None
    reported_ending_line: str

    @property
    def computed_ending(self) -> Decimal | None:
        """Beginning plus every movement the filing disclosed.

        `None` when the beginning balance is absent: there is nothing to roll
        forward from, and starting at zero would report the period's entire
        closing balance as a movement.
        """
        if self.beginning.value is None:
            return None
        total = self.beginning.value
        for line in self.movements:
            if line.value is not None:
                total += line.value
        return total

    @property
    def unexplained(self) -> Decimal | None:
        """Computed ending minus the balance sheet's. Never applied."""
        if self.computed_ending is None or self.reported_ending is None:
            return None
        return self.computed_ending - self.reported_ending

    @property
    def absent_movements(self) -> tuple[str, ...]:
        return tuple(line.label for line in self.movements if line.value is None)


@dataclass(frozen=True, kw_only=True)
class RollForwardSchedule(Schedule):
    formula: str = ""
    years: tuple[RollForwardYear, ...] = ()


def _line(ledgers: dict, movement: Movement, year: str) -> ScheduleLine:
    ledger: Ledger = ledgers[movement.statement]
    value = ledger.get(movement.account, year)
    if value is None:
        return ScheduleLine(
            label=movement.label,
            value=None,
            basis=movement.basis,
            absent_reason=(
                f"the filing reports no {movement.account!r} on the "
                f"{movement.statement.value.replace('_', ' ')} for {year}"
            ),
        )
    return ScheduleLine(movement.label, value * movement.multiplier, movement.basis)


def build_rollforward(
    *,
    key: str,
    title: str,
    rule: str,
    formula: str,
    balance_account: str,
    movements: tuple[Movement, ...],
    ledgers: dict,
    years: tuple[str, ...],
    caveats: tuple[Caveat, ...] = (),
) -> RollForwardSchedule:
    """Roll one balance-sheet account forward through the periods reported."""
    balance: Ledger = ledgers[Statement.BALANCE]
    statement_line = f"balance_sheet.{balance_account}"

    rows: list[RollForwardYear] = []
    reconciliations: list[Reconciliation] = []

    for index, year in enumerate(years):
        if index == 0:
            continue  # no prior period in this filing to roll forward from
        prior = years[index - 1]
        opening = balance.get(balance_account, prior)
        beginning = (
            ScheduleLine(
                f"Beginning balance ({prior})",
                opening,
                f"{statement_line} as reported for {prior}",
            )
            if opening is not None
            else ScheduleLine(
                f"Beginning balance ({prior})",
                None,
                f"{statement_line} as reported for {prior}",
                absent_reason=f"the filing reports no {balance_account!r} for {prior}",
            )
        )
        row = RollForwardYear(
            year=year,
            prior_year=prior,
            beginning=beginning,
            movements=tuple(_line(ledgers, m, year) for m in movements),
            reported_ending=balance.get(balance_account, year),
            reported_ending_line=statement_line,
        )
        rows.append(row)

        note = ""
        if row.absent_movements:
            note = (
                "movements the filing does not report, and which therefore sit in "
                "the difference: " + ", ".join(row.absent_movements)
            )
        reconciliations.append(
            Reconciliation(
                year=year,
                statement_line=statement_line,
                computed=row.computed_ending,
                reported=row.reported_ending,
                note=note,
            )
        )

    if not rows:
        return RollForwardSchedule(
            key=key,
            title=title,
            rule=rule,
            availability=Availability.UNAVAILABLE,
            reason=(
                f"a roll-forward needs two consecutive periods and this filing "
                f"reports {len(years)}. STEP 3: use the years the company provides, "
                "and do not invent the missing one."
            ),
            formula=formula,
            caveats=caveats,
        )

    unavailable = [r for r in rows if r.computed_ending is None]
    if len(unavailable) == len(rows):
        return RollForwardSchedule(
            key=key,
            title=title,
            rule=rule,
            availability=Availability.UNAVAILABLE,
            reason=(
                f"no period has an opening {balance_account!r} balance to roll "
                "forward from, so there is nothing for the disclosed movements to "
                "move."
            ),
            formula=formula,
            caveats=caveats,
            years=tuple(rows),
            reconciliations=tuple(reconciliations),
        )

    absent_movements = sorted({label for row in rows for label in row.absent_movements})
    years_without_opening = [row.year for row in unavailable]
    partial = bool(absent_movements or years_without_opening)

    parts = []
    if absent_movements:
        parts.append(
            "the filing reports no "
            + ", ".join(absent_movements).lower()
            + ", so any such movement sits in the unexplained difference rather "
            "than being plugged in"
        )
    if years_without_opening:
        parts.append("no opening balance for " + ", ".join(years_without_opening))

    return RollForwardSchedule(
        key=key,
        title=title,
        rule=rule,
        availability=Availability.PARTIAL if partial else Availability.AVAILABLE,
        reason="; ".join(parts) if partial else "",
        formula=formula,
        caveats=caveats,
        years=tuple(rows),
        reconciliations=tuple(reconciliations),
    )


# --- item 70: PP&E (13.2) ---------------------------------------------------

PPE_FORMULA = (
    "Ending PP&E = Beginning PP&E + CapEx + Acquisitions - Depreciation "
    "- Disposals +/- FX and Other Adjustments"
)

_CAPEX_MOVEMENT = Movement(
    account=accounts.CAPEX,
    statement=Statement.CASHFLOW,
    multiplier=-1,
    label="Capital expenditure",
    basis=(
        "cash flow statement `capex`, which model/accounts.py stores as a "
        "negative outflow; negated here because buying PP&E increases it"
    ),
)

#: Used when the filing discloses depreciation separately (12.1.e).
_DEPRECIATION_MOVEMENT = Movement(
    account=accounts.DEPRECIATION,
    statement=Statement.CASHFLOW,
    multiplier=-1,
    label="Depreciation",
    basis=(
        "cash flow statement `depreciation`, disclosed separately from "
        "amortization; subtracted here because it reduces the carrying amount"
    ),
)

#: Used when it does not, which is most filings.
_COMBINED_DA_MOVEMENT = Movement(
    account=accounts.DEPRECIATION_AMORTIZATION,
    statement=Statement.CASHFLOW,
    multiplier=-1,
    label="Depreciation and amortization",
    basis=(
        "cash flow statement `depreciation_amortization`, a positive add-back "
        "in operating cash flow; subtracted here because it reduces the "
        "carrying amount"
    ),
)

PPE_MOVEMENTS = (_CAPEX_MOVEMENT, _COMBINED_DA_MOVEMENT)


def ppe_schedule(ledgers: dict, years: tuple[str, ...]) -> RollForwardSchedule:
    """13.2. Built from CapEx and D&A, with three honest gaps named."""
    cashflow_ledger: Ledger = ledgers[Statement.CASHFLOW]
    splits = any(cashflow_ledger.has(accounts.DEPRECIATION, year) for year in years)

    # 12.1.e. A filing that discloses depreciation separately gets the right
    # figure charged against PP&E; one that does not gets the combined line and
    # the caveat saying so. Preferring the split silently would be worse than
    # either: the caveat is what tells a reader which of the two they are
    # looking at.
    movements = (_CAPEX_MOVEMENT, _DEPRECIATION_MOVEMENT if splits else _COMBINED_DA_MOVEMENT)

    caveats = []
    if not splits:
        caveats.append(
            Caveat(
                "13.2 / 13.3",
                "This filing reports one combined `depreciation_amortization` "
                "figure, and this schedule charges all of it against PP&E. That "
                "is right only if the company amortizes nothing. The chart now "
                "carries a separate `depreciation` line (12.1.e) and this "
                "schedule uses it wherever a filing discloses it -- this one "
                "does not.",
            )
        )
    caveats += [
        Caveat(
            "13.2",
            "Disposals and FX have no canonical line. A disposal in the period "
            "therefore shows up in the unexplained difference, which is where it "
            "belongs: it is a real movement this filing's face statements do not "
            "quantify.",
        ),
    ]
    if any(cashflow_ledger.has(accounts.ACQUISITIONS, year) for year in years):
        caveats.append(
            Caveat(
                "13.2",
                "This filing reports acquisitions, and they are deliberately NOT "
                "added here. The cash flow statement's `acquisitions` line is total "
                "consideration paid, not the PP&E acquired in the transaction, "
                "which is disclosed only in the business-combination note. Adding "
                "it whole would overstate PP&E by the rest of the purchase price.",
            )
        )
    return build_rollforward(
        key="ppe",
        title="PP&E and depreciation",
        rule="13.2",
        formula=PPE_FORMULA,
        balance_account=accounts.PPE_NET,
        movements=movements,
        ledgers=ledgers,
        years=years,
        caveats=tuple(caveats),
    )


# --- item 71: intangibles (13.3) --------------------------------------------

INTANGIBLES_FORMULA = (
    "Ending Intangibles = Beginning Intangibles + Additions - Amortization "
    "- Impairment +/- FX and Other Adjustments"
)

INTANGIBLES_MOVEMENTS = (
    Movement(
        account=accounts.AMORTIZATION,
        statement=Statement.CASHFLOW,
        multiplier=-1,
        label="Amortization",
        basis=(
            "cash flow statement `amortization`, a positive add-back in "
            "operating cash flow; subtracted here because it reduces the "
            "carrying amount"
        ),
    ),
)


def intangibles_schedule(ledgers: dict, years: tuple[str, ...]) -> RollForwardSchedule:
    """13.3, buildable since the chart grew both of its sides (F-17).

    This schedule reported itself unavailable for eleven phases, because
    neither side existed: goodwill and intangibles both mapped to
    `other_noncurrent_assets`, and `depreciation_amortization` was one combined
    figure. Both are now canonical lines.

    **Amortization is the only movement the face statements quantify.**
    Additions, impairments and FX are real and are disclosed in the intangibles
    note rather than on the face, so they land in the unexplained difference --
    which is where a movement this filing does not quantify belongs. Solving
    for them would make the 13.8 reconciliation tie unconditionally and be
    worth nothing.

    **Goodwill is not rolled forward here.** It is not amortized under IFRS or
    US GAAP, so it has no charge to roll against: it moves only on an
    acquisition, a disposal or an impairment, none of which the face statements
    quantify either. A goodwill roll-forward built from this data would be a
    table of one number repeated, asserting that nothing happened.
    """
    balance: Ledger = ledgers[Statement.BALANCE]
    cashflow: Ledger = ledgers[Statement.CASHFLOW]

    caveats = [
        Caveat(
            "13.3",
            "Additions, impairments and FX have no canonical line: a filing "
            "discloses them in the intangibles note rather than on the face of "
            "the statements. Any such movement therefore shows up in the "
            "unexplained difference, which is where a movement this filing "
            "does not quantify belongs.",
        ),
    ]
    if any(balance.has(accounts.GOODWILL, year) for year in years):
        caveats.append(
            Caveat(
                "13.3",
                "This filing reports goodwill, and it is deliberately NOT "
                "rolled forward here. Goodwill is not amortized under either "
                "IFRS or US GAAP, so it has no charge to roll against -- it "
                "moves only on an acquisition, a disposal or an impairment, "
                "none of which the face statements quantify. A goodwill "
                "roll-forward from this data would be one number repeated, "
                "asserting that nothing happened.",
            )
        )
    if not any(cashflow.has(accounts.AMORTIZATION, year) for year in years):
        caveats.append(
            Caveat(
                "13.3 / 12.1.e",
                "This filing reports one combined "
                "`depreciation_amortization` figure rather than the split, so "
                "the amortization charge against these intangibles is not "
                "separable. The combined line is NOT used here: charging "
                "depreciation against intangibles would be wrong by the whole "
                "of it, and the PP&E schedule already carries the combined "
                "figure.",
            )
        )
    return build_rollforward(
        key="intangibles",
        title="Intangibles and amortization",
        rule="13.3",
        formula=INTANGIBLES_FORMULA,
        balance_account=accounts.INTANGIBLES,
        movements=INTANGIBLES_MOVEMENTS,
        ledgers=ledgers,
        years=years,
        caveats=tuple(caveats),
    )


# --- item 72: debt (13.4) ---------------------------------------------------

DEBT_FORMULA = "Ending Debt = Beginning Debt + Borrowing - Repayment +/- FX/Other"

DEBT_MOVEMENTS = (
    Movement(
        account=accounts.DEBT_ISSUANCE,
        statement=Statement.CASHFLOW,
        multiplier=1,
        label="Borrowing",
        basis="cash flow statement `debt_issuance`, a positive inflow, added as it stands",
    ),
    Movement(
        account=accounts.DEBT_REPAYMENT,
        statement=Statement.CASHFLOW,
        multiplier=1,
        label="Repayment",
        basis=(
            "cash flow statement `debt_repayment`, which model/accounts.py already "
            "stores as a negative outflow, so it is ADDED rather than subtracted -- "
            "subtracting it would increase debt by the amount repaid"
        ),
    ),
)


def debt_schedule(ledgers: dict, years: tuple[str, ...]) -> RollForwardSchedule:
    """13.4. The interest question is answered separately, in `interest.py`."""
    return build_rollforward(
        key="debt",
        title="Debt and interest",
        rule="13.4",
        formula=DEBT_FORMULA,
        balance_account=accounts.DEBT,
        movements=DEBT_MOVEMENTS,
        ledgers=ledgers,
        years=years,
        caveats=(
            Caveat(
                "13.4",
                "The chart carries one `debt` balance, so current and non-current "
                "borrowings are rolled forward together. A reclassification between "
                "them is invisible here, which is harmless for the balance but not "
                "for a maturity schedule.",
            ),
            Caveat(
                "13.4",
                "Non-cash debt movements -- FX on foreign-currency borrowings, "
                "amortization of discount, a new finance lease -- have no canonical "
                "line and appear in the unexplained difference.",
            ),
        ),
    )


# --- item 75: equity (13.7) -------------------------------------------------

RETAINED_EARNINGS_FORMULA = (
    "Ending Retained Earnings = Beginning Retained Earnings + Net Income "
    "- Dividends +/- Other Adjustments"
)

RETAINED_EARNINGS_MOVEMENTS = (
    Movement(
        account=accounts.NET_INCOME,
        statement=Statement.INCOME,
        multiplier=1,
        label="Net income",
        basis=(
            "income statement `net_income`. Taken from the income statement rather "
            "than the cash flow statement's own copy; the two are compared by the "
            "net-income linkage check, and this schedule should not silently pick "
            "a side if they disagree"
        ),
    ),
    Movement(
        account=accounts.DIVIDENDS,
        statement=Statement.CASHFLOW,
        multiplier=1,
        label="Dividends",
        basis=(
            "cash flow statement `dividends`, stored negative as an outflow and added as it stands"
        ),
    ),
)


def retained_earnings_schedule(ledgers: dict, years: tuple[str, ...]) -> RollForwardSchedule:
    """13.7's retained-earnings half."""
    return build_rollforward(
        key="retained_earnings",
        title="Retained earnings",
        rule="13.7",
        formula=RETAINED_EARNINGS_FORMULA,
        balance_account=accounts.RETAINED_EARNINGS,
        movements=RETAINED_EARNINGS_MOVEMENTS,
        ledgers=ledgers,
        years=years,
        caveats=(
            Caveat(
                "13.7",
                "Retained earnings move on dividends DECLARED; the cash flow "
                "statement reports dividends PAID. In a year where the two differ "
                "the gap is a dividend payable, and it lands in the unexplained "
                "difference.",
            ),
            Caveat(
                "13.7",
                "Some jurisdictions charge share repurchases against retained "
                "earnings rather than against paid-in capital. Where they do, the "
                "buyback appears in this schedule's unexplained difference and not "
                "in the common-equity schedule's.",
            ),
        ),
    )


COMMON_EQUITY_MOVEMENTS = (
    Movement(
        account=accounts.SHARE_REPURCHASES,
        statement=Statement.CASHFLOW,
        multiplier=1,
        label="Share repurchases",
        basis="cash flow statement `share_repurchases`, stored negative and added as it stands",
    ),
    Movement(
        account=accounts.STOCK_BASED_COMP,
        statement=Statement.CASHFLOW,
        multiplier=1,
        label="Stock-based compensation",
        basis=(
            "cash flow statement `stock_based_compensation`, a positive non-cash "
            "add-back that credits equity as it is expensed"
        ),
    ),
)


def common_equity_schedule(ledgers: dict, years: tuple[str, ...]) -> RollForwardSchedule:
    """13.7's contributed-capital half. Its gap is share issuance."""
    return build_rollforward(
        key="common_equity",
        title="Common equity",
        rule="13.7",
        formula=(
            "Ending Common Equity = Beginning Common Equity + Issuance "
            "- Repurchases + Stock Compensation +/- Other Adjustments"
        ),
        balance_account=accounts.COMMON_EQUITY,
        movements=COMMON_EQUITY_MOVEMENTS,
        ledgers=ledgers,
        years=years,
        caveats=(
            Caveat(
                "13.7",
                "The chart has no share-issuance line: proceeds from issuing shares "
                "map to `other_financing`, which also carries everything else. "
                "Issuance therefore cannot be shown as a movement and appears in "
                "the unexplained difference.",
            ),
        ),
    )
