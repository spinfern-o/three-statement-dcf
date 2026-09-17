"""Computing a model's 7.1 standing from what it actually contains.

Each gate below is the entry condition for one status, and each is evaluated
against the real objects rather than against a flag. The cost is that the
portfolio screen does real work per model; the benefit is that it cannot be
wrong, which for the first thing a reader sees is the trade worth making.
"""

from __future__ import annotations

from ..assumptions.gate import evaluate as evaluate_gate
from ..assumptions.scenarios import BASE, ScenarioSet
from ..extraction.records import ExtractionResult
from ..forecast.build import ForecastError, build_scenario_forecast, forecast_periods
from ..review.progress import review_progress
from ..statements.build import BuildError, build_statements
from ..valuation.build import missing_inputs
from .status import ModelStatus, Standing


def _metadata(result: ExtractionResult, name: str) -> str:
    field = result.document.metadata.fields.get(name)
    if field is None or not field.confirmed:
        return ""
    return str(field.value or "")


def standing_for(
    result: ExtractionResult, scenarios: ScenarioSet | None = None
) -> Standing:
    """7.1.b and 7.1.c for one model."""
    progress = review_progress(result)
    gates: "list[tuple[str, bool, str]]" = []
    unresolved: "list[str]" = []

    # --- Extracting: the pipeline produced facts -----------------------------
    extracted = bool(result.facts)
    gates.append((
        "Extraction produced facts",
        extracted,
        f"{len(result.facts)} fact(s) read from the filing"
        if extracted
        else "the pipeline has not produced any facts from this document yet",
    ))

    # --- Needs Review: there is something for a person to do ----------------
    reviewed = extracted and progress.decided == progress.total and progress.metadata_confirmed
    detail = (
        f"{progress.decided} of {progress.total} facts decided"
        + ("" if progress.metadata_confirmed else "; metadata not confirmed")
    )
    gates.append(("Every fact decided and the metadata confirmed", reviewed, detail))
    if extracted and not reviewed:
        if progress.decided < progress.total:
            unresolved.append(
                f"{progress.total - progress.decided} fact(s) nobody has decided"
            )
        if not progress.metadata_confirmed:
            unresolved.append("the document's metadata is not confirmed (10.9)")
    if progress.unresolved:
        unresolved.append(
            f"{progress.unresolved} fact(s) carry a blocking code nobody resolved"
        )

    # --- Validated: the statements build strictly ---------------------------
    validated = False
    statements = None
    if reviewed:
        try:
            statements = build_statements(result, strict=True)
            validated = True
            gates.append((
                "The historical statements build from verified, approved facts",
                True,
                f"{len(statements.years)} period(s), every cell citing a page",
            ))
        except BuildError as exc:
            gates.append(("The historical statements build", False, str(exc)))
            unresolved.append(str(exc).split(".")[0])
    else:
        gates.append((
            "The historical statements build", False,
            "not attempted: the review is not finished",
        ))

    # --- Forecast Ready and Valuation Ready ---------------------------------
    forecast_ready = False
    valuation_ready = False
    if validated and scenarios is not None:
        periods = forecast_periods(statements)
        gate = evaluate_gate(scenarios, BASE, periods.forecast)
        gates.append((
            "Every required assumption is an answer (14.1)",
            gate.may_calculate,
            gate.describe(),
        ))
        if not gate.may_calculate:
            unresolved.append(gate.describe())
        else:
            try:
                build_scenario_forecast(statements, scenarios, BASE)
                forecast_ready = True
                gates.append(("The forecast builds", True, "every period, from approved drivers"))
            except ForecastError as exc:
                gates.append(("The forecast builds", False, str(exc)))
                unresolved.append(str(exc).split(".")[0])

        if forecast_ready:
            missing = missing_inputs(scenarios, BASE)
            valuation_ready = not missing
            gates.append((
                "Every cost-of-capital input is supplied (16.6-16.10)",
                valuation_ready,
                "all present" if valuation_ready else "not supplied: " + ", ".join(missing),
            ))
            if missing:
                unresolved.append(
                    "cost-of-capital inputs not supplied: " + ", ".join(missing)
                )
    elif validated:
        gates.append((
            "Every required assumption is an answer (14.1)", False,
            "no scenario has been started for this model",
        ))
        unresolved.append("no scenario has been started")

    # The furthest stage whose gate is satisfied.
    if valuation_ready:
        status = ModelStatus.VALUATION_READY
    elif forecast_ready:
        status = ModelStatus.FORECAST_READY
    elif validated:
        status = ModelStatus.VALIDATED
    elif extracted:
        # Both "nobody has looked at it" and "somebody looked and the
        # statements still do not build" are Needs Review, deliberately: in
        # each case what is outstanding is a person's judgement, and
        # `blocked_by` says which.
        status = ModelStatus.NEEDS_REVIEW
    else:
        status = ModelStatus.EXTRACTING if result.document else ModelStatus.DRAFT

    blocked_by = _next_step(status, gates)

    return Standing(
        status=status,
        source_date=_metadata(result, "reporting_period_end") or "(not confirmed)",
        valuation_date=_metadata(result, "reporting_period_end") or "(not set)",
        owner=result.document.company_id or "(unassigned)",
        unresolved=tuple(dict.fromkeys(unresolved)),
        blocked_by=blocked_by,
        gates=tuple(gates),
    )


def _next_step(status: ModelStatus, gates) -> str:
    """The first gate that is not satisfied, in words a reader can act on."""
    for name, passed, detail in gates:
        if not passed:
            return f"{name}: {detail}"
    if status is ModelStatus.VALUATION_READY:
        return ""
    return "nothing outstanding on this stage"
