"""Item 92: the Scenario entity, its inheritance, and its lineage.

**This entity is designed here, not transcribed.** Section 9 makes
`scenario_id` a required field on `Assumption` (9.10) and `CalculatedValue`
(9.12), and references it from `ValidationResult` (9.13) -- and then defines no
Scenario row. That is finding F-5 in the decision ledger. Item 92 requires
scenario creation and inheritance regardless, so the entity below is built from
the only things the specification does constrain about it, with every choice
stated so the owner can overrule one:

  14.6  "Provide Base, Upside, and Downside scenarios only after their
        differences are explicitly entered."
  14.7  "A copied scenario must retain inherited assumption lineage."
  14.9  "Scenario names must not imply probability unless probability is
        explicitly modeled and sourced."
  1.19  "Never describe a scenario forecast as a fact or guarantee."

Three consequences follow, and each is enforced rather than documented.

**A scenario that differs from its parent in nothing is refused** (14.6). An
Upside identical to Base is not an upside case; it is a label. `differences()`
reports what actually departs, and `ScenarioSet.check_differences` refuses to
present a named variant that has none.

**Inheritance is by lineage, not by copy** (14.7). A child scenario holds only
its overrides; resolution walks up to the parent for everything else, and every
resolved assumption says which scenario it came from. Copying the values
instead would make the child's provenance a snapshot that silently goes stale
the moment the parent is corrected.

**A name that implies probability is refused** (14.9). "Likely case",
"expected case", "P90" and the rest are claims about distribution, and this
system models no distribution. The refusal names the word, and it lifts only
when the scenario carries an explicitly sourced probability -- which is what
14.9 says, read strictly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal

from .schema import Assumption, AssumptionError, Evidence, SourceType

#: The reserved identifier for the root scenario. Every other scenario
#: descends from it, so there is always exactly one set of assumptions a
#: variant is a variant OF.
BASE = "base"

#: 14.9. Words that assert something about likelihood. The list is short and
#: explicit on purpose -- a heuristic that guesses would refuse "Downside" for
#: containing "down", and a reviewer arguing with a guess stops reading the
#: rule.
PROBABILITY_WORDS = (
    "likely", "unlikely", "probable", "probability", "improbable",
    "expected", "certain", "uncertain", "guaranteed", "odds", "chance",
    "median", "percentile", "confidence",
)
#: `P50`, `P90`: percentile shorthand, which is the same claim in fewer letters.
PERCENTILE = re.compile(r"\bp\s?\d{1,3}\b", re.IGNORECASE)


class ScenarioError(ValueError):
    """A scenario is not usable as named or as structured."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Probability:
    """14.9's escape clause: an explicitly modelled and sourced likelihood.

    Required before a scenario may be named for its likelihood. It is a
    separate object rather than two more fields so that "sourced" cannot be
    satisfied by leaving a string empty.
    """

    value: Decimal
    source: str
    date: str

    def __post_init__(self) -> None:
        from model.numeric import D

        object.__setattr__(self, "value", D(self.value, what="scenario probability"))
        if not 0 <= self.value <= 1:
            raise ScenarioError(
                f"a probability must be between 0 and 1, got {self.value}"
            )
        if not self.source.strip() or not self.date.strip():
            raise ScenarioError(
                "14.9 allows a probability-implying name only when the "
                "probability is explicitly modelled AND sourced. A probability "
                "with no source and date is neither."
            )


@dataclass(frozen=True)
class Scenario:
    """One set of assumption overrides over a parent.

    The entity Section 9 references and does not define. Its fields follow
    Section 9's own conventions for the rows it does define -- an id, a name,
    a parent reference, who made it and when -- plus what 14.6 to 14.9 need.
    """

    id: str
    name: str
    #: The scenario this one varies from. None only for `base`.
    parent_id: str | None = BASE
    description: str = ""
    created_by: str = ""
    created_at: str = field(default_factory=_now)
    #: 14.9. Present only when the name asserts a likelihood.
    probability: Probability | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ScenarioError("a scenario needs an id")
        if not self.name.strip():
            raise ScenarioError(f"{self.id}: a scenario needs a name")
        if self.id == BASE and self.parent_id is not None:
            raise ScenarioError("the base scenario has no parent")
        if self.id != BASE and not self.parent_id:
            raise ScenarioError(
                f"{self.id}: every scenario but {BASE!r} varies from another "
                "one, so a parent is required (14.7)"
            )
        if self.parent_id == self.id:
            raise ScenarioError(f"{self.id}: a scenario cannot be its own parent")
        self._check_name()

    def _check_name(self) -> None:
        """14.9, and 1.19 behind it."""
        if self.probability is not None:
            return
        lowered = self.name.lower()
        for word in PROBABILITY_WORDS:
            if re.search(rf"\b{word}\b", lowered):
                raise ScenarioError(
                    f"{self.id}: the name {self.name!r} contains {word!r}, which "
                    "asserts something about likelihood. This system models no "
                    "distribution, so the claim would be unsupported (14.9, and "
                    "1.19: never describe a scenario forecast as a fact). Rename "
                    "it, or attach an explicitly sourced probability."
                )
        if PERCENTILE.search(lowered):
            raise ScenarioError(
                f"{self.id}: the name {self.name!r} uses percentile shorthand, "
                "which is a claim about a distribution this system does not "
                "model (14.9). Rename it, or attach a sourced probability."
            )

    @property
    def is_base(self) -> bool:
        return self.id == BASE


def base_scenario(created_by: str = "") -> Scenario:
    return Scenario(
        id=BASE,
        name="Base",
        parent_id=None,
        description=(
            "The assumptions as sourced, with no variant applied. Every other "
            "scenario is a set of departures from this one."
        ),
        created_by=created_by,
    )


@dataclass(frozen=True)
class Resolved:
    """One assumption as a scenario sees it, and where it came from."""

    assumption: Assumption
    #: The scenario whose own record supplied this value.
    from_scenario: str
    #: The chain walked to reach it, nearest first.
    lineage: tuple[str, ...]

    @property
    def is_inherited(self) -> bool:
        return self.from_scenario != self.lineage[0]


@dataclass(frozen=True)
class ScenarioSet:
    """The scenarios of one model, and the assumptions each one holds.

    Immutable, like `MappingSet` and `FormulaSet`, for the same reason: a
    calculated value records the scenario it was produced under, and a
    scenario that can be edited in place makes that reference meaningless.
    """

    scenarios: tuple[Scenario, ...]
    assumptions: tuple[Assumption, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        by_id: dict[str, Scenario] = {}
        for scenario in self.scenarios:
            if scenario.id in by_id:
                raise ScenarioError(f"two scenarios share the id {scenario.id!r}")
            by_id[scenario.id] = scenario
        if BASE not in by_id:
            raise ScenarioError(
                f"a scenario set needs a {BASE!r} scenario: every variant is a "
                "variant of something (14.7)"
            )
        for scenario in self.scenarios:
            if scenario.parent_id and scenario.parent_id not in by_id:
                raise ScenarioError(
                    f"{scenario.id}: parent {scenario.parent_id!r} is not in this set"
                )
        # A cycle would make `lineage` walk forever; the same lesson as 18.6.
        for scenario in self.scenarios:
            seen, node = {scenario.id}, scenario
            while node.parent_id:
                if node.parent_id in seen:
                    raise ScenarioError(
                        f"scenario inheritance is circular through {node.parent_id!r}"
                    )
                seen.add(node.parent_id)
                node = by_id[node.parent_id]
        for assumption in self.assumptions:
            if assumption.scenario_id not in by_id:
                raise ScenarioError(
                    f"assumption {assumption.code!r} names scenario "
                    f"{assumption.scenario_id!r}, which is not in this set"
                )

    # --- reading ------------------------------------------------------------
    def scenario(self, scenario_id: str) -> Scenario:
        for scenario in self.scenarios:
            if scenario.id == scenario_id:
                return scenario
        raise KeyError(
            f"no scenario {scenario_id!r}; known: {[s.id for s in self.scenarios]}"
        )

    def lineage(self, scenario_id: str) -> tuple[str, ...]:
        """This scenario, then its parent, then its parent's parent."""
        chain = [scenario_id]
        node = self.scenario(scenario_id)
        while node.parent_id:
            chain.append(node.parent_id)
            node = self.scenario(node.parent_id)
        return tuple(chain)

    def own(self, scenario_id: str) -> tuple[Assumption, ...]:
        return tuple(a for a in self.assumptions if a.scenario_id == scenario_id)

    def resolve(self, scenario_id: str, period: str | None = None) -> dict[str, Resolved]:
        """14.7: every assumption this scenario sees, and where each came from.

        Two precedence rules, in this order.

        **Nearer scenario wins.** A scenario's own record for a code shadows
        its parent's, and the parent's stays reachable -- which is what makes
        an override legible as an override rather than as a different number.

        **More specific period wins.** Within one scenario, an assumption
        scoped to this period shadows one scoped to every period. That is the
        engine's own rule -- `model/assumptions.py:get` tries `(name, year)`
        before `(name, None)` -- and STEP 14 depends on it: "do not assume
        every expense should remain a constant percentage of revenue" is
        followed by setting an all-years default and overriding the years that
        differ. Without this the two would race on insertion order.
        """
        chain = self.lineage(scenario_id)
        out: dict[str, Resolved] = {}
        general: dict[str, Resolved] = {}
        for source_scenario in chain:
            for assumption in self.own(source_scenario):
                if period is not None and not assumption.applies_to(period):
                    continue
                bucket = (
                    general
                    if period is not None and assumption.applies_to_every_period
                    else out
                )
                if assumption.code in bucket:
                    continue  # a nearer scenario already answered
                bucket[assumption.code] = Resolved(assumption, source_scenario, chain)
        for code, resolved in general.items():
            out.setdefault(code, resolved)
        return out

    def differences(
        self, scenario_id: str
    ) -> tuple[tuple[str, Decimal | None, Decimal], ...]:
        """14.6: what this scenario actually departs from its parent in.

        `(code, parent value, this scenario's value)` for every code where the
        two disagree. A code the scenario introduces that the parent does not
        carry counts as a difference; a code it restates at the same value
        does not, because restating a number is not a departure.
        """
        scenario = self.scenario(scenario_id)
        if scenario.parent_id is None:
            return ()
        parent = self.resolve(scenario.parent_id)
        out = []
        for assumption in self.own(scenario_id):
            inherited = parent.get(assumption.code)
            before = inherited.assumption.value if inherited else None
            if before is None or before != assumption.value:
                out.append((assumption.code, before, assumption.value))
        # Sorted on the code, not on the whole row: `before` is None for an
        # assumption the parent does not carry, and sorting whole rows would
        # compare a Decimal against None the moment two codes matched.
        return tuple(sorted(out, key=lambda row: row[0]))

    def check_differences(self, scenario_id: str) -> str:
        """14.6, as a sentence. Empty when the scenario is a real variant."""
        scenario = self.scenario(scenario_id)
        if scenario.is_base:
            return ""
        if not self.differences(scenario_id):
            return (
                f"{scenario.name!r} differs from {scenario.parent_id!r} in nothing. "
                "14.6 allows a named variant only after its differences are "
                "explicitly entered -- until then the name asserts a case the "
                "model does not contain."
            )
        return ""

    # --- writing ------------------------------------------------------------
    def with_scenario(self, scenario: Scenario) -> ScenarioSet:
        return replace(
            self, scenarios=self.scenarios + (scenario,), version=self.version + 1
        )

    def with_assumption(self, assumption: Assumption) -> ScenarioSet:
        kept = tuple(
            a for a in self.assumptions
            if not (
                a.scenario_id == assumption.scenario_id
                and a.code == assumption.code
                and a.periods == assumption.periods
            )
        )
        return replace(
            self, assumptions=kept + (assumption,), version=self.version + 1
        )

    def override(
        self,
        scenario_id: str,
        code: str,
        value,
        *,
        owner: str,
        rationale: str,
        periods: tuple[str, ...] = (),
    ) -> ScenarioSet:
        """14.7: override an inherited assumption, keeping its lineage.

        The override records the scenario it departs from and carries the
        inherited assumption's own evidence forward, because the evidence for
        the *base* number is still the evidence a reviewer needs to judge the
        departure from it.
        """
        scenario = self.scenario(scenario_id)
        if scenario.parent_id is None:
            raise ScenarioError(
                f"{scenario_id} has no parent, so there is nothing to override. "
                "Add the assumption to it directly."
            )
        inherited = self.resolve(scenario.parent_id).get(code)
        if inherited is None:
            raise AssumptionError(
                f"{code!r} is not an assumption {scenario.parent_id!r} carries, so "
                "overriding it would invent a driver rather than vary one. Add it "
                "to the parent scenario first."
            )
        source = inherited.assumption
        return self.with_assumption(
            Assumption(
                code=code,
                name=source.name,
                value=value,
                unit=source.unit,
                periods=periods or source.periods,
                scenario_id=scenario_id,
                source_type=SourceType.SCENARIO_OVERRIDE,
                evidence=Evidence(
                    document_id=source.evidence.document_id,
                    page=source.evidence.page,
                    url=source.evidence.url,
                    date=source.evidence.date,
                    measured_over=source.evidence.measured_over,
                ),
                rationale=rationale,
                owner=owner,
                inherited_from=inherited.from_scenario,
                overrides=f"{inherited.from_scenario}:{code}",
            )
        )

    def describe(self) -> str:
        lines = [f"  version {self.version}, {len(self.scenarios)} scenario(s)"]
        for scenario in self.scenarios:
            own = len(self.own(scenario.id))
            resolved = len(self.resolve(scenario.id))
            lines.append(
                f"    {scenario.id}: {own} own, {resolved} resolved"
                + (f" (varies {scenario.parent_id})" if scenario.parent_id else "")
            )
        return "\n".join(lines)
