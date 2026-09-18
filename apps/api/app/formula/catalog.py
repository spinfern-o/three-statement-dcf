"""The derivation formulas of `docs/formula-catalog.md`, as runnable definitions.

18.1 asks that formulas be stored as versioned definitions. The catalogue
already assigns every formula in the engine a stable code, a unit and a
rounding classification; this module turns the derivation family -- `IS-*-D`,
`BS-*-D`, `CF-*-D` -- into `FormulaDefinition` rows the formula engine can
actually evaluate.

**They are generated from `model/accounts.py:DERIVED`, not retyped from it.**
That is the whole point. A catalogue transcribed by hand is a second chart of
accounts, and two charts that disagree is worse than one -- `mapping/chart.py`
made the same choice for the same reason. The expressions below are built from
the engine's own tuples, so a component added to a subtotal in
`model/accounts.py` appears here without anyone remembering to, and a test
asserts the two produce identical values on the golden fixture.

**The residual-line policy stays in the chart.** `Ledger._try_derive` treats
`OPTIONAL_IN_DERIVATION` members as zero when absent, because a filing that
omits "other operating activities" is saying nothing else happened rather than
that the figure is unknown. The formula engine deliberately does NOT know
that: a reference it cannot resolve is refused (18.14), full stop. The policy
is applied where it belongs, in `ledger_environment` below, which supplies the
zero *and records that it did*. A reviewer can then see that a subtotal rested
on an assumed-nil residual, which is invisible if the engine quietly tolerates
a missing reference.
"""

from __future__ import annotations

from decimal import Decimal

from model import accounts
from model.accounts import Statement
from model.numeric import ZERO
from model.statements import Ledger

from .evaluate import Environment
from .registry import FormulaDefinition, FormulaSet
from .units import CURRENCY

#: The catalogue's codes for the derivation family, by account.
CODES = {
    accounts.GROSS_PROFIT: ("IS-GP-D", "STEP 5; 12.1.c"),
    accounts.EBIT: ("IS-EBIT-D", "STEP 5; 12.1.g"),
    accounts.PRETAX_INCOME: ("IS-PTI-D", "STEP 5; 12.1.j; 12.4.d"),
    accounts.NET_INCOME: ("IS-NI-D", "STEP 5; 12.1.l; 12.4.e"),
    accounts.TOTAL_ASSETS: ("BS-TA-D", "STEP 6; 12.2"),
    accounts.TOTAL_LIABILITIES: ("BS-TL-D", "STEP 6; 12.2"),
    accounts.TOTAL_EQUITY: ("BS-TE-D", "STEP 6; 12.2.l"),
    accounts.CFO: ("CF-CFO-D", "STEP 7; 12.3.d"),
    accounts.CFI: ("CF-CFI-D", "STEP 7"),
    accounts.CFF: ("CF-CFF-D", "STEP 7"),
}

#: A sentence per subtotal. Written here rather than derived, because a
#: definition is the thing arithmetic cannot supply (11.3).
DEFINITIONS = {
    accounts.GROSS_PROFIT: "Revenue less the direct cost of the goods and services sold.",
    accounts.EBIT: "Gross profit less operating expenses: the result of trading, before financing and tax.",
    accounts.PRETAX_INCOME: "EBIT plus other income and expense, less interest expense.",
    accounts.NET_INCOME: "Pretax income less the tax charge: the bottom line, and the link to the cash flow statement.",
    accounts.TOTAL_ASSETS: "The sum of every asset account the chart carries.",
    accounts.TOTAL_LIABILITIES: "The sum of every liability account the chart carries.",
    accounts.TOTAL_EQUITY: "Contributed capital plus retained earnings.",
    accounts.CFO: "Net income adjusted for non-cash charges and the movement in working capital.",
    accounts.CFI: "Cash spent on and received from long-lived assets and acquisitions.",
    accounts.CFF: "Cash raised from and returned to providers of capital.",
}

#: Which statement each derived subtotal is printed on, so an environment can
#: be built from the right ledger.
STATEMENT_OF = {
    **dict.fromkeys(accounts.INCOME_ACCOUNTS, Statement.INCOME),
    **dict.fromkeys(accounts.BALANCE_ACCOUNTS, Statement.BALANCE),
    **dict.fromkeys(accounts.CASHFLOW_ACCOUNTS, Statement.CASHFLOW),
}


def _expression(account: str) -> str:
    """`DERIVED[account]` as the text of a formula, in the chart's own order."""
    plus, minus = accounts.DERIVED[account]
    text = " + ".join(plus)
    for term in minus:
        text += f" - {term}"
    return text


def derivation_formulas() -> FormulaSet:
    """The ten subtotal derivations, generated from `model/accounts.py`.

    Version 1 for every row: the engine has never versioned a formula, so
    there is no prior version to preserve (18.9 has nothing to hold yet).
    """
    definitions = []
    for account in accounts.DERIVED:
        code, rule = CODES[account]
        definitions.append(
            FormulaDefinition(
                code=code,
                target=account,
                expression=_expression(account),
                output_unit=CURRENCY.name,
                version=1,
                rule=rule,
                definition=DEFINITIONS[account],
                # Addition and subtraction only: exact under 4.12's second
                # clause, with no division anywhere to round.
                rounding="exact",
            )
        )
    return FormulaSet(
        tuple(definitions),
        version=1,
        note=(
            "The derivation family of docs/formula-catalog.md, generated from "
            "model/accounts.py:DERIVED so the two cannot drift."
        ),
    )


def ledger_environment(
    ledgers: dict[Statement, Ledger],
    year: str,
    *,
    reported_only: bool = True,
) -> tuple[Environment, dict[str, str]]:
    """Build a formula environment from one year of the built statements.

    Returns the environment and a record of every residual line supplied as
    zero, with the reason. That second value is the point: `Ledger._try_derive`
    applies the same policy silently, and a subtotal resting on an assumed-nil
    residual reads exactly like one resting on a reported figure.

    `reported_only` keeps derived cells out, so the formulas recompute the
    subtotals from their components rather than reading a subtotal the ledger
    already derived and calling that agreement.
    """
    environment = Environment()
    assumed_nil: dict[str, str] = {}

    for account, statement in STATEMENT_OF.items():
        if account in accounts.DERIVED:
            continue  # the formulas compute these; they are not inputs
        ledger = ledgers.get(statement)
        if ledger is None:
            continue
        cell = ledger.cell(account, year)
        if cell is None:
            continue
        if reported_only and cell.origin != "reported":
            continue
        environment.put(account, cell.value, CURRENCY, origin=f"{statement.value}.{account}")

    # The residual-line policy, applied here and recorded, not hidden in the
    # evaluator. model/accounts.py OPTIONAL_IN_DERIVATION is its source.
    for account in sorted(accounts.OPTIONAL_IN_DERIVATION):
        if environment.has(account):
            continue
        statement = STATEMENT_OF[account]
        if ledgers.get(statement) is None:
            continue
        environment.put(account, ZERO, CURRENCY, origin=f"{account} assumed nil")
        assumed_nil[account] = (
            f"the filing reports no {account!r} for {year}, and it is a residual "
            "'and anything else' line: silence means nothing else happened rather "
            "than the figure being unknown (model/accounts.py "
            "OPTIONAL_IN_DERIVATION)"
        )

    return environment, assumed_nil


def computable_subset(formulas: FormulaSet, environment: Environment) -> FormulaSet:
    """The formulas whose inputs this environment can reach, transitively.

    A filing with no cash flow statement cannot compute CFO, and asking for it
    and catching the refusal is a worse way to find that out than not asking.
    This is not a tolerance for missing inputs -- what it removes is a formula
    with nothing to run on, not a formula that ran and came up short.
    """
    available = set(environment.paths)
    keep: set[str] = set()
    changed = True
    while changed:
        changed = False
        for definition in formulas:
            if definition.target in keep:
                continue
            if definition.inputs <= available:
                keep.add(definition.target)
                available.add(definition.target)
                changed = True
    return formulas.subset(frozenset(keep))


def as_decimal(value) -> Decimal:  # pragma: no cover - re-export for callers
    return Decimal(value)
