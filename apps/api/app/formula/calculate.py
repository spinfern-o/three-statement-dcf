"""Items 85 and 86: running a formula set, and running it again after a change.

18.15 says deterministic calculations run server-side, and 18.16 that the
browser may preview an edit but released outputs must come from the
authoritative calculation. Everything in this module is that authoritative
side: pure functions over immutable inputs, returning a `CalculatedModel` that
carries its own fingerprint.

Two requirements are easy to state and easy to get subtly wrong.

**18.8 -- recalculate only affected descendants after a change.** The
temptation is to recompute everything, which is always correct and makes the
requirement pointless. `recalculate` walks the reverse graph from the changed
paths, recomputes exactly that set in topological order, and carries every
other cell across unchanged -- and a test asserts the untouched cells are the
*same objects*, because "was not recalculated" is not observable from equal
values.

**18.9 -- preserve the prior calculated model version.** The new model holds a
reference to the one it came from, which is what makes an audit trail possible
and what lets a reviewer see that a number moved rather than merely that it is
now different.

A cell whose inputs are not all available is not computed and is not zero.
With `strict=True` that is an error, because an export must not move on a
value nobody has; with `strict=False` it is recorded in `unavailable` with the
reason, and treated as absent for everything downstream. That is the same
distinction `statements/build.py` draws, for the same reason. A division by
zero is handled the same way and for the same reason -- see `_compute`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .evaluate import (
    DivisionByZeroRefused,
    Environment,
    Evaluation,
    EvaluationError,
    MissingInput,
    evaluate,
)
from .graph import DependencyGraph
from .registry import FormulaDefinition, FormulaSet, calculation_fingerprint
from .units import UnitError


@dataclass(frozen=True)
class CalculatedCell:
    """One computed value, with everything 18.10 and 18.11 ask for beside it."""

    target: str
    code: str
    version: int
    evaluation: Evaluation

    @property
    def value(self) -> Decimal:
        return self.evaluation.value

    def explain(self) -> str:
        return f"{self.target} = {self.evaluation.explain()}  [{self.code} v{self.version}]"


@dataclass(frozen=True)
class CalculatedModel:
    """The result of running a formula set, and the one it replaced (18.9)."""

    formulas: FormulaSet
    cells: dict[str, CalculatedCell]
    #: target -> why it could not be computed. Never a zero.
    unavailable: dict[str, str]
    #: The leaf inputs this calculation actually rested on.
    inputs: dict[str, Decimal]
    #: 18.7.
    fingerprint: str
    version: int = 1
    #: 18.9. The model this one replaced, or None for the first calculation.
    previous: CalculatedModel | None = field(default=None, repr=False)
    #: 18.8. Which targets this round actually recomputed.
    recalculated: tuple[str, ...] = ()

    def value(self, target: str) -> Decimal | None:
        cell = self.cells.get(target)
        return None if cell is None else cell.value

    def require(self, target: str) -> Decimal:
        if target not in self.cells:
            reason = self.unavailable.get(target, "it was not calculated")
            raise EvaluationError(f"{target} has no value: {reason}")
        return self.cells[target].value

    @property
    def carried_over(self) -> tuple[str, ...]:
        """Cells this round reused rather than recomputed (18.8)."""
        return tuple(sorted(set(self.cells) - set(self.recalculated)))

    def changed_from_previous(self) -> tuple[str, ...]:
        """Targets whose value differs from the model this one replaced."""
        if self.previous is None:
            return tuple(sorted(self.cells))
        return tuple(
            sorted(
                target
                for target in self.cells
                if self.previous.value(target) != self.cells[target].value
            )
        )

    def describe(self) -> str:
        lines = [
            f"  version {self.version}, fingerprint {self.fingerprint[:16]}",
            f"  {len(self.cells)} calculated, {len(self.unavailable)} unavailable",
        ]
        if self.previous is not None:
            lines.append(
                f"  recalculated {len(self.recalculated)}, "
                f"carried over {len(self.carried_over)} (18.8)"
            )
        return "\n".join(lines)


def _fingerprint(formulas: FormulaSet, environment: Environment, graph: DependencyGraph):
    used = {
        path: environment.get(path).amount
        for path in sorted(graph.required_inputs)
        if environment.has(path)
    }
    return used, calculation_fingerprint(formulas, used)


def _compute(
    definition: FormulaDefinition,
    environment: Environment,
    strict: bool,
) -> tuple[CalculatedCell | None, str]:
    """Evaluate one definition, or say why it could not be.

    Two kinds of failure, and the difference matters.

    A **missing input** and a **division by zero** are facts about the data.
    4.12 says outright that a relative measure against a zero expected value is
    *undefined*, which is a legitimate state for a figure to be in, not a
    defect in the formula that found it: `gross_profit / revenue` is a correct
    formula and a company with no revenue has no gross margin. Not strict, both
    are recorded with their reason; strict, both refuse, because an export must
    not move on a figure nobody has.

    A **unit error** is a fact about the formula. No data makes
    `revenue * revenue` mean something, and tolerating it would hide a defect
    rather than report a gap -- so it is raised either way.
    """
    try:
        evaluation = evaluate(definition.tree, environment, definition.unit)
    except (MissingInput, DivisionByZeroRefused) as exc:
        if strict:
            raise
        return None, str(exc).split(". ")[0]
    except (EvaluationError, UnitError):
        raise
    return (
        CalculatedCell(
            target=definition.target,
            code=definition.code,
            version=definition.version,
            evaluation=evaluation,
        ),
        "",
    )


def calculate(
    formulas: FormulaSet, environment: Environment, *, strict: bool = True
) -> CalculatedModel:
    """Run a whole formula set, in the order 18.5 requires.

    The graph refuses up front if there is a cycle (18.6), so nothing here has
    to guard against one at evaluation time.
    """
    graph = DependencyGraph(formulas)
    order = graph.order()  # raises CycleError before anything is evaluated
    by_target = {d.target: d for d in formulas}

    working = Environment(dict(environment.values))
    cells: dict[str, CalculatedCell] = {}
    unavailable: dict[str, str] = {}

    for target in order:
        definition = by_target[target]
        cell, reason = _compute(definition, working, strict)
        if cell is None:
            # Absent, not zero: it stays out of the environment, so anything
            # downstream refuses for the same reason rather than inheriting a
            # fabricated zero (18.14).
            unavailable[target] = reason
            continue
        cells[target] = cell
        working.put(target, cell.value, definition.unit, origin=definition.code)

    inputs, fingerprint = _fingerprint(formulas, environment, graph)
    return CalculatedModel(
        formulas=formulas,
        cells=cells,
        unavailable=unavailable,
        inputs=inputs,
        fingerprint=fingerprint,
        version=1,
        previous=None,
        recalculated=order,
    )


def recalculate(
    model: CalculatedModel,
    environment: Environment,
    changed: tuple[str, ...],
    *,
    strict: bool = True,
) -> CalculatedModel:
    """18.8: recompute only what the change reaches.

    `changed` names the input paths whose values moved. `environment` is the
    full environment with those new values in it -- the whole environment
    rather than a delta, because a recalculation that trusts the caller to
    have told it about every change is a recalculation that silently goes
    stale.

    The model it returns keeps `model` as `previous` (18.9), and every cell
    outside the affected set is carried across as the same object, so "was not
    recalculated" is observable and testable.
    """
    graph = DependencyGraph(model.formulas)
    affected = graph.descendants(*changed)
    order = graph.order_for(affected)
    by_target = {d.target: d for d in model.formulas}

    working = Environment(dict(environment.values))
    # Everything that is not being recalculated keeps the value it had, so a
    # downstream formula reads the same number it read last time.
    for target, cell in model.cells.items():
        if target not in affected:
            working.put(target, cell.value, by_target[target].unit, origin=cell.code)

    cells = {t: c for t, c in model.cells.items() if t not in affected}
    unavailable = {t: r for t, r in model.unavailable.items() if t not in affected}

    for target in order:
        definition = by_target[target]
        # `computed`, not `cell`: the loop above binds `cell` to a stored
        # CalculatedCell, and reusing the name here made the optional result
        # of `_compute` look non-optional to anything reading the function.
        computed, reason = _compute(definition, working, strict)
        if computed is None:
            unavailable[target] = reason
            continue
        cells[target] = computed
        working.put(target, computed.value, definition.unit, origin=definition.code)

    inputs, fingerprint = _fingerprint(model.formulas, environment, graph)
    return CalculatedModel(
        formulas=model.formulas,
        cells=cells,
        unavailable=unavailable,
        inputs=inputs,
        fingerprint=fingerprint,
        version=model.version + 1,
        previous=model,
        recalculated=order,
    )


def environment_from(values: dict[str, tuple]) -> Environment:
    """`{"revenue": (Decimal("100"), CURRENCY)}` -> an `Environment`."""
    environment = Environment()
    for path, (amount, unit) in values.items():
        environment.put(path, amount, unit, origin=path)
    return environment
