"""Item 41: statement and page bookmarks.

Specification 7.3.b asks the Source Room for "a page index and
statement/footnote bookmarks". 10.14 asks for a source map covering the income
statement, balance sheet, cash flow statement, statement of equity and the
relevant notes.

The bookmarks here are **derived from what was extracted, not from a reading
of the document**: a page carrying a table whose caption names a statement is
bookmarked as that statement. That is a proposal for the reviewer, in exactly
the sense 11.10 means by "system-proposed" -- and the confirmed source map,
the one the model relies on, is the reviewer's, which Phase 5 owns.

Saying which it is matters. A bookmark that looks authoritative and was
guessed from a caption is the kind of thing rule 1.3 is about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..extraction.records import ExtractionResult

#: Caption patterns, most specific first. A caption matching none of them is
#: not bookmarked rather than being filed under a guess.
STATEMENT_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("Income statement", re.compile(r"(?i)statements?\s+of\s+(operations|income|profit)|income\s+statement|profit\s+and\s+loss|gewinn")),
    ("Balance sheet", re.compile(r"(?i)balance\s+sheets?|statements?\s+of\s+financial\s+position|bilanz")),
    ("Cash flow statement", re.compile(r"(?i)statements?\s+of\s+cash\s+flows?|cash\s+flow\s+statement|kapitalfluss")),
    ("Statement of equity", re.compile(r"(?i)statements?\s+of\s+(changes\s+in\s+)?(stockholders|shareholders|owners)'?\s+equity")),
    ("Comprehensive income", re.compile(r"(?i)comprehensive\s+income")),
    ("Segment information", re.compile(r"(?i)segment\s+information|by\s+segment")),
    ("Notes", re.compile(r"(?i)notes\s+to\s+the\s+(consolidated\s+)?financial\s+statements")),
)


@dataclass(frozen=True)
class Bookmark:
    page_number: int
    label: str
    #: The caption the label was derived from, so the reviewer can judge it.
    evidence: str
    #: Always "system-proposed" today. 11.10's other value needs Phase 5.
    origin: str = "system-proposed"


def bookmarks(result: ExtractionResult) -> tuple[Bookmark, ...]:
    """One bookmark per (page, statement) a table caption names."""
    seen: set[tuple[int, str]] = set()
    found: list[Bookmark] = []
    for table in result.tables:
        for label, pattern in STATEMENT_PATTERNS:
            if pattern.search(table.caption):
                key = (table.page_number, label)
                if key not in seen:
                    seen.add(key)
                    found.append(
                        Bookmark(
                            page_number=table.page_number,
                            label=label,
                            evidence=table.caption[:120],
                        )
                    )
                break
    return tuple(sorted(found, key=lambda b: (b.page_number, b.label)))


def unmapped_statements(result: ExtractionResult) -> tuple[str, ...]:
    """The 10.14 sections no bookmark covers. An empty source map is a gap."""
    found = {b.label for b in bookmarks(result)}
    required = ("Income statement", "Balance sheet", "Cash flow statement")
    return tuple(label for label in required if label not in found)
