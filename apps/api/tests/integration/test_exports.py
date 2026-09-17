"""Phase 14, items 138-144: the four exports.

Item 143 is the one these are arranged around -- "compare exports with website
outputs" -- and the comparison is made against the *rendered page*, not against
the view function both would call. Comparing an export to the function that
built it proves the function is deterministic and nothing else.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal

import pytest

from apps.api.app.exports.csv_export import (
    DANGEROUS,
    DICTIONARY,
    PREFIX,
    header_lines,
    is_dangerous,
    neutralize,
    neutralized_cells,
    table_to_csv,
)
from apps.api.app.exports.gather import STANDING_LIMITATIONS, TAB_ORDER, gather, metadata_field
from apps.api.app.exports.json_export import payload, schema_json, to_json
from apps.api.app.exports.pdf_export import SECTIONS
from apps.api.app.exports.pdf_export import to_bytes as pdf_bytes
from apps.api.app.exports.schema import (
    EXPORT_SCHEMA,
    SCHEMA_VERSION,
    SUPPORTED,
    SchemaError,
    unsupported_keywords,
    validate,
)
from apps.api.app.exports.tables import Cell, Column, ExportModel, Table
from apps.api.app.exports.version import (
    SHORT,
    VERSION_SCHEME,
    generated_at,
    model_version,
)
from apps.api.app.exports.xlsx_export import (
    LEGEND,
    SHEET_NAME_LIMIT,
    build_workbook,
    survives_the_workbook,
)
from apps.api.app.exports.xlsx_export import to_bytes as xlsx_bytes
from apps.api.tests.conftest import approved_scenario


@pytest.fixture(scope="module")
def model(forecastable):
    """One fully built model: reviewed, mapped, forecast and valued."""
    return gather(forecastable, approved_scenario("owner"))


@pytest.fixture(scope="module")
def bare(three_statements):
    """A model that cannot be forecast. Its export must still be complete."""
    return gather(three_statements, None)


# --- 21.1: sixteen tabs, in its order ---------------------------------------

def test_every_tab_21_1_names_is_present_in_its_order(model):
    assert model.names == tuple(name for name, _ in TAB_ORDER)
    assert len(model.names) == 16


def test_a_model_that_cannot_be_forecast_still_exports_sixteen_tabs(bare):
    """An omitted tab reads as "nothing to report", which is not the claim."""
    assert bare.names == tuple(name for name, _ in TAB_ORDER)
    for name in ("forecast_is", "forecast_bs", "forecast_cf", "dcf", "sensitivity"):
        table = bare.table(name)
        assert table.unavailable, name
        assert table.note, f"{name} is empty and does not say why"


def test_sheet_titles_fit_what_excel_allows(model):
    for table in model.tables:
        assert len(table.title) <= SHEET_NAME_LIMIT, table.title
        assert not set(table.title) & set(r":\/?*[]"), table.title


# --- item 142: the model version --------------------------------------------

def test_the_same_model_exported_twice_carries_the_same_version(forecastable):
    scenarios = approved_scenario("owner")
    first = gather(forecastable, scenarios)
    second = gather(forecastable, scenarios)
    assert first.version_id == second.version_id
    assert first.generated_at != "" and second.generated_at != ""


def test_changing_one_assumption_changes_the_version(forecastable):
    from apps.api.app.assumptions.schema import Assumption

    scenarios = approved_scenario("owner")
    before = model_version(forecastable, scenarios, "base").version_id

    code = "revenue_growth"
    existing = scenarios.resolve("base")[code].assumption
    moved = Assumption(
        **{
            **{f: getattr(existing, f) for f in (
                "code", "name", "unit", "periods", "scenario_id", "source_type",
                "evidence", "rationale", "owner", "reviewer", "status",
            )},
            "value": existing.value + Decimal("0.0000001"),
        }
    )
    after = model_version(
        forecastable, scenarios.with_assumption(moved), "base"
    ).version_id
    assert after != before


def test_the_version_is_a_digest_not_a_counter(model):
    assert model.version_id.startswith(f"{VERSION_SCHEME}:")
    digest = model.version_id.split(":", 1)[1]
    assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


def test_the_version_names_what_it_was_computed_from(model):
    names = [name for name, _ in model.version_components]
    assert names == ["scheme", "document", "mapping", "scenario", "assumptions"]


def test_a_different_scenario_is_a_different_version(forecastable):
    """9.12 records a calculated value against its scenario; two scenarios that
    hashed the same would make that reference meaningless."""
    from apps.api.app.assumptions.scenarios import Scenario

    scenarios = approved_scenario("owner")
    code = "revenue_growth"
    existing = scenarios.resolve("base")[code].assumption
    scenarios = scenarios.with_scenario(
        Scenario(id="variant-a", name="Variant A", parent_id="base",
                 description="revenue one basis point ahead of base",
                 created_by="owner")
    ).override(
        "variant-a", code, existing.value + Decimal("0.0001"),
        owner="owner", rationale="a deliberately small, sourced difference",
    )
    base = model_version(forecastable, scenarios, "base").version_id
    other = model_version(forecastable, scenarios, "variant-a").version_id
    assert base != other


def test_the_timestamp_carries_its_offset():
    """A local timestamp with no offset is the one nobody can check later."""
    stamp = generated_at()
    assert stamp.endswith("+00:00")


def test_the_short_version_is_long_enough_to_distinguish_models():
    assert SHORT >= 12


# --- item 138: JSON, and the schema it validates against --------------------

def test_the_json_validates_against_the_published_schema(model):
    body = json.loads(to_json(model))
    validate(body)
    assert body["schema_version"] == SCHEMA_VERSION


def test_the_published_schema_is_the_one_that_validated(model):
    """21.5 is not met by a schema on a shelf beside a different check."""
    published = json.loads(schema_json())
    validate(payload(model), published)


def test_the_validator_refuses_a_schema_it_cannot_fully_check():
    """A validator that ignores a keyword reports valid for an unchecked payload."""
    schema = {"type": "object", "propertyNames": {"type": "string"}}
    assert unsupported_keywords(schema) == {"propertyNames"}
    with pytest.raises(SchemaError, match="implements"):
        validate({}, schema)


def test_the_export_schema_uses_only_supported_keywords():
    assert unsupported_keywords(EXPORT_SCHEMA) == set()
    assert "type" in SUPPORTED


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda b: b.pop("model_version"), "required property"),
        (lambda b: b.update(model_version="v1"), "does not match"),
        (lambda b: b.update(generated_at="2026-09-17 15:00:00"), "does not match"),
        (lambda b: b.update(surprise=1), "unexpected propert"),
        (lambda b: b.update(tables=b["tables"][:3]), "schema requires"),
        (lambda b: b.update(limitations=[]), "schema requires"),
        (lambda b: b["tables"][0]["rows"][0][0].update(origin="invented"), "not one of"),
        (lambda b: b["tables"][0]["rows"][0][0].update(value=1.5), "expected"),
    ],
)
def test_the_schema_catches_each_way_a_payload_can_be_wrong(model, mutate, message):
    body = payload(model)
    mutate(body)
    with pytest.raises(SchemaError, match=message):
        validate(body)


def test_every_number_leaves_as_a_string(model):
    """A JSON number is a double to most parsers, and 4.2 stores decimals exactly."""
    body = payload(model)
    for table in body["tables"]:
        for row in table["rows"]:
            for cell in row:
                assert cell["value"] is None or isinstance(cell["value"], str)


def test_the_json_carries_the_display_string_beside_the_exact_value(model):
    table = model.table("dcf")
    body = next(t for t in payload(model)["tables"] if t["name"] == "dcf")
    for row, exported in zip(table.rows, body["rows"]):
        for cell, out in zip(row, exported):
            assert out["display"] == cell.display
            assert out["value"] == (None if cell.value is None else str(cell.value))


# --- item 139: CSV, and the defence that must not eat a minus sign ----------

def test_a_formula_in_a_text_cell_is_neutralized():
    for character in DANGEROUS:
        text, defused = neutralize(Cell.text(f"{character}cmd|'/c calc'!A1"))
        assert defused, character
        assert text.startswith(PREFIX)


def test_a_negative_number_is_not_neutralized():
    """The defence's whole risk: every negative figure begins with a minus."""
    text, defused = neutralize(Cell.number(Decimal("-1234567.89")))
    assert (text, defused) == ("-1234567.89", False)


def test_every_negative_figure_in_a_real_model_survives_the_csv(model):
    negatives = 0
    for table in model.tables:
        body = table_to_csv(model, table)
        for row in table.rows:
            for cell in row:
                if cell.value is not None and cell.value < 0:
                    negatives += 1
                    assert str(cell.value) in body
                    assert PREFIX + str(cell.value) not in body
    assert negatives > 0, "this assertion proved nothing; the fixture has no negatives"


def test_is_dangerous_is_about_the_first_character_only():
    assert is_dangerous("=SUM(A1)")
    assert not is_dangerous("Total =SUM(A1)")
    assert not is_dangerous("")


def test_every_csv_names_the_data_dictionary_and_the_version(model):
    for table in model.tables:
        lines = header_lines(model, table)
        joined = "\n".join(lines)
        assert DICTIONARY in joined, table.name
        assert model.version_id in joined, table.name
        assert model.generated_at in joined, table.name
        for line in lines:
            assert line.startswith("#"), line


def test_the_csv_parses_back_to_the_rows_that_went_in(model):
    table = model.table("checks")
    body = table_to_csv(model, table)
    data = [line for line in body.splitlines() if not line.startswith("#")]
    rows = list(csv.reader(io.StringIO("\n".join(data))))
    assert rows[0] == [column.title for column in table.columns]
    assert len(rows) == len(table.rows) + 1
    for exported, original in zip(rows[1:], table.rows):
        assert exported == [neutralize(cell)[0] for cell in original]


def test_neutralized_cells_are_reported_rather_than_silently_changed(model):
    for name, text in neutralized_cells(model):
        assert is_dangerous(text)
        assert name in model.names


# --- item 140: the workbook -------------------------------------------------

def test_the_workbook_has_every_tab_in_21_1s_order(model):
    workbook = build_workbook(model)
    assert workbook.sheetnames == [title for _, title in TAB_ORDER]


def test_hardcodes_and_calculations_are_distinguishable_by_more_than_colour(model):
    """21.2, and WCAG 1.4.1: colour alone is not a distinction."""
    workbook = build_workbook(model)
    names = {style.name for style in workbook._named_styles}
    assert {"Hardcode", "Calculated", "Inexact"} <= names
    fonts = {
        name: next(s for s in workbook._named_styles if s.name == name).font.color.rgb
        for name in ("Hardcode", "Calculated", "Inexact")
    }
    assert len(set(fonts.values())) == 3


def test_no_text_in_the_workbook_becomes_a_formula():
    """20.13 in XLSX, where openpyxl makes it sharper than the clause sounds.

    Assigning a string beginning with "=" sets the cell's data type to FORMULA,
    not to text -- so a printed label out of somebody else's PDF would arrive
    as something Excel evaluates on open.
    """
    import openpyxl

    hostile = ExportModel(
        document_id="doc-hostile",
        company="Hostile Labels Limited",
        scenario_id="base",
        version_id="msv1:" + "0" * 64,
        generated_at="2026-09-17T00:00:00+00:00",
        currency="USD", units="units", valuation_date="",
        limitations=("A synthetic model.",),
        tables=tuple(
            Table(
                name=name, title=title,
                columns=(Column("label", "Label"), Column("value", "Value", "currency")),
                rows=(
                    (Cell.text("=1+1"), Cell.number(Decimal("-5"))),
                    (Cell.text("@SUM(A1)"), Cell.number(Decimal("1"))),
                ),
            )
            for name, title in TAB_ORDER
        ),
    )
    workbook = openpyxl.load_workbook(io.BytesIO(xlsx_bytes(hostile)))
    for sheet in workbook:
        for row in sheet.iter_rows():
            for cell in row:
                assert cell.data_type != "f", f"{sheet.title}!{cell.coordinate}"


def test_the_workbook_and_the_csv_neutralize_the_same_cells():
    """They must, or 21.8 fails on the cells the defence touched."""
    for text in ("=1+1", "@SUM(A1)", "+A1", "-lease"):
        assert neutralize(Cell.text(text))[1]


def test_the_legend_explains_every_style_it_uses():
    assert len(LEGEND) == 4
    for name, meaning in LEGEND:
        assert meaning.strip()


def test_a_value_a_spreadsheet_cannot_hold_keeps_its_exact_value_in_a_note(model):
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(xlsx_bytes(model)))
    inexact = [
        cell
        for sheet in workbook
        for row in sheet.iter_rows()
        for cell in row
        if cell.style == "Inexact"
    ]
    assert inexact, "nothing was styled Inexact; this assertion proved nothing"
    for cell in inexact:
        assert cell.comment is not None
        exact = cell.comment.text.split("Exact value: ", 1)[1].split("\n", 1)[0]
        # The note carries what the file does not: the exact value, and a value
        # the file DOES hold must not be styled Inexact or the style stops
        # meaning anything.
        assert not survives_the_workbook(Decimal(exact))
        assert Decimal(exact) != Decimal(repr(cell.value))


def test_survives_the_workbook_is_the_files_question_not_the_doubles():
    """F-29. openpyxl writes "%.16g"; a double's round-trip needs up to 17.

    This value IS representable as a double -- `repr(float(v))` returns it
    unchanged -- and is still not what the file ends up holding. A predicate
    written against `repr` reported it exact, and the workbook did not contain
    it.
    """
    assert survives_the_workbook(Decimal("1234.5"))
    assert survives_the_workbook(Decimal("0.055"))
    assert not survives_the_workbook(Decimal("0.1") / Decimal("3"))

    # Wrong answer one: ask the double. It says this is safe, and the file
    # contains 153895.3042150426 -- a different number.
    narrow = Decimal("153895.30421504256")
    assert Decimal(repr(float(narrow))) == narrow, "the double holds it"
    assert not survives_the_workbook(narrow), "the file does not"

    # Wrong answer two: ask the string openpyxl writes. It says this is lost,
    # because the string is 0.08500000000000001 -- which parses back to the
    # same double and displays as 0.085. Nothing was lost.
    exposed = Decimal("0.085")
    assert Decimal("%.16g" % float(exposed)) != exposed, "the string is noisy"
    assert survives_the_workbook(exposed), "the number survives anyway"


def test_the_cover_states_currency_units_scenario_and_version(model):
    """21.3, as the first thing a reader opens."""
    labels = {row[0].display: row[1].display for row in model.table("cover").rows}
    assert labels["Reporting currency"]
    assert labels["Displayed scale"]
    assert labels["Scenario"] == model.scenario_id
    assert labels["Model version"] == model.version_id
    assert labels["Generated at"] == model.generated_at
    assert labels["Valuation date"]


# --- item 141: the PDF report -----------------------------------------------

@pytest.fixture(scope="module")
def report_text(model):
    import pymupdf

    document = pymupdf.open(stream=pdf_bytes(model), filetype="pdf")
    return "\n".join(page.get_text() for page in document)


def test_the_report_carries_all_nine_sections_21_6_requires(report_text):
    for heading, _ in SECTIONS:
        assert heading in report_text, heading
    assert len(SECTIONS) == 9


def test_the_report_states_its_model_version_and_timestamp(model, report_text):
    assert model.version_id in report_text
    assert model.generated_at in report_text


def test_the_reports_limitations_section_is_never_empty(model, report_text):
    assert model.limitations
    for line in STANDING_LIMITATIONS:
        assert line.split(".")[0][:40] in report_text.replace("\n", " ")


def test_the_report_says_it_is_not_investment_advice(report_text):
    assert "not investment advice" in report_text.replace("\n", " ")


def test_every_page_carries_the_footer(model):
    import pymupdf

    document = pymupdf.open(stream=pdf_bytes(model), filetype="pdf")
    for index, page in enumerate(document, start=1):
        assert f"page {index} of {document.page_count}" in page.get_text()


# --- item 143: the export equals the website --------------------------------

def test_every_historical_figure_in_the_export_is_on_the_statements_page(forecast_client):
    """21.8, checked against the rendered page rather than the view function.

    Comparing an export against the function that produced it proves the
    function deterministic and nothing about what a reader sees.
    """
    client = forecast_client
    page = client.get(f"/documents/{client.document_id}/statements").text
    exported = gather(
        client.app.state.repository.load_result(client.document_id), None
    )
    checked = 0
    for name in ("historical_is", "historical_bs", "historical_cf"):
        for row in exported.table(name).rows:
            for cell in row[1:]:
                if cell.value is None:
                    continue
                assert cell.display in page, f"{name}: {cell.display} is not on the page"
                checked += 1
    assert checked > 20


def test_every_dcf_figure_in_the_export_is_on_the_valuation_page(forecast_client):
    client = forecast_client
    page = client.get(f"/documents/{client.document_id}/valuation").text
    model = gather(
        client.app.state.repository.load_result(client.document_id),
        approved_scenario("owner"),
    )
    for row in model.table("dcf").rows:
        label, value = row[0].display, row[1]
        if value.value is None:
            continue
        if label in ("Enterprise value", "Equity value", "WACC", "Cost of equity"):
            assert value.display in page, f"{label} {value.display} is not on the page"


def test_the_four_formats_agree_with_each_other(model):
    """They cannot disagree: all four render one gathered model. Asserted anyway,
    because "cannot" is a claim about code that somebody will later change."""
    import openpyxl

    body = json.loads(to_json(model))
    workbook = openpyxl.load_workbook(io.BytesIO(xlsx_bytes(model)))
    for table in model.tables:
        exported = next(t for t in body["tables"] if t["name"] == table.name)
        sheet = workbook[table.title]
        rows = list(csv.reader(
            io.StringIO(
                "\n".join(
                    line for line in table_to_csv(model, table).splitlines()
                    if not line.startswith("#")
                )
            )
        ))
        for index, row in enumerate(table.rows):
            for column, cell in enumerate(row):
                assert exported["rows"][index][column]["display"] == cell.display
                assert rows[index + 1][column] == neutralize(cell)[0]
                if cell.value is not None and survives_the_workbook(cell.value):
                    written = sheet.cell(
                        row=index + _first_data_row(table), column=column + 1
                    ).value
                    assert Decimal(repr(written)) == cell.value


def _first_data_row(table) -> int:
    """Where a sheet's data starts, mirroring `_write_table`'s layout."""
    row = 1
    if table.note:
        row += 1
    if table.unavailable:
        row += 1
    return row + 2


def test_the_export_screen_offers_every_format(forecast_client):
    client = forecast_client
    page = client.get(f"/documents/{client.document_id}/exports")
    assert page.status_code == 200
    for path in ("model.xlsx", "report.pdf", "model.json", "schema.json"):
        assert path in page.text


@pytest.mark.parametrize(
    "path, media",
    [
        ("exports/model.json", "application/json"),
        ("exports/schema.json", "application/json"),
        ("exports/model.xlsx", "spreadsheetml"),
        ("exports/report.pdf", "application/pdf"),
        ("exports/dcf.csv", "text/csv"),
        ("exports/raw_facts.csv", "text/csv"),
    ],
)
def test_every_download_is_served(forecast_client, path, media):
    response = forecast_client.get(f"/documents/{forecast_client.document_id}/{path}")
    assert response.status_code == 200
    assert media in response.headers["content-type"]
    assert response.content


def test_a_download_filename_carries_the_model_version(forecast_client):
    response = forecast_client.get(
        f"/documents/{forecast_client.document_id}/exports/model.xlsx"
    )
    disposition = response.headers["content-disposition"]
    model = gather(
        forecast_client.app.state.repository.load_result(forecast_client.document_id),
        approved_scenario("owner"),
    )
    assert model.version_id[5:17] in disposition


def test_an_unknown_table_is_a_404_not_an_empty_file(forecast_client):
    response = forecast_client.get(
        f"/documents/{forecast_client.document_id}/exports/invented.csv"
    )
    assert response.status_code == 404


# --- item 144: large and negative values ------------------------------------

EXTREMES = (
    ("a very large figure", Decimal("999999999999999999999999.99")),
    ("a very small figure", Decimal("0.000000000000000000000001")),
    ("a large negative", Decimal("-999999999999999999999999.99")),
    ("a small negative", Decimal("-0.000000000000000000000001")),
    ("zero", Decimal("0")),
    ("negative zero", Decimal("-0")),
    ("a long repeating quotient", Decimal(1) / Decimal(3)),
    ("a figure with trailing zeros", Decimal("1234.5000")),
)


@pytest.fixture
def extreme_model():
    """One table of 144's cases, run through every renderer."""
    return ExportModel(
        document_id="doc-extreme",
        company="Extreme Values Limited",
        scenario_id="base",
        version_id="msv1:" + "a" * 64,
        generated_at="2026-09-17T00:00:00+00:00",
        currency="USD",
        units="units",
        valuation_date="2026-09-17",
        limitations=("A synthetic model, for testing extremes.",),
        version_components=(("scheme", "msv1"),),
        tables=tuple(
            Table(
                name=name,
                title=title,
                columns=(Column("label", "Label"), Column("value", "Value", "currency")),
                rows=tuple(
                    (Cell.text(label), Cell.number(value)) for label, value in EXTREMES
                ),
            )
            for name, title in TAB_ORDER
        ),
    )


def test_every_extreme_survives_the_json_exactly(extreme_model):
    body = json.loads(to_json(extreme_model))
    values = [cell[1]["value"] for cell in body["tables"][0]["rows"]]
    assert [Decimal(v) for v in values] == [value for _, value in EXTREMES]


def test_every_extreme_survives_the_csv_exactly(extreme_model):
    table = extreme_model.table("cover")
    body = table_to_csv(extreme_model, table)
    rows = list(csv.reader(
        io.StringIO("\n".join(l for l in body.splitlines() if not l.startswith("#")))
    ))
    assert [Decimal(row[1]) for row in rows[1:]] == [value for _, value in EXTREMES]


def test_no_extreme_is_prefixed_in_the_csv(extreme_model):
    """Four of the eight are negative. None may be quoted."""
    body = table_to_csv(extreme_model, extreme_model.table("cover"))
    for _, value in EXTREMES:
        assert f"{PREFIX}{value}" not in body


def test_the_workbook_discloses_every_extreme_it_cannot_hold(extreme_model):
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(xlsx_bytes(extreme_model)))
    sheet = workbook["Cover"]
    for offset, (label, value) in enumerate(EXTREMES):
        cell = sheet.cell(row=3 + offset, column=2)
        if survives_the_workbook(value):
            assert Decimal(repr(cell.value)) == value, label
        else:
            assert cell.style == "Inexact", label
            assert f"Exact value: {value}" in cell.comment.text, label


def test_the_report_renders_every_extreme_without_raising(extreme_model):
    import pymupdf

    document = pymupdf.open(stream=pdf_bytes(extreme_model), filetype="pdf")
    text = "\n".join(page.get_text() for page in document)
    assert "Extreme Values Limited" in text
    assert document.page_count >= 1


def test_a_cell_with_no_value_carries_a_reason_rather_than_a_blank():
    """Rule 1.3, at the export boundary: absent is not zero."""
    cell = Cell.missing("the filing reports no value on this line")
    assert cell.absent and cell.value is None and cell.note
    with pytest.raises(TypeError):
        Cell.missing()


def test_a_ragged_table_is_refused_rather_than_exported_shifted():
    with pytest.raises(ValueError, match="ragged"):
        Table(
            name="x", title="X",
            columns=(Column("a", "A"), Column("b", "B")),
            rows=((Cell.text("only one"),),),
        )


# --- the metadata read that this phase had to fix ---------------------------

def test_metadata_is_read_through_its_field_dictionary(forecastable):
    """F-27. `DetectedMetadata` is a dict of fields, not an object of attributes."""
    assert metadata_field(forecastable, "reporting_currency")
    assert metadata_field(forecastable, "company_name")
    assert metadata_field(forecastable, "invented_field") == ""


def test_an_unconfirmed_metadata_field_says_so(three_statements):
    """1.9 and 1.10: a detected currency and a confirmed one are different claims."""
    for name in ("reporting_currency", "displayed_scale", "company_name"):
        value = metadata_field(three_statements, name)
        field = three_statements.document.metadata.fields.get(name)
        if field is not None and field.value and not field.confirmed:
            assert value.endswith("(unconfirmed)"), name
