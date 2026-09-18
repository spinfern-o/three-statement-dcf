"""Items 59, 60 and 61: the normalized statements, as the engine's own objects.

Specification 12.1-12.3 asks for a normalized income statement, balance sheet
and cash flow statement. The engine already has the type for that -- a sparse
`Ledger` of account x year -> `Cell` -- and has had it since before any of
this existed. So this does not build a second one. It fills the engine's.

Three properties of the result are worth stating because they are what makes
the join defensible rather than merely working:

**Every cell carries a real citation.** `Cell.source` is a `Source(document,
page, line_item)` built from the fact's `SourceLocation` and the company's own
printed label. Running `ledger.get(...).cite()` returns "Example Industries
FY2025 10-K p.2: 'Cost of goods sold'", which is what STEP 4 asked for and
what a hand-transcribed model has only if the modeller was disciplined.

**Absent stays absent.** A canonical line no fact maps to is not in the
ledger. A line whose contributors could not be parsed is not in the ledger
either -- `normalize()` already refuses to present a partial sum as a total,
and this carries that through rather than defaulting it.

**Nothing unverified gets in by default.** `strict=True` refuses to build
from a fact that has not satisfied source-policy.md §9's seven conditions.
The screen passes `strict=False` so a reviewer can watch the statements fill
up as they work; the export does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model.accounts import Statement
from model.provenance import Figure, Source
from model.statements import Ledger

from ..extraction.records import ExtractionResult, ReportedFact
from ..mapping.chart import StatementType
from ..mapping.normalized import NormalizedValue, normalize
from ..review.progress import is_verified

#: Which engine statement a chart statement belongs to.
ENGINE_STATEMENT = {
    StatementType.INCOME: Statement.INCOME,
    StatementType.BALANCE: Statement.BALANCE,
    StatementType.CASHFLOW: Statement.CASHFLOW,
}


class BuildError(Exception):
    """The statements could not be built, and this says what is missing."""


@dataclass(frozen=True)
class BuiltStatements:
    """The three ledgers, the years they cover, and what was left out."""

    ledgers: dict[Statement, Ledger]
    years: tuple[str, ...]
    #: `(canonical_code, year, why)` for everything that did not make it in.
    omitted: tuple[tuple[str, str, str], ...]
    #: Cells resting on a fact that is not yet VERIFIED (strict=False only).
    unverified: tuple[tuple[str, str], ...]

    @property
    def is_verified(self) -> bool:
        """11.11: the historical model may be labelled Verified only if this."""
        return not self.unverified

    def describe(self) -> str:
        lines = [
            f"  years: {', '.join(self.years) or '(none)'}",
            "  cells: "
            + ", ".join(
                f"{statement.value} "
                + str(sum(len(ledger.accounts_present(y)) for y in self.years))
                for statement, ledger in self.ledgers.items()
            ),
        ]
        if self.unverified:
            lines.append(f"  {len(self.unverified)} cell(s) rest on unverified facts")
        if self.omitted:
            lines.append(f"  {len(self.omitted)} line-year(s) omitted")
        return "\n".join(lines)


def engine_year(period_label: str) -> str:
    """`2025` -> `2025A`. STEP 12's A/E suffix, which `Periods` validates.

    The mapping stage works in the label the filing printed. The engine tags
    every year actual or estimate, because a forecast year that looks like an
    actual one is how a projection gets quoted as a fact (rule 1.19).
    """
    label = period_label.strip()
    return label if label.endswith(("A", "E")) else f"{label}A"


def _figure_for(
    value: NormalizedValue,
    figure: Decimal,
    fact: ReportedFact,
    result: ExtractionResult,
    document_label: str,
) -> Figure:
    """Build the engine's provenance from the extraction's.

    `figure` is passed in rather than read off `value`, which holds it as
    `Decimal | None`. The caller has already established it is present --
    taking it as an argument carries that across the boundary rather than
    restating it here as something nothing can check.
    """
    location = result.location(fact.source_location_id)
    return Figure(
        value=figure,
        year=engine_year(value.period_label),
        source=Source(
            document=document_label,
            page=location.page_number if location else None,
            # STEP 4 wants the company's own wording, and an aggregate has
            # several. Naming them all is the aggregation 11.5 asks be shown.
            line_item=_label_for(value, result),
        ),
    )


def _label_for(value: NormalizedValue, result: ExtractionResult) -> str:
    facts = {f.id: f for f in result.facts}
    labels = [facts[fid].raw_label for fid in value.contributors if fid in facts]
    labels = [label for label in labels if label]
    if not labels:
        return "(no reported label)"
    if len(labels) == 1:
        return labels[0]
    return " + ".join(labels)


def document_label(result: ExtractionResult) -> str:
    """What `Source.document` should say. STEP 2's source-map document.

    Built from the CONFIRMED company name and reporting period rather than the
    PDF's own `/Title`. A document's claim about itself is routinely stale --
    a filing generated from last year's template keeps last year's title -- and
    a reviewer confirming the company name has checked the cover page. The
    title is the fallback, and the stored filename the fallback to that.
    """
    fields = result.document.metadata.fields
    name = fields.get("company_name")
    period = fields.get("reporting_period_end")
    filing = fields.get("filing_type")
    if name is not None and name.value:
        parts = [name.value]
        if period is not None and period.value:
            parts.append(f"FY{period.value[:4]}")
        if filing is not None and filing.value:
            parts.append(
                {"annual": "annual report", "quarterly": "quarterly report"}.get(
                    filing.value, filing.value
                )
            )
        return " ".join(parts)
    title = fields.get("document_title")
    if title is not None and title.value:
        return title.value
    return result.document.sanitized_filename


def build_statements(result: ExtractionResult, *, strict: bool = True) -> BuiltStatements:
    """Fill the engine's ledgers from this document's approved mappings.

    `strict` refuses anything that has not reached VERIFIED. Turn it off to
    watch the statements fill up during review; leave it on for anything that
    leaves this system.
    """
    mappings = result.mappings
    if mappings is None:
        raise BuildError(
            "this document has no mapping set. The statements are built from "
            "approved mappings (11.11), so there is nothing to build from yet."
        )

    ledger_values = normalize(result)
    facts = {f.id: f for f in result.facts}
    label = document_label(result)

    years = tuple(sorted({engine_year(key[1]) for key in ledger_values}))
    if not years:
        raise BuildError("no mapped value carries a period, so there are no years to build")

    ledgers = {engine: Ledger(engine, years) for engine in ENGINE_STATEMENT.values()}

    omitted: list[tuple[str, str, str]] = []
    unverified: list[tuple[str, str]] = []

    for (code, period, statement_type), value in sorted(
        ledger_values.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2].value)
    ):
        year = engine_year(period)

        figure_value = value.value
        if figure_value is None:
            omitted.append((code, year, value.absent_because or "no parsed value"))
            continue
        if not value.approved:
            if strict:
                raise BuildError(
                    f"{code} {year} is mapped but the mapping is not "
                    f"human-approved. 11.11 requires approval before the "
                    f"historical model is Verified, so a strict build takes the "
                    f"whole document or none of it. Approve it in the mapping "
                    f"review, or build with strict=False to see the statements "
                    f"mid-review."
                )
            omitted.append((code, year, "the mapping is not human-approved (11.11)"))
            continue

        contributors = [facts[fid] for fid in value.contributors if fid in facts]
        if not contributors:
            omitted.append((code, year, "its contributing facts are gone"))
            continue

        unverified_here = [f for f in contributors if not is_verified(f, result)]
        if unverified_here:
            if strict:
                names = ", ".join(repr(f.raw_label) for f in unverified_here)
                raise BuildError(
                    f"{code} {year} rests on {len(unverified_here)} unverified "
                    f"fact(s): {names}. source-policy.md §9 lists the seven "
                    f"conditions; the source room names the one that is failing. "
                    f"Build with strict=False to see the statements mid-review."
                )
            unverified.append((code, year))

        # The statement comes from where the figure was PRINTED, not from the
        # chart. `net_income` appears on two statements and a filing prints it
        # twice; writing one reading to both ledgers would make the linkage
        # check compare a figure with itself.
        figure = _figure_for(value, figure_value, contributors[0], result, label)
        ledgers[ENGINE_STATEMENT[statement_type]].set_reported(code, year, figure)

    return BuiltStatements(
        ledgers=ledgers,
        years=years,
        omitted=tuple(omitted),
        unverified=tuple(unverified),
    )
