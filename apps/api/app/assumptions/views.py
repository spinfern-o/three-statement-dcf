"""The 7.7 Assumptions screen, as rows a template can iterate.

7.7 asks for five things, and each maps onto a section of the screen:

  a. Historical driver analysis      -> `proposals.py`, from Phase 7's schedules
  b. Forecast assumptions by scenario-> `ScenarioSet.resolve`, with lineage
  c. Source, date, owner, rationale
     and confidence for every one    -> the `Assumption` record itself
  d. Base, upside, downside, custom  -> the scenario list, with 14.6's check
  e. No hidden assumptions           -> the gate, which names what is missing

**Confidence (7.7.c) is not a field on `Assumption`, deliberately.** Phase 3
computes a fact's confidence as `EvidenceCheck` -- a count of conditions
satisfied out of eight -- rather than as a number someone typed, because a
self-declared confidence is an opinion wearing a measurement's clothes. The
same reasoning applies here, so what the screen shows is the *evidence
standing*: the source type, whether the evidence its type demands is present,
the status, and whether it was reviewed by anyone other than its owner. That is
a description a reader can check, which a "high/medium/low" is not.
"""

from __future__ import annotations

from dataclasses import dataclass

from .drivers import BY_CODE, REQUIRED, describe_choice
from .scenarios import Resolved, ScenarioSet
from .schema import Assumption, Status


@dataclass(frozen=True)
class Standing:
    """7.7.c's "confidence", as a description rather than a self-assessment."""

    source_type: str
    evidence: str
    status: str
    reviewed_by: str
    self_reviewed: bool
    inherited_from: str

    @property
    def concerns(self) -> tuple[str, ...]:
        out = []
        if self.self_reviewed:
            out.append("approved by its own owner")
        if self.status in ("Draft", "Needs Source"):
            out.append("not yet an answer a forecast may use (14.1)")
        if self.status == "Rejected":
            out.append("rejected")
        return tuple(out)


@dataclass(frozen=True)
class Row:
    """One driver the forecast needs, and what the scenario has for it."""

    choice: str
    codes: tuple[str, ...]
    #: The assumption supplying it, if exactly one does.
    assumption: Assumption | None
    standing: Standing | None
    from_scenario: str
    #: Set when the row is not usable: missing, ambiguous, or unresolved.
    problem: str
    step: str
    unit: str
    note: str

    @property
    def is_satisfied(self) -> bool:
        return self.assumption is not None and not self.problem


def _standing(resolved: Resolved) -> Standing:
    assumption = resolved.assumption
    return Standing(
        source_type=assumption.source_type.value,
        evidence=assumption.evidence.describe(),
        status=assumption.status.value,
        reviewed_by=assumption.reviewer or "(nobody yet)",
        self_reviewed=assumption.is_self_reviewed,
        inherited_from=assumption.inherited_from,
    )


def required_rows(
    scenarios: ScenarioSet, scenario_id: str, period: str | None = None
) -> tuple[Row, ...]:
    """One row per required driver choice, satisfied or not.

    Driven by `REQUIRED` rather than by what happens to be stored, so a driver
    nobody has entered appears as an empty row rather than not appearing. 14.5
    and 7.7.e are the same requirement read twice: an assumption that is not on
    the screen is hidden, whether it is hidden in a formula or in an absence.
    """
    resolved = scenarios.resolve(scenario_id, period=period)
    rows = []
    for choice in sorted(REQUIRED, key=sorted):
        codes = tuple(sorted(choice))
        supplied = [code for code in codes if code in resolved]
        first = BY_CODE[codes[0]]

        if not supplied:
            rows.append(
                Row(
                    choice=describe_choice(choice), codes=codes, assumption=None,
                    standing=None, from_scenario="",
                    problem="not supplied", step=first.step, unit=first.unit,
                    note=first.note,
                )
            )
            continue
        if len(supplied) > 1:
            rows.append(
                Row(
                    choice=describe_choice(choice), codes=codes, assumption=None,
                    standing=None, from_scenario="",
                    problem=(
                        f"{' and '.join(supplied)} are both declared; STEP 14/18 "
                        "require one stated methodology per line"
                    ),
                    step=first.step, unit=first.unit, note=first.note,
                )
            )
            continue

        item = resolved[supplied[0]]
        driver = BY_CODE[supplied[0]]
        problem = ""
        if item.assumption.status.blocks_calculation:
            problem = f"status is {item.assumption.status.value}"
        elif item.assumption.unit != driver.unit:
            problem = (
                f"declared in {item.assumption.unit}, and {driver.code} is a "
                f"{driver.unit} driver (18.12)"
            )
        rows.append(
            Row(
                choice=describe_choice(choice),
                codes=codes,
                assumption=item.assumption,
                standing=_standing(item),
                from_scenario=item.from_scenario,
                problem=problem,
                step=driver.step,
                unit=driver.unit,
                note=driver.note,
            )
        )
    return tuple(rows)


def optional_rows(
    scenarios: ScenarioSet, scenario_id: str, period: str | None = None
) -> tuple[Row, ...]:
    """Discretionary drivers the scenario actually carries.

    Not listed when absent: `_optional` in the engine defaults them to zero
    because zero is the meaningful "this did not happen" value for a buyback
    or an acquisition, so an absent one is an answer rather than a gap.
    """
    resolved = scenarios.resolve(scenario_id, period=period)
    required_codes = {code for choice in REQUIRED for code in choice}
    rows = []
    for code in sorted(resolved):
        if code in required_codes or code not in BY_CODE:
            continue
        item = resolved[code]
        driver = BY_CODE[code]
        rows.append(
            Row(
                choice=code, codes=(code,), assumption=item.assumption,
                standing=_standing(item), from_scenario=item.from_scenario,
                problem="", step=driver.step, unit=driver.unit, note=driver.note,
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class ScenarioRow:
    scenario_id: str
    name: str
    parent_id: str | None
    lineage: tuple[str, ...]
    own: int
    resolved: int
    #: 14.6's check: empty when the scenario is a real variant.
    problem: str
    differences: tuple[tuple[str, object, object], ...]
    probability: str


def scenario_rows(scenarios: ScenarioSet) -> tuple[ScenarioRow, ...]:
    """7.7.d, with 14.6 evaluated for each."""
    return tuple(
        ScenarioRow(
            scenario_id=scenario.id,
            name=scenario.name,
            parent_id=scenario.parent_id,
            lineage=scenarios.lineage(scenario.id),
            own=len(scenarios.own(scenario.id)),
            resolved=len(scenarios.resolve(scenario.id)),
            problem=scenarios.check_differences(scenario.id),
            differences=scenarios.differences(scenario.id),
            probability=(
                ""
                if scenario.probability is None
                else f"{scenario.probability.value} ({scenario.probability.source}, "
                     f"{scenario.probability.date})"
            ),
        )
        for scenario in scenarios.scenarios
    )


def status_choices(assumption: Assumption) -> tuple[Status, ...]:
    """The statuses this assumption may legally move to, for the form."""
    from .workflow import LEGAL_TRANSITIONS

    return tuple(sorted(LEGAL_TRANSITIONS[assumption.status], key=lambda s: s.value))
