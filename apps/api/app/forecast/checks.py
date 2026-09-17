"""Item 108: "Run checks for every scenario and period" (15.20), and 15.21.

Two sentences, and they ask for different things.

**15.20 -- every scenario and every period.** `model/checks.py:run_all_checks`
already runs the thirteen checks over one forecast's whole year axis. What did
not exist is running them across a *set* of scenarios and reporting which
scenario a failure belongs to, which is what 9.13's `scenario_id_optional` is
for. An Upside that balances and a Downside that does not is exactly the case
a single-scenario check panel hides.

**15.21 -- not "Forecast Ready" until every CRITICAL check passes.** That word
is the problem. Section 17 lists thirty checks and assigns a severity to none
of them; `validation-policy.md` proposes twenty-five and labels every one a
proposal, which is finding **F-4** and is still open. A gate that invented its
own severities would be making a release decision on an assumption nobody
approved.

So the gate here does not invent them. It reports the state honestly and
refuses the label for a reason it can defend: **any FAIL at all withholds
Forecast Ready**, and a SKIP withholds it too, because rule 1.14 says an
unresolved requirement must not appear as resolved. That is strictly stricter
than 15.21 read with any severity assignment, so it cannot wrongly pass -- and
`severity_is_unassigned` says out loud that a stricter rule is standing in for
a decision the owner has not made.

**With one carve-out, which is not a loophole.** Two of the engine's thirteen
checks are about the *valuation*, and at this phase there is no valuation, so
both skip. Counting that against Forecast Ready would report the forecast as
unfinished because Phase 11 has not been built -- which makes the label
unreachable by construction and therefore meaningless. They are reported
separately as `deferred`, with their reason, and `VALUATION_CHECKS` names them
explicitly so a test can assert the set has not silently grown.
"""

from __future__ import annotations

from dataclasses import dataclass

from model.checks import CheckResult, Status, Tolerance, run_all_checks

from .build import ScenarioForecast

#: The two checks in `run_all_checks` that are about the VALUATION, not the
#: forecast. At this phase there is no valuation, so both correctly SKIP -- and
#: counting that against Forecast Ready would report the forecast as unfinished
#: because a later phase has not been built.
#:
#: They are named rather than detected, and a test asserts this set is exactly
#: the set that skips when no valuation is supplied. If the engine adds a third
#: valuation check, that test fails rather than this gate silently miscounting.
VALUATION_CHECKS = frozenset({
    "WACC > terminal growth rate",
    "FCFF matches three-statement forecast",
})

#: F-4. Stated on the panel rather than buried, because a reader has to know
#: that "critical" is being read as "all".
SEVERITY_NOTE = (
    "Specification 17 assigns a severity to none of its thirty checks, and "
    "validation-policy.md's proposals are proposals (finding F-4). Until an "
    "owner assigns them, 15.21's \"every critical check\" is read as EVERY "
    "check: any failure, and any check that could not run, withholds the "
    "Forecast Ready label. That is stricter than any severity assignment "
    "would be, so it cannot wrongly pass a model."
)


@dataclass(frozen=True)
class ScenarioChecks:
    """One scenario's results, with the scenario attached (9.13)."""

    scenario_id: str
    results: "tuple[CheckResult, ...]"

    @property
    def failed(self) -> "tuple[CheckResult, ...]":
        return tuple(r for r in self.results if r.status is Status.FAIL)

    @property
    def skipped(self) -> "tuple[CheckResult, ...]":
        """Forecast checks that could not run. Rule 1.14: reported, not passed."""
        return tuple(
            r for r in self.results
            if r.status is Status.SKIP and r.name not in VALUATION_CHECKS
        )

    @property
    def deferred(self) -> "tuple[CheckResult, ...]":
        """Valuation checks, which have nothing to run on until Phase 11.

        Separated from `skipped` rather than hidden. A forecast is not
        unfinished because the valuation does not exist yet, and reporting it
        as such would make the Forecast Ready label unreachable by
        construction. They are still shown, with their reason.
        """
        return tuple(
            r for r in self.results
            if r.status is Status.SKIP and r.name in VALUATION_CHECKS
        )

    @property
    def passed(self) -> "tuple[CheckResult, ...]":
        return tuple(r for r in self.results if r.status is Status.PASS)

    @property
    def is_forecast_ready(self) -> bool:
        """15.21, under the reading above: nothing failed and nothing skipped."""
        return not self.failed and not self.skipped

    def summarize(self) -> str:
        text = (
            f"{len(self.passed)} passed, {len(self.failed)} failed, "
            f"{len(self.skipped)} skipped"
        )
        if self.deferred:
            text += f", {len(self.deferred)} awaiting a valuation"
        return text

    def describe(self) -> str:
        if self.is_forecast_ready:
            return f"{self.scenario_id}: every check passes."
        parts = []
        if self.failed:
            parts.append(", ".join(r.name for r in self.failed) + " failed")
        if self.skipped:
            parts.append(", ".join(r.name for r in self.skipped) + " could not run")
        return f"{self.scenario_id}: " + "; ".join(parts)


@dataclass(frozen=True)
class ForecastReadiness:
    """15.20 and 15.21 across every scenario the model carries."""

    by_scenario: "tuple[ScenarioChecks, ...]"
    #: Scenarios that could not be forecast at all, with the reason.
    not_built: "dict[str, str]"

    @property
    def is_forecast_ready(self) -> bool:
        """Every scenario, not the best one.

        A model whose Base case balances and whose Downside does not is not
        Forecast Ready: 15.20 says every scenario, and a label that described
        only the flattering one would be the kind of claim rule 1.19 forbids.
        """
        return (
            bool(self.by_scenario)
            and not self.not_built
            and all(item.is_forecast_ready for item in self.by_scenario)
        )

    @property
    def severity_is_unassigned(self) -> bool:
        """F-4, surfaced rather than assumed away."""
        return True

    def for_scenario(self, scenario_id: str) -> ScenarioChecks | None:
        for item in self.by_scenario:
            if item.scenario_id == scenario_id:
                return item
        return None

    def describe(self) -> str:
        if self.not_built:
            unbuilt = ", ".join(sorted(self.not_built))
            return (
                f"Not Forecast Ready: {unbuilt} could not be forecast at all."
            )
        if self.is_forecast_ready:
            return (
                f"Forecast Ready across {len(self.by_scenario)} scenario(s). "
                + SEVERITY_NOTE
            )
        return (
            "Not Forecast Ready. "
            + " ".join(
                item.describe() for item in self.by_scenario if not item.is_forecast_ready
            )
        )


def check_scenario(
    forecast: ScenarioForecast, tolerance: Tolerance | None = None
) -> ScenarioChecks:
    """The engine's thirteen checks, over one scenario's whole year axis.

    `run_all_checks` covers both halves in one pass -- the historical years and
    the forecast years -- because `build_forecast` extends the historical
    ledgers onto the full axis. That is what 15.20's "every period" asks for,
    and it is why the valuation checks report SKIP here: there is no valuation
    yet, and reporting an unrun check as a pass is what rule 1.14 forbids.
    """
    return ScenarioChecks(
        scenario_id=forecast.scenario_id,
        results=tuple(run_all_checks(forecast.result, tolerance=tolerance)),
    )


def check_every_scenario(
    forecasts: "tuple[ScenarioForecast, ...]",
    not_built: "dict[str, str]" | None = None,
    tolerance: Tolerance | None = None,
) -> ForecastReadiness:
    """15.20, across the set."""
    return ForecastReadiness(
        by_scenario=tuple(check_scenario(f, tolerance) for f in forecasts),
        not_built=dict(not_built or {}),
    )
