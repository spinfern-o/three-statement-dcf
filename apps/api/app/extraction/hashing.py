"""Item 27: the immutable hash, and duplicate detection.

Specification 10.2: "Calculate and store a SHA-256 hash." 10.3: "Refuse exact
duplicate uploads unless the user explicitly creates a linked duplicate
record."

source-policy.md §2 fixes two details the specification leaves implicit:

  * The hash is computed **on the bytes as received**, before any processing.
    Hashing after a normalization pass would hash the system's opinion of the
    document rather than the document.
  * It is the document's identity for the life of the system. Check
    `VAL-017-001` rehashes the stored bytes and compares.

The duplicate rule is scoped to the company, not globally. Two companies
uploading the same industry PDF is not the error 10.3 guards against; the same
filing uploaded twice to one company is.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from ..core.errors import DUPLICATE_DOCUMENT, IngestionRefusal

#: Read size for streaming. 1 MiB keeps a 300-page filing to a few hundred
#: iterations without holding two copies of a large file in memory.
CHUNK = 1024 * 1024


def sha256_hex(data: bytes) -> str:
    """The SHA-256 of the bytes as received, lowercase hex. 10.2."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    """The SHA-256 of a file on disk, streamed. Used to re-verify storage."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class DuplicateCheck:
    """The outcome of 10.3 for one upload."""

    immutable_hash: str
    #: The id of the existing document with the same hash, when there is one.
    existing_document_id: str | None
    #: True when this upload is being recorded as an explicit linked duplicate.
    linked: bool = False
    #: Required when `linked` -- 10.3 permits the linked record only as an
    #: explicit action, and source-policy.md §2 requires it be recorded with a
    #: reason in the audit log.
    link_reason: str | None = None

    @property
    def is_duplicate(self) -> bool:
        return self.existing_document_id is not None


def check_duplicate(
    data: bytes,
    *,
    existing_id_for_hash: Callable[[str], str | None],
    allow_linked_duplicate: bool = False,
    link_reason: str | None = None,
) -> DuplicateCheck:
    """Hash the upload and apply 10.3.

    `existing_id_for_hash` is a lookup over documents already held for this
    company. It is passed in rather than imported so that this module has no
    dependency on how records are stored.

    Refuses a duplicate by default. A linked duplicate is permitted only when
    the caller asks for it explicitly AND supplies a reason -- an unexplained
    linked duplicate is the silent overwrite rule 1.12 forbids, wearing a
    different name.
    """
    digest = sha256_hex(data)
    existing = existing_id_for_hash(digest)

    if existing is None:
        return DuplicateCheck(immutable_hash=digest, existing_document_id=None)

    if not allow_linked_duplicate:
        raise IngestionRefusal(
            DUPLICATE_DOCUMENT,
            f"SHA-256 {digest} is already stored for this company as document "
            f"{existing}. Use the existing document, or create a linked "
            f"duplicate record explicitly and state why (10.3).",
        )

    reason = (link_reason or "").strip()
    if not reason:
        raise IngestionRefusal(
            DUPLICATE_DOCUMENT,
            f"a linked duplicate of document {existing} was requested without a "
            f"reason. 10.3 permits the linked record only as an explicit "
            f"action, and it is recorded with its reason in the audit log.",
        )

    return DuplicateCheck(
        immutable_hash=digest,
        existing_document_id=existing,
        linked=True,
        link_reason=reason,
    )
