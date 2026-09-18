"""Item 139: CSV, and the injection defence that must not eat a minus sign.

20.13: "Prefix spreadsheet values beginning with =, +, -, or @ when exporting
**raw text**." Those characters start a formula in Excel, LibreOffice and
Google Sheets, and the defence is to prefix an apostrophe, which they read as
"the rest is text".

The two emphasised words are load-bearing, and
[`docs/security-model.md`](../../../../docs/security-model.md) §20.13 recorded
why before any export existed.

**Applied to everything, that defence corrupts this export.** Every negative
figure in a financial model starts with `-`. Prefixing them turns `-1234.56` into the
text `'-1234.56`, which sorts as text, sums as zero, and charts as nothing --
and the reader sees plausible numbers, not an error. A defence that silently
destroys the values it protects is worse than the risk: the injection needs
somebody to open a hostile file, and this one would fire on every ordinary
export of an ordinary company having an ordinary bad year.

So the rule follows 20.13's own words -- *raw text*, and a `Decimal` is not
raw text:

**A cell is neutralized only when it is not a number.** Numeric cells are
written from `Cell.value` -- the exact Decimal -- and a Decimal cannot contain
a formula. Text cells (a label, a note, a reason a reviewer typed) are checked
against the dangerous leading characters, and only those are prefixed. A filing
whose printed label begins with `=` is the case this protects, and it is the
case worth protecting: the label came out of somebody else's PDF.

`neutralized` is reported per file so a scripted consumer can strip the prefix
rather than guess, and 21.4's data-dictionary reference is written into every
file's header comment.
"""

from __future__ import annotations

import csv
import io

from .gather import gather
from .schema import SCHEMA_VERSION
from .tables import Cell, ExportModel, Table

#: The characters a spreadsheet treats as the start of a formula.
DANGEROUS = ("=", "+", "-", "@", "\t", "\r")

#: What a neutralized cell is prefixed with. An apostrophe, because that is
#: what the three major spreadsheets read as "this is text".
PREFIX = "'"

#: 21.4. Every file names the dictionary its columns are defined in.
DICTIONARY = "docs/data-dictionary.md"


def is_dangerous(text: str) -> bool:
    """True when a spreadsheet would read this string as a formula."""
    return bool(text) and text[0] in DANGEROUS


def neutralize(cell: Cell) -> tuple[str, bool]:
    """The string to write, and whether it had to be defused.

    A cell holding a value is written from that value and is never defused: a
    Decimal's string form is digits, a sign, a point and possibly an exponent,
    none of which a spreadsheet evaluates.
    """
    if cell.value is not None:
        return str(cell.value), False
    text = cell.display
    if is_dangerous(text):
        return PREFIX + text, True
    return text, False


def header_lines(model: ExportModel, table: Table) -> list[str]:
    """21.4 and 21.7, as comment lines above the data.

    Comments rather than columns: a reader opening this in a spreadsheet wants
    the provenance visible, and a consumer parsing it wants the header row to
    be the header row. `#` is the convention every CSV reader can be told to
    skip, and `csv.reader` does not strip it, so the lines are counted here and
    the count is part of the contract.
    """
    return (
        [
            f"# {table.title} -- {model.company or model.document_id}",
            f"# Model version: {model.version_id}",
            f"# Generated at: {model.generated_at}",
            f"# Scenario: {model.scenario_id}",
            f"# Currency: {model.currency or '(unconfirmed)'}; "
            f"displayed scale: {model.units or '(unconfirmed)'}",
            f"# Column definitions: {DICTIONARY} (21.4); JSON schema version {SCHEMA_VERSION}",
            f"# A cell beginning {PREFIX} was prefixed to stop a spreadsheet "
            f"evaluating it as a formula (20.13). Numeric cells are never "
            f"prefixed.",
        ]
        + ([f"# NOTE: {table.note}"] if table.note else [])
        + ([f"# THIS TABLE IS EMPTY: {table.note}"] if table.unavailable else [])
    )


def table_to_csv(model: ExportModel, table: Table) -> str:
    """One table as one CSV file."""
    out = io.StringIO()
    for line in header_lines(model, table):
        out.write(line + "\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([column.title for column in table.columns])
    for row in table.rows:
        writer.writerow([neutralize(cell)[0] for cell in row])
    return out.getvalue()


def neutralized_cells(model: ExportModel) -> tuple[tuple[str, str], ...]:
    """Every cell the defence touched, as `(table, original text)`.

    Reported rather than silent: a reader who finds an apostrophe in their data
    is owed the list of where it was added and why.
    """
    found = []
    for table in model.tables:
        for row in table.rows:
            for cell in row:
                _, defused = neutralize(cell)
                if defused:
                    found.append((table.name, cell.display))
    return tuple(found)


def export_csv(result, scenarios=None, scenario_id: str = "base", *, now=None) -> dict[str, str]:
    """Every 21.1 table as its own CSV, keyed by filename."""
    model = gather(result, scenarios, scenario_id, now=now)
    return {f"{table.name}.csv": table_to_csv(model, table) for table in model.tables}
