"""Item 76 / 13.8: every schedule reconciles to its statement line, every period.

One sentence in the specification, and the only one that makes the rest of
Section 13 worth building. A roll-forward nobody reconciles is a second,
unverified copy of the balance sheet.

Three properties of these checks are deliberate.

**They run on the schedule, not on the ledger.** `statements/checks.py`
already verifies the statements against each other. These verify that the
explanation of *how* a balance moved lands on the balance the filing reports.
A filing can pass every check in Phase 6 and still have a PP&E schedule that
misses a disposal, because the balance sheet's own total is right either way.

**A schedule that cannot be built is a SKIP, with the reason.** Not a pass.
Rule 1.14 is explicit that an unrun check is a reported gap, and the three
unavailable schedules here (13.3, 13.5, and 13.7's share counts) are the
clearest case of it in the system so far.

**Nothing is corrected.** The `unexplained` difference is reported at full
precision, and beside it the relative error 4.10 asks for. STEP 6 and 12.5:
keep differences visible; do not plug.
"""

from __future__ import annotations

from decimal import Decimal

from model.checks import CheckResult, Status, Tolerance
from model.numeric import ZERO, relative_error

from .base import Availability, Reconciliation, Schedule
from .build import ScheduleSet


def _result(name: str, status: Status, detail: str = "") -> CheckResult:
    return CheckResult(name, status, detail)


def _difference(
    reconciliation: Reconciliation, computed: Decimal, reported: Decimal
) -> str:
    """One failure, written so a reviewer can go and find it in the filing.

    `computed` and `reported` are passed in rather than read off the
    reconciliation, which holds them as `Decimal | None`. The caller has
    already established both are present -- taking them as arguments carries
    that across the function boundary instead of restating it as an
    annotation the checker cannot verify.
    """
    delta = computed - reported
    text = (
        f"{reconciliation.year}: schedule ends at {computed:,} but "
        f"{reconciliation.statement_line} reports {reported:,}, "
        f"unexplained {delta:,}"
    )
    if reported != ZERO:
        text += f" ({relative_error(computed, reported):.6f}%)"
    if reconciliation.note:
        text += f". {reconciliation.note}"
    return text


def reconcile(schedule: Schedule, tol: Tolerance) -> CheckResult:
    """13.8 for one schedule, across every period it covers."""
    name = f"{schedule.title} reconciles to its statement line ({schedule.rule}, 13.8)"

    if schedule.availability is Availability.UNAVAILABLE:
        return _result(
            name, Status.SKIP,
            f"this schedule could not be built, so there is nothing to reconcile. "
            f"{schedule.reason}",
        )
    if not schedule.reconciliations:
        return _result(
            name, Status.SKIP,
            "the schedule covers no period that can be reconciled -- a "
            "reconciliation needs a closing balance and the movements into it",
        )

    checked, failures, skipped, within_tolerance = 0, [], [], []
    for reconciliation in schedule.reconciliations:
        computed, reported = reconciliation.computed, reconciliation.reported
        if computed is None or reported is None:
            missing = "the schedule's own closing figure" if computed is None else None
            missing = missing or f"{reconciliation.statement_line}"
            skipped.append(f"{reconciliation.year} ({missing} is absent)")
            continue
        checked += 1
        if not tol.close(computed, reported):
            failures.append(_difference(reconciliation, computed, reported))
        elif not reconciliation.ties:
            # Inside the tolerance is not the same claim as tying, and saying
            # the second when only the first is true is how a rounding
            # difference and a missing disposal come to look identical.
            within_tolerance.append(_difference(reconciliation, computed, reported))

    if not checked:
        return _result(
            name, Status.SKIP,
            "no period has both a schedule figure and a reported one: "
            + "; ".join(skipped),
        )
    if failures:
        return _result(name, Status.FAIL, " | ".join(failures))

    exact = checked - len(within_tolerance)
    detail = f"{exact} period(s) tie exactly"
    if within_tolerance:
        detail += (
            f"; {len(within_tolerance)} within {tol.describe()} but not exact: "
            + " | ".join(within_tolerance)
        )
    if skipped:
        detail += f"; not checked: {', '.join(skipped)}"
    if schedule.availability is Availability.PARTIAL:
        detail += (
            f". The schedule is partial: {schedule.reason}"
        )
    return _result(name, Status.PASS, detail)


def interest_basis_is_stated(schedules: ScheduleSet, tol: Tolerance) -> CheckResult:
    """13.4: "Interest must state whether it uses beginning, ending, or average debt."

    A check on the model rather than on the filing, and it earns its place:
    the failure it guards against is `model/forecast.py` changing which basis
    it charges interest on while this screen keeps reporting the old one, so
    a rate read off the history no longer reproduces the history.
    """
    name = "Interest basis is stated and matches the forecast (13.4)"
    if not schedules.interest:
        return _result(
            name, Status.SKIP,
            "no period has a prior-period debt balance to imply a rate from",
        )
    from .interest import ENGINE_BASIS

    # Paired with its year, so the skip message below can name the period
    # without calling `on()` a second time -- and so the None check narrows the
    # values this function goes on to use rather than a throwaway list.
    engine_rates = [(row.year, row.on(ENGINE_BASIS)) for row in schedules.interest]
    if any(rate is None for _year, rate in engine_rates):
        return _result(
            name, Status.FAIL,
            f"the basis model/forecast.py uses ({ENGINE_BASIS} debt) is not among "
            "the bases this schedule reports, so the historical rate and the "
            "forecast rate are not the same measurement",
        )
    present = [(year, rate) for year, rate in engine_rates if rate is not None]
    computed = [rate for _year, rate in present if rate.rate is not None]
    if not computed:
        return _result(
            name, Status.SKIP,
            f"the {ENGINE_BASIS}-debt rate could not be computed for any period: "
            + "; ".join(
                f"{year} ({rate.unavailable_reason})" for year, rate in present
            ),
        )
    return _result(
        name, Status.PASS,
        f"interest is stated on {ENGINE_BASIS} debt, which is what "
        f"model/forecast.py charges (STEP 19); {len(computed)} period(s) computed, "
        "with the average-debt rate shown alongside and not used",
    )


def unavailable_schedules_are_explained(schedules: ScheduleSet, tol: Tolerance) -> CheckResult:
    """Rule 1.14: a gap is reported, not left blank.

    `Schedule.__post_init__` already refuses to build an unavailable schedule
    without a reason, so this cannot fail from carelessness -- which is the
    point of writing it as a check anyway. It puts the three missing schedules
    on the same panel as the ones that ran, where a reviewer reading the
    results sees what was NOT verified without going looking for it.
    """
    name = "Every schedule Section 13 asks for is present or explained (1.14)"
    missing = [s for s in schedules.unavailable if not s.reason]
    if missing:
        return _result(
            name, Status.FAIL,
            "unavailable without a stated reason: " + ", ".join(s.key for s in missing),
        )
    if not schedules.unavailable:
        return _result(name, Status.PASS, "all seven schedules were built")
    return _result(
        name, Status.PASS,
        f"{len(schedules.unavailable)} of {len(schedules.all)} could not be built "
        "and each says why: "
        + "; ".join(f"{s.title} ({s.rule})" for s in schedules.unavailable),
    )


#: The order the schedules screen reads them in.
RECONCILED = (
    "working_capital", "ppe", "debt", "retained_earnings", "common_equity",
)


def run_schedule_checks(
    schedules: ScheduleSet, tol: Tolerance | None = None
) -> tuple[CheckResult, ...]:
    """13.8 across the set, plus the two checks about the set itself."""
    tolerance = tol or Tolerance()
    results = [reconcile(schedules.by_key(key), tolerance) for key in RECONCILED]
    results.append(interest_basis_is_stated(schedules, tolerance))
    results.append(unavailable_schedules_are_explained(schedules, tolerance))
    return tuple(results)


def summarize(results: tuple[CheckResult, ...]) -> str:
    counts = dict.fromkeys(Status, 0)
    for result in results:
        counts[result.status] += 1
    return (
        f"{counts[Status.PASS]} passed, {counts[Status.FAIL]} failed, "
        f"{counts[Status.SKIP]} skipped"
    )
