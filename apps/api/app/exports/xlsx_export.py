"""Item 140: the workbook, 21.1's sixteen tabs, and one thing XLSX cannot do.

**A spreadsheet cell cannot hold this model's numbers**, and it is worse than
the usual telling. Excel stores every number as an IEEE 754 double, so a value
needing more than about fifteen significant digits is rounded on the way in --
by the file format, before any program has done anything wrong. On top of that,
openpyxl writes each double into the sheet XML as `"%.16g"`, which is *narrower
than the double it came from*: a double's shortest round-tripping form needs up
to seventeen significant digits, so some values the format could have carried
are lost by the writer as well.

On the fixture model that is around one numeric cell in eight, and they are not
obscure: a forecast balance-sheet line carrying a division's full residual is
exactly the shape that overflows both.

4.11 promises 0.0001% accuracy end to end and 21.8 requires the export to equal
the website. This export cannot keep both promises inside a numeric cell, so it
does not pretend to:

  - the cell holds the double, because a reader wants to sum and chart it;
  - a cell note carries the **exact decimal string** wherever the double is not
    the value, so nothing is lost, only moved;
  - those cells are styled `Inexact` and counted on the Cover tab.

The alternative -- writing the exact string into the cell -- produces a
workbook whose every figure is text, which sums to zero. Disclosing the loss
beats either silently taking it or breaking the file to avoid it.

**20.13 binds here too, and openpyxl makes it sharper than the clause sounds.**
Assigning a string beginning with `=` to a cell does not store text: openpyxl
sets the cell's data type to *formula*. A filing whose printed label begins
with `=` would arrive in the workbook as something Excel evaluates on open. The
same `neutralize` the CSV uses is applied to text cells here, which also keeps
the two formats agreeing, as 21.8 requires.

**21.2: hardcodes and formulas are distinguishable by more than colour.** The
modelling convention is blue for an input and black for a calculation, and
colour alone fails WCAG 1.4.1. So each numeric cell also carries a *named cell
style* -- `Hardcode`, `Calculated`, `Inexact` -- which Excel shows by name in
its style gallery and which survives a monochrome print, and the Cover tab
carries the legend in words.
"""

from __future__ import annotations

import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, NamedStyle, PatternFill
from openpyxl.utils import get_column_letter

from .csv_export import neutralize
from .gather import gather
from .tables import CALCULATED, Cell, ExportModel, Table

#: 21.2's convention, stated once. Blue is the modelling world's "somebody
#: typed this"; black is "the model computed it".
HARDCODE_COLOUR = "FF0000CC"
CALCULATED_COLOUR = "FF000000"
INEXACT_COLOUR = "FF8A4B00"

#: An Excel sheet name may not exceed 31 characters or contain : \\ / ? * [ ].
#: 21.1's longest is well inside that, and a test asserts it stays so.
SHEET_NAME_LIMIT = 31

LEGEND = (
    ("Hardcode (blue)", "A figure somebody supplied: reported by the filing, or entered as an assumption."),
    ("Calculated (black)", "A figure this model computed from others."),
    ("Inexact (brown, noted)", "The exact value needs more precision than a spreadsheet number holds. The cell note carries it in full."),
    ("Empty with a note", "No value exists. Absent is not zero (rule 1.3), and the note says why."),
)


def _styles(workbook: Workbook) -> "dict[str, NamedStyle]":
    """Named styles, so the distinction survives without colour."""
    made = {}
    for name, colour in (
        ("Hardcode", HARDCODE_COLOUR),
        ("Calculated", CALCULATED_COLOUR),
        ("Inexact", INEXACT_COLOUR),
    ):
        style = NamedStyle(name=name)
        style.font = Font(color=colour, italic=(name == "Inexact"))
        made[name] = style
        workbook.add_named_style(style)
    header = NamedStyle(name="HeaderRow")
    header.font = Font(bold=True)
    header.fill = PatternFill("solid", fgColor="FFEFEFEF")
    header.alignment = Alignment(wrap_text=True, vertical="top")
    workbook.add_named_style(header)
    made["HeaderRow"] = header
    return made


#: How openpyxl serializes a float into the sheet XML. Not a guess: it is
#: `"%.16g" % value` in `openpyxl/compat/strings.py`, and it is *narrower* than
#: a double -- a double's shortest round-tripping repr needs up to 17
#: significant digits, so a number the format could have held is still lost on
#: the way out. Asserting against `repr` instead would have reported values
#: safe that the file does not contain.
WORKBOOK_DIGITS = 16


def survives_the_workbook(value: Decimal) -> bool:
    """True when the exact decimal is recoverable from what the file stores.

    The question is about the whole round trip, and neither representation
    answers it alone -- that is F-29's lesson, and both wrong answers were
    tried before this one:

      `Decimal(repr(float(v))) == v` asks whether a double holds the value and
      says nothing about what gets written. It reports 153895.30421504256 safe;
      the file contains 153895.3042150426, a different number.

      `Decimal("%.16g" % float(v)) == v` asks what the *string* looks like. It
      reports 0.085 lost, because the string is "0.08500000000000001" -- which
      parses back to the same double and displays as 0.085. Nothing was lost.

    So: take the value to a double, write it the way openpyxl writes it, read
    that string back as a double, and ask whether the result is still the
    number we had.
    """
    try:
        written = "%.*g" % (WORKBOOK_DIGITS, float(value))
        return Decimal(repr(float(written))) == value
    except (OverflowError, ValueError):
        return False


def _write_cell(sheet, row: int, column: int, cell: Cell, styles) -> bool:
    """Write one cell. Returns True when precision had to be moved to a note."""
    target = sheet.cell(row=row, column=column)
    if cell.value is None:
        # 20.13 binds here as much as it binds the CSV, and openpyxl makes it
        # sharper than the clause sounds: assigning a string that begins with
        # "=" does not store text, it sets the cell's data type to FORMULA.
        # A filing whose printed label starts with "=" would arrive in the
        # workbook as something Excel evaluates. `neutralize` is the CSV's own
        # function, used here so the two formats also cannot disagree (21.8).
        target.value = neutralize(cell)[0]
        if cell.note:
            target.comment = Comment(cell.note, "Three-Statement DCF")
        return False
    exact = survives_the_workbook(cell.value)
    target.value = float(cell.value)
    if not exact:
        target.style = "Inexact"
        target.comment = Comment(
            f"Exact value: {cell.value}\n\n"
            "A spreadsheet number is an IEEE 754 double, written into the file "
            f"at {WORKBOOK_DIGITS} significant digits, and cannot hold this "
            "one. The cell above is what the file stores; the line above is "
            "what the model holds (4.2).",
            "Three-Statement DCF",
        )
        return True
    target.style = "Calculated" if cell.is_calculated else "Hardcode"
    if cell.note:
        target.comment = Comment(cell.note, "Three-Statement DCF")
    return False


def _write_table(workbook: Workbook, table: Table, styles) -> int:
    sheet = workbook.create_sheet(title=table.title[:SHEET_NAME_LIMIT])
    row = 1
    if table.note:
        sheet.cell(row=row, column=1, value=table.note)
        sheet.cell(row=row, column=1).alignment = Alignment(wrap_text=False)
        row += 1
    if table.unavailable:
        sheet.cell(row=row, column=1, value=f"THIS TABLE IS EMPTY: {table.note}")
        row += 1
    row += 1

    for index, column in enumerate(table.columns, start=1):
        header = sheet.cell(row=row, column=index, value=column.title)
        header.style = "HeaderRow"
        sheet.column_dimensions[get_column_letter(index)].width = max(
            12, min(40, len(column.title) + 4)
        )
    sheet.freeze_panes = sheet.cell(row=row + 1, column=2)

    inexact = 0
    for offset, data_row in enumerate(table.rows, start=1):
        for index, cell in enumerate(data_row, start=1):
            if _write_cell(sheet, row + offset, index, cell, styles):
                inexact += 1
    return inexact


def build_workbook(model: ExportModel) -> Workbook:
    """21.1's sixteen tabs, in 21.1's order."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    styles = _styles(workbook)

    inexact = 0
    for table in model.tables:
        inexact += _write_table(workbook, table, styles)

    # 21.3 belongs on the first sheet a reader opens, and the legend with it.
    cover = workbook["Cover"]
    row = cover.max_row + 2
    cover.cell(row=row, column=1, value="How to read this workbook (21.2)").font = Font(bold=True)
    for offset, (name, meaning) in enumerate(LEGEND, start=1):
        cover.cell(row=row + offset, column=1, value=name)
        cover.cell(row=row + offset, column=2, value=meaning)
    note_row = row + len(LEGEND) + 2
    cover.cell(
        row=note_row, column=1,
        value=(
            f"{inexact} cell(s) hold a value a spreadsheet number cannot "
            "represent exactly. Each is styled Inexact and carries its exact "
            "value in a cell note. Nothing was rounded away silently."
        ),
    )
    cover.cell(row=note_row + 1, column=1, value=f"Model version: {model.version_id}")
    cover.cell(row=note_row + 2, column=1, value=f"Generated at: {model.generated_at}")

    # Section 25 and 20.19: the disclaimer and the model limitations belong in
    # the export, not only in the report. A workbook is the artefact that gets
    # forwarded, and it is the one most likely to be read on its own.
    limits_row = note_row + 4
    cover.cell(
        row=limits_row, column=1, value="What this model does not say (Section 25, 20.19)"
    ).font = Font(bold=True)
    for offset, line in enumerate(model.limitations, start=1):
        cover.cell(row=limits_row + offset, column=1, value=line).alignment = Alignment(
            wrap_text=True, vertical="top"
        )
    cover.column_dimensions["A"].width = 34
    cover.column_dimensions["B"].width = 80
    return workbook


def to_bytes(model: ExportModel) -> bytes:
    buffer = io.BytesIO()
    build_workbook(model).save(buffer)
    return buffer.getvalue()


def export_xlsx(result, scenarios=None, scenario_id: str = "base", *, now=None) -> bytes:
    return to_bytes(gather(result, scenarios, scenario_id, now=now))
