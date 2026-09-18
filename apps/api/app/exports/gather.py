"""21.1's sixteen tabs, gathered once from the screens' own view functions.

This module is the answer to 21.8. Every figure here comes from the function
that produces the same figure for the browser -- `statement_view` for the
historical statements, `statement_rows` for the forecast, `flow_rows` and
`build_grid` for the DCF, `evaluate` for the checks. Nothing is recomputed for
the export's benefit, because a second computation is a second answer.

**A stage that cannot be built produces a table that says why.** 21.1 names
sixteen tabs and a filing that cannot be forecast still has to export: the
alternative is an export that silently omits four tabs, and a reader counting
sixteen has no way to tell an omission from an absence. So the tab is present,
empty, and carries its reason -- the same rule the screens follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model.accounts import Statement
from model.disclaimer import DISCLAIMER
from model.checks import Status

from ..assumptions.scenarios import BASE, ScenarioSet
from ..diagnostics.run import evaluate as run_diagnostics
from ..forecast.build import ForecastError, build_scenario_forecast
from ..forecast.views import columns as forecast_columns, statement_rows
from ..forecast.views import driver_rows as forecast_drivers
from ..mapping.sets import MappingSet
from ..schedules.build import build_schedules
from ..schedules.views import driver_rows as wc_drivers, working_capital_rows
from ..statements.build import BuildError, build_statements
from ..statements.reported import reported_strings
from ..statements.views import statement_view
from ..valuation.build import ValuationError, build_scenario_valuation
from ..valuation.checks import terminal_share
from ..valuation.sensitivity import build_grid
from ..valuation.views import flow_rows
from .tables import (
    DERIVED,
    FORECAST,
    REPORTED,
    Cell,
    Column,
    ExportModel,
    Table,
)
from .version import generated_at, model_version

#: 21.1, verbatim and in its order. A test asserts the export produces exactly
#: these, because "sixteen tabs" is a contract and a missing one is a silent
#: omission rather than a visible gap.
TAB_ORDER = (
    ("cover", "Cover"),
    ("sources", "Sources"),
    ("raw_facts", "Raw Facts"),
    ("mapping", "Mapping"),
    ("historical_is", "Historical IS"),
    ("historical_bs", "Historical BS"),
    ("historical_cf", "Historical CF"),
    ("schedules", "Schedules"),
    ("assumptions", "Assumptions"),
    ("forecast_is", "Forecast IS"),
    ("forecast_bs", "Forecast BS"),
    ("forecast_cf", "Forecast CF"),
    ("dcf", "DCF"),
    ("sensitivity", "Sensitivity"),
    ("checks", "Checks"),
    ("audit_summary", "Audit Summary"),
)

#: 21.6's limitations, which are properties of this system rather than of any
#: one model. Written out because a report whose limitations section says
#: "none" is the one a reader should distrust.
STANDING_LIMITATIONS = (
    DISCLAIMER,
    "Every figure rests on one filing. A filing restated later restates this.",
    "Three of the seven Section 13 schedules cannot be built from the "
    "canonical chart: intangibles, leases and share count. Their lines are "
    "reported unavailable rather than taken as nil.",
    "16.19's lease liability line is not in the enterprise-to-equity bridge. "
    "A company with material leases is over-valued by their whole amount "
    "unless that line is supplied.",
    "There is no per-share value unless a verified diluted share count was "
    "supplied, because 16.20 permits none.",
    "Section 17 assigns a severity to no check, so the release gate blocks on "
    "every outstanding check rather than on a severity nobody ratified (F-4).",
)


@dataclass(frozen=True)
class GatherNotes:
    """What could not be reached, and why. Never silent."""

    statements: str = ""
    schedules: str = ""
    forecast: str = ""
    valuation: str = ""


def metadata_field(result, name: str) -> str:
    """One 10.10 metadata field, marked when nobody has confirmed it.

    `DetectedMetadata` is a dict of `DetectedField`, not an object with these
    as attributes, and reading it with `getattr` returns the default silently
    -- which would put "(unconfirmed)" on a document whose currency IS
    confirmed, and would do it on every export without failing anything.

    1.9 and 1.10 are why the confirmation state travels with the value rather
    than being dropped: a currency a detector guessed and a currency a human
    confirmed are different claims, and an export that prints them the same way
    makes the stronger one for both.
    """
    field = result.document.metadata.fields.get(name)
    if field is None or not field.value:
        return ""
    return field.value if field.confirmed else f"{field.value} (unconfirmed)"


def _units(result) -> "tuple[str, str]":
    return (
        metadata_field(result, "reporting_currency"),
        metadata_field(result, "displayed_scale"),
    )


def _assumption_kind(unit: str) -> str:
    """Which display precision an assumption's unit calls for.

    A rate shown at currency precision rounds 0.055 to 0, which is not a
    rounding error a reader can spot -- it looks like a zero cost of debt.
    """
    lowered = (unit or "").strip().lower()
    if lowered in ("currency", "money", "usd", "eur", "gbp"):
        return "currency"
    if lowered in ("percent", "%"):
        return "percent"
    if lowered in ("days", "day"):
        return "days"
    if lowered in ("shares", "count", "integer"):
        return "integer"
    return "ratio"


def _origin(origin: str) -> str:
    """The ledger's own origin word, mapped onto 21.2's distinction."""
    return {
        "reported": REPORTED, "derived": DERIVED, "forecast": FORECAST,
    }.get(str(origin), REPORTED)


# --- the tabs ---------------------------------------------------------------

def _cover(model_bits: dict) -> Table:
    """21.3: currency, units, dates, scenario and model version, stated."""
    rows = [
        (Cell.text(label), Cell.text(value))
        for label, value in model_bits["cover_rows"]
    ]
    return Table(
        name="cover",
        title="Cover",
        columns=(Column("field", "Field"), Column("value", "Value")),
        rows=tuple(rows),
        note=(
            "21.3 and 21.7. The model version is a digest of what this model "
            "contains -- the document, the mapping, the scenario and every "
            "assumption -- so the same model exported twice reads the same "
            "version, and one changed digit changes it."
        ),
    )


def _sources(result) -> Table:
    document = result.document
    rows = [
        (
            Cell.text(document.sanitized_filename),
            Cell.text(document.immutable_hash),
            Cell.text(document.page_count),
            Cell.text(metadata_field(result, "company_name") or "(not detected)"),
            Cell.text(metadata_field(result, "fiscal_year_end") or "(not detected)"),
            Cell.text(document.verification_status.value),
            Cell.text(document.uploaded_at.isoformat()),
        )
    ]
    return Table(
        name="sources",
        title="Sources",
        columns=(
            Column("filename", "File"),
            Column("hash", "SHA-256"),
            Column("pages", "Pages", "integer"),
            Column("company", "Company"),
            Column("fiscal_year_end", "Fiscal year end"),
            Column("status", "Verification"),
            Column("uploaded_at", "Ingested", "date"),
        ),
        rows=tuple(rows),
        note="17.1: the hash is of the stored bytes and is rehashed on load.",
    )


def _raw_facts(result) -> Table:
    rows = []
    locations = {location.id: location for location in result.locations}
    for fact in result.facts:
        location = locations.get(fact.source_location_id)
        decision = fact.decision
        rows.append(
            (
                Cell.text(fact.raw_label),
                Cell.text(fact.raw_value),
                Cell.text(fact.period_label),
                Cell.number(fact.value, origin=REPORTED)
                if fact.value is not None
                else Cell.missing("the parser refused this cell rather than guess"),
                Cell.text(location.page_number if location else ""),
                Cell.number(fact.confidence.score, origin=DERIVED, kind="ratio",
                            note=fact.confidence.explain()),
                Cell.text(fact.verification_status.value),
                Cell.text(decision.action if decision else "(not reviewed)"),
                Cell.text(decision.reason if decision else ""),
            )
        )
    return Table(
        name="raw_facts",
        title="Raw Facts",
        columns=(
            Column("label", "Printed label"),
            Column("raw", "Printed value"),
            Column("period", "Period"),
            Column("value", "Parsed value", "currency"),
            Column("page", "Page", "integer"),
            Column("confidence", "Confidence", "ratio"),
            Column("verification", "Verification"),
            Column("decision", "Decision"),
            Column("reason", "Reason"),
        ),
        rows=tuple(rows),
        note=(
            "10.25: the printed string is evidence and is never overwritten. A "
            "correction appears as a decision beside it, not in place of it."
        ),
    )


def _mapping(result) -> Table:
    mappings: MappingSet | None = result.mappings
    if mappings is None:
        return Table(
            name="mapping", title="Mapping",
            columns=(Column("fact", "Fact"), Column("code", "Canonical line")),
            note="Nobody has started mapping this filing.",
            unavailable=True,
        )
    by_id = {fact.id: fact for fact in result.facts}
    rows = []
    for mapping in mappings.mappings:
        fact = by_id.get(mapping.reported_fact_id)
        rows.append(
            (
                Cell.text(fact.raw_label if fact else mapping.reported_fact_id),
                Cell.text(mapping.canonical_code),
                Cell.text(mapping.mapping_type.value),
                Cell.text(mapping.sign_normalization.value),
                Cell.number(mapping.allocation_amount, origin=REPORTED)
                if mapping.allocation_amount is not None
                else Cell.text(""),
                Cell.text(mapping.allocation_basis or ""),
                Cell.text(mapping.approved_by or "(not approved)"),
                Cell.text(mapping.reviewer_note),
            )
        )
    return Table(
        name="mapping", title="Mapping",
        columns=(
            Column("fact", "Printed label"),
            Column("code", "Canonical line"),
            Column("type", "Type"),
            Column("sign", "Sign"),
            Column("allocation", "Allocation", "currency"),
            Column("basis", "Allocation basis"),
            Column("approved_by", "Approved by"),
            Column("note", "Note"),
        ),
        rows=tuple(rows),
        note=f"Mapping set version {mappings.version}, {len(mappings.mappings)} mapping(s).",
    )


_HISTORICAL = (
    ("historical_is", "Historical IS", Statement.INCOME),
    ("historical_bs", "Historical BS", Statement.BALANCE),
    ("historical_cf", "Historical CF", Statement.CASHFLOW),
)


def _historical(built, statement: Statement, name: str, title: str, raw, note: str) -> Table:
    if built is None:
        return Table(
            name=name, title=title,
            columns=(Column("line", "Line"),),
            note=note, unavailable=True,
        )
    columns = [Column("line", "Line")]
    for year in built.years:
        columns.append(Column(year, year, "currency"))
    rows = []
    for row in statement_view(built, statement, raw_values=raw):
        cells = [Cell.text(row.item.display_name)]
        for view in row.cells:
            if view.value is None:
                cells.append(Cell.missing("the filing reports no value on this line"))
            else:
                cells.append(
                    Cell.number(
                        view.value,
                        origin=_origin(getattr(view.cell, "origin", REPORTED)),
                        note=view.cite(),
                    )
                )
        rows.append(tuple(cells))
    return Table(
        name=name, title=title,
        columns=tuple(columns), rows=tuple(rows),
        note="Every figure carries the page it was printed on (10.31).",
    )


def _schedules(built, note: str) -> Table:
    if built is None:
        return Table(
            name="schedules", title="Schedules",
            columns=(Column("schedule", "Schedule"),),
            note=note, unavailable=True,
        )
    schedules = build_schedules(built)
    columns = [
        Column("schedule", "Schedule"),
        Column("rule", "Clause"),
        Column("availability", "Availability"),
        Column("line", "Line"),
    ]
    for year in schedules.years:
        columns.append(Column(year, year, "currency"))
    columns.append(Column("note", "Note"))

    rows: "list[tuple[Cell, ...]]" = []

    def add(schedule, label: str, values, note_text: str = "", origin: str = DERIVED,
            kind: str = "currency"):
        cells = [
            Cell.text(schedule.title),
            Cell.text(schedule.rule),
            Cell.text(schedule.availability.value),
            Cell.text(label),
        ]
        for value in values:
            cells.append(
                Cell.number(value, origin=origin, kind=kind)
                if value is not None
                else Cell.missing("not reported for this period")
            )
        cells.append(Cell.text(note_text))
        rows.append(tuple(cells))

    blank = tuple(None for _ in schedules.years)

    for row in working_capital_rows(schedules.working_capital):
        add(schedules.working_capital, row.label, row.values, row.absent_reason)
    for driver in wc_drivers(schedules.working_capital):
        add(
            schedules.working_capital,
            f"{driver.name} ({driver.numerator} / {driver.denominator})",
            tuple(item.days for item in driver.values),
            "13.1.d driver, computed on the closing balance the forecast rolls",
            kind="days",
        )

    for key in ("ppe", "debt", "retained_earnings", "common_equity"):
        schedule = schedules.by_key(key)
        by_year = {year.year: year for year in schedule.years}
        def series(pick):
            return tuple(
                pick(by_year[year]) if year in by_year else None
                for year in schedules.years
            )
        add(schedule, "Beginning balance", series(lambda y: y.beginning.value))
        labels = []
        for year in schedule.years:
            for line in year.movements:
                if line.label not in labels:
                    labels.append(line.label)
        for label in labels:
            def movement(y, label=label):
                for line in y.movements:
                    if line.label == label:
                        return line.value
                return None
            add(schedule, label, series(movement))
        add(schedule, "Computed ending", series(lambda y: y.computed_ending))
        add(schedule, "Reported ending", series(lambda y: y.reported_ending), origin=REPORTED)

    for schedule in schedules.all:
        for reconciliation in schedule.reconciliations:
            values = tuple(
                reconciliation.difference if year == reconciliation.year else None
                for year in schedules.years
            )
            add(
                schedule,
                f"Unexplained vs {reconciliation.statement_line}",
                values,
                reconciliation.note or "13.8: computed minus reported, never applied",
            )

    for schedule in schedules.unavailable:
        add(schedule, "(not built)", blank, schedule.reason)

    return Table(
        name="schedules", title="Schedules",
        columns=tuple(columns), rows=tuple(rows),
        note=(
            "13.8: each schedule's own closing figure against the statement's. "
            "The difference is reported and never applied to anything."
        ),
    )


def _assumptions(scenarios: ScenarioSet | None, scenario_id: str) -> Table:
    columns = (
        Column("code", "Code"),
        Column("name", "Name"),
        Column("value", "Value", "ratio"),
        Column("unit", "Unit"),
        Column("periods", "Periods"),
        Column("status", "Status"),
        Column("source_type", "Source type"),
        Column("evidence", "Evidence"),
        Column("rationale", "Rationale"),
        Column("owner", "Owner"),
        Column("reviewer", "Reviewer"),
        Column("from_scenario", "Supplied by"),
    )
    if scenarios is None or not scenarios.assumptions:
        return Table(
            name="assumptions", title="Assumptions", columns=columns,
            note="No assumption has been entered for this model.",
            unavailable=True,
        )
    resolved = scenarios.resolve(scenario_id)
    rows = []
    for code in sorted(resolved):
        item = resolved[code]
        assumption = item.assumption
        rows.append(
            (
                Cell.text(assumption.code),
                Cell.text(assumption.name),
                Cell.number(
                    assumption.value, origin=REPORTED,
                    kind=_assumption_kind(assumption.unit),
                ),
                Cell.text(assumption.unit),
                Cell.text(", ".join(assumption.periods) or "every forecast period"),
                Cell.text(assumption.status.value),
                Cell.text(assumption.source_type.value),
                Cell.text(assumption.evidence.describe()),
                Cell.text(assumption.rationale),
                Cell.text(assumption.owner),
                Cell.text(assumption.reviewer),
                Cell.text(item.from_scenario),
            )
        )
    return Table(
        name="assumptions", title="Assumptions", columns=columns, rows=tuple(rows),
        note=(
            f"Scenario {scenario_id!r}, resolved: a scenario's own record "
            "shadows its parent's, and the parent's stays reachable (14.7)."
        ),
    )


_FORECASTS = (
    ("forecast_is", "Forecast IS", Statement.INCOME),
    ("forecast_bs", "Forecast BS", Statement.BALANCE),
    ("forecast_cf", "Forecast CF", Statement.CASHFLOW),
)


def _forecast(forecast, statement: Statement, name: str, title: str, note: str) -> Table:
    if forecast is None:
        return Table(
            name=name, title=title, columns=(Column("line", "Line"),),
            note=note, unavailable=True,
        )
    periods = forecast_columns(forecast)
    columns = [Column("line", "Line"), Column("code", "Code")]
    for period in periods:
        columns.append(Column(period.year, f"{period.label} ({period.kind})", "currency"))
    rows = []
    for row in statement_rows(forecast, statement):
        cells = [Cell.text(row.label), Cell.text(row.code)]
        for cell in row.cells:
            if cell.value is None:
                cells.append(Cell.missing(cell.basis or "no value for this period"))
            else:
                cells.append(
                    Cell.number(cell.value, origin=_origin(cell.origin), note=cell.basis)
                )
        rows.append(tuple(cells))
    return Table(
        name=name, title=title, columns=tuple(columns), rows=tuple(rows),
        note="7.8.d: every column says whether it is an actual or an estimate.",
    )


def _dcf(valuation, note: str) -> Table:
    columns = (
        Column("line", "Line"),
        # Deliberately not typed: this column holds rates and currency alike,
        # and each cell carries its own display precision.
        Column("value", "Value", "text"),
        Column("detail", "Detail"),
    )
    if valuation is None:
        return Table(
            name="dcf", title="DCF", columns=columns, note=note, unavailable=True,
        )
    result = valuation.valuation
    capital = valuation.cost_of_capital
    rows: "list[tuple[Cell, ...]]" = []

    def add(label: str, value, detail: str = "", origin: str = DERIVED,
            kind: str = "currency"):
        rows.append(
            (
                Cell.text(label),
                Cell.number(value, origin=origin, kind=kind) if value is not None
                else Cell.missing(detail or "not available"),
                Cell.text(detail),
            )
        )

    for record in valuation.inputs:
        add(
            record.name, record.value,
            f"{record.source_type} - {record.evidence} ({record.status})",
            origin=REPORTED, kind=_assumption_kind(record.unit),
        )
    add("Cost of equity", capital.cost_of_equity, "CAPM (16.7)", kind="ratio")
    add("WACC", result.wacc, f"16.9, timing {valuation.schedule.basis}", kind="ratio")
    for year in result.discounted:
        add(
            f"FCFF {year.year}", year.fcff,
            f"period {year.period}, factor {year.discount_factor}",
        )
        add(f"PV of FCFF {year.year}", year.present_value, "16.14")
    add("Sum of PV, explicit period", result.pv_explicit, "16.14")
    add("Terminal-year FCFF", result.terminal_fcff, "16.15")
    add("Terminal value", result.terminal_value, "16.15 Gordon Growth")
    add("PV of terminal value", result.pv_terminal_value, "16.14")
    add("Enterprise value", result.enterprise_value, "16.17")
    for label, value in (
        ("Less: debt", valuation.bridge.debt),
        ("Plus: cash", valuation.bridge.cash),
        ("Plus: non-operating investments", valuation.bridge.non_operating_investments),
        ("Less: minority interest", valuation.bridge.minority_interest),
        ("Less: preferred stock", valuation.bridge.preferred_stock),
        ("Less: pension obligations", valuation.bridge.pension_obligations),
        ("Less: other claims", valuation.bridge.other_claims),
    ):
        add(label, value, "16.18 bridge", origin=REPORTED)
    add("Equity value", result.equity_value, "16.18")
    if result.implied_share_price is None:
        rows.append(
            (
                Cell.text("Implied value per share"),
                Cell.missing(valuation.per_share_status),
                Cell.text(valuation.per_share_status),
            )
        )
    else:
        add("Implied value per share", result.implied_share_price, "16.20")
    share = terminal_share(valuation)
    add(
        "Terminal value share of enterprise value",
        share.share, share.describe(), origin=DERIVED, kind="ratio",
    )
    return Table(
        name="dcf", title="DCF", columns=columns, rows=tuple(rows),
        note="16.2-16.22, in the order the valuation was built.",
    )


def _sensitivity(valuation, note: str) -> Table:
    if valuation is None:
        return Table(
            name="sensitivity", title="Sensitivity",
            columns=(Column("wacc", "WACC"),), note=note, unavailable=True,
        )
    grid = build_grid(valuation)
    columns = [Column("wacc", "WACC \\ terminal growth")]
    for growth in grid.growth_values:
        columns.append(Column(str(growth), str(growth), "currency"))
    rows = []
    for index, wacc in enumerate(grid.wacc_values):
        cells = [Cell.text(wacc)]
        for cell in grid.rows[index]:
            if cell.equity_value is None:
                cells.append(Cell.missing(cell.note or "16.16 blocks this corner"))
            else:
                cells.append(Cell.number(cell.equity_value, origin=DERIVED))
        rows.append(tuple(cells))
    return Table(
        name="sensitivity", title="Sensitivity",
        columns=tuple(columns), rows=tuple(rows),
        note=f"16.23. {grid.describe()}",
    )


def _checks(outcomes) -> Table:
    rows = []
    for outcome in outcomes.outcomes:
        rows.append(
            (
                Cell.text(outcome.check.code),
                Cell.text(outcome.check.clause),
                Cell.text(outcome.check.compares),
                Cell.text(outcome.status.value),
                Cell.text(outcome.check.severity.value),
                Cell.text("forced" if outcome.check.forced else "proposed (F-4)"),
                Cell.text(outcome.detail),
            )
        )
    return Table(
        name="checks", title="Checks",
        columns=(
            Column("code", "Code"),
            Column("clause", "Clause"),
            Column("compares", "What it compares"),
            Column("status", "Status"),
            Column("severity", "Severity"),
            Column("severity_basis", "Severity basis"),
            Column("detail", "Detail"),
        ),
        rows=tuple(rows),
        note=(
            "All thirty Section 17 checks. SKIP means the check could not run "
            "and is not a pass (rule 1.14). Severity is unratified for "
            "twenty-five of the thirty (F-4)."
        ),
    )


def _audit(result) -> Table:
    counts: "dict[tuple[str, str], int]" = {}
    latest: "dict[tuple[str, str], str]" = {}
    for event in result.audit:
        key = (event.actor, event.action)
        counts[key] = counts.get(key, 0) + 1
        latest[key] = event.at.isoformat()
    rows = [
        (
            Cell.text(actor),
            Cell.text(action),
            Cell.text(count),
            Cell.text(latest[(actor, action)]),
        )
        for (actor, action), count in sorted(counts.items())
    ]
    return Table(
        name="audit_summary", title="Audit Summary",
        columns=(
            Column("actor", "Actor"),
            Column("action", "Action"),
            Column("count", "Events", "integer"),
            Column("latest", "Most recent", "date"),
        ),
        rows=tuple(rows),
        note=(
            f"{len(result.audit)} event(s). A summary, not the log: the full "
            "log with its reasons is on the diagnostics screen (9.14)."
        ),
    )


# --- the gather -------------------------------------------------------------

def gather(
    result,
    scenarios: ScenarioSet | None = None,
    scenario_id: str = BASE,
    *,
    now=None,
) -> ExportModel:
    """Build every 21.1 tab for one model, in one pass.

    Strict, unlike the screens. A screen is a work surface and shows a partial
    model as it fills; an export is a claim about a model, and 11.11 says a
    historical model may be labelled verified only when nothing in it rests on
    an unverified fact. So this builds with `strict=True`, and when that
    refuses, the statement tabs carry the refusal rather than a weaker model.
    """
    notes = GatherNotes()
    try:
        built = build_statements(result, strict=True)
    except BuildError as exc:
        built = None
        notes = GatherNotes(statements=str(exc), schedules=str(exc))

    forecast = None
    valuation = None
    forecast_note = notes.statements or ""
    valuation_note = notes.statements or ""
    if built is not None and scenarios is not None:
        try:
            forecast = build_scenario_forecast(built, scenarios, scenario_id)
        except ForecastError as exc:
            forecast_note = str(exc)
        if forecast is not None:
            try:
                valuation = build_scenario_valuation(forecast, scenarios)
            except ValuationError as exc:
                valuation_note = str(exc)
        else:
            valuation_note = forecast_note
    elif scenarios is None:
        forecast_note = forecast_note or "No scenario has been created for this model."
        valuation_note = valuation_note or forecast_note

    currency, units = _units(result)
    version = model_version(result, scenarios, scenario_id)
    stamp = generated_at(now)
    # 21.6 asks the report for a valuation date. Under 16.11's year-end and
    # mid-year conventions there is no calendar date -- t is defined relative
    # to the last actual period end -- and inventing today's date would put a
    # number in the report that nothing was discounted from. So the convention
    # is reported instead, and says what would supply a date.
    if valuation is None:
        valuation_date = ""
    elif valuation.valuation_date is not None:
        valuation_date = valuation.valuation_date.isoformat()
    else:
        valuation_date = f"none supplied; {valuation.schedule.timing.value} convention (16.11)"

    cover_rows = [
        ("Product", "Three-Statement DCF"),
        ("Owner", "spinfern-o"),
        ("Document", result.document.sanitized_filename),
        ("Document SHA-256", result.document.immutable_hash),
        ("Company", metadata_field(result, "company_name") or "(not detected)"),
        ("Reporting currency", currency or "(not detected)"),
        ("Displayed scale", units or "(not detected)"),
        ("Scenario", scenario_id),
        ("Valuation date", valuation_date or "(no valuation)"),
        ("Model version", version.describe()),
        ("Generated at", stamp),
        ("Distribution", "Private model - not for distribution"),
    ]

    raw = reported_strings(result) if built is not None else {}
    tables = [
        _cover({"cover_rows": cover_rows}),
        _sources(result),
        _raw_facts(result),
        _mapping(result),
    ]
    for name, title, statement in _HISTORICAL:
        tables.append(_historical(built, statement, name, title, raw, notes.statements))
    tables.append(_schedules(built, notes.schedules))
    tables.append(_assumptions(scenarios, scenario_id))
    for name, title, statement in _FORECASTS:
        tables.append(_forecast(forecast, statement, name, title, forecast_note))
    tables.append(_dcf(valuation, valuation_note))
    tables.append(_sensitivity(valuation, valuation_note))
    tables.append(_checks(run_diagnostics(result, scenarios, scenario_id)))
    tables.append(_audit(result))

    limitations = list(STANDING_LIMITATIONS)
    for reason in (notes.statements, forecast_note, valuation_note):
        if reason and reason not in limitations:
            limitations.append(f"This export could not build a stage: {reason}")

    return ExportModel(
        document_id=result.document.id,
        company=metadata_field(result, "company_name"),
        scenario_id=scenario_id,
        version_id=version.describe(),
        generated_at=stamp,
        currency=currency,
        units=units,
        valuation_date=valuation_date,
        tables=tuple(tables),
        limitations=tuple(limitations),
        version_components=version.components,
    )
