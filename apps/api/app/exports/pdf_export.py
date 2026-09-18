"""Item 141: the PDF valuation report, and the nine sections 21.6 requires.

21.6 lists them: valuation date, source coverage, assumptions, forecast, DCF,
sensitivities, checks, limitations, model version. Each is a section here, each
is present whether or not it has content, and a section with nothing in it says
why -- an omitted section reads as "nothing to report", which is the opposite
of what an unbuilt stage means.

**Written with PyMuPDF, which this repository already depends on.** Phase 3
uses it to read filings; it writes them too. A reporting library would be a
fifth dependency for one file format, and the thing being drawn here is text in
boxes.

**The report is a claim, so it carries what a reader needs to challenge it.**
The model version identifies exactly which model this is, the checks section
carries every outstanding check rather than a summary count, and the
limitations section is not optional -- a valuation report whose limitations
section is empty is the one to distrust.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from .gather import gather
from .tables import ExportModel, Table

PAGE_WIDTH, PAGE_HEIGHT = 595.0, 842.0   # A4 portrait, in points
MARGIN = 54.0
BODY = "helv"
BOLD = "hebo"
MONO = "cour"

TITLE_SIZE = 18.0
HEADING_SIZE = 12.0
BODY_SIZE = 9.0
SMALL_SIZE = 7.5
LEADING = 1.35

#: 21.6's nine, in its order. `(heading, table name or "")`.
SECTIONS = (
    ("Valuation date and basis", ""),
    ("Source coverage", "sources"),
    ("Assumptions", "assumptions"),
    ("Forecast", "forecast_is"),
    ("DCF", "dcf"),
    ("Sensitivities", "sensitivity"),
    ("Checks", "checks"),
    ("Limitations", ""),
    ("Model version", ""),
)

#: How many rows of a table the report prints before saying where the rest is.
#: A report is a summary; the workbook and the JSON carry every row, and a
#: forty-page PDF of the raw facts is one nobody reads.
ROW_LIMIT = 24


@dataclass
class Cursor:
    """Where the next line goes, and the page it goes on."""

    document: pymupdf.Document
    page: pymupdf.Page
    y: float

    def space(self, needed: float) -> None:
        if self.y + needed > PAGE_HEIGHT - MARGIN - 18:
            self.page = self.document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            self.y = MARGIN


def _wrap(text: str, width: float, font: str, size: float) -> list[str]:
    """Greedy wrap on measured widths, because a character count is not one."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        for word in words[1:]:
            candidate = f"{line} {word}"
            if pymupdf.get_text_length(candidate, fontname=font, fontsize=size) <= width:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def _text(cursor: Cursor, text: str, *, font: str = BODY, size: float = BODY_SIZE,
          indent: float = 0.0, gap: float = 0.0) -> None:
    width = PAGE_WIDTH - 2 * MARGIN - indent
    for line in _wrap(text, width, font, size):
        cursor.space(size * LEADING)
        cursor.page.insert_text(
            (MARGIN + indent, cursor.y + size), line, fontname=font, fontsize=size
        )
        cursor.y += size * LEADING
    cursor.y += gap


def _heading(cursor: Cursor, text: str) -> None:
    cursor.space(HEADING_SIZE * 3)
    cursor.y += 10
    cursor.page.insert_text(
        (MARGIN, cursor.y + HEADING_SIZE), text, fontname=BOLD, fontsize=HEADING_SIZE
    )
    cursor.y += HEADING_SIZE * LEADING
    cursor.page.draw_line(
        pymupdf.Point(MARGIN, cursor.y + 2),
        pymupdf.Point(PAGE_WIDTH - MARGIN, cursor.y + 2),
        width=0.5,
    )
    cursor.y += 8


def _table(cursor: Cursor, table: Table, *, limit: int = ROW_LIMIT) -> None:
    """A table, or the reason it is empty. Never nothing."""
    if table.unavailable or not table.rows:
        _text(
            cursor,
            table.note or "This table could not be built, and no reason was recorded.",
            font=BODY, size=BODY_SIZE, gap=4,
        )
        return

    available = PAGE_WIDTH - 2 * MARGIN
    count = len(table.columns)
    # The first column is a label and needs the room; the rest share what is
    # left. Equal columns put "Total revenue" on three lines and 12.0 on one.
    first = min(available * 0.34, available / count * 2) if count > 1 else available
    others = (available - first) / (count - 1) if count > 1 else 0.0
    widths = [first] + [others] * (count - 1)

    def row(values, font: str, size: float) -> None:
        cells = [
            _wrap(str(value), widths[index] - 4, font, size)
            for index, value in enumerate(values)
        ]
        height = max(len(lines) for lines in cells) * size * LEADING
        cursor.space(height + 2)
        x = MARGIN
        for index, lines in enumerate(cells):
            for offset, line in enumerate(lines):
                cursor.page.insert_text(
                    (x, cursor.y + size + offset * size * LEADING),
                    line, fontname=font, fontsize=size,
                )
            x += widths[index]
        cursor.y += height + 2

    row([column.title for column in table.columns], BOLD, SMALL_SIZE)
    cursor.page.draw_line(
        pymupdf.Point(MARGIN, cursor.y), pymupdf.Point(PAGE_WIDTH - MARGIN, cursor.y),
        width=0.3,
    )
    cursor.y += 2

    for data_row in table.rows[:limit]:
        row(
            [cell.display if not cell.absent else "(absent)" for cell in data_row],
            BODY, SMALL_SIZE,
        )
    if len(table.rows) > limit:
        _text(
            cursor,
            f"{len(table.rows) - limit} further row(s) are in the workbook and "
            "the JSON export, which carry every row at full precision.",
            size=SMALL_SIZE, gap=4,
        )
    cursor.y += 4


def _cover(cursor: Cursor, model: ExportModel) -> None:
    cursor.page.insert_text(
        (MARGIN, cursor.y + TITLE_SIZE), "DCF valuation report",
        fontname=BOLD, fontsize=TITLE_SIZE,
    )
    cursor.y += TITLE_SIZE * LEADING + 6
    _text(cursor, model.company or model.document_id, font=BOLD, size=HEADING_SIZE, gap=6)
    _text(
        cursor,
        f"Scenario {model.scenario_id}. "
        f"Reporting currency {model.currency or '(unconfirmed)'}, "
        f"displayed scale {model.units or '(unconfirmed)'}.",
        gap=2,
    )
    _text(cursor, f"Generated at {model.generated_at} (21.7).", gap=2)
    _text(cursor, f"Model version {model.version_id}", font=MONO, size=SMALL_SIZE, gap=6)
    _text(
        cursor,
        "Private model - not for distribution. This is not investment advice "
        "and not a fairness opinion.",
        font=BOLD, gap=4,
    )


def _valuation_basis(cursor: Cursor, model: ExportModel) -> None:
    _text(
        cursor,
        f"Valuation date: {model.valuation_date or 'no valuation was built'}.",
        gap=4,
    )
    _text(
        cursor,
        "16.11 lets a valuation be discounted year-end, mid-year, or from an "
        "exact date. Only the third has a calendar valuation date; the other "
        "two are defined relative to the last actual period end, and this "
        "report names the convention rather than inventing a date for it.",
        gap=2,
    )


def _limitations(cursor: Cursor, model: ExportModel) -> None:
    for line in model.limitations:
        _text(cursor, f"- {line}", indent=8, gap=1)


def _version(cursor: Cursor, model: ExportModel) -> None:
    _text(cursor, model.version_id, font=MONO, size=SMALL_SIZE, gap=4)
    _text(
        cursor,
        "21.7's identifier is a digest of what this model contains, not a "
        "counter. It was computed from:",
        gap=2,
    )
    for name, value in model.version_components:
        _text(cursor, f"- {name}: {value}", font=MONO, size=SMALL_SIZE, indent=8, gap=0)


def build_report(model: ExportModel) -> pymupdf.Document:
    document = pymupdf.open()
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    cursor = Cursor(document=document, page=page, y=MARGIN)

    _cover(cursor, model)
    for heading, table_name in SECTIONS:
        _heading(cursor, heading)
        if heading == "Valuation date and basis":
            _valuation_basis(cursor, model)
        elif heading == "Limitations":
            _limitations(cursor, model)
        elif heading == "Model version":
            _version(cursor, model)
        elif heading == "Forecast":
            for name in ("forecast_is", "forecast_bs", "forecast_cf"):
                table = model.table(name)
                _text(cursor, table.title, font=BOLD, gap=2)
                _table(cursor, table, limit=12)
        else:
            _table(cursor, model.table(table_name))

    _footers(document, model)
    return document


def _footers(document: pymupdf.Document, model: ExportModel) -> None:
    total = document.page_count
    # By index rather than by iterating the Document: pymupdf ships no type
    # information, so iterating it yields an untyped value and `insert_text`
    # below is then a call on nothing in particular.
    for index in range(1, total + 1):
        page = document[index - 1]
        page.insert_text(
            (MARGIN, PAGE_HEIGHT - MARGIN + 12),
            f"Three-Statement DCF - {model.version_id[:26]}... - "
            f"page {index} of {total} - private, not for distribution",
            fontname=BODY, fontsize=SMALL_SIZE,
        )


def to_bytes(model: ExportModel) -> bytes:
    document = build_report(model)
    document.set_metadata(
        {
            "title": f"DCF valuation report - {model.company or model.document_id}",
            "author": "spinfern-o",
            "subject": f"Model version {model.version_id}",
            "keywords": f"scenario={model.scenario_id}; generated={model.generated_at}",
            "creator": "Three-Statement DCF",
            "producer": "Three-Statement DCF",
        }
    )
    return document.tobytes()


def export_pdf(result, scenarios=None, scenario_id: str = "base", *, now=None) -> bytes:
    return to_bytes(gather(result, scenarios, scenario_id, now=now))
