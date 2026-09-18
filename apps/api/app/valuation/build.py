"""Items 109-118: the DCF, driven from a scenario's approved inputs.

Like Phase 10, this is a boundary rather than a second implementation.
`model/dcf.py` already does 16.2 through 16.20: NOPAT, FCFF, CAPM, WACC,
discounting, Gordon Growth with 16.16's block, the enterprise-to-equity bridge
and the per-share division. What did not exist is the path from a Section 14
assumption register into it, with every market input carrying the URL and the
observation date a valuation has to be reproducible from.

Three refusals are enforced here rather than left to the engine, because the
engine's versions name one thing at a time or accept a weaker form of it.

**Every market input must be present and Approved, and the refusal names them
all at once.** The engine raises on the first missing source string.

**A source string is not enough.** `CostOfCapital` requires `sources[name]` be
non-empty, which "Bloomberg" satisfies. Section 14's evidence rules require a
URL and an observation date for market data, and those rules run before this.

**A per-share value needs verified diluted shares, or there is none.** 16.20
says "only when diluted shares are verified", and the chart carries no share
count to cross-check against (F-17), so the share count rests entirely on its
own citation -- which is exactly when the citation has to be real.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from model import accounts
from model.accounts import Statement
from model.dcf import (
    CostOfCapital,
    EquityBridge,
    FCFFYear,
    Valuation,
    build_fcff,
    run_dcf,
)
from model.numeric import ZERO
from model.provenance import ProvenanceError
from model.timing import Schedule, Timing, build_schedule

from ..assumptions.scenarios import ScenarioSet
from ..forecast.build import ScenarioForecast, forecast_ledger
from .inputs import BRIDGE_INPUTS, BY_CODE, MARKET_INPUTS, required_codes


class ValuationError(Exception):
    """The valuation could not be built, and this says exactly what is missing."""


@dataclass(frozen=True)
class InputRecord:
    """One valuation input as supplied, for the 16.6-16.10 source panel."""

    code: str
    name: str
    value: Decimal
    unit: str
    rule: str
    source_type: str
    evidence: str
    rationale: str
    status: str
    #: Set when the input is taken as nil because nobody addressed it.
    assumed_nil: bool = False


@dataclass(frozen=True)
class ScenarioValuation:
    """One scenario's valuation, and everything it rested on."""

    scenario_id: str
    #: The engine's own `Valuation`. Typed, for the same reason as
    #: `ScenarioForecast.result`: a comment naming the type is not the type.
    valuation: Valuation
    fcff_years: tuple[FCFFYear, ...]
    cost_of_capital: CostOfCapital
    bridge: EquityBridge
    schedule: Schedule
    inputs: tuple[InputRecord, ...]
    #: 16.19 lines taken as nil because nobody entered them.
    assumed_nil: tuple[str, ...]
    #: 16.20: why there is no per-share value, when there is none.
    per_share_status: str
    #: The calendar date this valuation counts from, when one was supplied.
    #: None under year-end and mid-year, which 16.11 defines relative to the
    #: last actual period rather than to a calendar -- and 21.6 asks the report
    #: for a valuation date, so the absence has to be reportable rather than
    #: guessed at from today.
    valuation_date: date | None = None

    @property
    def has_per_share(self) -> bool:
        return self.valuation.implied_share_price is not None


def _resolved(scenarios: ScenarioSet, scenario_id: str) -> dict:
    return scenarios.resolve(scenario_id)


def _record(code: str, item, resolved, assumed_nil: bool = False) -> InputRecord:
    definition = BY_CODE[code]
    if assumed_nil:
        return InputRecord(
            code=code, name=definition.name, value=ZERO, unit=definition.unit,
            rule=definition.rule, source_type="(not addressed)",
            evidence="taken as nil because nobody entered it",
            rationale=definition.why_sourced, status="-", assumed_nil=True,
        )
    assumption = resolved.assumption
    return InputRecord(
        code=code, name=definition.name, value=assumption.value,
        unit=definition.unit, rule=definition.rule,
        source_type=assumption.source_type.value,
        evidence=assumption.evidence.describe(),
        rationale=assumption.rationale,
        status=assumption.status.value,
    )


def _gather(scenarios: ScenarioSet, scenario_id: str):
    """Every valuation input the scenario carries, and what is missing."""
    resolved = _resolved(scenarios, scenario_id)
    missing, unresolved, wrong_unit, records = [], [], [], []

    for definition in MARKET_INPUTS + BRIDGE_INPUTS:
        item = resolved.get(definition.code)
        if item is None:
            if definition.required:
                missing.append(f"{definition.code} ({definition.rule})")
            continue
        assumption = item.assumption
        if assumption.status.blocks_calculation:
            unresolved.append(f"{definition.code} is {assumption.status.value}")
            continue
        if assumption.unit != definition.unit:
            wrong_unit.append(
                f"{definition.code} is declared in {assumption.unit} and "
                f"{definition.rule} needs {definition.unit} (18.12)"
            )
            continue
        records.append(_record(definition.code, definition, item))

    return resolved, records, missing, unresolved, wrong_unit


def _value(records, code: str, default=None):
    for record in records:
        if record.code == code:
            return record.value
    return default


def build_scenario_valuation(
    forecast: ScenarioForecast,
    scenarios: ScenarioSet,
    *,
    timing: Timing = Timing.YEAR_END,
    valuation_date: date | None = None,
    fiscal_year_end: date | None = None,
) -> ScenarioValuation:
    """Items 109-118 for one scenario, by running the engine that implements them."""
    scenario_id = forecast.scenario_id
    _resolved, records, missing, unresolved, wrong_unit = _gather(scenarios, scenario_id)

    problems = []
    if missing:
        problems.append("not supplied: " + ", ".join(missing))
    if unresolved:
        problems.append("not an answer yet: " + ", ".join(unresolved))
    if wrong_unit:
        problems.append("; ".join(wrong_unit))
    if problems:
        raise ValuationError(
            f"scenario {scenario_id!r} cannot be valued. "
            + " | ".join(problems)
            + ". None of these can be derived from the filing (STEP 25-27)."
        )

    # 16.2-16.5: NOPAT and FCFF, from the engine's own bridge.
    fcff_years = build_fcff(forecast.result)

    # 16.6-16.10. The engine's `sources` map keeps its own requirement
    # satisfied; the real evidence is the Section 14 record behind each row.
    sources = {
        record.code: f"{record.source_type}: {record.evidence}"
        for record in records
    }
    tax_rate = forecast.result.taxes.rate(forecast.periods.forecast[-1])
    cost_of_capital = CostOfCapital(
        risk_free_rate=_value(records, "risk_free_rate"),
        beta=_value(records, "beta"),
        equity_risk_premium=_value(records, "equity_risk_premium"),
        pretax_cost_of_debt=_value(records, "pretax_cost_of_debt"),
        tax_rate=tax_rate,
        market_value_equity=_value(records, "market_value_equity"),
        market_value_debt=_value(records, "market_value_debt"),
        sources=sources,
    )

    # 16.19. Cash and debt come from the balance sheet at the last actual year,
    # not from an assumption: they are reported figures with a page behind them.
    balance = forecast_ledger(forecast, Statement.BALANCE)
    last = forecast.periods.last_actual
    bridge_values = {}
    assumed_nil = []
    for definition in BRIDGE_INPUTS:
        if definition.code == "diluted_shares":
            continue
        supplied = _value(records, definition.code)
        if supplied is None:
            assumed_nil.append(definition.code)
            records.append(_record(definition.code, definition, None, assumed_nil=True))
            bridge_values[definition.code] = ZERO
        else:
            bridge_values[definition.code] = supplied

    bridge = EquityBridge(
        cash=balance.require(accounts.CASH, last, "16.19 (enterprise-to-equity bridge)"),
        debt=balance.require(accounts.DEBT, last, "16.19 (enterprise-to-equity bridge)"),
        **bridge_values,
    )

    # 16.11-16.14: the timing convention, stated.
    schedule = build_schedule(
        forecast.periods.forecast, timing,
        valuation_date=valuation_date, fiscal_year_end=fiscal_year_end,
    )

    # 16.20: a per-share value ONLY when diluted shares are verified.
    shares = _value(records, "diluted_shares")
    shares_source = None
    per_share_status = ""
    if shares is None:
        per_share_status = (
            "No per-share value. 16.20 permits one only when diluted shares are "
            "verified, and none has been entered. The chart carries no share "
            "count (F-17), so there is nothing to derive it from either."
        )
    else:
        record = next(r for r in records if r.code == "diluted_shares")
        shares_source = f"{record.source_type}: {record.evidence}"
        per_share_status = (
            f"Diluted shares {shares}, on {shares_source}. Nothing in this "
            "system cross-checks that figure -- the chart carries no share "
            "count -- so it rests entirely on its citation."
        )

    try:
        valuation = run_dcf(
            fcff_years=fcff_years,
            cost_of_capital=cost_of_capital,
            terminal_growth=_value(records, "terminal_growth"),
            bridge=bridge,
            periods=forecast.periods,
            diluted_shares=shares,
            shares_source=shares_source,
            schedule=schedule,
        )
    except ProvenanceError as exc:
        # 16.16 lands here: WACC <= g blocks the calculation rather than
        # returning a negative or infinite terminal value.
        raise ValuationError(f"scenario {scenario_id!r}: {exc}") from None

    return ScenarioValuation(
        scenario_id=scenario_id,
        valuation=valuation,
        fcff_years=tuple(fcff_years),
        cost_of_capital=cost_of_capital,
        bridge=bridge,
        schedule=schedule,
        inputs=tuple(records),
        assumed_nil=tuple(assumed_nil),
        per_share_status=per_share_status,
        valuation_date=valuation_date,
    )


def missing_inputs(scenarios: ScenarioSet, scenario_id: str) -> tuple[str, ...]:
    """The required market inputs this scenario does not yet carry."""
    resolved = _resolved(scenarios, scenario_id)
    return tuple(sorted(required_codes() - set(resolved)))
