"""Item 95 and 96: the approval workflow, and the 14.1 gate.

14.2 lists five statuses and says nothing about how one becomes another. The
transitions below are designed from what each status means, and the shape is
the one `extraction/jobs.py` already uses for the ingestion lifecycle: legal
transitions declared as data, every move requiring an actor and a written
reason, and the refusal naming the transition rather than the state.

    Draft ──────────► Needs Source ──────► Draft
      │                                      │
      ├──────────────► Reviewed ◄────────────┤
      │                  │   │
      │                  │   └────► Rejected
      │                  ▼
      └───────────────► Approved ──► Draft (reopened)
                           │
                           └───────► Rejected

Three rules are enforced beyond the diagram, and each exists because the
alternative lets an unsourced number into a valuation.

**Reviewed and Approved require a reviewer** (14.4.i). It may be the same
person as the owner -- this system is single-user -- and `is_self_reviewed`
records that rather than pretending otherwise.

**Approved requires the evidence its source type demands.** The schema already
refuses to construct an assumption without it, so this is a second gate on the
same rule; it catches the case where the source type was changed after the
evidence was entered.

**Nothing may move to Approved from Draft directly.** Review is the step where
a second pair of eyes looks at the evidence, and a workflow that lets it be
skipped is a workflow with four statuses and a decoration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .schema import Assumption, AssumptionError, Status

#: Which status may follow which. Declared as data so the diagram above and
#: the code cannot drift.
LEGAL_TRANSITIONS: dict[Status, frozenset[Status]] = {
    Status.DRAFT: frozenset({Status.NEEDS_SOURCE, Status.REVIEWED, Status.REJECTED}),
    Status.NEEDS_SOURCE: frozenset({Status.DRAFT, Status.REVIEWED, Status.REJECTED}),
    Status.REVIEWED: frozenset({Status.APPROVED, Status.REJECTED, Status.DRAFT}),
    Status.APPROVED: frozenset({Status.DRAFT, Status.REJECTED}),
    Status.REJECTED: frozenset({Status.DRAFT}),
}

#: Statuses that require a named reviewer (14.4.i).
NEEDS_REVIEWER = frozenset({Status.REVIEWED, Status.APPROVED})


class WorkflowError(ValueError):
    """A status change was refused, and this says which one and why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class StatusChange:
    """9.14's audit event, for one assumption's status."""

    code: str
    scenario_id: str
    was: Status
    became: Status
    actor: str
    reason: str
    at: str = field(default_factory=_now)

    def describe(self) -> str:
        return (
            f"{self.code} [{self.scenario_id}] {self.was.value} -> "
            f"{self.became.value} by {self.actor}: {self.reason}"
        )


def transition(
    assumption: Assumption,
    to: Status,
    *,
    actor: str,
    reason: str,
    reviewer: str = "",
) -> tuple[Assumption, StatusChange]:
    """Move one assumption's status, or refuse and say why.

    The reason is mandatory for the same reason `review/actions.py` makes it
    mandatory on a fact correction: 10.32 permits a change "only with a
    reviewer note", and a status change with no note is a change nobody can
    account for later.
    """
    if not isinstance(to, Status):
        raise WorkflowError(f"{to!r} is not one of 14.2's five statuses")
    if not actor.strip():
        raise WorkflowError(f"{assumption.code}: a status change needs an actor")
    if not reason.strip():
        raise WorkflowError(
            f"{assumption.code}: a status change needs a written reason. "
            "A change nobody explained is a change nobody can account for."
        )
    if to == assumption.status:
        raise WorkflowError(
            f"{assumption.code} is already {to.value}. A no-op transition would "
            "write an audit entry recording that nothing happened."
        )
    allowed = LEGAL_TRANSITIONS[assumption.status]
    if to not in allowed:
        detail = ""
        if assumption.status is Status.DRAFT and to is Status.APPROVED:
            detail = (
                " Review is where the evidence is looked at; a workflow that "
                "lets it be skipped has four statuses and a decoration."
            )
        raise WorkflowError(
            f"{assumption.code} cannot go from {assumption.status.value} to "
            f"{to.value}. From {assumption.status.value} the legal moves are: "
            f"{', '.join(sorted(s.value for s in allowed))}.{detail}"
        )

    named = reviewer or assumption.reviewer
    if to in NEEDS_REVIEWER and not named.strip():
        raise WorkflowError(
            f"{assumption.code} cannot become {to.value} without a named "
            "reviewer (14.4.i). It may be the same person as the owner -- that "
            "is recorded as self-review rather than refused -- but it must be "
            "someone."
        )
    if to is Status.APPROVED:
        _check_evidence_still_holds(assumption)

    moved = assumption.with_status(to, reviewer=named)
    return moved, StatusChange(
        code=assumption.code,
        scenario_id=assumption.scenario_id,
        was=assumption.status,
        became=to,
        actor=actor,
        reason=reason,
    )


def _check_evidence_still_holds(assumption: Assumption) -> None:
    """A second pass over the schema's own rule, at the moment it matters.

    The constructor already refuses an assumption whose evidence does not
    match its source type. This catches the sequence where the source type was
    edited afterwards -- the object was valid when built and is not now.
    """
    try:
        assumption._check_evidence()
    except AssumptionError as exc:
        raise WorkflowError(f"{assumption.code} cannot be approved: {exc}") from None


# --- 14.1: the gate -------------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    """Whether a forecast may calculate, and exactly what is in the way."""

    #: Required driver choices with nothing supplied at all.
    missing: tuple[str, ...]
    #: Supplied, but with a status that is not an answer.
    unresolved: tuple[tuple[str, str], ...]
    #: Both members of a one-of-two pair declared (STEP 14/18).
    ambiguous: tuple[str, ...]
    #: Approved on the strength of the owner's own review.
    self_reviewed: tuple[str, ...]

    @property
    def may_calculate(self) -> bool:
        return not (self.missing or self.unresolved or self.ambiguous)

    def describe(self) -> str:
        if self.may_calculate:
            note = ""
            if self.self_reviewed:
                note = f" {len(self.self_reviewed)} of them were approved by their own owner."
            return "Every required assumption is Approved or Reviewed." + note
        lines = []
        if self.missing:
            lines.append(f"not supplied: {', '.join(self.missing)}")
        if self.unresolved:
            lines.append(
                "not an answer yet: "
                + ", ".join(f"{code} ({status})" for code, status in self.unresolved)
            )
        if self.ambiguous:
            lines.append(f"two methodologies declared: {', '.join(self.ambiguous)}")
        return "; ".join(lines)
