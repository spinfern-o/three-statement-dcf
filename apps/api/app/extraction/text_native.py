"""Items 30, 32 and 33: text-native extraction, geometry, tables and facts.

Specification 10.7 ("extract embedded text AND coordinates"), 10.9 ("preserve
the original page number for every text span and table cell"), 10.14-10.15
(source map and raw-versus-normalized tables), 10.19 (columns with different
dates), 10.23 (consolidated versus segment), 10.25 (raw strings before
parsing).

Three choices worth stating, because each could reasonably have gone the other
way:

**Tables are found by text position, not by ruling lines.** MuPDF's default
table strategy follows drawn lines. Financial statements are typically ruled
only under the header and above a total, so a line-based strategy reads one
page as a single two-row table. The text strategy clusters by the x-positions
of the printed text, which is how a reader identifies the columns too.

**A row whose value cells are all empty produces no facts.** That is the
section heading -- `ASSETS`, `Operating activities` -- not a line item whose
values are missing. `docs/source-policy.md` §6 draws exactly this distinction:
an empty cell is `BLANK_CELL` and goes to review; a cell absent from the table
entirely creates nothing to review. One value present and another empty is the
first case, and the empty one becomes a fact with `BLANK_CELL`.

**A row label is read from the page, not stitched from cells.** A wide
statement title can put a column boundary in the middle of the label column,
and then "Net cash provided by operating activities" arrives as two cells:
`"Net cash provided by oper"` and `"ating activities"`. Taking column 0 alone
truncates it silently -- the number is still right, the label is still
plausible, and the mapping proposal quietly fails to match.

Stitching the fragments does not work either, and the reason is worth
recording. The table extractor strips each cell, so a split landing on a space
("Purchases of property and" + "equipment") loses it, while a split landing
mid-word ("Depreciation and amortiza" + "tion") must NOT gain one. Neither
join is right for both. So the label is re-read from the page over the
rectangle the label columns occupy, which is the text as printed, spaces and
all.

**Every fact inherits the document's unconfirmed metadata as blocking codes.**
`SCALE_UNCONFIRMED` and `CURRENCY_UNCONFIRMED` sit on every fact until a
reviewer confirms those fields (10.11-10.13). A fact extracted from a document
whose scale is unknown is not a number yet -- it is a number times one
thousand, or not.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pymupdf

from model.numeric import D

from ..core.config import DEFAULT_REVIEW_THRESHOLD
from .geometry import BoundingBox
from .metadata import DetectedMetadata
from .pages import PageKind, PageProfile
from .parsing import NumberLocale, SignSource, parse_reported_value
from .reasons import EvidenceCheck, ReasonCode, score_confidence
from .records import RawCell, RawTable, ReportedFact, Scope, SourceLocation

#: How far above a table to look for its caption.
CAPTION_REACH = 70

_YEAR = re.compile(r"^(?:FY\s*)?((?:19|20)\d{2})\s*(?:[AE])?$", re.IGNORECASE)
_DATE_LABEL = re.compile(
    r"(?i)((?:19|20)\d{2})\s*$"  # any label ending in a year: "December 31, 2025"
)
#: Labels that name a basis rule 1.7 forbids mixing with an annual column.
_OTHER_BASIS = re.compile(
    r"(?i)\b(?:Q[1-4]|quarter|three\s+months|six\s+months|nine\s+months|YTD|TTM|LTM|interim)\b"
)

#: Every four-digit year anywhere in a header, used only to detect that a
#: header names more than one. See `normalize_period_label`.
_ANY_YEAR = re.compile(r"(?:19|20)\d{2}")

#: A year followed by a qualifier: `2024 (restated)`, `2024 (unaudited)`,
#: `2024*`. The qualifier is what makes it interesting -- see
#: `normalize_period_label`.
_QUALIFIED_YEAR = re.compile(r"^(?:FY\s*)?(?:19|20)\d{2}\s*(?:[(\[*\u2020\u2021].*)$")

_SCOPE_WORDS = (
    (re.compile(r"(?i)\bconsolidated\b|\bkonzern"), Scope.CONSOLIDATED),
    (re.compile(r"(?i)\bsegment\b|\bby\s+segment\b"), Scope.SEGMENT),
    (re.compile(r"(?i)\bparent\s+company\b|\bcompany\s+only\b|\bstandalone\b"), Scope.PARENT),
)


def normalize_period_label(text: str) -> tuple[str | None, bool]:
    """Return (label, mixes_basis). `None` means the header is not a period.

    A bare year, `FY2025` and `2025A` all normalize to `2025`. A full date is
    kept as printed and normalized to its year for the label, because the
    exact date range still depends on the fiscal year-end (see `records.py`).
    """
    value = " ".join(text.split())
    if not value:
        return None, False
    if _OTHER_BASIS.search(value):
        return value, True
    # **A header naming two different years names neither.** `_DATE_LABEL`
    # below is anchored at the END, so that it can read "December 31, 2024" as
    # 2024 -- and it read a merged header cell "2025 2024" as 2024 too, which
    # labelled the 2025 column's values with the prior year. Silently, with no
    # reason code: the figures were right, the year was wrong, and nothing on
    # the page said so.
    #
    # Column headers merge into one cell from ordinary PDF geometry, so this
    # is not exotic. It was found by building the 22.3.f restatement fixture,
    # where "2025" and "2024 (restated)" landed in a single cell.
    #
    # The header is kept VERBATIM rather than resolved, so a reviewer sees
    # what the cell actually said, and `PERIOD_AMBIGUOUS` blocks the fact
    # until they resolve it (1.7, 10.19, 10.24). The value is preserved; only
    # the guess is refused.
    if len(set(_ANY_YEAR.findall(value))) > 1:
        return value, True
    # **A qualified year is a period, and the qualifier is the point.**
    # `2024 (restated)`, `2024 (unaudited)`, `2024*` -- all ordinary in a
    # filing, and all returned None before, which meant the column was not a
    # period column and every figure under it was silently dropped. A whole
    # year of comparatives vanishing without a reason code is worse than a
    # wrong one: nothing on the screen says anything is missing.
    #
    # Kept verbatim and flagged rather than resolved to the bare year, because
    # the qualifier may change what the column MEANS. "2024 (restated)" and
    # "2024" are different readings of one period, which is 22.3.f's whole
    # subject, and a reviewer confirms which is which (1.7, 10.24).
    if _QUALIFIED_YEAR.match(value):
        return value, True
    match = _YEAR.match(value)
    if match:
        return match.group(1), False
    match = _DATE_LABEL.search(value)
    if match and len(value) <= 40:
        return match.group(1), False
    return None, False


def _caption_for(page: pymupdf.Page, box: BoundingBox) -> str:
    """The nearest text above a table, used for 10.23's scope detection."""
    lines: list[tuple[float, str]] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line.get("spans", [])).strip()
            if not text:
                continue
            _, y0, _, y1 = line["bbox"]
            if float(box.y0) - CAPTION_REACH <= y1 <= float(box.y0) + 1:
                lines.append((y0, text))
    lines.sort()
    return " | ".join(text for _, text in lines)


def _scope_from(caption: str) -> Scope:
    for pattern, scope in _SCOPE_WORDS:
        if pattern.search(caption):
            return scope
    return Scope.UNDETERMINED


def extract_tables(
    doc: pymupdf.Document,
    profiles: tuple[PageProfile, ...],
    *,
    document_id: str,
) -> tuple[RawTable, ...]:
    """Find every table, keeping the raw cells and their geometry. 10.14, 10.15."""
    tables: list[RawTable] = []
    for profile in profiles:
        if profile.kind not in (PageKind.TEXT_NATIVE, PageKind.MIXED):
            continue
        page = doc[profile.page_number - 1]
        found = page.find_tables(horizontal_strategy="text", vertical_strategy="text")
        for order, table in enumerate(found.tables):
            tables.append(_build_table(page, table, document_id, profile, order))

    return tuple(_mark_splits(tables))


def _build_table(page, table, document_id: str, profile: PageProfile, order: int) -> RawTable:
    rows = table.extract()
    cells: list[RawCell] = []
    for r, row in enumerate(rows):
        geometry = table.rows[r].cells if r < len(table.rows) else []
        for c, text in enumerate(row):
            box = geometry[c] if c < len(geometry) else None
            if box is None:
                continue
            cells.append(
                RawCell(
                    row=r,
                    column=c,
                    text=(text or "").replace("\n", " ").strip(),
                    bounding_box=BoundingBox.from_parser(box),
                )
            )

    header_row = _find_header_row(rows)
    repeated = _repeated_headers(rows, header_row)
    row_labels = _read_row_labels(page, table, rows, header_row)
    box = BoundingBox.from_parser(table.bbox)
    # The caption is whatever names this table: text printed above it, plus any
    # rows the text strategy swept in above the header. A statement title sits
    # close enough to the first column that it usually lands inside the table's
    # own bounding box, so looking only above it finds nothing.
    above = _caption_for(page, box)
    # Join a row's cells with nothing, for the same reason labels are: a title
    # split by a spurious column boundary is one text run, and "CONSOLIDATED
    # STA" + "TEMENTS OF CASH FLOWS" is only the caption it should be when the
    # pieces are put back without a separator between them.
    inside = " | ".join(
        stitched
        for index, row in enumerate(rows)
        if header_row is not None and index < header_row
        for stitched in [" ".join("".join(cell or "" for cell in row).split())]
        if stitched
    )
    caption = " | ".join(part for part in (above, inside) if part)

    return RawTable.create(
        document_id=document_id,
        page_number=profile.page_number,
        bounding_box=box,
        cells=tuple(cells),
        row_count=len(rows),
        column_count=max((len(r) for r in rows), default=0),
        header_row=header_row,
        repeated_header_rows=repeated,
        caption=caption or f"(no caption above table {order + 1})",
        row_labels=row_labels,
    )


def _read_row_labels(page, table, rows, header_row) -> tuple[str, ...]:
    """Re-read each row's label from the page over its label columns."""
    first_value = _first_value_column(rows, header_row)
    labels: list[str] = []
    for index in range(len(rows)):
        geometry = table.rows[index].cells if index < len(table.rows) else []
        boxes = [box for box in geometry[:first_value] if box]
        if not boxes:
            labels.append("")
            continue
        rect = pymupdf.Rect(
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        labels.append(" ".join(page.get_textbox(rect).split()))
    return tuple(labels)


def _first_value_column(rows, header_row) -> int:
    """The leftmost column whose header is a period. Everything left is label."""
    if header_row is None or header_row >= len(rows):
        return 1
    for column, cell in enumerate(rows[header_row]):
        if column and normalize_period_label(cell or "")[0]:
            return column
    return 1


def _find_header_row(rows) -> int | None:
    """The first row whose non-label cells are period headings. 10.19."""
    for index, row in enumerate(rows):
        periods = [normalize_period_label(cell or "")[0] for cell in row[1:]]
        if sum(1 for p in periods if p) >= 1 and not (row[0] or "").strip():
            return index
        if sum(1 for p in periods if p) >= 2:
            return index
    return None


def _repeated_headers(rows, header_row: int | None) -> tuple[int, ...]:
    """Rows inside the body identical to the header. 10.15."""
    if header_row is None:
        return ()
    header = [(c or "").strip() for c in rows[header_row]]
    return tuple(
        i
        for i, row in enumerate(rows)
        if i != header_row and [(c or "").strip() for c in row] == header
    )


def _mark_splits(tables: list[RawTable]) -> list[RawTable]:
    """Flag a table continued from the previous page. 22.3.h.

    The test is deliberately conservative: a table with no header row of its
    own, on the page after a table with the same column count, is a
    continuation. Anything less specific would flag every headerless block.
    """
    out: list[RawTable] = []
    for index, table in enumerate(tables):
        previous = tables[index - 1] if index else None
        continued = bool(
            previous
            and table.header_row is None
            and previous.header_row is not None
            and table.page_number == previous.page_number + 1
            and table.column_count == previous.column_count
        )
        out.append(replace(table, split_across_pages=continued))
    return out


def build_facts(
    tables: tuple[RawTable, ...],
    profiles: tuple[PageProfile, ...],
    metadata: DetectedMetadata,
    *,
    document_id: str,
    locale: NumberLocale = NumberLocale.UNKNOWN,
    review_threshold=D(DEFAULT_REVIEW_THRESHOLD),
) -> tuple[tuple[SourceLocation, ...], tuple[ReportedFact, ...]]:
    """Turn raw table cells into located, parsed, scored facts. 10.25-10.30."""
    by_page = {p.page_number: p for p in profiles}
    document_codes = _document_level_codes(metadata)

    locations: list[SourceLocation] = []
    facts: list[ReportedFact] = []

    for table in tables:
        if table.header_row is None:
            continue
        headers = _column_periods(table)
        if not headers:
            continue
        scope = _scope_from(table.caption)
        profile = by_page.get(table.page_number)

        for row in range(table.header_row + 1, table.row_count):
            if row in table.repeated_header_rows:
                continue
            label, label_box = _row_label(table, row, headers)
            value_cells = {c: table.cell(row, c) for c in headers}
            if all(cell is None or not cell.text for cell in value_cells.values()):
                continue  # a section heading, not a line with missing values

            for column, (period, mixes_basis) in headers.items():
                cell = value_cells.get(column)
                if cell is None:
                    continue
                location, fact = _fact_from_cell(
                    table=table,
                    cell=cell,
                    label=label,
                    label_box=label_box or cell.bounding_box,
                    period=period,
                    mixes_basis=mixes_basis,
                    scope=scope,
                    profile=profile,
                    document_id=document_id,
                    document_codes=document_codes,
                    locale=locale,
                    review_threshold=review_threshold,
                )
                locations.append(location)
                facts.append(fact)

    return tuple(locations), tuple(facts)


def _row_label(table: RawTable, row: int, headers: dict) -> tuple[str, BoundingBox | None]:
    """The label read from the page, and the box the label columns occupy."""
    first_value_column = min(headers) if headers else 1
    label = table.row_labels[row] if row < len(table.row_labels) else ""
    boxes = []
    for column in range(first_value_column):
        cell = table.cell(row, column)
        if cell is not None:
            boxes.append(cell.bounding_box)
    if not boxes:
        return label, None
    box = BoundingBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )
    return label, box


def _column_periods(table: RawTable) -> dict[int, tuple[str, bool]]:
    headers: dict[int, tuple[str, bool]] = {}
    header_row = table.header_row
    if header_row is None:
        # No detected header row means no period columns to read. Returning
        # empty says that; indexing with None would have raised on the first
        # table whose header could not be found.
        return headers
    for column in range(1, table.column_count):
        cell = table.cell(header_row, column)
        if cell is None:
            continue
        period, mixes = normalize_period_label(cell.text)
        if period:
            headers[column] = (period, mixes)
    return headers


def _document_level_codes(metadata: DetectedMetadata) -> tuple[ReasonCode, ...]:
    """10.11-10.13: an unconfirmed scale or currency blocks every fact under it."""
    codes: list[ReasonCode] = []
    scale = metadata.fields.get("displayed_scale")
    currency = metadata.fields.get("reporting_currency")
    if scale is None or not scale.confirmed:
        codes.append(ReasonCode.SCALE_UNCONFIRMED)
    if currency is None or not currency.confirmed:
        codes.append(ReasonCode.CURRENCY_UNCONFIRMED)
    return tuple(codes)


def _fact_from_cell(
    *,
    table: RawTable,
    cell: RawCell,
    label: str,
    label_box: BoundingBox,
    period: str,
    mixes_basis: bool,
    scope: Scope,
    profile: PageProfile | None,
    document_id: str,
    document_codes: tuple[ReasonCode, ...],
    locale: NumberLocale,
    review_threshold,
) -> tuple[SourceLocation, ReportedFact]:
    header_cell = None if table.header_row is None else table.cell(table.header_row, cell.column)
    location = SourceLocation.create(
        document_id=document_id,
        page_number=table.page_number,
        bounding_box=cell.bounding_box,
        raw_text=cell.text,
        table_id=table.id,
        row_label=label or None,
        column_label=header_cell.text if header_cell else None,
    )

    parsed = parse_reported_value(cell.text, locale=locale)

    codes = list(parsed.reason_codes)
    codes.extend(document_codes)
    if mixes_basis:
        codes.append(ReasonCode.PERIOD_AMBIGUOUS)
    if scope is Scope.UNDETERMINED:
        codes.append(ReasonCode.SCOPE_AMBIGUOUS)
    if scope is Scope.SEGMENT:
        pass  # recorded on the fact itself; not a defect
    if table.split_across_pages:
        codes.append(ReasonCode.TABLE_SPLIT_ACROSS_PAGES)
    if table.repeated_header_rows:
        codes.append(ReasonCode.HEADER_REPEATED)
    if profile is not None and profile.geometry.is_rotated:
        codes.append(ReasonCode.PAGE_ROTATED)
    if profile is not None and profile.kind is PageKind.MIXED:
        codes.append(ReasonCode.IMAGE_REGION_NOT_EXTRACTED)

    confidence = score_confidence(
        {
            # No OCR path exists (decision 2.3.c), so this always holds today.
            EvidenceCheck.TEXT_LAYER: True,
            EvidenceCheck.IN_TABLE: True,
            EvidenceCheck.ROW_LABEL: bool(label.strip()),
            EvidenceCheck.COLUMN_PERIOD: bool(period) and not mixes_basis,
            EvidenceCheck.PARSED: parsed.is_parsed,
            EvidenceCheck.SIGN_EXPLICIT: parsed.sign_source is not SignSource.UNRESOLVED,
            EvidenceCheck.CLEAN_NUMERIC: not parsed.footnote_markers,
            EvidenceCheck.TABLE_INTACT: not table.split_across_pages
            and not table.repeated_header_rows,
        }
    )

    # 10.29: a sub-threshold score forces review on its own. The threshold is
    # configuration, not a constant -- see core/config.py.
    if confidence.needs_review(review_threshold):
        codes.append(ReasonCode.LOW_CONFIDENCE)

    fact = ReportedFact.create(
        document_id=document_id,
        source_location_id=location.id,
        raw_label=label,
        raw_value=cell.text,
        parsed=parsed,
        period_label=period,
        scope=scope,
        confidence=confidence,
        reason_codes=_dedupe(codes),
        segment=table.caption if scope is Scope.SEGMENT else None,
    )
    return location, fact


def _dedupe(codes) -> tuple[ReasonCode, ...]:
    seen: list[ReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.append(code)
    return tuple(seen)
