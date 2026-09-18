"""Item 138: the JSON export, and why every number in it is a string.

**Decimals go out as strings.** JSON has one numeric type and most parsers read
it as a double, so `1234567.89` written as a JSON number comes back as a float
and 4.2's exact decimal is gone before the consumer has done anything wrong.
Writing it as `"1234567.89"` costs two characters and keeps the contract 4.11
makes about the whole pipeline. The schema says so in the field's own
description, because a consumer meeting a quoted number will otherwise assume
it is a mistake and cast it.

**`display` travels beside `value`.** 21.8 requires the export to equal the
website at the same display precision, and a consumer that formats the exact
value with its own rules will not reproduce the screen. Shipping both settles
it: `value` is what the model holds, `display` is what the reader saw.
"""

from __future__ import annotations

import json

from .gather import gather
from .schema import EXPORT_SCHEMA, SCHEMA_VERSION, validate
from .tables import Cell, ExportModel, Table

#: The filename a consumer gets, and the one the schema is published under.
SCHEMA_FILENAME = f"three-statement-dcf-export-{SCHEMA_VERSION}.schema.json"


def _cell(cell: Cell) -> dict:
    return {
        "display": cell.display,
        "value": None if cell.value is None else str(cell.value),
        "origin": cell.origin,
        "absent": cell.absent,
        "note": cell.note,
    }


def _table(table: Table) -> dict:
    return {
        "name": table.name,
        "title": table.title,
        "note": table.note,
        "unavailable": table.unavailable,
        "columns": [
            {"key": column.key, "title": column.title, "kind": column.kind}
            for column in table.columns
        ],
        "rows": [[_cell(cell) for cell in row] for row in table.rows],
    }


def payload(model: ExportModel) -> dict:
    """The export as plain Python, ready for `json.dumps`."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": model.generated_at,
        "model_version": model.version_id,
        "model_version_components": [
            {"component": name, "value": value} for name, value in model.version_components
        ],
        "document_id": model.document_id,
        "company": model.company,
        "scenario_id": model.scenario_id,
        "currency": model.currency,
        "units": model.units,
        "valuation_date": model.valuation_date,
        "limitations": list(model.limitations),
        "tables": [_table(table) for table in model.tables],
    }


def to_json(model: ExportModel, *, indent: int = 2) -> str:
    """Serialize, after validating. 21.5 is not satisfied by a schema on a shelf.

    Validation runs on the way out rather than in a test, because the test
    proves this export valid and the next filing is the one nobody tested.
    """
    body = payload(model)
    validate(body)
    return json.dumps(body, indent=indent, ensure_ascii=False, sort_keys=False)


def schema_json(*, indent: int = 2) -> str:
    """The schema document itself, exported so a consumer can check us."""
    return json.dumps(EXPORT_SCHEMA, indent=indent, ensure_ascii=False)


def export_json(result, scenarios=None, scenario_id: str = "base", *, now=None) -> str:
    model = gather(result, scenarios, scenario_id, now=now)
    return to_json(model)
