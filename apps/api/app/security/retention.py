"""Item 151: 2.6.b's retention, 2.6.c's deletion, and the flag Phase 2 raised.

Three decisions govern this, all confirmed:

  2.6.b  **Indefinite until the owner deletes.** Single user, private, own
         data -- a retention clock would delete the owner's own work to
         satisfy a policy nobody imposed. So there is no expiry job here, and
         its absence is a decision rather than an omission.
  2.6.c  **An administrator may permanently delete**, with 20.18's explicit
         confirmation. The owner is the only user; a delete they cannot
         perform is data they cannot control.
  1.12   **Never overwrite an uploaded source document.** Deletion removes; it
         does not overwrite in place, and nothing here writes over evidence.

**The interaction `security-model.md` flagged, answered.** It asked what
happens to the `AuditEvent` rows that reference a deleted document, and named
three options: tombstone, cascade, or refuse while references exist.

This tombstones, and the reasoning is the point. Cascading deletes the record
of the deletion along with everything else, which is the one entry somebody
will later need. Refusing means a document can never be deleted, because it
always has audit events -- ingestion writes one. A tombstone keeps the
identifier resolvable, so an audit entry saying "rejected fact X on document Y"
still has a Y to point at, and that Y says when it was deleted, by whom, and
why.

**What a tombstone deliberately does not keep**: the PDF bytes, the extracted
values, the company name. The whole point of a permanent deletion is that the
confidential content is gone (20.1). What remains is the hash, the identifier,
the filename, and the deletion's own audit trail -- enough to answer "what
happened to that document" and not enough to reconstruct any of it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

#: Where tombstones live, beside the records they replace.
TOMBSTONE_DIRNAME = "tombstones"

#: 2.6.b. Named so a reader looking for a retention period finds the decision
#: rather than an absence they have to interpret.
RETENTION = (
    "Indefinite until the owner deletes (2.6.b). There is no expiry job: a "
    "retention clock would delete the owner's own work to satisfy a policy "
    "nobody imposed."
)


class DeletionRefused(Exception):
    """The deletion did not happen, and this says what was missing."""


@dataclass(frozen=True)
class Tombstone:
    """What remains after a permanent deletion."""

    document_id: str
    immutable_hash: str
    sanitized_filename: str
    deleted_at: str
    deleted_by: str
    reason: str
    #: What was removed, counted rather than kept.
    facts_removed: int = 0
    audit_events_kept: int = 0

    def describe(self) -> str:
        return (
            f"{self.document_id} ({self.sanitized_filename}) was permanently "
            f"deleted on {self.deleted_at} by {self.deleted_by}: {self.reason}"
        )


def tombstone_path(storage_root: str | Path, document_id: str) -> Path:
    return Path(storage_root) / TOMBSTONE_DIRNAME / f"{document_id}.json"


def load_tombstone(storage_root: str | Path, document_id: str) -> Tombstone | None:
    path = tombstone_path(storage_root, document_id)
    if not path.exists():
        return None
    return Tombstone(**json.loads(path.read_text()))


def tombstones(storage_root: str | Path) -> tuple[Tombstone, ...]:
    directory = Path(storage_root) / TOMBSTONE_DIRNAME
    if not directory.exists():
        return ()
    return tuple(
        Tombstone(**json.loads(path.read_text())) for path in sorted(directory.glob("*.json"))
    )


def check_confirmation(result, typed: str, reason: str) -> None:
    """20.18: the confirmation names the specific object.

    Typing the filename back, rather than clicking a button that says Yes. A
    button is the same gesture whatever it is attached to, and the gesture is
    what muscle memory performs; a filename is a thing the person has to have
    read. No default focus, no pre-filled field -- the form has neither.
    """
    expected = result.document.sanitized_filename
    if typed.strip() != expected:
        raise DeletionRefused(
            f"To delete this permanently, type its filename exactly: "
            f"{expected!r}. Nothing was deleted."
        )
    if not reason.strip():
        raise DeletionRefused(
            "A permanent deletion needs a written reason (9.14, 10.33). Nothing was deleted."
        )


def delete_permanently(
    result,
    storage_root: str | Path,
    *,
    actor: str,
    reason: str,
    typed_filename: str,
    store=None,
    repository=None,
) -> Tombstone:
    """Remove the bytes and the record; leave a tombstone. 2.6.c, 20.18."""
    check_confirmation(result, typed_filename, reason)

    root = Path(storage_root)
    document = result.document

    stone = Tombstone(
        document_id=document.id,
        immutable_hash=document.immutable_hash,
        sanitized_filename=document.sanitized_filename,
        deleted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        deleted_by=actor,
        reason=reason.strip(),
        facts_removed=len(result.facts),
        audit_events_kept=len(result.audit),
    )

    # The tombstone is written FIRST. A crash between the two leaves a
    # tombstone for a document that still exists, which is a visible
    # inconsistency somebody can fix; the other order leaves a deleted
    # document with no record of the deletion, which is the one that cannot
    # be reconstructed.
    path = tombstone_path(root, document.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(stone), indent=2, sort_keys=True))

    if store is not None:
        bytes_path = store.path_for(document.immutable_hash)
        if bytes_path.exists():
            bytes_path.unlink()
    if repository is not None:
        record = Path(repository.root) / f"{document.id}.json"
        if record.exists():
            record.unlink()

    # Renders are derivatives of the bytes and must not outlive them.
    renders = root / "renders"
    if renders.exists():
        for cached in renders.rglob(f"{document.immutable_hash}-*"):
            cached.unlink()

    return stone
