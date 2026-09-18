"""Items 97-107: the forecast, built from a scenario's approved assumptions.

**Nothing here forecasts anything.** `model/forecast.py` already implements
every one of Section 15's twenty-one steps -- revenue from a stated method,
COGS and opex from documented drivers, D&A from the PP&E schedule rather than
a disconnected input, working capital account by account, debt and interest
from the debt schedule, taxes from the tax schedule, the three statements and
the cash link. It has a test suite, an independent benchmark, and 0.0001%
accuracy assertions behind it.

So this module does the one thing that did not exist: it turns a *scenario* --
Section 14's reviewed assumption register, with lineage and statuses -- into
the engine's `Assumptions` and `TaxSchedule`, runs the engine, and hands back
its `ForecastResult`. Reimplementing the forecast against the website's data
structures would produce a second answer to every question in Section 15, and
the two would disagree the first time either changed.

Three things this boundary has to get right, and each is enforced.

**14.1 is checked before the engine is touched.** The engine raises when a
driver is missing, naming one at a time; the gate names all of them at once,
per period, before anything runs. A reviewer fixing eleven missing drivers one
engine traceback at a time is a reviewer the gate exists to spare.

**Only Reviewed and Approved assumptions cross.** A Draft is not an answer
(`Status.blocks_calculation`), and letting one through would put an unsourced
number into a valuation while the screen still showed it as unfinished.

**The scenario travels with the result.** 9.12 records a `CalculatedValue`
against its `scenario_id`, and a forecast that does not know which scenario
produced it cannot satisfy that or 15.20's "every scenario".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model.accounts import Statement
from model.assumptions import Assumption as EngineAssumption
from model.assumptions import Assumptions, Basis
from model.forecast import ForecastResult
from model.profile import Periods
from model.provenance import ProvenanceError
from model.schedules import TaxSchedule
from model.statements import Ledger

from ..assumptions.gate import evaluate as evaluate_gate
from ..assumptions.scenarios import ScenarioSet
from ..assumptions.schema import Assumption
from ..statements.build import BuiltStatements

#: 15.1 and 15.2: the forecast begins the year after the last actual, and
#: every period is labelled. `Periods` validates both.
from ..statements.export import FORECAST_YEARS


class ForecastError(Exception):
    """The forecast could not be built, and this says exactly what is missing."""


@dataclass(frozen=True)
class ScenarioForecast:
    """One scenario's forecast, and what it rested on."""

    scenario_id: str
    periods: Periods
    #: The engine's own result. Not a copy, not a reimplementation.
    #:
    #: Typed as `ForecastResult` rather than `object`. It was the latter, which
    #: said "the engine's" in a comment and told no checker and no editor
    #: anything -- and five modules downstream were reaching through it for
    #: `.income`, `.balance`, `.cashflow` and `.taxes` on nothing but faith.
    result: ForecastResult
    #: The tax basis STEP 16 requires be stated, and where it came from.
    tax_basis: str
    tax_source: str
    #: Every driver the engine read, with the status it carried.
    drivers: tuple[tuple[str, str, Decimal, str], ...]
    #: Assumptions declared and never read -- usually a misspelled code.
    unused: tuple[str, ...]

    @property
    def forecast_years(self) -> tuple[str, ...]:
        return self.periods.forecast

    @property
    def last_actual(self) -> str:
        return self.periods.last_actual


#: 14.3's six source types onto STEP 10's three bases. Declared in
#: `assumptions/schema.py`; re-exported through the assumption itself.
def _engine_basis(assumption: Assumption) -> Basis:
    return Basis(assumption.engine_basis)


def forecast_periods(built: BuiltStatements, count: int = FORECAST_YEARS) -> Periods:
    """15.1 and 15.2: estimate periods immediately after the last actual.

    `Periods` refuses a gap, a non-consecutive run, or a first forecast year
    that does not follow the last actual -- so "immediately after" is checked
    rather than assumed.
    """
    if not built.years:
        raise ForecastError(
            "this filing produced no historical periods, so there is nothing for "
            "a forecast to follow (15.1)"
        )
    last = int(built.years[-1][:4])
    return Periods(
        historical=built.years,
        forecast=tuple(f"{last + offset}E" for offset in range(1, count + 1)),
    )


def _tax_schedule(
    scenarios: ScenarioSet, scenario_id: str, periods: Periods
) -> tuple[TaxSchedule, str, str]:
    """STEP 16: the rate, and which basis it is, stated.

    The engine takes the tax rate through a `TaxSchedule` rather than through
    the assumptions register, because STEP 16 makes the model state which of
    three bases it uses. The register still holds the number -- that is where
    it was sourced and reviewed -- and this reads it back out and names the
    basis its source type implies.
    """
    from ..assumptions.schema import SourceType

    rates: dict[str, Decimal] = {}
    basis = ""
    source = ""
    for year in periods.forecast:
        resolved = scenarios.resolve(scenario_id, period=year).get("tax_rate")
        if resolved is None:
            raise ForecastError(
                f"no tax_rate for {year}. STEP 16 requires the model state which "
                "rate it uses and why; the engine halts on 'tax.source is required "
                "by STEP 16' rather than assuming one."
            )
        assumption = resolved.assumption
        rates[year] = assumption.value
        if assumption.source_type is SourceType.HISTORICAL_DRIVER:
            basis = basis or "historical_effective"
        elif assumption.source_type in (
            SourceType.COMPANY_FILING, SourceType.COMPANY_GUIDANCE
        ):
            basis = basis or "statutory"
        else:
            basis = basis or "normalized_effective"
        source = source or f"{assumption.source_type.value}: {assumption.evidence.describe()}"
    return TaxSchedule(basis=basis, rate_by_year=rates), basis, source


def _register(
    scenarios: ScenarioSet, scenario_id: str, periods: Periods
) -> tuple[Assumptions, tuple[tuple[str, str, Decimal, str], ...]]:
    """The website's register, narrowed to the engine's.

    Every assumption keeps its rationale as the engine's `source` string, so
    the engine's own report still shows where each driver came from -- STEP 10
    asks for a visible source or explanation, and losing it at this boundary
    would make the engine's report thinner than the screen that fed it.
    """
    register = Assumptions()
    drivers: list[tuple[str, str, Decimal, str]] = []
    seen: set[tuple[str, str | None]] = set()

    for year in periods.forecast:
        for code, resolved in sorted(scenarios.resolve(scenario_id, period=year).items()):
            assumption = resolved.assumption
            if assumption.status.blocks_calculation:
                continue  # 14.1; the gate has already reported it
            if code == "tax_rate":
                continue  # STEP 16's route is the TaxSchedule, not the register
            scope = year if assumption.periods else None
            if (code, scope) in seen:
                continue
            seen.add((code, scope))
            register.add(
                EngineAssumption(
                    name=code,
                    value=assumption.value,
                    basis=_engine_basis(assumption),
                    source=(
                        f"{assumption.source_type.value} | "
                        f"{assumption.evidence.describe()} | {assumption.rationale}"
                    ),
                    year=scope,
                    note=(
                        f"scenario {resolved.from_scenario}, {assumption.status.value}"
                        + (
                            f", inherited from {assumption.inherited_from}"
                            if assumption.is_inherited
                            else ""
                        )
                    ),
                )
            )
            drivers.append(
                (code, scope or "all years", assumption.value, assumption.status.value)
            )
    return register, tuple(drivers)


def build_scenario_forecast(
    built: BuiltStatements,
    scenarios: ScenarioSet,
    scenario_id: str,
    *,
    periods: Periods | None = None,
) -> ScenarioForecast:
    """Items 97-107, by running the engine that already implements them."""
    span = periods or forecast_periods(built)

    gate = evaluate_gate(scenarios, scenario_id, span.forecast)
    if not gate.may_calculate:
        raise ForecastError(
            f"scenario {scenario_id!r} may not calculate yet (14.1). {gate.describe()}"
        )

    taxes, basis, tax_source = _tax_schedule(scenarios, scenario_id, span)
    register, drivers = _register(scenarios, scenario_id, span)

    from model.forecast import build_forecast

    try:
        result = build_forecast(
            periods=span,
            historical_income=built.ledgers[Statement.INCOME],
            historical_balance=built.ledgers[Statement.BALANCE],
            historical_cashflow=built.ledgers[Statement.CASHFLOW],
            assumptions=register,
            taxes=taxes,
        )
    except ProvenanceError as exc:
        # The engine names one missing thing at a time. The gate has already
        # checked the drivers, so anything that gets here is a historical
        # balance the forecast anchors on -- which the gate cannot know about.
        raise ForecastError(
            f"scenario {scenario_id!r}: {exc}"
        ) from None

    return ScenarioForecast(
        scenario_id=scenario_id,
        periods=span,
        result=result,
        tax_basis=basis,
        tax_source=tax_source,
        drivers=drivers,
        unused=tuple(register.unused()),
    )


def forecast_ledger(forecast: ScenarioForecast, statement: Statement) -> Ledger:
    """The engine's own ledger for one statement, covering actuals AND estimates.

    `build_forecast` extends the historical ledgers onto the full year axis, so
    one ledger carries both halves -- which is what lets 15.19's cash link and
    STEP 37's hardcode check look at a single object.
    """
    return {
        Statement.INCOME: forecast.result.income,
        Statement.BALANCE: forecast.result.balance,
        Statement.CASHFLOW: forecast.result.cashflow,
    }[statement]
