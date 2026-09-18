"""Items 93 and 94: the unsaved-change preview and the dependency impact.

14.8: "Changing one assumption must show all affected outputs before saving."

The word doing the work is *before*. A preview computed by saving,
recalculating and then offering an undo is not a preview -- it has already
changed the model, and if the reviewer walks away the change stands. So
`preview` takes the proposed value, runs the calculation on a copy, and
returns both sides without touching the set it was given. `ScenarioSet` is
immutable, which is what makes that cheap rather than careful.

The dependency half (item 94) is Phase 8's graph, reused rather than rebuilt.
`DependencyGraph.descendants` already answers "what reads this, directly or
not", and `recalculate` already recomputes exactly that set. A second
traversal written here would be a second answer to the same question, and the
two would disagree the first time either changed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ..formula.calculate import CalculatedModel, calculate, recalculate
from ..formula.evaluate import Environment
from ..formula.graph import DependencyGraph
from ..formula.registry import FormulaSet
from ..formula.units import unit_for
from .scenarios import ScenarioSet
from .schema import Assumption


@dataclass(frozen=True)
class MovedValue:
    target: str
    before: Decimal | None
    after: Decimal | None

    @property
    def difference(self) -> Decimal | None:
        if self.before is None or self.after is None:
            return None
        return self.after - self.before

    @property
    def is_new(self) -> bool:
        return self.before is None and self.after is not None

    @property
    def disappeared(self) -> bool:
        return self.before is not None and self.after is None


@dataclass(frozen=True)
class Impact:
    """What a proposed change would do, computed without doing it."""

    code: str
    before: Decimal
    after: Decimal
    #: Everything that reads this assumption, directly or through others.
    reaches: tuple[str, ...]
    #: Of those, the ones whose value actually moves.
    moved: tuple[MovedValue, ...]
    #: Targets that could not be calculated either way, with the reason.
    unavailable: dict[str, str]

    @property
    def changes_nothing(self) -> bool:
        return not self.moved

    def describe(self) -> str:
        if self.before == self.after:
            return f"{self.code} is unchanged."
        head = f"{self.code}: {self.before} -> {self.after}"
        if not self.reaches:
            return (
                f"{head}. Nothing in the calculation reads it, so no output "
                "moves -- which is worth seeing before saving, because a driver "
                "nothing reads is usually a driver that is misnamed."
            )
        if self.changes_nothing:
            return f"{head}. {len(self.reaches)} output(s) depend on it and none of them moves."
        return f"{head}. {len(self.moved)} of {len(self.reaches)} dependent output(s) move."


def _environment(
    base: Environment, resolved: Mapping[str, object], override: tuple[str, Decimal] | None
) -> Environment:
    """A copy of `base` with the scenario's assumptions written over it."""
    environment = Environment(dict(base.values))
    for code, item in resolved.items():
        assumption: Assumption = item.assumption  # type: ignore[attr-defined]
        value = assumption.value
        if override is not None and override[0] == code:
            value = override[1]
        environment.put(code, value, unit_for(assumption.unit), origin=f"assumption {code}")
    return environment


def preview(
    *,
    formulas: FormulaSet,
    base_environment: Environment,
    scenarios: ScenarioSet,
    scenario_id: str,
    code: str,
    proposed: Decimal,
    period: str | None = None,
) -> Impact:
    """14.8: what changing `code` to `proposed` would do, before saving.

    Nothing is written. The `ScenarioSet` passed in is returned untouched by
    virtue of never being touched: both sides are computed into fresh
    environments.
    """
    resolved = scenarios.resolve(scenario_id, period=period)
    if code not in resolved:
        raise KeyError(
            f"{code!r} is not an assumption {scenario_id!r} carries"
            + (f" for {period}" if period else "")
        )
    current = resolved[code].assumption.value

    before_model = calculate(formulas, _environment(base_environment, resolved, None), strict=False)
    after_environment = _environment(base_environment, resolved, (code, proposed))
    # Recalculating from the first model rather than calculating afresh is the
    # 18.8 path, and it is also the honest one: it is what saving would do, so
    # the preview shows what saving would produce.
    after_model = recalculate(before_model, after_environment, (code,), strict=False)

    reaches = tuple(sorted(DependencyGraph(formulas).descendants(code)))
    moved = tuple(
        MovedValue(target, before_model.value(target), after_model.value(target))
        for target in reaches
        if before_model.value(target) != after_model.value(target)
    )
    unavailable = {
        target: reason for target, reason in after_model.unavailable.items() if target in reaches
    }
    return Impact(
        code=code,
        before=current,
        after=proposed,
        reaches=reaches,
        moved=moved,
        unavailable=unavailable,
    )


def reaches(formulas: FormulaSet, code: str) -> tuple[str, ...]:
    """Item 94 on its own: what depends on this driver, without changing it."""
    return tuple(sorted(DependencyGraph(formulas).descendants(code)))


def unread_assumptions(
    formulas: FormulaSet, scenarios: ScenarioSet, scenario_id: str
) -> tuple[str, ...]:
    """Assumptions nothing in the calculation reads.

    Not an error -- a driver may feed a formula family this set does not carry.
    It is reported because a misspelled driver code looks exactly like this,
    and the engine's own failure mode for one is to halt several steps later
    naming a different driver.
    """
    graph = DependencyGraph(formulas)
    known = graph.required_inputs | graph.targets
    return tuple(sorted(code for code in scenarios.resolve(scenario_id) if code not in known))


def model_for(
    formulas: FormulaSet,
    base_environment: Environment,
    scenarios: ScenarioSet,
    scenario_id: str,
    period: str | None = None,
) -> CalculatedModel:
    """The calculation as one scenario currently stands."""
    resolved = scenarios.resolve(scenario_id, period=period)
    return calculate(formulas, _environment(base_environment, resolved, None), strict=False)
