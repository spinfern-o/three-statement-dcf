"""The normalized ledger: what the mappings actually produce.

Nothing in Section 11 names this file, and everything in it is required by
items 54 and 55: you cannot check that a subtotal reconciles against its
components until the components have values, and they have values only once
their mappings are applied.

Two properties carry over from the engine's `Ledger`, and they are the whole
reason this is not a dictionary comprehension:

**Absent is not zero.** A canonical line with no mapped fact is absent. An
aggregate one of whose contributors could not be parsed is **absent, not a
partial sum** -- adding up the three of four figures you could read and
presenting the result as the total is exactly the silent damage rule 1.2 is
about.

**Sign normalization is applied here and recorded there.** 11.8 keeps the
source sign on the fact and the normalization on the mapping; this is where
the two combine, once, in one place, so a value's sign has a single
explanation.

**The statement is part of the key.** `net_income` is printed on both the
income statement and the top of the cash flow statement -- the same figure,
twice, which is what the linkage check reconciles. Keying only on
(code, period) would group those two facts and ADD them, doubling net income
on any filing that presents a cash flow statement. Thirty-nine of the forty
canonical codes belong to exactly one statement and are unaffected; the
fortieth is the reason the key has three parts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from ..extraction.records import ExtractionResult, ReportedFact
from .chart import StatementType, line_item
from .sets import FactMapping, MappingSet, MappingType, SignNormalization

#: Which statement a table belongs to, from its caption. Used to tell a
#: cross-statement duplicate (net income on both) from a double count.
_STATEMENT_PATTERNS = (
    (StatementType.INCOME, re.compile(r"(?i)statements?\s+of\s+(operations|income|profit)|income\s+statement|profit\s+and\s+loss|gewinn|verlustrechnung")),
    (StatementType.BALANCE, re.compile(r"(?i)balance\s+sheets?|financial\s+position|bilanz")),
    (StatementType.CASHFLOW, re.compile(r"(?i)cash\s+flows?|kapitalfluss")),
)


def statement_of_caption(caption: str) -> StatementType | None:
    for statement, pattern in _STATEMENT_PATTERNS:
        if pattern.search(caption or ""):
            return statement
    return None


def statement_of_fact(result: ExtractionResult, fact: ReportedFact) -> StatementType | None:
    """Which statement this fact was printed on, from its table's caption."""
    location = result.location(fact.source_location_id)
    if location is None or location.table_id is None:
        return None
    for table in result.tables:
        if table.id == location.table_id:
            return statement_of_caption(table.caption)
    return None


@dataclass(frozen=True)
class NormalizedValue:
    """One canonical line, on one statement, for one period."""

    canonical_code: str
    period_label: str
    statement: StatementType
    #: None means absent. It never means zero (rule 1.2).
    value: Decimal | None
    #: The facts that produced it, in mapping order.
    contributors: tuple[str, ...]
    mapping_type: MappingType
    #: Why the value is absent, when it is and something was mapped.
    absent_because: str = ""
    #: True when every contributing mapping is human-approved (11.11).
    approved: bool = False

    @property
    def is_present(self) -> bool:
        return self.value is not None


def statement_for(code: str, fact: ReportedFact, result: ExtractionResult) -> StatementType:
    """Which statement this contribution belongs on.

    For thirty-nine codes the chart answers it outright. For `net_income` the
    answer is where the figure was printed, which the table's caption gives;
    when even that is unknown the income statement is the documented fallback,
    because that is where net income is defined and the cash flow statement
    merely restates it.
    """
    item = line_item(code)
    if len(item.statement_types) == 1:
        return item.statement_types[0]
    return statement_of_fact(result, fact) or item.statement_types[0]


def _contribution(fact: ReportedFact, mapping: FactMapping) -> Decimal | None:
    """One mapping's contribution, with 11.8's sign normalization applied."""
    if mapping.mapping_type is MappingType.SPLIT:
        raw = mapping.allocation_amount
    else:
        raw = fact.value
    if raw is None:
        return None
    return -raw if mapping.sign_normalization is SignNormalization.NEGATED else raw


def normalize(
    result: ExtractionResult, mappings: MappingSet | None = None
) -> dict[tuple[str, str, StatementType], NormalizedValue]:
    """Build `(code, period, statement) -> NormalizedValue` from the mappings.

    Rejected mappings contribute nothing. A contributor with no parsed value
    makes the whole line absent, with the reason recorded.
    """
    mapping_set = mappings if mappings is not None else result.mappings
    if mapping_set is None:
        return {}

    facts = {f.id: f for f in result.facts}
    grouped: dict = {}

    for mapping in mapping_set.mappings:
        if not mapping.contributes:
            continue
        fact = facts.get(mapping.reported_fact_id)
        if fact is None:
            continue
        line_item(mapping.canonical_code)  # refuses an unknown code
        key = (
            mapping.canonical_code,
            fact.period_label,
            statement_for(mapping.canonical_code, fact, result),
        )
        grouped.setdefault(key, []).append((fact, mapping))

    ledger: dict = {}
    for (code, period, statement), pairs in grouped.items():
        contributions = [_contribution(fact, mapping) for fact, mapping in pairs]
        unreadable = [
            fact for (fact, _), value in zip(pairs, contributions) if value is None
        ]
        kind = (
            MappingType.AGGREGATE
            if len(pairs) > 1
            else pairs[0][1].mapping_type
        )

        if unreadable:
            names = ", ".join(f"{f.raw_label!r} ({f.raw_value!r})" for f in unreadable)
            ledger[(code, period, statement)] = NormalizedValue(
                canonical_code=code,
                period_label=period,
                statement=statement,
                value=None,
                contributors=tuple(f.id for f, _ in pairs),
                mapping_type=kind,
                absent_because=(
                    f"{len(unreadable)} of {len(pairs)} contributing fact(s) have no "
                    f"parsed value: {names}. A partial sum would look like a total."
                ),
                approved=all(m.approved for _, m in pairs),
            )
            continue

        ledger[(code, period, statement)] = NormalizedValue(
            canonical_code=code,
            period_label=period,
            statement=statement,
            # A narrowed list, because the `unreadable` guard above already
            # returned for any absent contribution. Summing the unnarrowed one
            # would add a None on the day that guard changes.
            value=_total([c for c in contributions if c is not None]),
            contributors=tuple(f.id for f, _ in pairs),
            mapping_type=kind,
            approved=all(m.approved for _, m in pairs),
        )
    return ledger


def periods(ledger: dict) -> tuple[str, ...]:
    return tuple(sorted({key[1] for key in ledger}))


def lookup(
    ledger: dict, code: str, period: str, statement: StatementType | None = None
) -> NormalizedValue | None:
    """Fetch one value, resolving the statement when the code has only one."""
    if statement is None:
        item = line_item(code)
        if len(item.statement_types) != 1:
            raise KeyError(
                f"{code} appears on {len(item.statement_types)} statements; say "
                f"which one you mean"
            )
        statement = item.statement_types[0]
    return ledger.get((code, period, statement))


def describe(ledger: dict) -> str:
    lines = []
    for period in periods(ledger):
        lines.append(f"  {period}")
        for (code, other, statement), value in sorted(
            ledger.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2].value)
        ):
            if other != period:
                continue
            shown = "(absent)" if value.value is None else f"{value.value:,}"
            flag = "" if value.approved else "  [mapping unapproved]"
            lines.append(f"    {code:30} {statement.value:9} {shown:>16}{flag}")
    return "\n".join(lines)


def _total(values: list[Decimal]) -> Decimal:
    """Sum, seeded with the first term rather than with an int.

    `sum(values)` starts from `0`, an `int`, and 4.2 keeps this pipeline in
    `Decimal` end to end.
    """
    if not values:
        raise ValueError("a total over no contributions is not a total")
    return sum(values[1:], values[0])
