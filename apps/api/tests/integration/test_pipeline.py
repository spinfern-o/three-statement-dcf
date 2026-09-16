"""Items 26-38 end to end, against the committed fixture PDFs."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.app.extraction.hashing import sha256_hex
from apps.api.app.extraction.jobs import (
    DocumentVerificationState,
    FactVerificationState,
    JobState,
)
from apps.api.app.extraction.pages import PageKind
from apps.api.app.extraction.parsing import NumberLocale
from apps.api.app.extraction.reasons import ReasonCode
from apps.api.app.extraction.records import Scope, confirm_metadata
from apps.api.tests.conftest import (
    ENCRYPTED,
    EU_LOCALE,
    IMAGE_ONLY,
    MIXED,
    NOT_A_PDF,
    PARTLY_SCANNED,
    STATEMENTS,
    TRUNCATED,
)


# --- refusals ---------------------------------------------------------------

@pytest.mark.parametrize(
    "fixture, code",
    [
        (NOT_A_PDF, "ING-010-01"),
        (TRUNCATED, "ING-010-02"),
        (ENCRYPTED, "ING-010-04"),
        (IMAGE_ONLY, "ING-010-07"),
        (PARTLY_SCANNED, "ING-010-08"),
    ],
)
def test_each_refusal_names_its_rule(ingest_fixture, fixture, code):
    outcome = ingest_fixture(fixture)
    assert not outcome.accepted
    assert outcome.refusal.reason.code == code
    assert outcome.job.state is JobState.REFUSED
    assert outcome.job.refusal_code == code


def test_a_scanned_page_names_the_page_rather_than_being_skipped(ingest_fixture):
    """Item 31 under decision 2.3.c: refuse loudly, do not extract silently."""
    outcome = ingest_fixture(PARTLY_SCANNED)
    assert "page(s) 2" in outcome.refusal.detail
    assert "2.3.c" in outcome.refusal.detail


def test_a_refused_upload_still_has_a_job_history(ingest_fixture):
    outcome = ingest_fixture(NOT_A_PDF)
    assert outcome.job.history
    assert outcome.job.history[-1].to_state is JobState.REFUSED


# --- the accepted path ------------------------------------------------------

def test_the_statements_fixture_extracts(extracted):
    assert extracted.document.page_count == 3
    assert extracted.document.extraction_status is JobState.EXTRACTED
    assert len(extracted.tables) == 3
    assert len(extracted.facts) == 50


def test_page_classification(extracted):
    assert [p.kind for p in extracted.document.pages] == [PageKind.TEXT_NATIVE] * 3


def test_a_mixed_page_is_extracted_and_the_gap_recorded(ingest_fixture):
    outcome = ingest_fixture(MIXED)
    assert outcome.accepted
    result = outcome.result
    assert result.document.pages[0].kind is PageKind.MIXED
    assert all(
        ReasonCode.IMAGE_REGION_NOT_EXTRACTED in f.reason_codes for f in result.facts
    )


def test_every_fact_has_a_page_and_a_box(extracted):
    """10.9 and acceptance criterion 24.3: no value without a location."""
    for fact in extracted.facts:
        location = extracted.location(fact.source_location_id)
        assert location is not None
        assert location.page_number >= 1
        assert location.bounding_box.width > 0


def test_every_fact_retains_the_printed_string(extracted):
    """10.25: raw strings before numeric parsing, and both are kept."""
    for fact in extracted.facts:
        assert fact.raw_value == fact.parsed.raw_value


def test_no_fact_starts_verified(extracted):
    for fact in extracted.facts:
        assert fact.verification_status is FactVerificationState.UNVERIFIED


def test_metadata_starts_unconfirmed(extracted):
    """10.11, without exception -- including the fields that are obviously right."""
    assert extracted.document.verification_status is DocumentVerificationState.UNCONFIRMED
    for name, field in extracted.document.metadata.fields.items():
        assert not field.confirmed, name
    assert "displayed_scale" in extracted.document.metadata.unconfirmed_required


def test_the_detected_values_are_the_right_ones(extracted):
    fields = extracted.document.metadata.fields
    assert fields["displayed_scale"].value == "thousands"
    assert fields["reporting_currency"].value == "USD"
    assert fields["reporting_period_end"].value == "2025-12-31"
    assert fields["audited_status"].value == "audited"
    assert fields["accounting_standard"].value == "US_GAAP"
    assert fields["number_locale"].value == "dot_decimal"


def test_detected_metadata_carries_its_evidence(extracted):
    field = extracted.document.metadata.fields["displayed_scale"]
    assert field.evidence is not None
    assert field.evidence.page_number == 1
    assert "thousands" in field.evidence.matched_text


def test_scope_is_read_from_the_statement_caption(extracted):
    """10.23. Rule 1.11 forbids mixing consolidated and segment figures."""
    assert {f.scope for f in extracted.facts} == {Scope.CONSOLIDATED}


def test_column_periods_are_resolved(extracted):
    assert {f.period_label for f in extracted.facts} == {"2025", "2024"}


# --- rule 1.5, on a real page -----------------------------------------------

def _fact(result, label, period):
    for f in result.facts:
        if f.raw_label == label and f.period_label == period:
            return f
    raise AssertionError(f"no fact for {label!r} {period}")


def test_an_em_dash_on_the_page_does_not_become_zero(extracted):
    fact = _fact(extracted, "Restructuring charges", "2025")
    assert fact.raw_value == "—"
    assert fact.value is None
    assert ReasonCode.DASH_AMBIGUOUS in fact.reason_codes


def test_an_n_a_on_the_page_does_not_become_zero(extracted):
    fact = _fact(extracted, "Goodwill", "2025")
    assert fact.raw_value == "N/A"
    assert fact.value is None


def test_a_footnote_marker_does_not_change_the_number(extracted):
    fact = _fact(extracted, "Restructuring charges", "2024")
    assert fact.raw_value == "(12,000)¹"
    assert ReasonCode.FOOTNOTE_MARKER_STRIPPED in fact.reason_codes


# --- 10.13 and 10.35 --------------------------------------------------------

def test_everything_is_blocked_until_the_metadata_is_confirmed(extracted):
    assert len(extracted.facts_needing_review) == len(extracted.facts)
    for fact in extracted.facts:
        assert ReasonCode.SCALE_UNCONFIRMED in fact.reason_codes
        assert ReasonCode.CURRENCY_UNCONFIRMED in fact.reason_codes


def test_confirming_metadata_re_runs_what_depends_on_it(extracted):
    """10.35: after an approved change, dependent work re-runs."""
    detected = {
        name: None
        for name, field in extracted.document.metadata.fields.items()
        if field.value is not None
    }
    after = confirm_metadata(extracted, detected, actor="owner", reason="checked the cover page")

    assert after.document.verification_status is DocumentVerificationState.CONFIRMED
    assert _fact(after, "Revenue", "2025").value == Decimal("1250000")
    assert _fact(after, "Cost of goods sold", "2025").value == Decimal("-750000")

    # What remains blocked is exactly rule 1.5's three ambiguous cells.
    blocked = after.facts_needing_review
    assert len(blocked) == 3
    assert {f.raw_value for f in blocked} == {"—", "–", "N/A"}


def test_confirming_the_locale_alone_does_not_clear_the_scale(extracted):
    from apps.api.app.extraction.records import reparse_with_locale

    after = reparse_with_locale(
        extracted, NumberLocale.DOT_DECIMAL, actor="owner", reason="US filing"
    )
    fact = _fact(after, "Gross profit", "2025")
    assert fact.value == Decimal("500000")
    assert ReasonCode.SCALE_UNCONFIRMED in fact.reason_codes
    assert after.document.verification_status is DocumentVerificationState.IN_REVIEW


def test_confirmation_is_recorded_in_the_audit_log(extracted):
    after = confirm_metadata(
        extracted, {"displayed_scale": None}, actor="owner", reason="page 1 says thousands"
    )
    actions = [e.action for e in after.audit]
    assert "confirm_metadata" in actions and "revalidate" in actions
    assert any("page 1 says thousands" in e.detail for e in after.audit)


def test_an_audit_entry_without_a_reason_is_refused():
    from apps.api.app.extraction.records import AuditEvent

    with pytest.raises(ValueError):
        AuditEvent.create(
            actor="owner", action="accept", entity_type="Fact", entity_id="f", detail="  "
        )


def test_a_correction_replaces_the_detected_value(extracted):
    after = confirm_metadata(
        extracted,
        {"company_name": "Example Industries plc"},
        actor="owner",
        reason="the cover prints it in capitals",
    )
    field = after.document.metadata.fields["company_name"]
    assert field.value == "Example Industries plc"
    assert field.confirmed


# --- the EU fixture ---------------------------------------------------------

def test_the_same_machinery_reads_a_comma_decimal_filing(ingest_fixture):
    outcome = ingest_fixture(EU_LOCALE)
    assert outcome.accepted
    result = outcome.result
    assert result.document.metadata.fields["number_locale"].value == "comma_decimal"
    confirmed = confirm_metadata(
        result,
        {
            name: None
            for name, f in result.document.metadata.fields.items()
            if f.value is not None
        },
        actor="owner",
        reason="German filing, confirmed",
    )
    assert _fact(confirmed, "Umsatzerloese", "2025").value == Decimal("1250000")
    assert _fact(confirmed, "Steuerquote", "2025").value == Decimal("25.5")


# --- 10.3, 10.2, item 38 ----------------------------------------------------

def test_a_duplicate_upload_is_refused(ingest_fixture, repository):
    first = ingest_fixture(STATEMENTS)
    repository.save(first.result)
    second = ingest_fixture(STATEMENTS)
    assert not second.accepted
    assert second.refusal.reason.code == "ING-010-03"


def test_a_different_company_is_not_a_duplicate(ingest_fixture, repository):
    first = ingest_fixture(STATEMENTS, company_id="co-1")
    repository.save(first.result)
    second = ingest_fixture(STATEMENTS, company_id="co-2")
    assert second.accepted


def test_a_linked_duplicate_is_permitted_with_a_reason(ingest_fixture, repository):
    first = ingest_fixture(STATEMENTS)
    repository.save(first.result)
    second = ingest_fixture(
        STATEMENTS, allow_linked_duplicate=True, link_reason="reissued under a new cover"
    )
    assert second.accepted
    assert second.result.document.duplicate_of == first.result.document.id


def test_item_38_the_uploaded_pdf_is_unchanged(ingest_fixture, store):
    """The bytes on disk hash to the bytes uploaded, after the whole pipeline."""
    original = Path(STATEMENTS).read_bytes()
    before = sha256_hex(original)
    outcome = ingest_fixture(STATEMENTS)
    assert outcome.result.document.immutable_hash == before
    assert store.verify(before)
    assert store.read(before) == original
    assert Path(STATEMENTS).read_bytes() == original


# --- persistence ------------------------------------------------------------

def test_records_round_trip_through_storage(extracted, repository):
    repository.save(extracted)
    loaded = repository.load(extracted.document.id)
    assert len(loaded["facts"]) == len(extracted.facts)
    assert loaded["document"]["immutable_hash"] == extracted.document.immutable_hash


def test_every_stored_number_is_a_string(extracted, repository):
    """4.2: decimal strings at boundaries, never a float in the record."""
    path = repository.save(extracted)
    text = path.read_text()
    loaded = repository.load(extracted.document.id)
    for fact in loaded["facts"]:
        assert fact["parsed"]["value"] is None or isinstance(fact["parsed"]["value"], str)
        assert isinstance(fact["confidence"]["score"], str)
    assert "1250000" in text


def test_a_float_is_refused_by_the_serializer():
    from apps.api.app.persistence.json_store import SerializationError, _jsonable

    with pytest.raises(SerializationError):
        _jsonable({"value": 1.5})
