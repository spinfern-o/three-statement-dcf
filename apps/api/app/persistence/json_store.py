"""Item 33 (persistence): record storage, in JSON, behind a protocol.

Specification 3.2.d requires PostgreSQL for a hosted deployment and decision
2.2.a is private hosted, so PostgreSQL is where this ends up. It is Phase 15/17
work and nothing here pretends otherwise. What Phase 3 needs is somewhere to
put a `SourceDocument`, its tables, its locations, its facts and its audit
trail, so that duplicate detection works across runs (10.3) and an extraction
can be read back.

The contract is `DocumentRepository`. Everything above it -- the pipeline, the
CLI -- depends on the protocol, not on JSON, so a PostgreSQL implementation is
a new class rather than a rewrite.

**Every number is written as a string** (4.2). A `Decimal` serialized through
`json` with `float` would lose exactly what `model/numeric.py` exists to
protect, so `_jsonable` refuses floats outright rather than converting them.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Protocol

from ..extraction.geometry import BoundingBox, PageGeometry
from ..extraction.jobs import (
    DocumentVerificationState,
    FactVerificationState,
    JobState,
)
from ..extraction.metadata import (
    ConfirmationState,
    DetectedField,
    DetectedMetadata,
    Evidence,
)
from ..extraction.pages import PageKind, PageProfile
from ..extraction.parsing import NumberLocale, ParsedValue, SignSource, UnitMarker
from ..extraction.reasons import Confidence, EvidenceCheck, ReasonCode
from ..extraction.records import (
    AuditEvent,
    ExtractionResult,
    RawCell,
    RawTable,
    ReportedFact,
    Resolution,
    ReviewDecision,
    Scope,
    SourceDocument,
    SourceLocation,
)
from ..mapping.sets import (
    FactMapping,
    MappingSet,
    MappingType,
    Origin,
    SignNormalization,
)


class SerializationError(TypeError):
    """A value reached the serializer in a form that would lose information."""


def _jsonable(value: object) -> object:
    """Convert to JSON-safe types. Decimals become strings; floats are refused."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise SerializationError(
            f"a float ({value!r}) reached the record serializer. Specification "
            f"4.2 requires monetary values cross boundaries as decimal strings, "
            f"and writing this would store {Decimal(value)}."
        )
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    raise SerializationError(f"cannot serialize {type(value).__name__}: {value!r}")


class DocumentRepository(Protocol):
    """What the pipeline needs from storage. Implement this for PostgreSQL."""

    def id_for_hash(self, company_id: str, immutable_hash: str) -> str | None:
        """10.3. The existing document with this hash for this company, if any."""

    def save(self, result: ExtractionResult) -> Path:
        """Persist one extraction."""

    def load(self, document_id: str) -> dict:
        """Read one extraction back as plain data."""

    def load_result(self, document_id: str) -> ExtractionResult:
        """Read one extraction back as objects, for a review session."""

    def document_ids(self) -> tuple[str, ...]:
        """Every stored document, oldest first."""


class JsonDocumentRepository:
    """A file-per-document repository. Single-user, which 2.2.b confirms."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root) / "records"
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def _index(self) -> dict[str, str]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text())

    @staticmethod
    def _key(company_id: str, immutable_hash: str) -> str:
        return f"{company_id}:{immutable_hash}"

    def id_for_hash(self, company_id: str, immutable_hash: str) -> str | None:
        return self._index().get(self._key(company_id, immutable_hash))

    def lookup_for(self, company_id: str):
        """A callable for `pipeline.ingest`'s `existing_id_for_hash`."""
        return lambda digest: self.id_for_hash(company_id, digest)

    def save(self, result: ExtractionResult) -> Path:
        document = result.document
        path = self.root / f"{document.id}.json"
        payload = {
            "document": _jsonable(document),
            "tables": _jsonable(result.tables),
            "locations": _jsonable(result.locations),
            "facts": _jsonable(result.facts),
            "audit": _jsonable(result.audit),
            "job_history": list(result.job_history),
            "mappings": _jsonable(result.mappings),
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))

        index = self._index()
        index[self._key(document.company_id, document.immutable_hash)] = document.id
        self.index_path.write_text(json.dumps(index, indent=2, sort_keys=True))
        return path

    def load(self, document_id: str) -> dict:
        """Read one extraction back as plain data."""
        return json.loads((self.root / f"{document_id}.json").read_text())

    def load_result(self, document_id: str) -> ExtractionResult:
        """Rebuild the objects. A review session has to survive a restart."""
        return result_from_jsonable(self.load(document_id))

    def document_ids(self) -> tuple[str, ...]:
        return tuple(sorted(p.stem for p in self.root.glob("doc-*.json")))


# --- reading back ----------------------------------------------------------
#
# Reconstruction is written out longhand rather than driven by reflection over
# the dataclass fields. That is deliberate: a field added to a record and not
# added here fails loudly on the next load, which is what should happen. A
# generic rebuilder would silently drop it, and the field it dropped would be
# a reviewer's decision or a bounding box.


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str):
        return Decimal(value)
    raise SerializationError(f"expected a decimal string, got {value!r}")


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _date(value: object) -> date | None:
    return None if value is None else date.fromisoformat(str(value))


def _box(data: dict) -> BoundingBox:
    return BoundingBox(
        x0=Decimal(data["x0"]),
        y0=Decimal(data["y0"]),
        x1=Decimal(data["x1"]),
        y1=Decimal(data["y1"]),
    )


def _codes(values: Iterable[str]) -> tuple[ReasonCode, ...]:
    """Look each stored code back up by value.

    `ReasonCode(value)` is an enum lookup, not construction -- but the class
    has a four-argument `__new__` for its attached metadata, so a checker
    reads the one-argument call as a constructor missing three arguments.
    `_by_value` does the lookup explicitly and raises a readable error for a
    code this version does not know, which is what a stored record from a
    later version would produce.
    """
    return tuple(_by_value(v) for v in values)


def _by_value(value: str) -> ReasonCode:
    for code in ReasonCode:
        if code.value == value:
            return code
    raise ValueError(
        f"{value!r} is not a reason code this version knows. A record written "
        "by a later version is not one this one can read back safely."
    )


def _evidence(data: dict | None) -> Evidence | None:
    if data is None:
        return None
    return Evidence(
        page_number=data["page_number"],
        matched_text=data["matched_text"],
        bounding_box=_box(data["bounding_box"]) if data.get("bounding_box") else None,
        detector=data["detector"],
    )


def _metadata(data: dict) -> DetectedMetadata:
    fields = {
        name: DetectedField(
            name=f["name"],
            value=f["value"],
            required=f["required"],
            state=ConfirmationState(f["state"]),
            evidence=_evidence(f.get("evidence")),
            derived_from=f.get("derived_from"),
        )
        for name, f in data["fields"].items()
    }
    return DetectedMetadata(fields=fields)


def _page(data: dict) -> PageProfile:
    geometry = data["geometry"]
    return PageProfile(
        geometry=PageGeometry(
            page_number=geometry["page_number"],
            width=Decimal(geometry["width"]),
            height=Decimal(geometry["height"]),
            rotation=geometry["rotation"],
        ),
        kind=PageKind(data["kind"]),
        character_count=data["character_count"],
        image_count=data["image_count"],
        image_boxes=tuple(_box(b) for b in data["image_boxes"]),
    )


def _parsed(data: dict) -> ParsedValue:
    return ParsedValue(
        raw_value=data["raw_value"],
        value=_decimal(data["value"]),
        sign_source=SignSource(data["sign_source"]),
        locale_used=NumberLocale(data["locale_used"]),
        unit_marker=UnitMarker(data["unit_marker"]),
        currency_symbol=data["currency_symbol"],
        decimals=data["decimals"],
        footnote_markers=tuple(data["footnote_markers"]),
        reason_codes=_codes(data["reason_codes"]),
        note=data["note"],
    )


def _confidence(data: dict) -> Confidence:
    return Confidence(
        score=Decimal(data["score"]),
        passed=tuple(EvidenceCheck(v) for v in data["passed"]),
        failed=tuple(EvidenceCheck(v) for v in data["failed"]),
    )


def _table(data: dict) -> RawTable:
    return RawTable(
        id=data["id"],
        document_id=data["document_id"],
        page_number=data["page_number"],
        bounding_box=_box(data["bounding_box"]),
        cells=tuple(
            RawCell(
                row=c["row"],
                column=c["column"],
                text=c["text"],
                bounding_box=_box(c["bounding_box"]),
            )
            for c in data["cells"]
        ),
        row_count=data["row_count"],
        column_count=data["column_count"],
        header_row=data["header_row"],
        repeated_header_rows=tuple(data["repeated_header_rows"]),
        caption=data["caption"],
        split_across_pages=data["split_across_pages"],
        row_labels=tuple(data.get("row_labels", ())),
    )


def _location(data: dict) -> SourceLocation:
    return SourceLocation(
        id=data["id"],
        document_id=data["document_id"],
        page_number=data["page_number"],
        bounding_box=_box(data["bounding_box"]),
        raw_text=data["raw_text"],
        table_id=data["table_id"],
        row_label=data["row_label"],
        column_label=data["column_label"],
    )


def _decision(data: dict | None) -> ReviewDecision | None:
    if data is None:
        return None
    return ReviewDecision(
        action=data["action"],
        actor=data["actor"],
        reason=data["reason"],
        at=_dt(data["at"]),
        previous_value=_decimal(data["previous_value"]),
        new_value=_decimal(data["new_value"]),
    )


def _fact(data: dict) -> ReportedFact:
    return ReportedFact(
        id=data["id"],
        document_id=data["document_id"],
        source_location_id=data["source_location_id"],
        raw_label=data["raw_label"],
        raw_value=data["raw_value"],
        parsed=_parsed(data["parsed"]),
        period_label=data["period_label"],
        scope=Scope(data["scope"]),
        confidence=_confidence(data["confidence"]),
        reason_codes=_codes(data["reason_codes"]),
        verification_status=FactVerificationState(data["verification_status"]),
        corrected_value=_decimal(data["corrected_value"]),
        resolutions=tuple(
            Resolution(
                code=_by_value(r["code"]),
                actor=r["actor"],
                note=r["note"],
                at=_dt(r["at"]),
            )
            for r in data["resolutions"]
        ),
        decision=_decision(data["decision"]),
        mapping_codes=_codes(data.get("mapping_codes", ())),
        mapping_notes=tuple(data.get("mapping_notes", ())),
        period_start=_date(data["period_start"]),
        period_end=_date(data["period_end"]),
        instant_date=_date(data["instant_date"]),
        segment=data["segment"],
        reviewer_id=data["reviewer_id"],
    )


def _mapping(data: dict) -> FactMapping:
    return FactMapping(
        id=data["id"],
        reported_fact_id=data["reported_fact_id"],
        canonical_code=data["canonical_code"],
        mapping_type=MappingType(data["mapping_type"]),
        reviewer_note=data["reviewer_note"],
        origin=Origin(data["origin"]),
        sign_normalization=SignNormalization(data["sign_normalization"]),
        allocation_amount=_decimal(data["allocation_amount"]),
        allocation_basis=data["allocation_basis"],
        approved_by=data["approved_by"],
        approved_at=_dt(data["approved_at"]) if data["approved_at"] else None,
        proposal_score=_decimal(data["proposal_score"]),
        proposal_rule=data["proposal_rule"],
    )


def _mapping_set(data: dict | None) -> MappingSet | None:
    if data is None:
        return None
    return MappingSet(
        version=data["version"],
        created_at=_dt(data["created_at"]),
        created_by=data["created_by"],
        reason=data["reason"],
        mappings=tuple(_mapping(m) for m in data["mappings"]),
        supersedes=data["supersedes"],
    )


def _document(data: dict) -> SourceDocument:
    return SourceDocument(
        id=data["id"],
        company_id=data["company_id"],
        immutable_hash=data["immutable_hash"],
        original_filename=data["original_filename"],
        sanitized_filename=data["sanitized_filename"],
        mime_type=data["mime_type"],
        byte_size=data["byte_size"],
        page_count=data["page_count"],
        pdf_version=data["pdf_version"],
        uploaded_at=_dt(data["uploaded_at"]),
        extraction_status=JobState(data["extraction_status"]),
        verification_status=DocumentVerificationState(data["verification_status"]),
        metadata=_metadata(data["metadata"]),
        pages=tuple(_page(p) for p in data["pages"]),
        storage_path=data["storage_path"],
        duplicate_of=data["duplicate_of"],
        scan_notes=tuple(data["scan_notes"]),
    )


def result_from_jsonable(payload: dict) -> ExtractionResult:
    """Rebuild an `ExtractionResult` from what `save()` wrote."""
    return ExtractionResult(
        document=_document(payload["document"]),
        tables=tuple(_table(t) for t in payload["tables"]),
        locations=tuple(_location(item) for item in payload["locations"]),
        facts=tuple(_fact(f) for f in payload["facts"]),
        audit=tuple(
            AuditEvent(
                id=e["id"],
                at=_dt(e["at"]),
                actor=e["actor"],
                action=e["action"],
                entity_type=e["entity_type"],
                entity_id=e["entity_id"],
                detail=e["detail"],
            )
            for e in payload["audit"]
        ),
        job_history=tuple(payload["job_history"]),
        mappings=_mapping_set(payload.get("mappings")),
    )
