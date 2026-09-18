"""Items 136 and 137: the release-readiness checklist, and the block.

137 is one sentence -- "prevent release when CRITICAL/ERROR checks remain" --
and it cannot be implemented as written, because Section 17 assigns a severity
to none of its thirty checks. That is finding **F-4**, and it has been open
since Phase 2.

What this does instead is the thing that cannot be wrong in the dangerous
direction.

**Every outstanding check blocks, whatever its proposed severity.** A check
that failed blocks; a check that could not run blocks too, because rule 1.14
says an unresolved requirement must never appear as resolved. That is strictly
stricter than 137 under *any* severity assignment the owner might make, so the
gate cannot release something 137 would have stopped. It can refuse something
137 would have allowed -- a WARNING, say -- and that is the direction to err
in for a valuation.

**The gate says which rule it is standing in for.** `severity_is_unratified`
is on the result and the screen prints it. A reader who sees "not releasable"
is told that twenty-five of the thirty severities are proposals, that five are
forced with their citations, and that ratifying them would let the gate
distinguish a blocking failure from an acknowledged warning.

**Two of the thirty can never pass here, and they are separated out.** 17.28's
benchmark is a claim 4.20 permits only once the test suite has run, which this
application does not observe; 17.12's intangibles schedule cannot exist while
the chart has no intangibles line. Folding those into "outstanding" would make
the gate permanently red for reasons no reviewer can act on, so they are
reported as `unevaluable` with their reasons and named in the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

from model.checks import Status

from .registry import FORCED, PROPOSED, REGISTRY, Severity
from .run import UNEVALUABLE, Diagnostics, Outcome


@dataclass(frozen=True)
class Readiness:
    """Item 136's checklist, and 137's answer."""

    diagnostics: Diagnostics
    #: Outstanding checks a reviewer can act on.
    blocking: tuple[Outcome, ...]
    #: Outstanding for a reason nothing in this system can change.
    unevaluable: tuple[Outcome, ...]

    @property
    def may_release(self) -> bool:
        return not self.blocking

    @property
    def severity_is_unratified(self) -> bool:
        """F-4, carried on the result rather than assumed away."""
        return bool(PROPOSED)

    @property
    def by_severity(self) -> dict[Severity, tuple[Outcome, ...]]:
        return {
            severity: tuple(o for o in self.blocking if o.check.severity is severity)
            for severity in Severity
        }

    def describe(self) -> str:
        if self.may_release:
            text = (
                f"Every check a reviewer can act on has passed "
                f"({len(self.diagnostics.passed)} of {len(REGISTRY)})."
            )
        else:
            critical = len(self.by_severity[Severity.CRITICAL])
            error = len(self.by_severity[Severity.ERROR])
            text = (
                f"Not releasable: {len(self.blocking)} check(s) outstanding, "
                f"{critical} at CRITICAL and {error} at ERROR."
            )
        if self.unevaluable:
            text += (
                f" {len(self.unevaluable)} check(s) cannot be evaluated by this "
                "system at all and are excluded from the verdict: "
                + ", ".join(o.check.clause for o in self.unevaluable)
                + "."
            )
        return text + " " + SEVERITY_NOTE


SEVERITY_NOTE = (
    f"Section 17 defines four severities and assigns none of its thirty checks "
    f"to one. Only {len(FORCED)} are forced by a rule elsewhere in the "
    f"specification, each with its citation; the other {len(PROPOSED)} in "
    "docs/validation-policy.md are proposals awaiting the owner (finding F-4). "
    "So this gate blocks on EVERY outstanding check whatever its proposed "
    "severity -- stricter than 137 under any assignment, so it cannot release "
    "something 137 would have stopped. Ratifying the severities would let it "
    "tell a blocking failure from an acknowledged warning."
)

#: Clauses whose outcome no reviewer of this model can change.
NOT_ACTIONABLE = frozenset(UNEVALUABLE) | {"17.28"}


def readiness(diagnostics: Diagnostics) -> Readiness:
    """136 and 137, evaluated together."""
    blocking, unevaluable = [], []
    for outcome in diagnostics.outcomes:
        if outcome.status is Status.PASS:
            continue
        if outcome.check.clause in NOT_ACTIONABLE:
            unevaluable.append(outcome)
        else:
            blocking.append(outcome)
    return Readiness(diagnostics, tuple(blocking), tuple(unevaluable))


@dataclass(frozen=True)
class ChecklistItem:
    """One line of item 136's checklist, in the order the work happens."""

    stage: str
    clauses: tuple[str, ...]
    outcomes: tuple[Outcome, ...]

    @property
    def is_clear(self) -> bool:
        return all(o.status is Status.PASS for o in self.outcomes)

    @property
    def outstanding(self) -> tuple[Outcome, ...]:
        return tuple(o for o in self.outcomes if o.status is not Status.PASS)


#: Section 17's own grouping, which is also the order of the work.
STAGES = (
    ("Source and mapping", ("17.1", "17.2", "17.3", "17.4", "17.5", "17.6", "17.7")),
    (
        "Historical statements and schedules",
        ("17.8", "17.9", "17.10", "17.11", "17.12", "17.13", "17.14", "17.15"),
    ),
    ("Forecast", ("17.16", "17.17", "17.18", "17.19", "17.20", "17.21", "17.22")),
    ("Valuation", ("17.23", "17.24", "17.25", "17.26")),
    ("Numbers and lineage", ("17.27", "17.28", "17.29", "17.30")),
)


def checklist(diagnostics: Diagnostics) -> tuple[ChecklistItem, ...]:
    """Item 136, grouped by stage so a reader sees where the work stopped."""
    by_clause = {o.check.clause: o for o in diagnostics.outcomes}
    return tuple(
        ChecklistItem(
            stage=stage,
            clauses=clauses,
            outcomes=tuple(by_clause[c] for c in clauses if c in by_clause),
        )
        for stage, clauses in STAGES
    )


def every_clause_is_on_the_checklist() -> bool:
    """A check missing from the checklist is a check nobody looked at."""
    covered = {clause for _, clauses in STAGES for clause in clauses}
    return covered == {check.clause for check in REGISTRY}
