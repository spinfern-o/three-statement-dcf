"""Items 45-48: the reviewer actions, their refusals, and the audit trail."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.extraction.jobs import FactVerificationState
from apps.api.app.extraction.reasons import ReasonCode
from apps.api.app.extraction.records import confirm_metadata
from apps.api.app.review.actions import (
    ReviewError,
    accept_fact,
    correct_fact,
    reject_fact,
)
from apps.api.app.review.progress import (
    is_review_complete,
    is_verified,
    review_progress,
    verification_gates,
)


@pytest.fixture
def confirmed(extracted):
    """The statements fixture with its detected metadata confirmed."""
    detected = {
        name: None
        for name, field in extracted.document.metadata.fields.items()
        if field.value is not None
    }
    return confirm_metadata(extracted, detected, actor="owner", reason="checked the cover page")


def _fact(result, label, period="2025"):
    for f in result.facts:
        if f.raw_label == label and f.period_label == period:
            return f
    raise AssertionError(f"no fact {label!r} {period}")


# --- item 46: a reason is not optional --------------------------------------

@pytest.mark.parametrize("call", ["accept", "reject"])
def test_a_decision_without_a_reason_is_refused(confirmed, call):
    fact = _fact(confirmed, "Revenue")
    action = {"accept": accept_fact, "reject": reject_fact}[call]
    with pytest.raises(ReviewError) as exc:
        action(confirmed, fact.id, actor="owner", reason="   ")
    assert "reason is required" in str(exc.value)


def test_a_correction_without_a_reason_is_refused(confirmed):
    fact = _fact(confirmed, "Revenue")
    with pytest.raises(ReviewError):
        correct_fact(confirmed, fact.id, "1", actor="owner", reason="")


# --- item 45: what each action does -----------------------------------------

def test_accepting_records_the_decision_and_resolves_the_codes(confirmed):
    fact = _fact(confirmed, "Revenue")
    after = accept_fact(confirmed, fact.id, actor="owner", reason="matches page 2 line 1")
    updated = _fact(after, "Revenue")
    assert updated.verification_status is FactVerificationState.ACCEPTED
    assert updated.decision.action == "accept"
    assert updated.decision.reason == "matches page 2 line 1"
    assert not updated.blocking_codes


def test_accepting_a_fact_with_no_value_is_refused(confirmed):
    """Rule 1.5: a dash becomes zero only when someone says so, in words."""
    fact = _fact(confirmed, "Restructuring charges")
    assert fact.value is None
    with pytest.raises(ReviewError) as exc:
        accept_fact(confirmed, fact.id, actor="owner", reason="it is zero")
    assert "no value to accept" in str(exc.value)
    assert "correct it" in str(exc.value)


def test_accepting_while_the_scale_is_unconfirmed_is_refused(extracted):
    """10.11-10.13: scale and currency are confirmed on the document, once."""
    fact = _fact(extracted, "Revenue")
    with pytest.raises(ReviewError) as exc:
        accept_fact(extracted, fact.id, actor="owner", reason="looks right")
    assert "SCALE_UNCONFIRMED" in str(exc.value)


def test_correcting_supplies_a_value_without_overwriting_the_evidence(confirmed):
    """10.25: the raw string and its parse are evidence, and evidence is not edited."""
    fact = _fact(confirmed, "Restructuring charges")
    after = correct_fact(
        confirmed, fact.id, "0",
        actor="owner", reason="the legend on page 2 defines the dash as nil",
    )
    updated = _fact(after, "Restructuring charges")
    assert updated.value == Decimal("0")
    assert updated.corrected_value == Decimal("0")
    assert updated.parsed.value is None            # untouched
    assert updated.raw_value == "—"           # untouched
    assert updated.verification_status is FactVerificationState.CORRECTED


def test_a_corrected_value_must_be_a_decimal_string(confirmed):
    fact = _fact(confirmed, "Revenue")
    with pytest.raises(ReviewError):
        correct_fact(confirmed, fact.id, "about a million", actor="owner", reason="eyeball")


def test_a_float_correction_is_refused(confirmed):
    """4.2. Accepting 0.1 as a float would store 0.1000000000000000055511151231."""
    fact = _fact(confirmed, "Revenue")
    with pytest.raises(ReviewError) as exc:
        correct_fact(confirmed, fact.id, 1234.5, actor="owner", reason="typed it")
    assert "decimal string" in str(exc.value)


def test_rejecting_resolves_nothing(confirmed):
    """A rejected fact is out, not fixed. Its codes stand as the record."""
    fact = _fact(confirmed, "Goodwill")
    after = reject_fact(confirmed, fact.id, actor="owner", reason="the filer does not report goodwill")
    updated = _fact(after, "Goodwill")
    assert updated.verification_status is FactVerificationState.REJECTED
    assert updated.resolutions == ()
    assert updated.blocking_codes


def test_a_decision_can_be_changed_and_the_old_one_is_named(confirmed):
    """1.13 asks for an audit entry, not for the decision to be frozen."""
    fact = _fact(confirmed, "Revenue")
    after = accept_fact(confirmed, fact.id, actor="owner", reason="first look")
    after = reject_fact(after, fact.id, actor="owner", reason="this row is a subtotal, not a line")
    assert _fact(after, "Revenue").verification_status is FactVerificationState.REJECTED
    assert any("replacing an earlier decision" in e.detail for e in after.audit)


# --- item 47: the audit log -------------------------------------------------

def test_every_action_writes_an_audit_entry(confirmed):
    before = len(confirmed.audit)
    after = accept_fact(confirmed, _fact(confirmed, "Revenue").id, actor="owner", reason="checked")
    after = reject_fact(after, _fact(after, "Goodwill").id, actor="owner", reason="not reported")
    assert len(after.audit) == before + 2
    assert all(e.detail.strip() for e in after.audit)


def test_the_audit_entry_names_the_resolved_codes(confirmed):
    fact = _fact(confirmed, "Restructuring charges")
    after = correct_fact(confirmed, fact.id, "0", actor="owner", reason="page 2 legend")
    entry = after.audit[-1]
    assert ReasonCode.DASH_AMBIGUOUS.value in entry.detail


# --- item 48: progress, and what it must not claim --------------------------

def test_progress_counts_what_is_done(confirmed):
    after = accept_fact(confirmed, _fact(confirmed, "Revenue").id, actor="owner", reason="checked")
    after = reject_fact(after, _fact(after, "Goodwill").id, actor="owner", reason="not reported")
    progress = review_progress(after)
    assert progress.accepted == 1 and progress.rejected == 1
    assert progress.decided == 2
    assert progress.undecided == progress.total - 2


def test_progress_never_reports_a_verified_fact(confirmed):
    """Rule 1.14: an unresolved requirement must not appear as PASS."""
    after = confirmed
    for fact in confirmed.facts:
        if fact.value is not None:
            after = accept_fact(after, fact.id, actor="owner", reason="checked against the page")
    progress = review_progress(after)
    assert progress.verified == 0
    assert progress.review_complete > 0


def test_the_seventh_condition_is_the_mapping(confirmed):
    """Phase 4 can satisfy conditions 1-6. The seventh is Phase 5's approval."""
    after = accept_fact(confirmed, _fact(confirmed, "Revenue").id, actor="owner", reason="checked")
    gates = verification_gates(_fact(after, "Revenue"), after)
    unmet = [g for g in gates if not g.met]
    assert [g.number for g in unmet] == [7]
    assert "mapping set" in unmet[0].detail
    assert is_review_complete(_fact(after, "Revenue"), after)
    assert not is_verified(_fact(after, "Revenue"), after)


def test_percent_decided_floors_rather_than_rounding_up(confirmed):
    """99.6% must not display as 100%."""
    after = confirmed
    for fact in confirmed.facts[:-1]:
        if fact.value is not None:
            after = accept_fact(after, fact.id, actor="owner", reason="checked")
        else:
            after = reject_fact(after, fact.id, actor="owner", reason="not a number")
    progress = review_progress(after)
    assert progress.decided == progress.total - 1
    assert progress.percent_decided == 98


# --- 10.35, the uncomfortable half ------------------------------------------

def test_a_reparse_withdraws_an_acceptance_of_a_value_that_changed(extracted):
    """An acceptance is of a number. If the number changes, so must the acceptance."""
    from apps.api.app.extraction.records import DOCUMENT_CODES

    # "1,250,000" parses under an unconfirmed locale; confirm only the scale and
    # currency so the fact becomes acceptable without the locale being settled.
    partly = confirm_metadata(
        extracted,
        {"displayed_scale": None, "reporting_currency": None},
        actor="owner", reason="page 1 states both",
    )
    fact = _fact(partly, "Revenue")
    assert not any(c in DOCUMENT_CODES for c in fact.blocking_codes)
    accepted = accept_fact(partly, fact.id, actor="owner", reason="matches the page")
    assert _fact(accepted, "Revenue").decision is not None

    # Now confirm the locale as comma-decimal, which reads 1,250,000 differently.
    reparsed = confirm_metadata(
        accepted, {"number_locale": "comma_decimal"},
        actor="owner", reason="testing the invalidation path",
    )
    updated = _fact(reparsed, "Revenue")
    assert updated.decision is None
    assert updated.verification_status is FactVerificationState.UNVERIFIED
    assert any("withdrawn" in e.detail for e in reparsed.audit)


def test_a_correction_survives_a_reparse(confirmed):
    """The reviewer supplied that number. A re-parse does not overrule them."""
    fact = _fact(confirmed, "Restructuring charges")
    corrected = correct_fact(confirmed, fact.id, "0", actor="owner", reason="page 2 legend")
    after = confirm_metadata(
        corrected, {"company_name": "Example Industries plc"},
        actor="owner", reason="the cover prints it in capitals",
    )
    updated = _fact(after, "Restructuring charges")
    assert updated.value == Decimal("0")
    assert updated.decision is not None
