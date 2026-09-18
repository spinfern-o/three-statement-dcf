"""Item 36: reason codes and the confidence model."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.extraction.reasons import (
    ADVISORY_CODES,
    ALL_EVIDENCE,
    BLOCKING_CODES,
    EVIDENCE_COUNT,
    EvidenceCheck,
    ReasonCode,
    has_blocking,
    score_confidence,
)


def test_every_code_is_either_blocking_or_advisory():
    assert set(ReasonCode) == BLOCKING_CODES | ADVISORY_CODES
    assert not BLOCKING_CODES & ADVISORY_CODES


def test_every_code_cites_a_rule():
    for code in ReasonCode:
        assert code.rule, code.name
        assert code.summary, code.name


@pytest.mark.parametrize(
    "code",
    [
        ReasonCode.BLANK_CELL,
        ReasonCode.DASH_AMBIGUOUS,
        ReasonCode.NOT_APPLICABLE,
        ReasonCode.SEPARATOR_AMBIGUOUS,
        ReasonCode.SCALE_UNCONFIRMED,
        ReasonCode.CURRENCY_UNCONFIRMED,
        ReasonCode.SUBTOTAL_MISMATCH,
        ReasonCode.CROSS_STATEMENT_MISMATCH,
    ],
)
def test_source_policy_blocking_codes_block(code):
    assert code.blocking
    assert has_blocking([ReasonCode.OCR_DERIVED, code])


def test_10_30_is_not_negotiable():
    """A reconciliation failure forces review whatever the score says."""
    perfect = score_confidence(dict.fromkeys(ALL_EVIDENCE, True))
    assert perfect.score == Decimal("1.0000")
    assert has_blocking([ReasonCode.SUBTOTAL_MISMATCH])


def test_confidence_is_the_fraction_of_evidence_conditions_met():
    evidence = dict.fromkeys(ALL_EVIDENCE, True)
    evidence[EvidenceCheck.COLUMN_PERIOD] = False
    evidence[EvidenceCheck.CLEAN_NUMERIC] = False
    result = score_confidence(evidence)
    assert result.score == Decimal(EVIDENCE_COUNT - 2) / Decimal(EVIDENCE_COUNT)
    assert set(result.failed) == {EvidenceCheck.COLUMN_PERIOD, EvidenceCheck.CLEAN_NUMERIC}


def test_confidence_explains_itself():
    evidence = dict.fromkeys(ALL_EVIDENCE, True)
    evidence[EvidenceCheck.PARSED] = False
    text = score_confidence(evidence).explain()
    assert EvidenceCheck.PARSED.value in text


def test_an_unstated_condition_is_an_error_not_a_default():
    """"We did not record it" is not "it did not happen"."""
    with pytest.raises(ValueError) as exc:
        score_confidence({EvidenceCheck.PARSED: True})
    assert "TEXT_LAYER" in str(exc.value)


def test_the_threshold_is_compared_strictly():
    evidence = dict.fromkeys(ALL_EVIDENCE, True)
    evidence[EvidenceCheck.CLEAN_NUMERIC] = False
    result = score_confidence(evidence)
    assert result.score == Decimal("0.8750")
    assert not result.needs_review(Decimal("0.875"))
    assert result.needs_review(Decimal("0.9"))


def test_confidence_is_exact():
    result = score_confidence({c: i % 2 == 0 for i, c in enumerate(ALL_EVIDENCE)})
    assert isinstance(result.score, Decimal)
    assert result.score == Decimal("0.5000")
