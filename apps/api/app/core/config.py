"""Ingestion policy configuration.

Rule 1.4 forbids silently choosing a currency, unit, fiscal year-end, tax
rate, WACC, terminal growth, forecast period or valuation date. Everything in
this file is an *operational* limit -- how large a file may be, how many pages
-- and none of it is a financial parameter, so defaults are legitimate here in
a way they are never legitimate in `model/`.

The one value that is close to the line is `review_threshold`: specification
10.29 requires manual review for every low-confidence fact, so the threshold
decides how much review happens. 7.10 requires it be displayed on the
diagnostics page, and source-policy.md requires it be a recorded configuration
value rather than a constant buried in code. It is therefore here, named, with
its default stated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal

from model.numeric import D

#: 20.8 requires size and page-count limits. These are the defaults; a 10-K
#: with exhibits is routinely 10-20 MB and 150-300 pages, so the limits are set
#: above that rather than at it.
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_PAGES = 1000

#: A page whose text layer yields fewer than this many characters is treated as
#: having no text layer. Page numbers, headers and stray marks routinely leave a
#: handful of characters on an otherwise scanned page, so the floor is not 1.
DEFAULT_MIN_CHARS_FOR_TEXT_NATIVE = 32

#: 10.29. Facts scoring below this go to manual review. The confidence model is
#: ordinal evidence-counting, not a calibrated probability -- see
#: `extraction/reasons.py` -- so this is "at most one piece of evidence may be
#: missing", not a probability statement.
DEFAULT_REVIEW_THRESHOLD = "0.875"


@dataclass(frozen=True)
class IngestionConfig:
    """Operational limits and policy switches for ingestion."""

    storage_root: str
    max_bytes: int = DEFAULT_MAX_BYTES
    max_pages: int = DEFAULT_MAX_PAGES
    min_chars_for_text_native: int = DEFAULT_MIN_CHARS_FOR_TEXT_NATIVE
    review_threshold: Decimal = D(DEFAULT_REVIEW_THRESHOLD)

    def __post_init__(self) -> None:
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.max_pages <= 0:
            raise ValueError("max_pages must be positive")
        if not (D("0") <= self.review_threshold <= D("1")):
            raise ValueError("review_threshold must lie in [0, 1]")

    @classmethod
    def from_env(cls, storage_root: str | None = None) -> IngestionConfig:
        """Build from environment variables. Names are listed in .env.example."""
        root = storage_root or os.environ.get("INGEST_STORAGE_ROOT")
        if not root:
            raise ValueError(
                "INGEST_STORAGE_ROOT is not set. Uploaded PDFs are immutable "
                "evidence (rule 1.12); the service will not pick a directory "
                "for them."
            )
        return cls(
            storage_root=root,
            max_bytes=int(os.environ.get("INGEST_MAX_BYTES", DEFAULT_MAX_BYTES)),
            max_pages=int(os.environ.get("INGEST_MAX_PAGES", DEFAULT_MAX_PAGES)),
            min_chars_for_text_native=int(
                os.environ.get(
                    "INGEST_MIN_CHARS_FOR_TEXT_NATIVE", DEFAULT_MIN_CHARS_FOR_TEXT_NATIVE
                )
            ),
            # Read as a string, never float(): 4.2.
            review_threshold=D(
                os.environ.get("INGEST_REVIEW_THRESHOLD", DEFAULT_REVIEW_THRESHOLD),
                what="INGEST_REVIEW_THRESHOLD",
            ),
        )
