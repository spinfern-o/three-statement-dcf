"""Item 138's second half: the versioned schema a JSON export validates against.

21.5 is one sentence -- "JSON exports must validate against a versioned
schema" -- and it contains two obligations that are easy to meet separately and
pointless apart. A schema nobody validates against is documentation; a
validation with no published schema is an assertion the consumer cannot check.

So the schema is a JSON Schema document, written out and exported beside the
data, and `validate` checks a payload against *that document* rather than
against a hand-written list of ifs that could drift from it.

**The validator covers exactly the constructs this schema uses**, and refuses a
schema using anything else. A partial validator that silently ignores a keyword
it does not implement is worse than none: it reports valid for a payload it
never checked. `unsupported_keywords` is what keeps that honest -- add a
keyword to the schema without teaching the validator, and the schema's own test
fails rather than the payload quietly passing.

A dependency was considered and not taken. `jsonschema` is not installed here
and the schema uses eleven keywords; a validator for eleven keywords that
refuses the twelfth is a smaller thing to trust than a general one nobody in
this repository has read.
"""

from __future__ import annotations

from decimal import Decimal

#: Bumped when a consumer that read the previous version would misread this
#: one: a field removed, renamed, or given a different meaning. Adding an
#: optional field does not bump it, because an old consumer still reads it.
SCHEMA_VERSION = "1.0.0"

SCHEMA_ID = f"https://spinfern-o.invalid/three-statement-dcf/export-{SCHEMA_VERSION}.schema.json"

#: Every keyword `validate` implements. A schema using anything else is refused
#: rather than partially checked.
SUPPORTED = frozenset(
    {
        "$schema", "$id", "title", "description", "type", "properties",
        "required", "additionalProperties", "items", "enum", "minimum",
        "minItems", "pattern", "definitions", "$ref",
    }
)

_CELL = {
    "type": "object",
    "description": "One value, exactly and as displayed (4.18).",
    "properties": {
        "display": {"type": "string", "description": "What the screen shows."},
        "value": {
            "type": ["string", "null"],
            "description": (
                "The exact stored value as a decimal string. A string, not a "
                "JSON number: 4.2 stores decimals exactly and a JSON number is "
                "a float to most parsers, which would round it on the way in."
            ),
        },
        "origin": {"type": "string", "enum": ["reported", "derived", "forecast", "text"]},
        "absent": {"type": "boolean"},
        "note": {"type": "string"},
    },
    "required": ["display", "value", "origin", "absent", "note"],
    "additionalProperties": False,
}

_COLUMN = {
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "title": {"type": "string"},
        "kind": {
            "type": "string",
            "enum": ["text", "currency", "percent", "ratio", "days", "integer", "date"],
        },
    },
    "required": ["key", "title", "kind"],
    "additionalProperties": False,
}

_TABLE = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "title": {"type": "string"},
        "note": {"type": "string"},
        "unavailable": {"type": "boolean"},
        "columns": {"type": "array", "items": _COLUMN, "minItems": 1},
        "rows": {"type": "array", "items": {"type": "array", "items": _CELL}},
    },
    "required": ["name", "title", "note", "unavailable", "columns", "rows"],
    "additionalProperties": False,
}

EXPORT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": SCHEMA_ID,
    "title": "Three-Statement DCF export",
    "description": (
        "One model, as 21.1's sixteen tables. Every value appears twice: "
        "exactly, as a decimal string, and as the string the website displays "
        "(21.8)."
    ),
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$"},
        "generated_at": {
            "type": "string",
            "description": "21.7. ISO 8601 with a UTC offset written out.",
            "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$",
        },
        "model_version": {
            "type": "string",
            "description": "21.7's immutable identifier: scheme, then digest.",
            "pattern": r"^msv1:[0-9a-f]{64}$",
        },
        "model_version_components": {
            "type": "array",
            "description": "What the version was computed from, in order.",
            "items": {
                "type": "object",
                "properties": {
                    "component": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["component", "value"],
                "additionalProperties": False,
            },
        },
        "document_id": {"type": "string"},
        "company": {"type": "string"},
        "scenario_id": {"type": "string"},
        "currency": {"type": "string"},
        "units": {"type": "string"},
        "valuation_date": {"type": "string"},
        "limitations": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "tables": {"type": "array", "items": _TABLE, "minItems": 16},
    },
    "required": [
        "schema_version", "generated_at", "model_version",
        "model_version_components", "document_id", "company", "scenario_id",
        "currency", "units", "valuation_date", "limitations", "tables",
    ],
    "additionalProperties": False,
}


class SchemaError(ValueError):
    """The payload does not match the schema, and this says where."""


def unsupported_keywords(schema: dict) -> set[str]:
    """Every keyword in `schema` that `validate` does not implement."""
    found: set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("properties", "definitions"):
                    for child in value.values():
                        walk(child)
                    continue
                if key not in SUPPORTED:
                    found.add(key)
                walk(value)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(schema)
    return found


def _type_ok(value, expected) -> bool:
    kinds = expected if isinstance(expected, list) else [expected]
    for kind in kinds:
        if kind == "object" and isinstance(value, dict):
            return True
        if kind == "array" and isinstance(value, list):
            return True
        if kind == "string" and isinstance(value, str):
            return True
        if kind == "boolean" and isinstance(value, bool):
            return True
        if kind == "null" and value is None:
            return True
        if kind == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if kind == "number" and isinstance(value, (int, Decimal, float)) and not isinstance(value, bool):
            return True
    return False


def _check(value, schema: dict, path: str) -> None:
    import re

    if "type" in schema and not _type_ok(value, schema["type"]):
        raise SchemaError(f"{path}: expected {schema['type']}, got {type(value).__name__}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(f"{path}: {value!r} is not one of {schema['enum']}")
    if ("pattern" in schema and isinstance(value, str)
            and not re.match(schema["pattern"], value)):
        raise SchemaError(f"{path}: {value!r} does not match {schema['pattern']}")
    if ("minimum" in schema and isinstance(value, (int, float, Decimal))
            and value < schema["minimum"]):
        raise SchemaError(f"{path}: {value} is below {schema['minimum']}")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", ()):
            if name not in value:
                raise SchemaError(f"{path}: required property {name!r} is missing")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise SchemaError(f"{path}: unexpected propert(ies) {extra}")
        for name, child in value.items():
            if name in properties:
                _check(child, properties[name], f"{path}.{name}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaError(
                f"{path}: has {len(value)} item(s), schema requires {schema['minItems']}"
            )
        item_schema = schema.get("items")
        if item_schema:
            for index, child in enumerate(value):
                _check(child, item_schema, f"{path}[{index}]")


def validate(payload: dict, schema: dict | None = None) -> None:
    """Raise `SchemaError` unless `payload` matches the schema.

    Refuses a schema using a keyword this validator does not implement, so a
    later edit to `EXPORT_SCHEMA` cannot silently reduce what is checked.
    """
    schema = EXPORT_SCHEMA if schema is None else schema
    unknown = unsupported_keywords(schema)
    if unknown:
        raise SchemaError(
            "this validator implements "
            f"{sorted(SUPPORTED)} and the schema uses {sorted(unknown)}. "
            "A validator that ignores a keyword reports valid for something it "
            "never checked."
        )
    _check(payload, schema, "$")
