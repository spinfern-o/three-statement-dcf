"""Printable output for an ingestion run.

The same principle as `model/report.py`: show the reasoning, not just the
answer. A reviewer reading this should be able to see which page a number came
from, what it said before parsing, and exactly why anything that was not
parsed was not parsed.
"""

from __future__ import annotations

from decimal import Decimal

from .metadata import DetectedMetadata
from .pages import PageProfile
from .records import ExtractionResult, ReportedFact

WIDTH = 96


def rule(char: str = "-") -> str:
    return char * WIDTH


def heading(text: str) -> str:
    return f"\n{rule('=')}\n{text}\n{rule('=')}"


def document_block(result: ExtractionResult) -> str:
    doc = result.document
    lines = [
        heading("DOCUMENT (10.1-10.5)"),
        f"  id                 {doc.id}",
        f"  company            {doc.company_id}",
        f"  filename           {doc.sanitized_filename}",
        f"  stored as          {doc.storage_path}",
        f"  SHA-256            {doc.immutable_hash}",
        f"  MIME (signature)   {doc.mime_type}",
        f"  PDF version        {doc.pdf_version}",
        f"  size / pages       {doc.byte_size:,} bytes / {doc.page_count} pages",
        f"  uploaded           {doc.uploaded_at.isoformat()}",
        f"  extraction status  {doc.extraction_status.value}",
        f"  verification       {doc.verification_status.value}",
    ]
    if doc.duplicate_of:
        lines.append(f"  linked duplicate of {doc.duplicate_of} (10.3)")
    for note in doc.scan_notes:
        lines.append(f"  scan note          {note}")
    return "\n".join(lines)


def pages_block(pages: tuple[PageProfile, ...]) -> str:
    lines = [heading("PAGES (10.6)"), f"  {'page':>5}  {'kind':13} {'chars':>7} {'images':>7}  rotation"]
    for page in pages:
        lines.append(
            f"  {page.page_number:>5}  {page.kind.value:13} {page.character_count:>7} "
            f"{page.image_count:>7}  {page.geometry.rotation}"
        )
    return "\n".join(lines)


def metadata_block(metadata: DetectedMetadata) -> str:
    lines = [
        heading("DETECTED METADATA (10.10-10.13)"),
        "  Every field starts UNCONFIRMED. Nothing downstream may run until each",
        "  required field is confirmed or corrected by a reviewer (10.13).",
        "",
    ]
    for field in metadata.fields.values():
        lines.append("  " + field.describe())
        if field.derived_from:
            lines.append(f"                         derived from {field.derived_from}")
    missing = metadata.unconfirmed_required
    lines.append("")
    if missing:
        lines.append(f"  {len(missing)} required field(s) still unconfirmed: {', '.join(missing)}")
    else:
        lines.append("  All required fields confirmed.")
    return "\n".join(lines)


def tables_block(result: ExtractionResult) -> str:
    lines = [heading("RAW TABLES (10.14, 10.15)")]
    for table in result.tables:
        box = table.bounding_box
        lines.append(
            f"  {table.id}  page {table.page_number}  "
            f"{table.row_count} rows x {table.column_count} cols  "
            f"header row {table.header_row}"
        )
        lines.append(f"      box    ({box.x0}, {box.y0}) - ({box.x1}, {box.y1}) pt")
        lines.append(f"      caption {table.caption[:78]}")
        if table.repeated_header_rows:
            lines.append(f"      repeated header rows: {table.repeated_header_rows} (10.15)")
        if table.split_across_pages:
            lines.append("      continued from the previous page (22.3.h)")
    return "\n".join(lines)


def facts_block(result: ExtractionResult, *, limit: int | None = None) -> str:
    lines = [
        heading("REPORTED FACTS (10.25-10.30)"),
        f"  {'line item':38} {'period':>6} {'value':>14}  {'raw':16} {'conf':>6}  codes",
        "  " + rule(),
    ]
    facts = result.facts if limit is None else result.facts[:limit]
    for fact in facts:
        lines.append("  " + _fact_line(fact))
    if limit is not None and len(result.facts) > limit:
        lines.append(f"  ... {len(result.facts) - limit} more")
    return "\n".join(lines)


def _fact_line(fact: ReportedFact) -> str:
    value = fact.value
    shown = "(no value)" if value is None else _format(value)
    codes = " ".join(c.value for c in fact.reason_codes)
    return (
        f"{fact.raw_label[:38]:38} {fact.period_label:>6} {shown:>14}  "
        f"{fact.raw_value[:16]:16} {fact.confidence.score:>6}  {codes}"
    )


def _format(value: Decimal) -> str:
    return f"{value:,}"


def review_block(result: ExtractionResult) -> str:
    blocked = result.facts_needing_review
    lines = [heading("MANUAL REVIEW REQUIRED (10.29, 10.30)")]
    if not blocked:
        lines.append("  No fact carries a blocking reason code.")
        return "\n".join(lines)

    lines.append(
        f"  {len(blocked)} of {len(result.facts)} fact(s) cannot proceed without a reviewer.\n"
    )
    for fact in blocked:
        location = result.location(fact.source_location_id)
        where = location.cite() if location else "(location missing)"
        lines.append(f"  {fact.raw_label or '(no label)'} - {fact.period_label} - {where}")
        lines.append(f"      printed as {fact.raw_value!r}")
        for code in fact.blocking_codes:
            lines.append(f"      {code.value} ({code.rule}): {code.summary}")
        if fact.parsed.note:
            lines.append(f"      {fact.parsed.note}")
        lines.append("")
    return "\n".join(lines)


def confidence_block(result: ExtractionResult) -> str:
    buckets: dict[str, int] = {}
    for fact in result.facts:
        buckets[str(fact.confidence.score)] = buckets.get(str(fact.confidence.score), 0) + 1
    lines = [
        heading("CONFIDENCE (10.28)"),
        "  The score is the fraction of eight named evidence conditions the fact",
        "  satisfies. It is ordinal, not a probability -- see extraction/reasons.py.",
        "",
    ]
    for score in sorted(buckets, reverse=True):
        lines.append(f"  {score}  {buckets[score]:>4} fact(s)")
    worst = min(result.facts, key=lambda f: f.confidence.score, default=None)
    if worst is not None and worst.confidence.failed:
        lines.append(f"\n  Lowest-scoring fact: {worst.raw_label!r} {worst.period_label}")
        lines.append("  " + worst.confidence.explain().replace("\n", "\n  "))
    return "\n".join(lines)


def audit_block(result: ExtractionResult) -> str:
    lines = [heading("AUDIT LOG (10.33, 9.14)")]
    for event in result.audit:
        lines.append("  " + event.describe())
    return "\n".join(lines)


def job_block(history: tuple[str, ...]) -> str:
    lines = [heading("EXTRACTION JOB (item 29)")]
    lines.extend("  " + entry for entry in history)
    return "\n".join(lines)
