"""Item 26: verify an upload is a PDF by signature, not by filename.

Specification 10.1: "Verify the upload is a PDF by MIME signature, not
filename alone." 20.8 adds size limits and 20.11 adds "never execute document
content".

Three checks run on the bytes before any parser is handed the file:

  1. The header. A PDF begins `%PDF-` at offset 0. The format tolerates
     leading junk and most readers scan the first 1024 bytes for the header,
     but this is a security boundary, so the strict reading is used: offset 0
     or refuse. A file whose header sits at offset 600 is a file with 600
     bytes of something else in front of it.
  2. The trailer. A complete PDF ends with `%%EOF`. A truncated upload
     otherwise reaches the parser and yields a partial extraction that looks
     like a short filing.
  3. The size limit (20.8).

What this is NOT: an antivirus scan. 10.4 requires "the approved security
process" and security-model.md §20.9 records that the scanner is an
implementation choice. No scanner is available in this environment, so what
runs is a *structural* scan -- encryption, active content, embedded files --
performed in `scan.py` after the document is parsed. That limitation is
recorded rather than papered over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.errors import FILE_TOO_LARGE, NOT_A_PDF, TRUNCATED_PDF, IngestionRefusal

PDF_HEADER = b"%PDF-"
PDF_EOF = b"%%EOF"

#: How far back from the end to look for `%%EOF`. The PDF specification asks
#: for it in the last 1024 bytes; incremental updates and generator comments
#: push it around, so the window is doubled.
EOF_WINDOW = 2048

_VERSION = re.compile(rb"^%PDF-(\d)\.(\d)")


@dataclass(frozen=True)
class SignatureResult:
    """What the bytes themselves say about the file."""

    pdf_version: str
    byte_size: int
    #: True when `%%EOF` is the last non-whitespace content in the file.
    eof_at_end: bool


def detect_mime_type(data: bytes) -> str:
    """Return the MIME type implied by the leading bytes.

    Deliberately narrow: this answers "is this a PDF", not "what is this".
    Anything that is not a PDF is `application/octet-stream`, because naming
    a type the system will not accept anyway adds nothing and invites the
    caller to branch on it.
    """
    if data.startswith(PDF_HEADER):
        return "application/pdf"
    return "application/octet-stream"


def validate_signature(data: bytes, *, max_bytes: int) -> SignatureResult:
    """Refuse anything that is not a complete PDF. 10.1, 20.8.

    Raises `IngestionRefusal`. Returns the version and size on success.
    """
    byte_size = len(data)
    if byte_size == 0:
        raise IngestionRefusal(NOT_A_PDF, "the uploaded file is empty (0 bytes)")
    if byte_size > max_bytes:
        raise IngestionRefusal(
            FILE_TOO_LARGE,
            f"the file is {byte_size:,} bytes; the limit is {max_bytes:,} bytes",
        )

    if not data.startswith(PDF_HEADER):
        found = data[:16]
        hint = ""
        offset = data[:4096].find(PDF_HEADER)
        if offset > 0:
            hint = (
                f" A PDF header was found at offset {offset}, so the file has "
                f"{offset} bytes of other content in front of it."
            )
        raise IngestionRefusal(
            NOT_A_PDF,
            f"the file does not begin with {PDF_HEADER!r}; it begins with {found!r}."
            f"{hint} Specification 10.1 requires the type be determined by "
            f"signature, so the filename extension is not consulted.",
        )

    match = _VERSION.match(data)
    if match is None:
        raise IngestionRefusal(
            NOT_A_PDF,
            f"the header {data[:9]!r} is not a valid PDF version marker",
        )
    version = f"{match.group(1).decode()}.{match.group(2).decode()}"

    tail = data[-EOF_WINDOW:]
    if PDF_EOF not in tail:
        raise IngestionRefusal(
            TRUNCATED_PDF,
            f"no {PDF_EOF!r} marker appears in the last {min(EOF_WINDOW, byte_size)} "
            f"bytes. The upload is incomplete or corrupt. A truncated PDF can "
            f"still be parsed, and would yield a short extraction that looks "
            f"like a short filing.",
        )

    eof_at_end = data.rstrip(b"\r\n \t\x00").endswith(PDF_EOF)
    return SignatureResult(pdf_version=version, byte_size=byte_size, eof_at_end=eof_at_end)
