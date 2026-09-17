"""Item 63's reported view: the strings the filing actually printed.

The normalized view is what the model uses -- parsed, sign-normalized, mapped.
The reported view is what the page said. 1.8 and 11.8 both turn on being able
to see both, and 10.25 is the reason it is possible: `raw_value` is kept.

The engine's `Ledger` has nowhere to put a raw string -- a `Cell` holds a
`Decimal` and a `Source` -- so this reads the facts and the mapping set
directly rather than the built ledgers.
"""

from __future__ import annotations

from ..extraction.records import ExtractionResult
from ..mapping.normalized import statement_for
from .build import engine_year


def reported_strings(result: ExtractionResult) -> "dict[tuple[str, str], str]":
    """`(canonical_code, engine year) -> what was printed`.

    An aggregate shows every contributor, joined, because 11.5's "show the
    aggregation" applies to the reported view most of all: `345,500` as one
    figure hides that the filing printed three.
    """
    mappings = result.mappings
    if mappings is None:
        return {}
    facts = {f.id: f for f in result.facts}
    collected: dict[tuple[str, str], list[str]] = {}

    for mapping in mappings.mappings:
        if not mapping.contributes:
            continue
        fact = facts.get(mapping.reported_fact_id)
        if fact is None:
            continue
        key = (mapping.canonical_code, engine_year(fact.period_label))
        collected.setdefault(key, []).append(fact.raw_value)

    return {key: " + ".join(values) for key, values in collected.items()}


def citations(result: ExtractionResult) -> "dict[tuple[str, str], list[dict]]":
    """Item 65. Everything a cell should be able to show about where it came from."""
    mappings = result.mappings
    if mappings is None:
        return {}
    facts = {f.id: f for f in result.facts}
    collected: dict[tuple[str, str], list[dict]] = {}

    for mapping in mappings.mappings:
        if not mapping.contributes:
            continue
        fact = facts.get(mapping.reported_fact_id)
        if fact is None:
            continue
        location = result.location(fact.source_location_id)
        key = (mapping.canonical_code, engine_year(fact.period_label))
        collected.setdefault(key, []).append(
            {
                "fact": fact,
                "location": location,
                "mapping": mapping,
                "page": location.page_number if location else None,
                "statement": statement_for(mapping.canonical_code, fact, result),
            }
        )
    return collected
