"""Item 48: review progress, the unresolved count, and what VERIFIED needs.

`docs/source-policy.md` §9 answers "what makes a fact verified" as a
conjunction of seven conditions. This module evaluates it, condition by
condition, and says which one is failing -- which is more use to a reviewer
than a boolean, and is what keeps the answer honest: **nothing reaches
VERIFIED in Phase 4**, because condition 7 needs an approved mapping and the
mapping stage is Phase 5.

Saying that plainly matters more than it looks. A progress bar that reaches
100% while condition 7 is structurally unmet would be the exact failure rule
1.14 names -- an unresolved requirement appearing as PASS.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..extraction.jobs import DocumentVerificationState, FactVerificationState
from ..extraction.reasons import ReasonCode
from ..extraction.records import ExtractionResult, ReportedFact

#: The two codes source-policy.md §9 condition 5 is about. Neither is raised
#: yet: a subtotal has no components to compare against until the mapping of
#: Phase 5 exists, so the condition is vacuously met today, and this names why
#: rather than leaving it looking checked.
RECONCILIATION_CODES = (
    ReasonCode.SUBTOTAL_MISMATCH,
    ReasonCode.CROSS_STATEMENT_MISMATCH,
)

DECIDED = (
    FactVerificationState.ACCEPTED,
    FactVerificationState.CORRECTED,
    FactVerificationState.REJECTED,
)


@dataclass(frozen=True)
class Gate:
    """One of source-policy.md §9's seven conditions, evaluated."""

    number: int
    description: str
    met: bool
    #: Who can satisfy it: the extractor, the reviewer, or a later phase.
    owner: str
    detail: str = ""

    def describe(self) -> str:
        mark = "yes" if self.met else "NO "
        return f"  {self.number}. [{mark}] {self.description}" + (
            f"\n        {self.detail}" if self.detail else ""
        )


def verification_gates(fact: ReportedFact, result: ExtractionResult) -> tuple[Gate, ...]:
    """Evaluate all seven conditions for one fact."""
    document = result.document
    location = result.location(fact.source_location_id)

    located = location is not None and location.page_number >= 1
    metadata_confirmed = document.verification_status is DocumentVerificationState.CONFIRMED
    outstanding = fact.blocking_codes
    reconciliation_outstanding = [c for c in outstanding if c in RECONCILIATION_CODES]
    decided = fact.verification_status in (
        FactVerificationState.ACCEPTED,
        FactVerificationState.CORRECTED,
    )

    return (
        Gate(
            1,
            "has a source location with a page number and a bounding box",
            located,
            "extraction",
            "" if located else "no location record -- this should be impossible",
        ),
        Gate(
            2,
            "its raw string is stored and its value came from the deterministic parser",
            bool(fact.raw_value == fact.parsed.raw_value),
            "extraction",
        ),
        Gate(
            3,
            "the document's metadata is CONFIRMED, not merely detected",
            metadata_confirmed,
            "reviewer",
            ""
            if metadata_confirmed
            else "still unconfirmed: "
            + ", ".join(document.metadata.unconfirmed_required),
        ),
        Gate(
            4,
            "it carries no unresolved blocking reason code",
            not outstanding,
            "reviewer",
            "" if not outstanding else "outstanding: " + ", ".join(c.value for c in outstanding),
        ),
        Gate(
            5,
            "it passes, or was explicitly accepted against, its reconciliations",
            not reconciliation_outstanding,
            "phase 5",
            "vacuously met: a subtotal has no mapped components to reconcile "
            "against until Phase 5 exists"
            if not reconciliation_outstanding
            else "outstanding: " + ", ".join(c.value for c in reconciliation_outstanding),
        ),
        Gate(
            6,
            "a reviewer accepted or corrected it, with the action in the audit log",
            decided,
            "reviewer",
            ""
            if decided
            else f"current status: {fact.verification_status.value}",
        ),
        Gate(
            7,
            "its mapping to a normalized line item is human-approved",
            False,
            "phase 5",
            "no mapping entity exists. Phase 5 owns 11.10 and 11.11, so no fact "
            "can reach VERIFIED yet, and none is reported as verified.",
        ),
    )


def is_review_complete(fact: ReportedFact, result: ExtractionResult) -> bool:
    """Conditions 1-6: everything Phase 4 can satisfy."""
    return all(g.met for g in verification_gates(fact, result) if g.number <= 6)


def is_verified(fact: ReportedFact, result: ExtractionResult) -> bool:
    """All seven. Returns False for every fact until Phase 5 exists."""
    return all(g.met for g in verification_gates(fact, result))


@dataclass(frozen=True)
class PageProgress:
    page_number: int
    total: int
    decided: int
    unresolved: int

    @property
    def complete(self) -> bool:
        return self.decided == self.total and self.unresolved == 0


@dataclass(frozen=True)
class ReviewProgress:
    """Item 48. What is left to do, and what cannot be done here at all."""

    total: int
    decided: int
    accepted: int
    corrected: int
    rejected: int
    #: Facts still carrying a blocking code nobody has resolved (10.29, 10.30).
    unresolved: int
    #: Facts meeting conditions 1-6.
    review_complete: int
    #: Facts meeting all seven. Zero until Phase 5.
    verified: int
    metadata_confirmed: bool
    unconfirmed_required: tuple[str, ...]
    pages: tuple[PageProgress, ...]

    @property
    def undecided(self) -> int:
        return self.total - self.decided

    @property
    def percent_decided(self) -> int:
        """Whole percent, floored, so 99.6% never displays as 100."""
        return 0 if not self.total else (self.decided * 100) // self.total

    @property
    def done(self) -> bool:
        """Everything Phase 4 can finish is finished. NOT the same as verified."""
        return self.total > 0 and self.review_complete == self.total

    def describe(self) -> str:
        lines = [
            f"  {self.decided} of {self.total} fact(s) decided ({self.percent_decided}%)"
            f" -- {self.accepted} accepted, {self.corrected} corrected, {self.rejected} rejected",
            f"  {self.unresolved} still carrying an unresolved blocking code",
            f"  {self.review_complete} meeting conditions 1-6 of source-policy.md §9",
            f"  {self.verified} VERIFIED -- condition 7 needs the approved mapping of Phase 5",
        ]
        if not self.metadata_confirmed:
            lines.append(
                f"  document metadata is not confirmed; {len(self.unconfirmed_required)} "
                f"required field(s) outstanding: {', '.join(self.unconfirmed_required)}"
            )
        return "\n".join(lines)


def review_progress(result: ExtractionResult) -> ReviewProgress:
    """Count what is done, what is not, and what cannot be. 10.29, item 48."""
    facts = result.facts
    by_page: dict[int, list[ReportedFact]] = {}
    for fact in facts:
        location = result.location(fact.source_location_id)
        page = location.page_number if location else 0
        by_page.setdefault(page, []).append(fact)

    pages = tuple(
        PageProgress(
            page_number=page,
            total=len(items),
            decided=sum(1 for f in items if f.verification_status in DECIDED),
            unresolved=sum(1 for f in items if f.blocking_codes),
        )
        for page, items in sorted(by_page.items())
    )

    return ReviewProgress(
        total=len(facts),
        decided=sum(1 for f in facts if f.verification_status in DECIDED),
        accepted=sum(1 for f in facts if f.verification_status is FactVerificationState.ACCEPTED),
        corrected=sum(1 for f in facts if f.verification_status is FactVerificationState.CORRECTED),
        rejected=sum(1 for f in facts if f.verification_status is FactVerificationState.REJECTED),
        unresolved=sum(1 for f in facts if f.blocking_codes),
        review_complete=sum(1 for f in facts if is_review_complete(f, result)),
        verified=sum(1 for f in facts if is_verified(f, result)),
        metadata_confirmed=(
            result.document.verification_status is DocumentVerificationState.CONFIRMED
        ),
        unconfirmed_required=result.document.metadata.unconfirmed_required,
        pages=pages,
    )
