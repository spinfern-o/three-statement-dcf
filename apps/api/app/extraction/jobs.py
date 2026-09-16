"""Item 29: extraction job states, and the transitions between them.

`docs/data-dictionary.md` records `SourceDocument.extraction_status` and
`verification_status` as **OPEN**: required fields whose value sets the
specification describes behaviourally (10.6-10.8, 10.11-10.13) but never
enumerates. Phase 3 item 29 cannot be built on an open enumeration, so this
module closes it, and the data dictionary is updated to match.

The states, and why each exists rather than being folded into its neighbour:

    RECEIVED      Bytes are in hand. Nothing has been read.
    VALIDATING    Signature, size, hash, duplicate, structural scan (10.1-10.5).
                  Separate from RECEIVED because source-policy.md §2 requires
                  the scan to happen BEFORE the file is written to storage, so
                  there is a real interval during which the document exists but
                  is not stored.
    STORED        The bytes are in the immutable store (1.12). The point of no
                  return: from here the document exists as evidence even if
                  everything afterwards fails.
    CLASSIFYING   Per-page text-native / image-only / mixed detection (10.6).
                  Separate because decision 2.3.c makes this a decision point:
                  an image-only page refuses the document.
    EXTRACTING    Text, geometry, tables and facts (10.7, 10.9, 10.25).
    EXTRACTED     Terminal. Facts exist and are UNVERIFIED, awaiting Phase 4.

    REFUSED       Terminal. A *policy* stop: a rule said no. Not an error --
                  this is the system working.
    FAILED        Terminal. An *unexpected* stop: the parser raised, the disk
                  was full. Distinguished from REFUSED because the two need
                  opposite responses. A refusal is answered by the reviewer; a
                  failure is answered by an engineer.

Why the graph has no backward edges: a re-extraction is a **new job** over the
same stored document, not a rewind of the old one. The old job's history is
the record of what happened, and 10.33 requires that record not be mutated.
The same reasoning is why every terminal state is terminal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from ..core.errors import IllegalTransition


class JobState(str, Enum):
    RECEIVED = "received"
    VALIDATING = "validating"
    STORED = "stored"
    CLASSIFYING = "classifying"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    REFUSED = "refused"
    FAILED = "failed"


TERMINAL: frozenset[JobState] = frozenset(
    {JobState.EXTRACTED, JobState.REFUSED, JobState.FAILED}
)

#: The legal transition graph. Every non-terminal state may refuse or fail,
#: because a rule can say no at any point and a parser can raise at any point.
LEGAL_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.RECEIVED: frozenset({JobState.VALIDATING, JobState.REFUSED, JobState.FAILED}),
    JobState.VALIDATING: frozenset({JobState.STORED, JobState.REFUSED, JobState.FAILED}),
    JobState.STORED: frozenset({JobState.CLASSIFYING, JobState.REFUSED, JobState.FAILED}),
    JobState.CLASSIFYING: frozenset({JobState.EXTRACTING, JobState.REFUSED, JobState.FAILED}),
    JobState.EXTRACTING: frozenset({JobState.EXTRACTED, JobState.REFUSED, JobState.FAILED}),
    JobState.EXTRACTED: frozenset(),
    JobState.REFUSED: frozenset(),
    JobState.FAILED: frozenset(),
}

assert set(LEGAL_TRANSITIONS) == set(JobState), "every state needs an outgoing row"
assert all(not LEGAL_TRANSITIONS[s] for s in TERMINAL), "terminal states have no exits"


class DocumentVerificationState(str, Enum):
    """`SourceDocument.verification_status` -- 10.11 to 10.13.

    Metadata detection produces UNCONFIRMED, without exception (10.11). A
    reviewer confirms or corrects every required field (10.13), and only then
    is the document CONFIRMED. Check `VAL-017-002` is the gate.
    """

    UNCONFIRMED = "unconfirmed"
    IN_REVIEW = "in_review"
    CONFIRMED = "confirmed"


class FactVerificationState(str, Enum):
    """`ReportedFact.verification_status` -- 10.29 to 10.33.

    UNVERIFIED is the state every extracted fact starts in. NEEDS_REVIEW is
    what a blocking reason code or a sub-threshold confidence forces (10.29,
    10.30). ACCEPTED, CORRECTED and REJECTED are the three reviewer actions
    (10.32), each requiring an audit entry (10.33). VERIFIED is the conjunction
    in source-policy.md §9 and is NOT a reviewer action -- it is a derived
    state that also requires an approved mapping (11.11), which Phase 5 owns.
    """

    UNVERIFIED = "unverified"
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"
    VERIFIED = "verified"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Transition:
    """One state change, with the reason and when it happened. 10.33."""

    from_state: JobState
    to_state: JobState
    at: datetime
    reason: str

    def describe(self) -> str:
        return (
            f"{self.at.isoformat()}  {self.from_state.value} -> "
            f"{self.to_state.value}  {self.reason}"
        )


@dataclass(frozen=True)
class ExtractionJob:
    """An attempt to extract one document. Immutable; `advance` returns a new one."""

    id: str
    state: JobState
    history: tuple[Transition, ...] = ()
    document_id: str | None = None
    #: The refusal code, when `state` is REFUSED. Kept so the reviewer sees
    #: which rule stopped the upload without parsing the reason text.
    refusal_code: str | None = None

    @classmethod
    def start(cls, *, job_id: str | None = None) -> "ExtractionJob":
        return cls(id=job_id or f"job-{uuid.uuid4().hex[:12]}", state=JobState.RECEIVED)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL

    def advance(
        self,
        to_state: JobState,
        reason: str,
        *,
        clock: Callable[[], datetime] = utc_now,
        document_id: str | None = None,
        refusal_code: str | None = None,
    ) -> "ExtractionJob":
        """Move to `to_state`, or raise `IllegalTransition`.

        The reason is required. A state change with no stated reason is exactly
        the audit gap 10.33 exists to close, and "" is not a reason.
        """
        if not reason or not reason.strip():
            raise ValueError("a transition reason is required (10.33)")

        allowed = LEGAL_TRANSITIONS[self.state]
        if to_state not in allowed:
            if self.is_terminal:
                detail = (
                    f"{self.state.value} is terminal. A re-extraction is a new "
                    f"job over the same stored document, not a rewind of this one."
                )
            else:
                names = ", ".join(sorted(s.value for s in allowed))
                detail = f"legal next states are: {names}"
            raise IllegalTransition(
                f"job {self.id} cannot move {self.state.value} -> {to_state.value}. {detail}"
            )

        transition = Transition(
            from_state=self.state, to_state=to_state, at=clock(), reason=reason.strip()
        )
        return replace(
            self,
            state=to_state,
            history=self.history + (transition,),
            document_id=document_id if document_id is not None else self.document_id,
            refusal_code=refusal_code if refusal_code is not None else self.refusal_code,
        )

    def describe(self) -> str:
        lines = [f"job {self.id}: {self.state.value}"]
        lines.extend("  " + t.describe() for t in self.history)
        return "\n".join(lines)
