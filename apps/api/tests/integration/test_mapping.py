"""Phase 5 end to end: items 50-58, on the committed fixture filing.

The single most important assertion in this file is
`test_a_fully_mapped_document_produces_verified_facts`. Through Phase 4 no fact
in this system could reach VERIFIED, because source-policy.md §9's seventh
condition is a human-approved mapping and there was no mapping stage. That test
is the first time the whole chain closes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.extraction.reasons import ReasonCode
from apps.api.app.extraction.records import confirm_metadata
from apps.api.app.mapping.actions import (
    approve_all,
    approve_fact_mapping,
    combine_facts,
    map_fact,
    propose_all,
    reject_mapping,
    split_fact,
)
from apps.api.app.mapping.checks import (
    all_findings,
    apply_findings,
    duplicate_counting,
    subtotal_reconciliation,
)
from apps.api.app.mapping.normalized import normalize
from apps.api.app.mapping.sets import MappingError, MappingType
from apps.api.app.review.actions import accept_fact, correct_fact
from apps.api.app.review.progress import review_progress, verification_gates
from model import accounts

OPEX_LABELS = {
    "Selling, general and administrative",
    "Research and development",
    "Restructuring charges",
}


def _fact(result, label, period="2025"):
    for fact in result.facts:
        if fact.raw_label == label and fact.period_label == period:
            return fact
    raise AssertionError(f"no fact {label!r} {period}")


@pytest.fixture
def reviewed(extracted):
    """Metadata confirmed, every rule-1.5 cell resolved, every fact decided."""
    result = confirm_metadata(
        extracted,
        {
            name: None
            for name, field in extracted.document.metadata.fields.items()
            if field.value is not None
        },
        actor="owner",
        reason="checked the cover page",
    )
    for fact in list(result.facts):
        if fact.raw_value in ("—", "–", "N/A"):
            result = correct_fact(
                result, fact.id, "0", actor="owner", reason="the filer reports nil here"
            )
    for fact in list(result.facts):
        if fact.value is not None and fact.decision is None:
            result = accept_fact(
                result, fact.id, actor="owner", reason="matches the printed page"
            )
    return result


@pytest.fixture
def proposed(reviewed):
    return apply_findings(propose_all(reviewed))


@pytest.fixture
def mapped(proposed):
    """Aggregated, approved, and reconciled. The finished state."""
    result = proposed
    for period in ("2025", "2024"):
        ids = [
            f.id for f in result.facts
            if f.raw_label in OPEX_LABELS and f.period_label == period
        ]
        result = combine_facts(
            result, ids, accounts.OPERATING_EXPENSES, actor="owner",
            note="the filer presents three operating expense categories; the chart has one line",
        )
    result = approve_all(result, actor="owner", note="each label matches the canonical definition")
    return apply_findings(result)


# --- item 51: proposals -----------------------------------------------------

def test_proposals_cover_the_statement_lines_and_skip_the_traps(proposed):
    mapped_labels = {
        _label(proposed, m.reported_fact_id) for m in proposed.mappings.mappings
    }
    assert "Revenue" in mapped_labels
    assert "Total assets" in mapped_labels
    assert "Total current assets" not in mapped_labels
    assert "Total liabilities and equity" not in mapped_labels


def _label(result, fact_id):
    return next(f.raw_label for f in result.facts if f.id == fact_id)


def test_no_proposal_is_approved(proposed):
    """11.11. The machine proposes; a person approves."""
    assert len(proposed.mappings.unapproved) == len(proposed.mappings.mappings)
    assert review_progress(proposed).verified == 0


def test_proposing_twice_does_not_duplicate(proposed):
    again = propose_all(proposed)
    assert len(again.mappings.mappings) == len(proposed.mappings.mappings)


# --- item 54: 11.6 ----------------------------------------------------------

def test_three_expense_lines_on_one_canonical_line_is_flagged(proposed):
    """Until it is declared an aggregate, it is two figures added where one
    was reported."""
    findings = duplicate_counting(proposed)
    assert findings
    assert all(f.code is ReasonCode.DOUBLE_COUNTED for f in findings)
    assert accounts.OPERATING_EXPENSES in {f.canonical_code for f in findings}


def test_a_double_counting_mapping_cannot_be_approved(proposed):
    """11.6 says prevent, not report."""
    fact = _fact(proposed, "Research and development")
    with pytest.raises(MappingError) as exc:
        approve_fact_mapping(proposed, fact.id, actor="owner", note="ok")
    assert "double-count" in str(exc.value)


def test_declaring_the_aggregation_clears_it(mapped):
    """11.5: show the aggregation, and it stops being a double count."""
    assert duplicate_counting(mapped) == ()
    value = normalize(mapped)[(accounts.OPERATING_EXPENSES, "2025")]
    assert len(value.contributors) == 3
    assert value.mapping_type is MappingType.AGGREGATE


def test_mapping_one_fact_to_a_subtotal_and_its_component_is_refused(mapped):
    """A figure counted directly and again through a subtotal."""
    fact = _fact(mapped, "Revenue")
    broken = mapped.mappings.add(
        mapped.mappings.for_fact(fact.id)[0],
        actor="owner", reason="deliberately duplicated for the test",
    )
    findings = duplicate_counting(mapped, broken)
    assert any(f.code is ReasonCode.DOUBLE_COUNTED for f in findings)


# --- item 55: 11.7 ----------------------------------------------------------

def test_every_subtotal_reconciles_on_a_correctly_mapped_filing(mapped):
    assert subtotal_reconciliation(mapped) == ()
    assert all_findings(mapped) == ()


def _misaggregate(result):
    """Fold interest expense into cost of sales -- a reviewer's plausible error.

    Note what does NOT work as a test here: remapping a required component
    somewhere else makes it *absent*, and an absent component correctly skips
    the check rather than failing it (STEP 5: absent is unknown, not zero). To
    make a subtotal disagree you have to leave every component present and get
    one of them wrong, which is exactly the error worth catching.
    """
    ids = [_fact(result, "Cost of goods sold").id, _fact(result, "Interest expense").id]
    return combine_facts(
        result, ids, accounts.COGS, actor="owner",
        note="deliberately wrong, for the test",
    )


def test_a_line_mapped_to_the_wrong_canonical_code_breaks_a_subtotal(mapped):
    """The check that makes a mapping error visible instead of plausible."""
    findings = subtotal_reconciliation(_misaggregate(mapped))
    assert findings
    assert findings[0].code is ReasonCode.SUBTOTAL_MISMATCH
    assert findings[0].canonical_code == accounts.GROSS_PROFIT
    assert "do not plug it" in findings[0].message.lower()


def test_a_mismatch_is_reported_never_corrected(mapped):
    """12.4 and STEP 6 agree: report the difference, do not plug it."""
    ledger = normalize(apply_findings(_misaggregate(mapped)))
    assert ledger[(accounts.GROSS_PROFIT, "2025")].value == Decimal("500000")
    assert ledger[(accounts.COGS, "2025")].value == Decimal("768000")


def test_a_mismatch_lands_on_the_facts_that_caused_it(mapped):
    """10.30: a fact failing a reconciliation goes to review, by name."""
    broken = apply_findings(_misaggregate(mapped))
    implicated = {
        f.raw_label for f in broken.facts if ReasonCode.SUBTOTAL_MISMATCH in f.mapping_codes
    }
    assert "Gross profit" in implicated
    assert "Interest expense" in implicated


def test_an_absent_component_skips_the_check_rather_than_assuming_zero(mapped):
    """STEP 5: an absent line is unknown, not zero. Total assets needs
    `other_current_assets`, which this filing does not report."""
    ledger = normalize(mapped)
    assert (accounts.OTHER_CURRENT_ASSETS, "2025") not in ledger
    assert not [f for f in subtotal_reconciliation(mapped)
                if f.canonical_code == accounts.TOTAL_ASSETS]


# --- item 53: split and combine --------------------------------------------

def test_a_split_must_account_for_the_whole_value(mapped):
    fact = _fact(mapped, "Revenue")
    with pytest.raises(MappingError) as exc:
        split_fact(
            mapped, fact.id,
            [(accounts.REVENUE, "1000000"), (accounts.OTHER_INCOME_EXPENSE, "1")],
            basis="note 3", actor="owner", note="test",
        )
    assert "account for the whole printed value" in str(exc.value)


def test_a_split_needs_the_disclosure_it_rests_on(mapped):
    """11.4: keep it combined UNLESS the notes provide a defensible split."""
    fact = _fact(mapped, "Revenue")
    with pytest.raises(MappingError) as exc:
        split_fact(
            mapped, fact.id,
            [(accounts.REVENUE, "1250000"), (accounts.OTHER_INCOME_EXPENSE, "0")],
            basis="  ", actor="owner", note="test",
        )
    assert "11.4" in str(exc.value)


def test_a_valid_split_records_its_parts_and_its_basis(mapped):
    fact = _fact(mapped, "Revenue")
    after = split_fact(
        mapped, fact.id,
        [(accounts.REVENUE, "1200000"), (accounts.OTHER_INCOME_EXPENSE, "50000")],
        basis="note 3 separates 50,000 of royalty income from product revenue",
        actor="owner", note="royalties are not revenue from contracts with customers",
    )
    mappings = after.mappings.for_fact(fact.id)
    assert len(mappings) == 2
    assert all(m.mapping_type is MappingType.SPLIT for m in mappings)
    assert sum(m.allocation_amount for m in mappings) == fact.value
    assert all("note 3" in m.allocation_basis for m in mappings)


def test_a_split_of_an_unparsed_fact_is_refused(reviewed, extracted):
    """There is nothing to divide."""
    result = propose_all(extracted)
    fact = next(f for f in result.facts if f.value is None)
    with pytest.raises(MappingError) as exc:
        split_fact(result, fact.id, [("revenue", "1"), ("cogs", "1")],
                   basis="note", actor="owner", note="test")
    assert "nothing to divide" in str(exc.value)


def test_combining_across_periods_is_refused(proposed):
    """Rule 1.7."""
    ids = [
        _fact(proposed, "Revenue", "2025").id,
        _fact(proposed, "Revenue", "2024").id,
    ]
    with pytest.raises(MappingError) as exc:
        combine_facts(proposed, ids, accounts.REVENUE, actor="owner", note="test")
    assert "1.7" in str(exc.value)


# --- item 56: approval, and what it unlocks ---------------------------------

def test_a_fully_mapped_document_produces_verified_facts(mapped):
    """The first VERIFIED facts in this system. All seven conditions of §9."""
    progress = review_progress(mapped)
    assert progress.verified > 0
    assert progress.verified == progress.mapped_and_approved
    gates = verification_gates(_fact(mapped, "Revenue"), mapped)
    assert all(g.met for g in gates), [g.describe() for g in gates if not g.met]


def test_the_unmapped_lines_are_the_ones_with_no_canonical_home(mapped):
    progress = review_progress(mapped)
    assert progress.unmapped == 4  # two labels, two periods
    unmapped = {
        f.raw_label for f in mapped.facts if not mapped.mappings.for_fact(f.id)
    }
    assert unmapped == {"Total current assets", "Total liabilities and equity"}


def test_an_excluded_line_is_reviewed_and_out_of_the_model(mapped):
    fact = _fact(mapped, "Total current assets")
    after = reject_mapping(
        mapped, fact.id, actor="owner",
        note="the chart has no current-total line; this is a subtotal of part of the balance sheet",
    )
    after = approve_fact_mapping(after, fact.id, actor="owner", note="confirmed, not a chart line")
    progress = review_progress(after)
    assert progress.excluded >= 1
    assert not after.mappings.is_approved(fact.id)
    assert (accounts.TOTAL_ASSETS, "2025") in normalize(after)  # unaffected


def test_mapping_a_fact_rejected_in_source_review_is_refused(reviewed):
    from apps.api.app.review.actions import reject_fact

    fact = _fact(reviewed, "Revenue")
    rejected = reject_fact(reviewed, fact.id, actor="owner", reason="this row is a heading")
    with pytest.raises(MappingError) as exc:
        map_fact(rejected, fact.id, accounts.REVENUE, actor="owner", note="test")
    assert "rejected in source review" in str(exc.value)


# --- item 58: invalidation --------------------------------------------------

def test_changing_a_mapping_withdraws_its_approval(mapped):
    """11.12. The approval was of a different mapping."""
    fact = _fact(mapped, "Revenue")
    assert mapped.mappings.is_approved(fact.id)
    after = map_fact(mapped, fact.id, accounts.COGS, actor="owner", note="changed my mind")
    assert not after.mappings.is_approved(fact.id)
    assert review_progress(after).verified < review_progress(mapped).verified


def test_changing_a_mapping_makes_a_new_version_and_keeps_the_old(mapped):
    before = mapped.mappings.version
    after = map_fact(mapped, _fact(mapped, "Revenue").id, accounts.COGS,
                     actor="owner", note="changed my mind")
    assert after.mappings.version == before + 1
    assert after.mappings.supersedes == before


def test_a_stale_finding_does_not_survive_the_fix(mapped):
    """11.12's invalidation: findings are recomputed, never accumulated."""
    broken = apply_findings(_misaggregate(mapped))
    assert any(f.mapping_codes for f in broken.facts)

    fixed = apply_findings(
        map_fact(broken, _fact(broken, "Interest expense").id, accounts.INTEREST_EXPENSE,
                 actor="owner", note="put it back where it belongs")
    )
    assert not any(f.mapping_codes for f in fixed.facts)
    assert all_findings(fixed) == ()


def test_applying_findings_twice_changes_nothing(mapped):
    assert apply_findings(apply_findings(mapped)).facts == apply_findings(mapped).facts


# --- persistence ------------------------------------------------------------

def test_mappings_survive_a_round_trip(mapped, repository):
    repository.save(mapped)
    back = repository.load_result(mapped.document.id)
    assert back == mapped
    assert back.mappings.version == mapped.mappings.version
    assert review_progress(back).verified == review_progress(mapped).verified
