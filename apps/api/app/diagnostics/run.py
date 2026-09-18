"""Item 131: run all thirty Section 17 checks against one model.

Most of these already exist. Phases 3 to 11 each built the checks their own
stage needed, and this does not rebuild them: it maps each Section 17 clause
onto the code that already answers it and reports the answer under the
clause's own code, so a reader meets one registry rather than six panels.

Three states, and the third is the one that matters.

  PASS  the check ran and held
  FAIL  the check ran and did not hold
  SKIP  the check could not run, WITH THE REASON

Rule 1.14 is why the third exists: "an unresolved requirement must never
appear as PASS". A check whose inputs do not exist yet has not passed, and the
release gate in `release.py` treats a skipped CRITICAL or ERROR exactly as it
treats a failed one.

One of the thirty cannot be evaluated by this system at all, and it says so
rather than skipping silently: 17.21's iterative-calculation clause, because
no iterative calculation is configured and the graph is checked for cycles
regardless. That reason is part of the answer.

17.12 was a second such clause until the chart grew an intangibles line and a
separate amortization line (F-17). It now runs like 17.11 and 17.13 -- and on
a filing with no intangibles it reports SKIP for the schedule's own reason,
which is a statement about that filing rather than about this system.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model.checks import Status

from .registry import REGISTRY, Check, Severity


@dataclass(frozen=True)
class Outcome:
    """One check's answer, with the reason when it could not run."""

    check: Check
    status: Status
    detail: str
    #: Set when a stage further back stopped this one from running at all.
    blocked_by: str = ""

    @property
    def is_outstanding(self) -> bool:
        """1.14: a check that did not run is not a check that passed."""
        return self.status is not Status.PASS


def _pass(check: Check, detail: str) -> Outcome:
    return Outcome(check, Status.PASS, detail)


def _fail(check: Check, detail: str) -> Outcome:
    return Outcome(check, Status.FAIL, detail)


def _skip(check: Check, detail: str, blocked_by: str = "") -> Outcome:
    return Outcome(check, Status.SKIP, detail, blocked_by)


@dataclass(frozen=True)
class Diagnostics:
    """Every Section 17 check for one model, in the specification's order."""

    outcomes: tuple[Outcome, ...]

    def by_code(self, code: str) -> Outcome:
        for outcome in self.outcomes:
            if outcome.check.code == code:
                return outcome
        raise KeyError(code)

    @property
    def failed(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.status is Status.FAIL)

    @property
    def skipped(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.status is Status.SKIP)

    @property
    def passed(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.status is Status.PASS)

    def outstanding_at(self, severity: Severity) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.is_outstanding and o.check.severity is severity)

    def summarize(self) -> str:
        return (
            f"{len(self.passed)} passed, {len(self.failed)} failed, "
            f"{len(self.skipped)} could not run"
        )


#: Clauses this system cannot evaluate, and why. Reported as SKIP with the
#: reason rather than omitted from the registry, because a check missing from
#: a diagnostics panel is a check nobody decided about.
UNEVALUABLE = {
    "17.21": (
        "no iterative calculation is configured. The formula graph is checked "
        "for cycles unconditionally and refuses any it finds (18.6), so the "
        "'unless an approved iterative calculation' branch of this clause has "
        "nothing to approve."
    ),
}


def _no_nan_or_infinity(values) -> tuple[bool, str]:
    """17.27, which is the one check that is about the numbers themselves."""
    bad = []
    for label, value in values:
        if isinstance(value, Decimal) and not value.is_finite():
            bad.append(f"{label} is {value}")
    return (not bad), ("; ".join(bad) if bad else "every value is finite")


def evaluate(result, scenarios=None, scenario_id: str = "base") -> Diagnostics:
    """All thirty checks, in Section 17's order, against one model.

    Built as one pass over the stages rather than thirty independent probes:
    each stage is attempted once, and every clause that depends on a stage
    that did not build reports SKIP naming the stage. That is what keeps a
    single missing mapping from producing twenty unrelated failures.
    """
    from model.checks import Tolerance

    from ..assumptions.gate import evaluate as evaluate_gate
    from ..assumptions.schema import Status as AssumptionStatus
    from ..forecast.build import ForecastError, build_scenario_forecast, forecast_periods
    from ..forecast.checks import check_scenario
    from ..mapping.checks import duplicate_counting
    from ..review.progress import review_progress
    from ..schedules.build import build_schedules
    from ..schedules.checks import reconcile as reconcile_schedule
    from ..statements.build import BuildError, build_statements
    from ..statements.checks import run_historical_checks
    from ..valuation.build import ValuationError, build_scenario_valuation
    from ..valuation.checks import headroom

    progress = review_progress(result)
    document = result.document
    outcomes: dict[str, Outcome] = {}
    by_clause = {check.clause: check for check in REGISTRY}

    def record(clause: str, status: Status, detail: str, blocked_by: str = "") -> None:
        outcomes[clause] = Outcome(by_clause[clause], status, detail, blocked_by)

    # --- 17.1-17.7: source and mapping --------------------------------------
    record(
        "17.1",
        Status.PASS if document.immutable_hash else Status.FAIL,
        f"SHA-256 {document.immutable_hash[:16]}... recorded at ingestion"
        if document.immutable_hash
        else "no immutable hash on this document",
    )
    record(
        "17.2",
        Status.PASS if progress.metadata_confirmed else Status.FAIL,
        "every required metadata field is confirmed"
        if progress.metadata_confirmed
        else f"{len(progress.unconfirmed_required)} required field(s) unconfirmed: "
        + ", ".join(progress.unconfirmed_required),
    )

    built = None
    build_error = ""
    try:
        built = build_statements(result, strict=True)
    except BuildError as exc:
        build_error = str(exc)

    if built is not None and built.years:
        # Verified rather than asserted. `Periods` enforces the A/E suffix at
        # construction, so this holds by construction today -- and a check
        # whose evidence names a property it never looked at is how 17.29
        # spent four phases passing on nothing (F-38). Checking something
        # guaranteed upstream costs one pass over a handful of labels.
        unlabelled = [year for year in built.years if not year.endswith(("A", "E"))]
        record(
            "17.3",
            Status.PASS if not unlabelled else Status.FAIL,
            (
                f"{len(built.years)} period(s), each labelled actual or estimate: "
                + ", ".join(built.years)
                + ". This clause also asks for an unambiguous BASIS and DATE "
                "RANGE, and neither is verified: the model carries no period "
                "dates and no cadence, so ambiguity of basis cannot arise here "
                "or be detected (validation-policy.md VAL-017-003)"
            )
            if not unlabelled
            else "period(s) with no actual/estimate label: " + ", ".join(unlabelled),
        )
    else:
        record(
            "17.3",
            Status.SKIP,
            "no period survived to the statements",
            blocked_by=build_error or "the build",
        )

    confirmed = {name for name, field in document.metadata.fields.items() if field.confirmed}
    needed = {"reporting_currency", "displayed_scale"}
    record(
        "17.4",
        Status.PASS if needed <= confirmed else Status.FAIL,
        "currency and displayed scale are both confirmed"
        if needed <= confirmed
        else "not confirmed: " + ", ".join(sorted(needed - confirmed)),
    )
    record(
        "17.5",
        Status.PASS if progress.verified == progress.total and progress.total else Status.FAIL,
        f"{progress.verified} of {progress.total} facts meet all seven conditions "
        "of source-policy.md §9",
    )
    record(
        "17.6",
        Status.PASS if progress.unmapped == 0 else Status.FAIL,
        f"{progress.mapped_and_approved} approved, {progress.excluded} deliberately "
        f"excluded, {progress.unmapped} with no mapping at all",
    )
    duplicates = duplicate_counting(result)
    record(
        "17.7",
        Status.PASS if not duplicates else Status.FAIL,
        "no fact contributes to a subtotal both directly and through a component"
        if not duplicates
        else f"{len(duplicates)} double-count finding(s): "
        + "; ".join(f.message for f in duplicates[:3]),
    )

    # --- 17.8-17.15: historical statements and schedules --------------------
    if built is None:
        for clause in ("17.8", "17.9", "17.10", "17.11", "17.13", "17.14", "17.15"):
            record(
                clause,
                Status.SKIP,
                "the historical statements did not build",
                blocked_by=build_error,
            )
    else:
        historical = {c.name: c for c in run_historical_checks(built)}
        _carry(record, historical, "17.8", "Historical balance sheet balances (17.8)")
        _carry(record, historical, "17.9", "Historical cash flow reconciliation (17.9)")
        _carry(record, historical, "17.10", "Reported subtotals reconcile (17.10)")

        schedules = build_schedules(built)
        tolerance = Tolerance()
        _schedule(record, "17.11", reconcile_schedule(schedules.ppe, tolerance))
        # 17.12 reads like its neighbours now. It reported SKIP for eleven
        # phases because the chart had no intangibles line and no separate
        # amortization line to roll against; closing F-17 gave it both, so the
        # check runs and `_schedule` reports SKIP with the schedule's own
        # reason when a filing simply has no intangibles -- which is a
        # statement about the filing rather than about this system.
        _schedule(record, "17.12", reconcile_schedule(schedules.intangibles, tolerance))
        _schedule(record, "17.13", reconcile_schedule(schedules.debt, tolerance))
        _schedule(
            record,
            "17.15",
            reconcile_schedule(schedules.retained_earnings, tolerance),
        )
        usable = schedules.tax.usable_rates()
        record(
            "17.14",
            Status.PASS if usable else Status.SKIP,
            f"effective rate computed for {', '.join(sorted(usable))}"
            if usable
            else "no period yields a rate STEP 16 could use; 17.14 is scoped "
            "'where data permits' and the data does not",
        )

    record("17.21", Status.SKIP, UNEVALUABLE["17.21"])

    # --- 17.16-17.22: the forecast ------------------------------------------
    forecast = None
    forecast_error = ""
    if built is not None and scenarios is not None:
        periods = forecast_periods(built)
        gate = evaluate_gate(scenarios, scenario_id, periods.forecast)
        record(
            "17.18",
            Status.PASS if gate.may_calculate else Status.FAIL,
            gate.describe(),
        )
        rejected = [
            code
            for code, item in scenarios.resolve(scenario_id).items()
            if item.assumption.status is AssumptionStatus.REJECTED
        ]
        record(
            "17.19",
            Status.PASS if not rejected else Status.FAIL,
            "no rejected assumption is in this scenario"
            if not rejected
            else "rejected and still present: " + ", ".join(sorted(rejected)),
        )
        try:
            forecast = build_scenario_forecast(built, scenarios, scenario_id)
        except ForecastError as exc:
            forecast_error = str(exc)
    else:
        reason = "no scenario has been started" if built is not None else build_error
        for clause in ("17.18", "17.19"):
            record(clause, Status.SKIP, "there is no scenario to check", blocked_by=reason)
        forecast_error = reason

    if forecast is None:
        for clause in ("17.16", "17.17", "17.20", "17.22"):
            record(clause, Status.SKIP, "the forecast did not build", blocked_by=forecast_error)
    else:
        results = {c.name: c for c in check_scenario(forecast).results}
        _carry(record, results, "17.16", "Forecast balance sheet balances")
        _carry(record, results, "17.17", "Ending cash linkage")
        _carry(record, results, "17.20", "No unintended forecast hardcodes")
        # 17.22 is deliberately NOT carried from here. The check compares the
        # DCF's FCFF against the three-statement bridge, and the FCFF years
        # are built by the valuation -- so evaluated at this stage it could
        # only ever skip. It is recorded below, once the valuation exists.

    # --- 17.23-17.26: the valuation -----------------------------------------
    valuation = None
    valuation_error = ""
    if forecast is not None and scenarios is not None:
        try:
            valuation = build_scenario_valuation(forecast, scenarios)
        except ValuationError as exc:
            valuation_error = str(exc)
    else:
        valuation_error = forecast_error or "no forecast"

    # `forecast is not None` is implied by `valuation is not None` -- a
    # valuation is only built from a forecast -- and is stated because nothing
    # in the name says so and the implication is exactly the kind that goes
    # quietly wrong when somebody adds a second way to build one.
    if valuation is None or forecast is None:
        for clause in ("17.22", "17.23", "17.24", "17.25", "17.26"):
            record(
                clause, Status.SKIP, "there is no valuation to check", blocked_by=valuation_error
            )
    else:
        from model.checks import run_all_checks

        with_valuation = {
            c.name: c
            for c in run_all_checks(
                forecast.result,
                fcff_years=list(valuation.fcff_years),
                valuation=valuation.valuation,
            )
        }
        _carry(record, with_valuation, "17.22", "FCFF matches three-statement forecast")

        undated = [
            r.code
            for r in valuation.inputs
            if not r.assumed_nil and "as at" not in r.evidence and "http" not in r.evidence
        ]
        record(
            "17.23",
            Status.PASS if not undated else Status.FAIL,
            "every cost-of-capital input carries a source and an observation date"
            if not undated
            else "not dated or not sourced: " + ", ".join(sorted(undated)),
        )
        gap = headroom(valuation)
        record(
            "17.24",
            Status.PASS if not gap.is_blocked else Status.FAIL,
            gap.describe(),
        )
        record(
            "17.25",
            Status.PASS if not valuation.assumed_nil else Status.FAIL,
            "every enterprise-to-equity adjustment is sourced"
            if not valuation.assumed_nil
            else "taken as nil with nobody having addressed them: "
            + ", ".join(valuation.assumed_nil),
        )
        record(
            "17.26",
            Status.PASS if valuation.has_per_share else Status.SKIP,
            valuation.per_share_status,
        )

    # --- 17.27, 17.29, 17.30: the numbers themselves ------------------------
    record("17.27", *_finite(built, valuation))
    record("17.29", *_rounding_ties(built))
    record("17.30", *_lineage(built))

    # --- 17.28: the benchmark, which is an attestation ----------------------
    record("17.28", *_benchmark_attestation())

    ordered = tuple(outcomes[check.clause] for check in REGISTRY if check.clause in outcomes)
    return Diagnostics(ordered)


def _carry(record, results, clause: str, name: str) -> None:
    """Report an existing check's answer under its Section 17 clause code."""
    found = results.get(name)
    if found is None:  # pragma: no cover - a renamed check would land here
        record(clause, Status.SKIP, f"no check named {name!r} was produced")
        return
    record(clause, found.status, found.detail)


def _schedule(record, clause: str, outcome) -> None:
    record(clause, outcome.status, outcome.detail)


def _finite(built, valuation) -> tuple[Status, str]:
    """17.27: no NaN, Infinity or null in a released calculation."""
    values = []
    if built is not None:
        for statement, ledger in built.ledgers.items():
            for year in built.years:
                for account in ledger.accounts_present(year):
                    values.append(
                        (f"{statement.value}.{account} {year}", ledger.get(account, year))
                    )
    if valuation is not None:
        values.append(("enterprise_value", valuation.valuation.enterprise_value))
        values.append(("equity_value", valuation.valuation.equity_value))
        values.append(("wacc", valuation.valuation.wacc))
    if not values:
        return Status.SKIP, "nothing has been calculated yet"
    finite, detail = _no_nan_or_infinity(values)
    return (Status.PASS if finite else Status.FAIL), (
        f"{len(values)} value(s) checked; {detail}" if finite else detail
    )


def _rounding_ties(built) -> tuple[Status, str]:
    """17.29: a displayed value must tie back to its full-precision one.

    **The previous version of this check was vacuous** (finding F-38). It read
    `quantize_for_display(value, 1) != quantize_for_display(value, 1)` -- a
    pure function compared with itself, which can never differ. It reported
    PASS with a count of values it had not examined, which is the failure mode
    rule 1.14 exists to prevent, appearing in the panel that enforces it.

    What 4.18 and 4.19 actually require is checkable, in three parts:

    1. **The string on screen is recoverable from the stored decimal.** Parsed
       back, it must equal the stored value at the display precision. That
       goes through the f-string formatting where a real bug would live -- a
       display computed from a float, or from a different value.
    2. **A value that loses something on display is owed a tooltip** carrying
       its full stored value (4.19).
    3. **A value that displays losslessly is not owed one**, and must not
       claim one. A tooltip repeating what is already on screen teaches a
       reader that tooltips are noise.
    """
    from model.numeric import D, quantize_for_display

    from ..display import PLACES, display, is_rounded, tooltip

    if built is None:
        return Status.SKIP, "nothing has been calculated yet"

    kind = "currency"
    places = PLACES[kind]
    checked = 0
    with_tooltip = 0
    for ledger in built.ledgers.values():
        for year in built.years:
            for account in ledger.accounts_present(year):
                value = ledger.get(account, year)
                if value is None:
                    continue
                shown = display(value, kind)
                try:
                    recovered = D(shown.replace(",", ""))
                except Exception:
                    return (
                        Status.FAIL,
                        f"{account} {year} displays as {shown!r}, which is not a number",
                    )
                expected = quantize_for_display(value, places)
                if recovered != expected:
                    return Status.FAIL, (
                        f"{account} {year} displays as {shown!r}, which reads back "
                        f"as {recovered} rather than the stored {value} rounded "
                        f"to {expected}"
                    )
                owed = is_rounded(value, kind)
                text = tooltip(value, kind)
                if owed:
                    with_tooltip += 1
                    if str(value) not in text:
                        return Status.FAIL, (
                            f"{account} {year} is rounded for display and its "
                            f"4.19 tooltip does not carry the stored {value}"
                        )
                elif text:
                    return Status.FAIL, (
                        f"{account} {year} displays losslessly and still claims a tooltip: {text!r}"
                    )
                checked += 1
    return Status.PASS, (
        f"{checked} value(s) display a figure that reads back to the stored "
        f"decimal at {places} decimal place(s); {with_tooltip} lose something "
        "in rounding and each carries 4.19's full-value tooltip"
    )


def _lineage(built) -> tuple[Status, str]:
    """17.30: every released output has source and formula lineage."""
    if built is None:
        return Status.SKIP, "nothing has been released yet"
    missing = []
    for statement, ledger in built.ledgers.items():
        for year in built.years:
            for account in ledger.accounts_present(year):
                cell = ledger.cell(account, year)
                if not cell.cite().strip():
                    missing.append(f"{statement.value}.{account} {year}")
    if missing:
        return Status.FAIL, f"{len(missing)} cell(s) cite nothing: " + ", ".join(missing[:5])
    return (
        Status.PASS,
        "every cell cites either a page of the filing or the formula that produced it",
    )


def _benchmark_attestation() -> tuple[Status, str]:
    """17.28 and 4.20, which is a rule about what may be CLAIMED.

    "Never claim less than 0.0001% error until the benchmark suite passes and
    the test report identifies the exact dataset and formulas tested." A
    running application cannot verify that for itself -- the benchmark lives
    in the test suite and runs in CI -- so this reports what the suite covers
    and where its result is, rather than asserting a pass it has not seen.
    That distinction is the whole of 4.20.
    """
    return Status.SKIP, (
        "4.20 makes this a claim that may only be made once the benchmark suite "
        "has passed and the report names the dataset and formulas tested. The "
        "suite is tests/test_precision.py, tests/test_timing.py, "
        "apps/api/tests/integration/test_formula_catalog.py and "
        "test_valuation.py; it runs in CI and this application does not observe "
        "its result. The accuracy report on this page lists what it covers."
    )
