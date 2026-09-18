"""Item 57: mapping sets are versioned and never mutated. 11.12."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.mapping.sets import (
    MappingError,
    MappingSet,
    MappingType,
    Origin,
    manual,
    proposal,
)


def _proposed(fact_id="f1", code="revenue"):
    return proposal(
        fact_id=fact_id,
        code=code,
        rule="the whole label is a revenue line",
        score=Decimal("0.95"),
        note="system proposal",
    )


def test_an_empty_set_starts_at_version_one():
    assert MappingSet.empty().version == 1
    assert MappingSet.empty().supersedes is None


def test_every_change_makes_a_new_version_and_leaves_the_old_one():
    first = MappingSet.empty()
    second = first.add(_proposed(), actor="system", reason="proposals")
    assert second.version == 2 and second.supersedes == 1
    assert first.mappings == ()


def test_a_version_needs_a_reason():
    with pytest.raises(MappingError):
        MappingSet.empty().add(_proposed(), actor="system", reason="  ")


def test_a_proposal_is_not_approved():
    """11.10. Proposed and approved are separate facts, not one status."""
    mapping = _proposed()
    assert mapping.origin is Origin.SYSTEM_PROPOSED
    assert not mapping.approved


def test_approving_requires_a_note():
    with pytest.raises(MappingError) as exc:
        _proposed().approve(actor="owner", note="")
    assert "11.3" in str(exc.value)


def test_approving_records_who_and_when():
    approved = _proposed().approve(actor="owner", note="Net sales is revenue")
    assert approved.approved
    assert approved.approved_by == "owner"
    assert approved.approved_at is not None
    assert approved.origin is Origin.HUMAN


def test_a_fact_is_approved_only_when_all_its_mappings_are():
    """A split produces several mappings; approving one is not approving it."""
    a = manual(
        fact_id="f1",
        code="revenue",
        note="n",
        mapping_type=MappingType.SPLIT,
        allocation_amount=Decimal("10"),
        allocation_basis="note 3",
    )
    b = manual(
        fact_id="f1",
        code="other_income_expense",
        note="n",
        mapping_type=MappingType.SPLIT,
        allocation_amount=Decimal("5"),
        allocation_basis="note 3",
    )
    subject = MappingSet.empty().add(a, b, actor="owner", reason="split")
    assert not subject.is_approved("f1")
    subject = subject.update(a.approve(actor="owner", note="ok"), actor="owner", reason="half")
    assert not subject.is_approved("f1")
    subject = subject.update(b.approve(actor="owner", note="ok"), actor="owner", reason="rest")
    assert subject.is_approved("f1")


def test_a_rejected_mapping_does_not_make_a_fact_verified():
    """ "I looked at this and it is not a statement line" is worth recording,
    and it is not a verified figure IN the model."""
    rejected = manual(
        fact_id="f1", code="revenue", note="a page number", mapping_type=MappingType.REJECTED
    ).approve(actor="owner", note="not a line")
    subject = MappingSet.empty().add(rejected, actor="owner", reason="rejected")
    assert subject.is_excluded("f1")
    assert not subject.is_approved("f1")


def test_replacing_a_facts_mappings_drops_the_old_ones():
    subject = MappingSet.empty().add(_proposed(), actor="system", reason="proposals")
    subject = subject.replace_fact("f1", _proposed(code="cogs"), actor="owner", reason="corrected")
    assert [m.canonical_code for m in subject.for_fact("f1")] == ["cogs"]


def test_editing_a_mapping_makes_it_unapproved_again():
    """11.12's invalidation at its smallest: the approval was of the old one."""
    subject = MappingSet.empty().add(_proposed(), actor="system", reason="proposals")
    approved = subject.for_fact("f1")[0].approve(actor="owner", note="ok")
    subject = subject.update(approved, actor="owner", reason="approved")
    assert subject.is_approved("f1")
    subject = subject.replace_fact("f1", _proposed(code="cogs"), actor="owner", reason="wrong line")
    assert not subject.is_approved("f1")


def test_unapproved_is_queryable_for_check_17_6():
    subject = MappingSet.empty().add(
        _proposed("f1"), _proposed("f2", "cogs"), actor="system", reason="proposals"
    )
    assert len(subject.unapproved) == 2


def test_removing_a_missing_fact_is_an_error_not_a_silent_no_op():
    with pytest.raises(MappingError):
        MappingSet.empty().remove_fact("nope", actor="owner", reason="tidy")
