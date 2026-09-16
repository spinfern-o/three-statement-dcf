"""Ingestion refusals, and the code family that names them.

Specification Section 17 gives validation checks the codes `VAL-017-001`
through `VAL-017-030` (see docs/validation-policy.md). Section 10 -- ingestion
-- has no code family, because Phase 2 item 23 defined error codes for checks
and the ingestion rules were still unimplemented. This module defines that
family on the same pattern:

    ING-010-NN   the Section 10 rule the refusal enforces
    ING-020-NN   the Section 20 (security and privacy) rule

A refusal is not a bug. It is the specified outcome, and Section 1's rules
are almost all refusals: the whole point is that the system stops rather than
proceeding on something it cannot justify. Every refusal therefore carries the
rule number that required it, so a reviewer can look up why the upload was
rejected instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RefusalCode:
    """One reason an upload or an extraction is refused."""

    code: str
    rule: str
    summary: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code} ({self.rule}): {self.summary}"


# --- Section 10: ingestion -------------------------------------------------

NOT_A_PDF = RefusalCode(
    "ING-010-01",
    "10.1",
    "the file is not a PDF by signature",
)
TRUNCATED_PDF = RefusalCode(
    "ING-010-02",
    "10.1",
    "the PDF has no end-of-file marker and is incomplete",
)
DUPLICATE_DOCUMENT = RefusalCode(
    "ING-010-03",
    "10.3",
    "a document with this SHA-256 already exists for this company",
)
ENCRYPTED_PDF = RefusalCode(
    "ING-010-04",
    "10.4",
    "the PDF is encrypted and cannot be read without a password",
)
ACTIVE_CONTENT = RefusalCode(
    "ING-010-05",
    "10.4",
    "the PDF carries active content (JavaScript, launch action, or embedded file)",
)
UNREADABLE_PDF = RefusalCode(
    "ING-010-06",
    "10.1",
    "the PDF structure could not be parsed",
)
IMAGE_ONLY_PAGE = RefusalCode(
    "ING-010-08",
    "10.8 / decision 2.3.c",
    "the document contains image-only pages and OCR is out of scope",
)
NO_TEXT_LAYER = RefusalCode(
    "ING-010-07",
    "10.7",
    "the document has no extractable text layer",
)
OVERWRITE_ATTEMPT = RefusalCode(
    "ING-010-12",
    "1.12",
    "an uploaded source document may never be overwritten",
)

# --- Section 20: security and privacy --------------------------------------

FILE_TOO_LARGE = RefusalCode(
    "ING-020-08",
    "20.8",
    "the file exceeds the configured byte-size limit",
)
TOO_MANY_PAGES = RefusalCode(
    "ING-020-08",
    "20.8",
    "the file exceeds the configured page-count limit",
)
UNSAFE_FILENAME = RefusalCode(
    "ING-020-11",
    "20.11",
    "the filename cannot be sanitized to a safe stored value",
)


class IngestionRefusal(Exception):
    """The system declined to ingest a document, and names the rule.

    Carries the refusal code so an API layer can map it to a status code and a
    reviewer can look the rule up, rather than receiving prose alone.
    """

    def __init__(self, reason: RefusalCode, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.code} ({reason.rule}): {detail}")


class IllegalTransition(Exception):
    """An extraction job was asked to move between states that do not connect."""
