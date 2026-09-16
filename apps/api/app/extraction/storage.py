"""Items 28 and 38: safe storage, and proof the original PDF is unchanged.

Specification 1.12: "Never overwrite an uploaded source document." 20.11
requires filenames be sanitized. source-policy.md §2 makes object storage
write-once: "A corrected document is a NEW SourceDocument, linked to the old
one, never a replacement."

Three mechanisms carry that, and none of them is a convention a future caller
could forget:

  1. **Content addressing.** The stored path is derived from the SHA-256, not
     from the filename. Two different documents cannot collide on a path, and
     the same document written twice writes the same bytes to the same path.
  2. **`O_EXCL` on create.** The file is created with an exclusive open, which
     the kernel refuses if the path exists. There is no code path in this
     module that opens an existing stored file for writing -- not "we check
     first", which races, but "the operating system will not do it".
  3. **Read-only mode after write.** `0o444`. This is defence in depth, not a
     guarantee -- a process running as root ignores it -- so the guarantee is
     `verify()`, which re-hashes the stored bytes and is what check
     `VAL-017-001` runs. Mode 0444 stops the ordinary accident; the hash
     catches the rest.

Item 38 ("confirm the original PDF remains unchanged") is then not a claim but
a measurement: `store()` re-reads what it wrote and re-hashes it before
returning, and `verify()` re-hashes at any later time. Check `VAL-017-001` is
the same operation on a schedule.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import OVERWRITE_ATTEMPT, UNSAFE_FILENAME, IngestionRefusal
from .hashing import sha256_file, sha256_hex

#: Punctuation kept verbatim in a stored filename. Letters and digits of any
#: script are kept too (see `_is_safe_char`) -- a filing named in German or
#: Japanese is not less legitimate than one named in English, and mangling it
#: to underscores loses information for no security gain. What is removed is
#: control characters, path separators, and everything else.
_SAFE_PUNCTUATION = frozenset("._ -()[]{}',&+#@~")

MAX_FILENAME_LENGTH = 200


def _is_safe_char(ch: str) -> bool:
    """True for letters, digits, marks and the kept punctuation -- any script.

    `unicodedata.category` starting with L, N or M covers letters, numbers and
    combining marks. Control characters (category C*) are excluded by that test
    on its own, which is the property that matters: a NUL or a newline in a
    stored name is what 20.11 is about.
    """
    if ch in _SAFE_PUNCTUATION:
        return True
    return unicodedata.category(ch)[0] in {"L", "N", "M"}

#: Stored files are read-only to their owner and everyone else.
STORED_MODE = 0o444


def sanitize_filename(original: str) -> str:
    """Return a safe display filename, or refuse. 10.5, 20.11.

    The result is never used to build a path -- `path_for()` does that from the
    hash -- so this is about what is safe to *store and display*, not about
    path traversal. Both are handled: traversal is impossible by construction,
    and the name is still stripped of separators so that a stored name can
    never be mistaken for a location.
    """
    if original is None:
        raise IngestionRefusal(UNSAFE_FILENAME, "no filename was supplied")

    # Normalize first: NFC collapses the decomposed forms that let two visually
    # identical names differ byte for byte.
    name = unicodedata.normalize("NFC", original)
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join(ch if _is_safe_char(ch) else "_" for ch in name).strip(" .")
    name = re.sub(r"_{2,}", "_", name)

    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, suffix = name.rpartition(".")
        suffix = (dot + suffix) if dot else ""
        name = stem[: MAX_FILENAME_LENGTH - len(suffix)] + suffix

    if not name or name in {".", ".."}:
        raise IngestionRefusal(
            UNSAFE_FILENAME,
            f"the filename {original!r} has no characters left after "
            f"sanitization (20.11)",
        )
    return name


@dataclass(frozen=True)
class StoredDocument:
    """Where the bytes went, and proof they arrived intact."""

    immutable_hash: str
    path: Path
    byte_size: int
    #: The filename as uploaded, retained as data (10.5). Never a path.
    original_filename: str
    sanitized_filename: str
    #: True when the bytes were already present and nothing was written.
    already_present: bool


class SourceStore:
    """A write-once, content-addressed store for uploaded PDFs."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def path_for(self, immutable_hash: str) -> Path:
        """The stored location for a hash.

        Two levels of fan-out keeps any one directory to roughly 256 entries
        per 65,536 documents, which matters on filesystems that degrade with
        very large directories.
        """
        if not re.fullmatch(r"[0-9a-f]{64}", immutable_hash):
            raise ValueError(f"not a SHA-256 hex digest: {immutable_hash!r}")
        return self.root / immutable_hash[:2] / immutable_hash[2:4] / f"{immutable_hash}.pdf"

    def store(self, data: bytes, *, original_filename: str) -> StoredDocument:
        """Write the bytes once, verify them, and return where they went.

        Re-storing identical bytes is a no-op rather than an error: the store
        is content-addressed, so the file already there IS this file. Storing
        *different* bytes at an existing hash is impossible without a SHA-256
        collision, and is checked for anyway.
        """
        digest = sha256_hex(data)
        sanitized = sanitize_filename(original_filename)
        path = self.path_for(digest)
        path.parent.mkdir(parents=True, exist_ok=True)

        already_present = False
        try:
            # O_EXCL is the guarantee, not a convention. See the module note.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            already_present = True
            existing = sha256_file(str(path))
            if existing != digest:
                raise IngestionRefusal(
                    OVERWRITE_ATTEMPT,
                    f"{path} already holds different bytes (SHA-256 {existing}) "
                    f"than the upload being stored under that hash ({digest}). "
                    f"The store is not overwriting it (rule 1.12).",
                ) from None
        else:
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                # A partially written file is worse than no file: it would hash
                # differently and look like a corrupted original.
                path.unlink(missing_ok=True)
                raise
            os.chmod(path, STORED_MODE)

        # Item 38, measured rather than asserted.
        written = sha256_file(str(path))
        if written != digest:
            raise IngestionRefusal(
                OVERWRITE_ATTEMPT,
                f"the stored file hashes to {written}, not {digest}. The bytes "
                f"on disk are not the bytes uploaded.",
            )

        return StoredDocument(
            immutable_hash=digest,
            path=path,
            byte_size=len(data),
            original_filename=original_filename,
            sanitized_filename=sanitized,
            already_present=already_present,
        )

    def verify(self, immutable_hash: str) -> bool:
        """Re-hash the stored file. Check `VAL-017-001` (17.1)."""
        path = self.path_for(immutable_hash)
        if not path.exists():
            return False
        return sha256_file(str(path)) == immutable_hash

    def read(self, immutable_hash: str) -> bytes:
        """Read stored bytes back, refusing to return anything that has changed."""
        path = self.path_for(immutable_hash)
        data = path.read_bytes()
        if sha256_hex(data) != immutable_hash:
            raise IngestionRefusal(
                OVERWRITE_ATTEMPT,
                f"{path} no longer hashes to {immutable_hash}; the stored "
                f"document has been altered outside this store.",
            )
        return data
