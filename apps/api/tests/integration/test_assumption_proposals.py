"""7.7.a on a real filing: the historical drivers Phase 7 measured.

The point of these tests is the join. Every proposal carries the periods it
was measured over, because it came out of a schedule that knows them -- and
`Assumption` refuses a historical driver that does not say which periods it
measured. A hand-entered driver is exactly where that field gets left blank.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.assumptions.drivers import BY_CODE
from apps.api.app.assumptions.proposals import propose_from_schedules, unproposable
from apps.api.app.assumptions.schema import SourceType, Status
from apps.api.app.schedules.build import build_schedules

D = Decimal


@pytest.fixture(scope="module")
def proposals(built):
    return propose_from_schedules(build_schedules(built), owner="larry")


def test_every_driver_the_schedules_can_measure_is_proposed(proposals):
    assert {p.assumption.code for p in proposals} == {
        "dso",
        "inventory_days",
        "dpo",
        "interest_rate_on_debt",
        "tax_rate",
        "depreciation_pct_beginning_ppe",
    }


#: Computed by hand from the fixture, and cross-checked against Phase 7's own
#: golden values.
GOLDEN = {
    "dso": ("59.9", "days"),  # 205,000 / 1,250,000 x 365
    "inventory_days": ("77.9", "days"),  # 160,000 /   750,000 x 365
    "dpo": ("63.3", "days"),  # 130,000 /   750,000 x 365
    "tax_rate": ("0.25", "ratio"),  #  45,500 /   182,000
}


@pytest.mark.parametrize("code", sorted(GOLDEN))
def test_the_proposed_value_is_the_schedules_own(proposals, code):
    value, unit = GOLDEN[code]
    proposal = next(p for p in proposals if p.assumption.code == code)
    assert proposal.assumption.value == D(value)
    assert proposal.assumption.unit == unit


def test_the_interest_rate_is_on_the_basis_the_forecast_charges(proposals):
    """13.4 and STEP 19 must be the same measurement or the rate is wrong."""
    proposal = next(p for p in proposals if p.assumption.code == "interest_rate_on_debt")
    assert proposal.assumption.value == D("18000") / D("425000")
    assert "BEGINNING debt" in proposal.assumption.rationale
    assert "STEP 19" in proposal.assumption.rationale


def test_depreciation_is_a_rate_on_opening_ppe(proposals):
    """75,000 of depreciation against 588,000 of opening PP&E."""
    proposal = next(p for p in proposals if p.assumption.code == "depreciation_pct_beginning_ppe")
    assert proposal.assumption.value == D("75000") / D("588000")
    assert "amortizes nothing" in proposal.caution


def test_every_proposal_says_which_periods_it_measured(proposals):
    """The field a hand-entered historical driver is where it gets left blank."""
    for proposal in proposals:
        assert proposal.assumption.source_type is SourceType.HISTORICAL_DRIVER
        assert proposal.assumption.evidence.measured_over, proposal.assumption.code
        assert all(year.endswith("A") for year in proposal.assumption.evidence.measured_over)


def test_every_proposal_arrives_as_a_draft(proposals):
    """A proposal that arrived Approved would make STEP 14's assumption for
    every driver at once, silently."""
    for proposal in proposals:
        assert proposal.assumption.status is Status.DRAFT
        assert proposal.assumption.status.blocks_calculation
        assert "not what the company will do" in proposal.assumption.rationale


def test_every_proposal_declares_the_unit_its_driver_expects(proposals):
    """18.12 at the seam: 0.164 where 59.9 was meant is not visibly wrong."""
    for proposal in proposals:
        assert proposal.assumption.unit == BY_CODE[proposal.assumption.code].unit


def test_every_proposal_carries_a_caution_a_reviewer_has_to_weigh(proposals):
    for proposal in proposals:
        assert len(proposal.caution.split()) >= 10, proposal.assumption.code
        assert proposal.schedule.startswith("13.")


def test_the_drivers_no_schedule_can_measure_are_named_not_omitted(built):
    """Revenue growth is the clearest: last year's growth is not evidence."""
    reasons = unproposable(build_schedules(built))
    assert "revenue_growth" in reasons
    assert "not evidence about the next period" in reasons["revenue_growth"]
    assert "cogs_pct_revenue / cogs_amount" in reasons
    # This filing reports neither other-current line, so both are named.
    assert "other_current_assets_pct_revenue" in reasons


def test_together_the_proposals_and_the_gaps_cover_every_required_driver(built):
    """Nothing a forecast needs is silently absent from the screen."""
    from apps.api.app.assumptions.drivers import REQUIRED

    schedules = build_schedules(built)
    proposed = {p.assumption.code for p in propose_from_schedules(schedules, "larry")}
    explained = set()
    for label in unproposable(schedules):
        explained |= {part.strip() for part in label.split("/")}

    uncovered = [
        sorted(choice)
        for choice in REQUIRED
        if not (choice & proposed) and not (choice & explained)
    ]
    assert not uncovered, f"no proposal and no explanation for {uncovered}"
