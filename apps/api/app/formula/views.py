"""18.10 and 18.11 as a screen, not only as a test.

Both clauses are written as obligations to a person: "provide a human-readable
formula for every calculated cell" and "provide the exact input values used for
every calculation". A trace that exists only inside an assertion satisfies
neither.

What the screen shows is a genuine STEP 9 cross-check, and not a demonstration.
Each derived subtotal is recomputed from its components by the formula engine
and set beside the figure the filing printed. Where they agree, the filing's
own arithmetic is confirmed by a second implementation that shares no code with
the one that read it. Where they do not, something is wrong in the extraction,
the mapping or the filing -- and 12.5 says show it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.accounts import Statement

from ..statements.build import BuiltStatements
from .calculate import CalculatedModel, calculate
from .catalog import computable_subset, derivation_formulas, ledger_environment
from .graph import DependencyGraph
from .registry import FormulaSet


@dataclass(frozen=True)
class CellTrace:
    """One calculated cell, with everything 18.10 and 18.11 require."""

    target: str
    code: str
    version: int
    #: 18.10.
    formula: str
    #: 18.11.
    substituted: str
    computed: Decimal
    #: What the filing printed for the same line, if it printed one.
    reported: Decimal | None
    statement: str

    @property
    def agrees(self) -> bool | None:
        """Exact equality. Both sides are exact decimal sums (4.12)."""
        return None if self.reported is None else self.computed == self.reported

    @property
    def difference(self) -> Decimal | None:
        return None if self.reported is None else self.computed - self.reported


@dataclass(frozen=True)
class YearTrace:
    year: str
    cells: tuple[CellTrace, ...]
    #: 18.14: what could not be computed, and why. Never a zero.
    unavailable: dict[str, str]
    #: Residual lines supplied as nil, and the policy that allowed it.
    assumed_nil: dict[str, str]
    #: 18.7.
    fingerprint: str
    #: 18.11: every leaf input the calculation rested on.
    inputs: dict[str, Decimal]

    @property
    def disagreements(self) -> tuple[CellTrace, ...]:
        return tuple(cell for cell in self.cells if cell.agrees is False)


@dataclass(frozen=True)
class FormulaReport:
    formulas: FormulaSet
    #: 18.5, and the proof of 18.6 -- an order exists, so there is no cycle.
    order: tuple[str, ...]
    required_inputs: tuple[str, ...]
    years: tuple[YearTrace, ...]

    @property
    def cycles(self) -> tuple[tuple[str, ...], ...]:
        return DependencyGraph(self.formulas).cycles()

    @property
    def disagreements(self) -> int:
        return sum(len(year.disagreements) for year in self.years)


_STATEMENT_NAMES = {
    Statement.INCOME: "Income statement",
    Statement.BALANCE: "Balance sheet",
    Statement.CASHFLOW: "Cash flow statement",
}


def _statement_of(account: str) -> Statement:
    for statement, names in (
        (Statement.INCOME, accounts.INCOME_ACCOUNTS),
        (Statement.BALANCE, accounts.BALANCE_ACCOUNTS),
        (Statement.CASHFLOW, accounts.CASHFLOW_ACCOUNTS),
    ):
        if account in names:
            return statement
    raise KeyError(account)  # pragma: no cover


def _traces(model: CalculatedModel, built: BuiltStatements, year: str) -> tuple[CellTrace, ...]:
    out = []
    for target in sorted(model.cells):
        cell = model.cells[target]
        statement = _statement_of(target)
        reported_cell = built.ledgers[statement].cell(target, year)
        reported = (
            reported_cell.value
            if reported_cell is not None and reported_cell.origin == "reported"
            else None
        )
        out.append(
            CellTrace(
                target=target,
                code=cell.code,
                version=cell.version,
                formula=cell.evaluation.formula,
                substituted=cell.evaluation.substituted,
                computed=cell.value,
                reported=reported,
                statement=_STATEMENT_NAMES[statement],
            )
        )
    return tuple(out)


def formula_report(built: BuiltStatements) -> FormulaReport:
    """Recompute every derivable subtotal, for every period, with its trace."""
    formulas = derivation_formulas()
    graph = DependencyGraph(formulas)

    years = []
    for year in built.years:
        environment, assumed_nil = ledger_environment(built.ledgers, year)
        subset = computable_subset(formulas, environment)
        # strict=False: a filing that does not report every component of a
        # subtotal is the normal case, not an error. The cell is reported as
        # not computable, with the component that is missing named.
        model = calculate(subset, environment, strict=False)
        skipped = dict(model.unavailable)
        for definition in formulas:
            if definition.target in subset.targets:
                continue
            missing = sorted(definition.inputs - set(environment.paths) - set(subset.targets))
            skipped[definition.target] = (
                "the filing reports none of " + ", ".join(missing)
                if len(missing) == len(definition.inputs)
                else "the filing does not report " + ", ".join(missing)
            )
        years.append(
            YearTrace(
                year=year,
                cells=_traces(model, built, year),
                unavailable=skipped,
                assumed_nil=assumed_nil,
                fingerprint=model.fingerprint,
                inputs=model.inputs,
            )
        )

    return FormulaReport(
        formulas=formulas,
        order=graph.order(),
        required_inputs=tuple(sorted(graph.required_inputs)),
        years=tuple(years),
    )
