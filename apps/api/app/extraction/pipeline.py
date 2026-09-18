"""The ingestion pipeline: items 26 to 38, in the order they must happen.

The order is not arbitrary. `docs/source-policy.md` §2 requires the security
scan run **before the file is written to storage**, and 10.2 requires the hash
be computed **on the bytes as received**, before any processing. So:

    1  signature and size          bytes only, no parser          10.1, 20.8
    2  hash                        bytes as received              10.2
    3  duplicate                   against this company's documents 10.3
    4  parse and structural scan   MuPDF; refuses encryption etc.  10.4
    5  page-count limit            20.8
    6  STORE                       write-once, verified            1.12, 10.5
    7  classify pages              image-only refuses here         10.6, 2.3.c
    8  detect metadata             all UNCONFIRMED                 10.10, 10.11
    9  extract tables and geometry                                 10.7, 10.9, 10.14
    10 parse cells into facts      raw string retained             10.25-10.28

Every step is a job transition, so the history is the record of what happened
and where it stopped (10.33). A refusal is returned, not raised, at this level:
the caller wants the job history for a refused upload just as much as for a
successful one, and losing it inside an exception would be the opposite of an
audit trail.

**Isolation (20.10).** PDF parsing runs in this process. The specification
requires it run outside the web process, which is a deployment concern -- this
function is the unit that would be moved to a worker, and nothing in it holds
a request, a session or a database handle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import pymupdf

from ..core.config import IngestionConfig
from ..core.errors import (
    TOO_MANY_PAGES,
    UNREADABLE_PDF,
    IngestionRefusal,
)
from .hashing import check_duplicate
from .jobs import DocumentVerificationState, ExtractionJob, JobState, utc_now
from .metadata import detect_metadata
from .pages import classify_pages
from .parsing import NumberLocale
from .records import AuditEvent, ExtractionResult, SourceDocument
from .scan import scan_document
from .signature import detect_mime_type, validate_signature
from .storage import SourceStore
from .text_native import build_facts, extract_tables


@dataclass(frozen=True)
class IngestionOutcome:
    """What happened, whether or not it worked."""

    job: ExtractionJob
    result: ExtractionResult | None = None
    refusal: IngestionRefusal | None = None

    @property
    def accepted(self) -> bool:
        return self.result is not None

    def describe(self) -> str:
        lines = [self.job.describe()]
        if self.refusal is not None:
            lines.append(f"REFUSED: {self.refusal}")
        return "\n".join(lines)


def ingest(
    data: bytes,
    *,
    original_filename: str,
    company_id: str,
    config: IngestionConfig,
    store: SourceStore,
    existing_id_for_hash: Callable[[str], str | None] = lambda _h: None,
    allow_linked_duplicate: bool = False,
    link_reason: str | None = None,
    actor: str = "owner",
) -> IngestionOutcome:
    """Run one document through Phase 3. Never raises for a policy refusal."""
    job = ExtractionJob.start()
    audit: list[AuditEvent] = []
    doc = None

    try:
        job = job.advance(JobState.VALIDATING, "checking signature, size and duplicates")

        signature = validate_signature(data, max_bytes=config.max_bytes)
        duplicate = check_duplicate(
            data,
            existing_id_for_hash=existing_id_for_hash,
            allow_linked_duplicate=allow_linked_duplicate,
            link_reason=link_reason,
        )

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise IngestionRefusal(
                UNREADABLE_PDF,
                f"the file carries a PDF signature but its structure could not "
                f"be parsed: {exc}",
            ) from exc

        scan = scan_document(doc)

        if doc.page_count > config.max_pages:
            raise IngestionRefusal(
                TOO_MANY_PAGES,
                f"the document has {doc.page_count} pages; the limit is {config.max_pages}",
            )

        stored = store.store(data, original_filename=original_filename)
        job = job.advance(
            JobState.STORED,
            f"stored {stored.byte_size:,} bytes at {stored.path.name} "
            f"({'already present' if stored.already_present else 'written'})",
        )
        audit.append(
            AuditEvent.create(
                actor=actor,
                action="upload",
                entity_type="SourceDocument",
                entity_id=stored.immutable_hash,
                detail=(
                    f"{original_filename!r} accepted as PDF {signature.pdf_version}, "
                    f"{stored.byte_size:,} bytes, SHA-256 {stored.immutable_hash}"
                ),
            )
        )

        job = job.advance(JobState.CLASSIFYING, "detecting text-native, image-only and mixed pages")
        profiles = classify_pages(doc, min_chars=config.min_chars_for_text_native)

        job = job.advance(JobState.EXTRACTING, "reading text, geometry, tables and facts")
        metadata = detect_metadata(doc)

        document = SourceDocument.create(
            company_id=company_id,
            immutable_hash=stored.immutable_hash,
            original_filename=stored.original_filename,
            sanitized_filename=stored.sanitized_filename,
            mime_type=detect_mime_type(data),
            byte_size=stored.byte_size,
            page_count=doc.page_count,
            pdf_version=signature.pdf_version,
            uploaded_at=utc_now(),
            extraction_status=JobState.EXTRACTING,
            verification_status=DocumentVerificationState.UNCONFIRMED,
            metadata=metadata,
            pages=profiles,
            storage_path=str(stored.path),
            duplicate_of=duplicate.existing_document_id if duplicate.linked else None,
            scan_notes=scan.notes,
        )

        tables = extract_tables(doc, profiles, document_id=document.id)
        locations, facts = build_facts(
            tables, profiles, metadata, document_id=document.id, locale=NumberLocale.UNKNOWN
        )

        job = job.advance(
            JobState.EXTRACTED,
            f"{len(tables)} table(s), {len(facts)} fact(s), "
            f"{sum(1 for f in facts if f.blocking_codes)} needing review",
            document_id=document.id,
        )
        audit.append(
            AuditEvent.create(
                actor="system",
                action="extract",
                entity_type="SourceDocument",
                entity_id=document.id,
                detail=(
                    f"{len(facts)} fact(s) extracted from {len(tables)} table(s); "
                    f"every field of the document's metadata is UNCONFIRMED (10.11)"
                ),
            )
        )

        result = ExtractionResult(
            document=replace(document, extraction_status=JobState.EXTRACTED),
            tables=tables,
            locations=locations,
            facts=facts,
            audit=tuple(audit),
            job_history=tuple(t.describe() for t in job.history),
        )
        return IngestionOutcome(job=job, result=result)

    except IngestionRefusal as refusal:
        job = job.advance(
            JobState.REFUSED,
            f"{refusal.reason.code}: {refusal.detail}",
            refusal_code=refusal.reason.code,
        )
        return IngestionOutcome(job=job, refusal=refusal)
    except Exception as exc:  # a failure, not a refusal -- see jobs.py
        job = job.advance(JobState.FAILED, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if doc is not None:
            doc.close()
