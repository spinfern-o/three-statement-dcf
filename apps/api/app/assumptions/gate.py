"""14.1, evaluated: "No forecast may calculate until all required assumptions
have a status."

Read literally, that sentence is satisfied by construction -- every
`Assumption` has a status, because the field has a default. Read as it is
plainly meant, it asks whether every driver the forecast needs has an answer,
and Draft, Needs Source and Rejected are not answers. `Status.blocks_calculation`
says which is which, and this evaluates it per scenario and per period.

The per-period part matters. A model with five forecast years and a revenue
growth assumption scoped to 2026E alone is missing four. The gate walks the
periods rather than the codes, so it names 2027E rather than reporting that
revenue growth "exists".
"""

from __future__ import annotations

from .drivers import REQUIRED, describe_choice
from .scenarios import ScenarioSet
from .workflow import GateResult


def evaluate(scenarios: ScenarioSet, scenario_id: str, periods: tuple[str, ...]) -> GateResult:
    """14.1 for one scenario across its forecast periods."""
    missing: list[str] = []
    unresolved: list[tuple[str, str]] = []
    ambiguous: list[str] = []
    self_reviewed: list[str] = []

    for period in periods:
        resolved = scenarios.resolve(scenario_id, period=period)
        for choice in REQUIRED:
            supplied = [code for code in sorted(choice) if code in resolved]
            if not supplied:
                missing.append(f"{describe_choice(choice)} for {period}")
                continue
            if len(supplied) > 1:
                ambiguous.append(
                    f"{' and '.join(supplied)} for {period} -- STEP 14/18 require "
                    "one stated methodology per line"
                )
                continue
            assumption = resolved[supplied[0]].assumption
            if assumption.status.blocks_calculation:
                unresolved.append((f"{assumption.code} for {period}", assumption.status.value))
            elif assumption.is_self_reviewed:
                self_reviewed.append(f"{assumption.code} for {period}")

    return GateResult(
        missing=tuple(dict.fromkeys(missing)),
        unresolved=tuple(dict.fromkeys(unresolved)),
        ambiguous=tuple(dict.fromkeys(ambiguous)),
        self_reviewed=tuple(dict.fromkeys(self_reviewed)),
    )
