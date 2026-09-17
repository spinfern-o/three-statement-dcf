"""Items 79 and 80: the dependency graph, its order, and its cycles.

18.4 parse formulas into a dependency graph, 18.5 topologically order the
calculations, 18.6 **detect cycles before evaluation**.

"Before" is the requirement that shapes this module. A cycle found during
evaluation is found by running out of stack or by a value that will not settle,
and either way the diagnostic names the place the machine gave up rather than
the loop a person has to break. So `DependencyGraph.order()` refuses up front
and names the cycle in the direction a reader follows it:

    interest_expense -> net_income -> retained_earnings -> debt -> interest_expense

That cycle is not hypothetical. It is the circularity every three-statement
model has -- interest depends on debt, debt depends on the cash flow, the cash
flow depends on net income, and net income depends on interest. Real models
break it with a policy: a fixed rate on beginning debt, which is exactly what
`model/forecast.py` does and what `schedules/interest.py` reports. The graph's
job is to make the choice visible rather than to iterate quietly towards a
fixed point.

The ordering is deterministic: among nodes that are ready at the same time, it
takes them in sorted order. A topological sort has many valid answers, and a
calculation that produces its results in a different order on two runs is a
calculation whose fingerprint depends on dictionary iteration (18.7).
"""

from __future__ import annotations

from dataclasses import dataclass

from .registry import FormulaDefinition, FormulaSet


class CycleError(ValueError):
    """18.6. One or more cycles, named, before anything was evaluated."""

    def __init__(self, cycles: "tuple[tuple[str, ...], ...]"):
        self.cycles = cycles
        drawn = "\n".join(
            "    " + " -> ".join(cycle + (cycle[0],)) for cycle in cycles
        )
        super().__init__(
            f"{len(cycles)} circular dependenc"
            f"{'y' if len(cycles) == 1 else 'ies'} found before evaluation "
            f"(18.6):\n{drawn}\n"
            "Break it with a stated policy -- charging interest on beginning "
            "debt is the usual one -- rather than iterating to a fixed point, "
            "which converges on an answer nobody chose."
        )


@dataclass(frozen=True)
class DependencyGraph:
    """Targets, what each depends on, and what depends on each."""

    formulas: FormulaSet

    @property
    def targets(self) -> "frozenset[str]":
        return frozenset(self.formulas.targets)

    @property
    def edges(self) -> "dict[str, frozenset[str]]":
        """target -> the references it needs, whether or not they are computed."""
        return {d.target: d.inputs for d in self.formulas}

    @property
    def internal_edges(self) -> "dict[str, frozenset[str]]":
        """target -> the references that are themselves computed here.

        A reference to something the graph does not compute is a leaf: it must
        come from the environment, and it is reported by `required_inputs`
        rather than ordered.
        """
        computed = self.targets
        return {target: inputs & computed for target, inputs in self.edges.items()}

    @property
    def required_inputs(self) -> "frozenset[str]":
        """Everything the graph needs and does not produce."""
        computed = self.targets
        needed: "frozenset[str]" = frozenset()
        for inputs in self.edges.values():
            needed |= inputs - computed
        return needed

    def dependents(self) -> "dict[str, frozenset[str]]":
        """The reverse graph: reference -> the targets that read it."""
        out: "dict[str, set[str]]" = {}
        for target, inputs in self.edges.items():
            for reference in inputs:
                out.setdefault(reference, set()).add(target)
        return {key: frozenset(value) for key, value in out.items()}

    # --- 18.6: cycles, before anything runs ---------------------------------
    def cycles(self) -> "tuple[tuple[str, ...], ...]":
        """Every elementary cycle among the computed targets.

        Depth-first with an explicit stack, taking successors in sorted order,
        so the cycle reported for a given graph is the same on every run.
        """
        edges = self.internal_edges
        found: "list[tuple[str, ...]]" = []
        seen: "set[frozenset[str]]" = set()
        visited: "set[str]" = set()

        def walk(node: str, path: "list[str]", on_path: "set[str]") -> None:
            path.append(node)
            on_path.add(node)
            # A target reads its inputs, so the arrow runs input -> target;
            # walking the inputs traverses the cycle backwards, and the path
            # is reversed before reporting so a reader follows it forwards.
            for successor in sorted(edges.get(node, frozenset())):
                if successor in on_path:
                    cycle = tuple(reversed(path[path.index(successor):]))
                    key = frozenset(cycle)
                    if key not in seen:
                        seen.add(key)
                        # Start the printed cycle at its alphabetically first
                        # member, so the same loop is drawn the same way
                        # whichever node the walk happened to reach first.
                        start = cycle.index(min(cycle))
                        found.append(cycle[start:] + cycle[:start])
                elif successor not in visited:
                    walk(successor, path, on_path)
            path.pop()
            on_path.discard(node)
            visited.add(node)

        for target in sorted(edges):
            if target not in visited:
                walk(target, [], set())
        return tuple(found)

    # --- 18.5: the order to calculate in ------------------------------------
    def order(self) -> "tuple[str, ...]":
        """A deterministic topological order, or `CycleError` naming the loops."""
        cycles = self.cycles()
        if cycles:
            raise CycleError(cycles)

        edges = self.internal_edges
        remaining = dict(edges)
        done: "list[str]" = []
        satisfied: "set[str]" = set()
        while remaining:
            ready = sorted(
                target for target, inputs in remaining.items()
                if inputs <= satisfied
            )
            if not ready:  # pragma: no cover - cycles() has already refused
                raise CycleError((tuple(sorted(remaining)),))
            for target in ready:
                done.append(target)
                satisfied.add(target)
                del remaining[target]
        return tuple(done)

    # --- 18.8: what a change affects ----------------------------------------
    def descendants(self, *changed: str) -> "frozenset[str]":
        """Every target that depends on one of `changed`, directly or not.

        This is what 18.8 means by "only affected descendants". The changed
        paths themselves are not included: a changed input is not recalculated,
        and a changed formula's own target is added by the caller, which knows
        whether the change was to a value or to an expression.
        """
        dependents = self.dependents()
        frontier = list(changed)
        affected: "set[str]" = set()
        while frontier:
            node = frontier.pop()
            for dependent in dependents.get(node, frozenset()):
                if dependent not in affected:
                    affected.add(dependent)
                    frontier.append(dependent)
        return frozenset(affected)

    def order_for(self, targets: "frozenset[str]") -> "tuple[str, ...]":
        """The full order, filtered to `targets`, so recalculation stays ordered."""
        return tuple(target for target in self.order() if target in targets)

    def describe(self) -> str:
        lines = [
            f"  {len(self.targets)} calculated target(s), "
            f"{len(self.required_inputs)} required input(s)"
        ]
        cycles = self.cycles()
        lines.append(
            "  no cycles" if not cycles else f"  {len(cycles)} CYCLE(S)"
        )
        return "\n".join(lines)


def definition_order(formulas: FormulaSet) -> "tuple[FormulaDefinition, ...]":
    """The set's definitions in the order 18.5 requires they be calculated."""
    graph = DependencyGraph(formulas)
    by_target = {d.target: d for d in formulas}
    return tuple(by_target[target] for target in graph.order())
