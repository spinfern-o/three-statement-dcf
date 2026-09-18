"""Specification 10.4: scan the file using the approved security process.

**What this is not.** It is not an antivirus scan. `docs/security-model.md`
§20.9 records that the scanner is an implementation choice rather than a
Section 2 decision, and no scanner is available in this environment. Claiming
otherwise would be worse than the gap.

**What this is.** A structural scan of the parsed document for the things that
have no business in a financial filing and are how a PDF attacks a reader:

  * **Encryption.** Refused. A document that cannot be read cannot be
    extracted, and a half-read encrypted file yields an empty extraction that
    looks like an empty filing (ING-010-04).
  * **Active content** -- JavaScript, an OpenAction, additional actions, or a
    launch link. Refused. 20.11 requires document content never be executed;
    this system does not execute it, but a filing that carries executable
    content is not the document it claims to be, and it will eventually be
    opened in a reader that does execute it (ING-010-05).
  * **Embedded files.** Refused for the same reason.
  * **Repair.** Recorded, not refused. MuPDF silently repairs damaged
    cross-reference tables; that is usually benign and always worth knowing,
    because a repaired document may not be the document the filer produced.

Everything found is reported, not just the first thing, so a reviewer sees the
whole picture rather than fixing one issue at a time.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from ..core.errors import ACTIVE_CONTENT, ENCRYPTED_PDF, IngestionRefusal


@dataclass(frozen=True)
class ScanResult:
    """What the structural scan found."""

    findings: tuple[str, ...] = ()
    #: Recorded rather than refused.
    notes: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.findings


def scan_document(doc: pymupdf.Document) -> ScanResult:
    """Inspect a parsed document. Raises `IngestionRefusal` on anything blocking."""
    if doc.needs_pass or doc.is_encrypted:
        raise IngestionRefusal(
            ENCRYPTED_PDF,
            "the PDF is password-protected. Supply an unprotected copy of the "
            "filing -- an encrypted file cannot be extracted, and extracting "
            "it partially would look like a short filing rather than a locked one.",
        )

    findings: list[str] = []
    notes: list[str] = []

    catalog = doc.pdf_catalog()
    for key, description in (
        ("OpenAction", "an action that runs when the document is opened"),
        ("AA", "additional actions attached to the document"),
    ):
        kind, value = doc.xref_get_key(catalog, key)
        if kind != "null":
            findings.append(f"/{key}: {description} ({kind} {value})")

    kind, value = doc.xref_get_key(catalog, "Names")
    if kind != "null":
        # /Names is ordinary on its own -- named destinations live there. Only
        # the JavaScript entry under it is active content.
        names_keys = _names_keys(doc, value)
        if "JavaScript" in names_keys:
            findings.append("/Names /JavaScript: document-level JavaScript")
        else:
            notes.append(f"/Names present with entries: {', '.join(names_keys) or '(none read)'}")

    embedded = doc.embfile_count()
    if embedded:
        findings.append(f"{embedded} embedded file(s) attached to the document")

    for number in range(doc.page_count):
        for link in doc[number].get_links():
            if link.get("kind") == pymupdf.LINK_LAUNCH:
                findings.append(f"a launch action on page {number + 1}: {link.get('file')!r}")

    if doc.is_repaired:
        notes.append(
            "MuPDF repaired this file's cross-reference table while opening it. "
            "The extraction is from the repaired structure, which may not be "
            "byte-identical to what the filer produced. The stored original is "
            "untouched."
        )

    if findings:
        raise IngestionRefusal(
            ACTIVE_CONTENT,
            "the PDF carries content that does not belong in a filing: "
            + "; ".join(findings)
            + ". This system does not execute document content (20.11), but a "
            "reader opening the same file might.",
        )

    return ScanResult(findings=(), notes=tuple(notes))


def _names_keys(doc: pymupdf.Document, value: str) -> list[str]:
    """Read the key names under the catalog's /Names dictionary, if reachable."""
    try:
        xref = int(value.split()[0]) if value and value.split()[0].isdigit() else None
    except (ValueError, IndexError):  # pragma: no cover - defensive
        return []
    if xref is None:
        return []
    try:
        return list(doc.xref_get_keys(xref))
    except Exception:  # pragma: no cover - a malformed /Names is not our business
        return []
