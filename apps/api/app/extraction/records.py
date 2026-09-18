"""Item 33: the records extraction produces. Section 9.3, 9.4, 9.5, 9.14.

`docs/data-dictionary.md` is the contract for these shapes, including where
they diverge from the engine's `provenance.Figure`. Three divergences are
introduced here deliberately, and each is recorded in the data dictionary:

  1. **`ReportedFact.period_label` exists; `period_start`/`period_end` may be
     null at ingestion.** 9.5 marks both dates required. A statement column
     headed `2025` is an unambiguous *label*, but its date range depends on the
     fiscal year-end, which is UNCONFIRMED until a reviewer confirms it
     (10.11-10.13). Filling the dates from an unconfirmed year-end is exactly
     what rule 1.4 forbids. So the label is stored, the dates are null, and
     `resolve_periods()` fills them once the metadata is confirmed.

  2. **`currency` and `source_scale` are references to the document's detected
     metadata, not values copied onto the fact.** Copying an UNCONFIRMED scale
     onto ten thousand facts makes correcting it a migration.

  3. **`confidence` is a `Confidence`, not a bare number** -- the score plus
     the evidence conditions that produced it (see `reasons.py`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from model.numeric import D

from ..core.config import DEFAULT_REVIEW_THRESHOLD
from .geometry import BoundingBox
from .jobs import DocumentVerificationState, FactVerificationState, JobState, utc_now
from .metadata import DetectedMetadata
from .pages import PageProfile
from .parsing import NumberLocale, ParsedValue, SignSource, parse_reported_value
from .reasons import Confidence, EvidenceCheck, ReasonCode, score_confidence

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    # `mapping` imports `extraction`; this is the same edge in the other
    # direction, which would be a cycle at runtime and is not one here.
    from ..mapping.sets import MappingSet


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Scope(str, Enum):
    """9.5 `scope`. Rule 1.11 forbids mixing these."""

    CONSOLIDATED = "consolidated"
    SEGMENT = "segment"
    PARENT = "parent"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True)
class SourceLocation:
    """9.4. Where on which page a value was printed."""

    id: str
    document_id: str
    page_number: int
    bounding_box: BoundingBox
    raw_text: str
    table_id: str | None = None
    row_label: str | None = None
    column_label: str | None = None

    @classmethod
    def create(cls, **kwargs) -> SourceLocation:
        return cls(id=_new_id("loc"), **kwargs)

    def cite(self) -> str:
        parts = [f"page {self.page_number}"]
        if self.row_label:
            parts.append(f"row {self.row_label!r}")
        if self.column_label:
            parts.append(f"column {self.column_label!r}")
        return ", ".join(parts)


@dataclass(frozen=True)
class RawCell:
    """One table cell as extracted, before any interpretation. 10.25."""

    row: int
    column: int
    text: str
    bounding_box: BoundingBox


@dataclass(frozen=True)
class RawTable:
    """A table as found on the page. 10.14, 10.15.

    Both representations are kept. `cells` is the raw extraction, evidence of
    what was printed. `header_row` and `data_rows` are the normalized view,
    with repeated headers removed -- 10.15 requires the removal happen only in
    the normalized data.
    """

    id: str
    document_id: str
    page_number: int
    bounding_box: BoundingBox
    cells: tuple[RawCell, ...]
    row_count: int
    column_count: int
    header_row: int | None = None
    #: Rows that repeat the header inside the body (10.15).
    repeated_header_rows: tuple[int, ...] = ()
    caption: str = ""
    split_across_pages: bool = False
    #: Each row's label, re-read from the page rather than stitched from cells.
    #: See the note in `text_native.py`: neither joining nor not joining the
    #: cell fragments is right for both a split on a space and a split
    #: mid-word, and the page has the answer to both.
    row_labels: tuple[str, ...] = ()

    @classmethod
    def create(cls, **kwargs) -> RawTable:
        return cls(id=_new_id("tbl"), **kwargs)

    def cell(self, row: int, column: int) -> RawCell | None:
        for c in self.cells:
            if c.row == row and c.column == column:
                return c
        return None


@dataclass(frozen=True)
class Resolution:
    """A blocking reason code cleared by a reviewer, with the note that did it.

    source-policy.md §9 condition 4 permits a fact to be verified when "every
    blocking code it carried has been resolved by a reviewer action with a
    note". The code is not deleted when that happens -- deleting it would
    erase the reason the fact needed a human in the first place. It is
    recorded as resolved, here, with who resolved it and why.
    """

    code: ReasonCode
    actor: str
    note: str
    at: datetime

    def describe(self) -> str:
        return f"{self.code.value} resolved by {self.actor}: {self.note}"


@dataclass(frozen=True)
class ReviewDecision:
    """What a reviewer decided about one fact. 10.32, 10.33.

    `reason` is mandatory everywhere it appears in this codebase, for the same
    reason: a correction with no stated basis is indistinguishable from a
    typo six months later.
    """

    action: str
    actor: str
    reason: str
    at: datetime
    #: Set on a correction: the value as parsed, before the reviewer changed it.
    previous_value: Decimal | None = None
    new_value: Decimal | None = None

    def describe(self) -> str:
        change = ""
        if self.action == "correct":
            before = "(no value)" if self.previous_value is None else str(self.previous_value)
            after = "(no value)" if self.new_value is None else str(self.new_value)
            change = f" {before} -> {after}"
        return f"{self.action}{change} by {self.actor}: {self.reason}"


@dataclass(frozen=True)
class ReportedFact:
    """9.5. One number as the company printed it, plus everything about it."""

    id: str
    document_id: str
    source_location_id: str
    raw_label: str
    raw_value: str
    parsed: ParsedValue
    period_label: str
    scope: Scope
    confidence: Confidence
    reason_codes: tuple[ReasonCode, ...] = ()
    verification_status: FactVerificationState = FactVerificationState.UNVERIFIED
    #: Set by a reviewer correction. `parsed` is NEVER overwritten -- 10.25
    #: makes the raw string and its parse evidence, and evidence does not get
    #: edited. `value` below prefers this when it exists.
    corrected_value: Decimal | None = None
    resolutions: tuple[Resolution, ...] = ()
    decision: ReviewDecision | None = None
    #: Codes raised by the MAPPING stage (11.6, 11.7, 10.30), kept apart from
    #: `reason_codes` because they are recomputed from the current mapping set
    #: every time it changes. Mixing them into the extraction's findings would
    #: leave a stale mismatch on a fact whose mapping was since corrected.
    mapping_codes: tuple[ReasonCode, ...] = ()
    mapping_notes: tuple[str, ...] = ()
    period_start: date | None = None
    period_end: date | None = None
    instant_date: date | None = None
    segment: str | None = None
    reviewer_id: str | None = None

    @classmethod
    def create(cls, **kwargs) -> ReportedFact:
        return cls(id=_new_id("fact"), **kwargs)

    @property
    def value(self) -> Decimal | None:
        """The number to use: a reviewer's correction if there is one, else the
        parse. **None is never zero** (rule 1.5)."""
        return self.corrected_value if self.corrected_value is not None else self.parsed.value

    @property
    def was_corrected(self) -> bool:
        return self.corrected_value is not None

    @property
    def resolved_codes(self) -> tuple[ReasonCode, ...]:
        return tuple(r.code for r in self.resolutions)

    @property
    def sign_source(self) -> SignSource:
        return self.parsed.sign_source

    @property
    def blocking_codes(self) -> tuple[ReasonCode, ...]:
        """Blocking codes a reviewer has NOT yet resolved. 10.29, 10.30.

        A resolved code stays on `reason_codes` as the record of what the
        extraction found; it simply no longer blocks.
        """
        resolved = set(self.resolved_codes)
        found = self.reason_codes + self.mapping_codes
        seen: list[ReasonCode] = []
        for code in found:
            if code.blocking and code not in resolved and code not in seen:
                seen.append(code)
        return tuple(seen)

    @property
    def all_blocking_codes(self) -> tuple[ReasonCode, ...]:
        """Every blocking code raised, resolved or not, at either stage."""
        return tuple(c for c in self.reason_codes + self.mapping_codes if c.blocking)

    def describe(self) -> str:
        shown = self.value if self.value is not None else "(no value)"
        codes = " ".join(c.value for c in self.reason_codes)
        return (
            f"{self.raw_label[:40]:40} {self.period_label:>8} "
            f"{shown!s:>14}  raw={self.raw_value!r:14} "
            f"conf={self.confidence.score} {codes}"
        )


@dataclass(frozen=True)
class AuditEvent:
    """9.14. 10.33 requires every acceptance, correction and rejection recorded."""

    id: str
    at: datetime
    actor: str
    action: str
    entity_type: str
    entity_id: str
    detail: str

    @classmethod
    def create(
        cls, *, actor: str, action: str, entity_type: str, entity_id: str, detail: str
    ) -> AuditEvent:
        if not detail.strip():
            raise ValueError("an audit entry without a reason is not an audit entry (10.33)")
        return cls(
            id=_new_id("audit"),
            at=utc_now(),
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail.strip(),
        )

    def describe(self) -> str:
        return f"{self.at.isoformat()}  {self.actor}  {self.action}  {self.entity_type}:{self.entity_id}  {self.detail}"


@dataclass(frozen=True)
class SourceDocument:
    """9.3. The uploaded filing, and everything known about it."""

    id: str
    company_id: str
    immutable_hash: str
    original_filename: str
    sanitized_filename: str
    mime_type: str
    byte_size: int
    page_count: int
    pdf_version: str
    uploaded_at: datetime
    extraction_status: JobState
    verification_status: DocumentVerificationState
    metadata: DetectedMetadata
    pages: tuple[PageProfile, ...] = ()
    storage_path: str = ""
    #: Set when this record was created as an explicit linked duplicate (10.3).
    duplicate_of: str | None = None
    scan_notes: tuple[str, ...] = ()

    @classmethod
    def create(cls, **kwargs) -> SourceDocument:
        return cls(id=_new_id("doc"), **kwargs)


@dataclass(frozen=True)
class ExtractionResult:
    """Everything known about one document.

    Named for what created it, but it accumulates: Phase 3 fills `tables`,
    `locations` and `facts`; Phase 4 writes reviewer decisions onto the facts;
    Phase 5 adds `mappings`. Keeping them in one record is what makes a
    reviewer's session a single thing to load, save and version.

    `mappings` is None until the mapping stage begins, which is distinct from
    an empty set: "nobody has started" and "somebody started and mapped
    nothing" are different states and only one of them is a problem.
    """

    document: SourceDocument
    tables: tuple[RawTable, ...]
    locations: tuple[SourceLocation, ...]
    facts: tuple[ReportedFact, ...]
    audit: tuple[AuditEvent, ...]
    job_history: tuple[str, ...]
    #: Phase 5. A `mapping.sets.MappingSet`, imported under `TYPE_CHECKING` so
    #: that `extraction` does not import `mapping` at runtime -- the dependency
    #: runs the other way and a cycle between them would be the wrong shape --
    #: while the declared type is still the real one.
    #:
    #: It was `object` before, which meant every reader of `.mappings` had to
    #: know what it really held and nothing could check that they did. Two
    #: modules were reaching straight for `.mappings.mappings` through it.
    mappings: MappingSet | None = None

    @property
    def facts_needing_review(self) -> tuple[ReportedFact, ...]:
        """10.29, 10.30."""
        return tuple(f for f in self.facts if f.blocking_codes)

    def location(self, location_id: str) -> SourceLocation | None:
        for loc in self.locations:
            if loc.id == location_id:
                return loc
        return None


#: The reason codes that belong to the *document*, not the fact. They clear
#: when the corresponding metadata field is confirmed (10.13).
DOCUMENT_CODES = (ReasonCode.SCALE_UNCONFIRMED, ReasonCode.CURRENCY_UNCONFIRMED)


def confirm_metadata(
    result: ExtractionResult,
    confirmations: dict[str, str | None],
    *,
    actor: str,
    reason: str,
    review_threshold=D(DEFAULT_REVIEW_THRESHOLD),
) -> ExtractionResult:
    """Confirm or correct metadata fields, then re-run what depends on them.

    Specification 10.13 requires confirmation or correction of every required
    metadata field, and 10.35 requires all dependent work re-run after an
    approved change. This is the smallest honest instance of both: confirming
    the scale and currency clears `SCALE_UNCONFIRMED` and
    `CURRENCY_UNCONFIRMED` from every fact, and confirming the number locale
    re-parses every cell -- which turns `SEPARATOR_AMBIGUOUS` into either a
    value or a different, still-blocking problem.

    `confirmations` maps a field name to `None` (accept what was detected) or
    to a replacement string (correct it). Nothing is mutated; a new
    `ExtractionResult` is returned and every change is in the audit log.

    The reviewer *interface* for this is Phase 4 item 44. This is the state
    transition underneath it, which Phase 3 needs in order to show that an
    unconfirmed document is a real state and not a permanent one.
    """
    if not reason.strip():
        raise ValueError("confirming metadata requires a reason (10.32, 10.33)")

    fields = dict(result.document.metadata.fields)
    events = list(result.audit)

    for name, replacement in confirmations.items():
        if name not in fields:
            raise KeyError(f"{name!r} is not a detected metadata field")
        before = fields[name]
        fields[name] = before.confirm() if replacement is None else before.correct(replacement)
        events.append(
            AuditEvent.create(
                actor=actor,
                action="confirm_metadata" if replacement is None else "correct_metadata",
                entity_type="SourceDocument",
                entity_id=result.document.id,
                detail=(
                    f"{name}: {before.value!r} -> {fields[name].value!r} "
                    f"({fields[name].state.value}). {reason}"
                ),
            )
        )

    metadata = DetectedMetadata(fields=fields)
    locale = _confirmed_locale(metadata)
    document_codes = tuple(
        code
        for code, field_name in zip(DOCUMENT_CODES, ("displayed_scale", "reporting_currency"))
        if not fields[field_name].confirmed
    )

    facts = tuple(
        _refresh_fact(
            fact,
            locale=locale,
            document_codes=document_codes,
            review_threshold=review_threshold,
        )
        for fact in result.facts
    )
    withdrawn = sum(
        1
        for before, after in zip(result.facts, facts)
        if before.decision is not None and after.decision is None
    )

    status = (
        DocumentVerificationState.CONFIRMED
        if metadata.all_required_confirmed
        else DocumentVerificationState.IN_REVIEW
    )
    document = replace(result.document, metadata=metadata, verification_status=status)

    events.append(
        AuditEvent.create(
            actor="system",
            action="revalidate",
            entity_type="SourceDocument",
            entity_id=document.id,
            detail=(
                f"{len(facts)} fact(s) re-evaluated after the metadata change (10.35); "
                f"{sum(1 for f in facts if f.blocking_codes)} still need review"
                + (
                    f"; {withdrawn} acceptance(s) withdrawn because the value they accepted changed"
                    if withdrawn
                    else ""
                )
            ),
        )
    )
    return replace(result, document=document, facts=facts, audit=tuple(events))


def reparse_with_locale(
    result: ExtractionResult, locale: NumberLocale, *, actor: str, reason: str
) -> ExtractionResult:
    """Confirm the number locale alone. A thin wrapper over `confirm_metadata`."""
    return confirm_metadata(result, {"number_locale": locale.value}, actor=actor, reason=reason)


def _confirmed_locale(metadata: DetectedMetadata) -> NumberLocale:
    """The locale to parse with -- UNKNOWN unless a reviewer has confirmed it."""
    field_ = metadata.fields.get("number_locale")
    if field_ is None or not field_.confirmed or not field_.value:
        return NumberLocale.UNKNOWN
    try:
        return NumberLocale(field_.value)
    except ValueError:
        return NumberLocale.UNKNOWN


def _refresh_fact(
    fact: ReportedFact,
    *,
    locale: NumberLocale,
    document_codes: tuple[ReasonCode, ...],
    review_threshold,
) -> ReportedFact:
    """Re-parse and re-score one fact against the current metadata."""
    reparsed = parse_reported_value(fact.raw_value, locale=locale)

    # Codes that belong to the table and the page survive; the parse's own codes
    # and the document's codes are recomputed.
    intrinsic = tuple(
        c
        for c in fact.reason_codes
        if c not in fact.parsed.reason_codes and c not in DOCUMENT_CODES
    )
    intrinsic = tuple(c for c in intrinsic if c is not ReasonCode.LOW_CONFIDENCE)
    codes = _dedupe(reparsed.reason_codes + intrinsic + document_codes)

    confidence = score_confidence(
        {
            **{c: c in fact.confidence.passed for c in EvidenceCheck},
            EvidenceCheck.PARSED: reparsed.is_parsed,
            EvidenceCheck.SIGN_EXPLICIT: reparsed.sign_source is not SignSource.UNRESOLVED,
            EvidenceCheck.CLEAN_NUMERIC: not reparsed.footnote_markers,
        }
    )
    if confidence.needs_review(review_threshold):
        codes = _dedupe(codes + (ReasonCode.LOW_CONFIDENCE,))

    updated = replace(fact, parsed=reparsed, reason_codes=codes, confidence=confidence)

    # 10.35, the uncomfortable half. If the re-parse produced a DIFFERENT number
    # and a reviewer had already accepted the old one, their acceptance was of a
    # value that no longer exists. Keeping it would leave a fact marked accepted
    # by someone who never saw what it now says. The acceptance is withdrawn and
    # the fact goes back to the queue; `confirm_metadata` records how many.
    #
    # A *correction* is not withdrawn: the reviewer supplied that number
    # themselves, and a re-parse of the printed string does not overrule them.
    if (
        fact.decision is not None
        and fact.decision.action == "accept"
        and reparsed.value != fact.parsed.value
    ):
        updated = replace(
            updated,
            decision=None,
            resolutions=(),
            verification_status=FactVerificationState.UNVERIFIED,
            reviewer_id=None,
        )
    return updated


def _dedupe(codes) -> tuple[ReasonCode, ...]:
    seen: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.append(code)
    return tuple(seen)
