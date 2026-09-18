"""Phase 7 end to end: items 69-77, on the three-statement fixture.

Item 77 asks for unit and integration tests. These are the integration half:
the schedules built from a real PDF taken through extraction, review, mapping
and approval, with a golden table of every figure each schedule produces.

A note on what makes these tests worth having. Every reconciliation in
Section 13 would pass unconditionally if the schedules solved for their own
residual, so the tests that matter are the ones that break a figure and assert
the reconciliation notices. Those are at the bottom of this file, one per
schedule, and each corrupts a *different* input so that a single bug cannot
make them all pass together.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.review.actions import correct_fact
from apps.api.app.schedules.base import Availability
from apps.api.app.schedules.build import build_schedules
from apps.api.app.schedules.checks import run_schedule_checks, summarize
from apps.api.app.schedules.interest import ENGINE_BASIS
from apps.api.app.schedules.views import driver_rows, working_capital_rows
from apps.api.app.statements.build import build_statements
from model.checks import Status

D = Decimal


@pytest.fixture(scope="module")
def schedules(built):
    return build_schedules(built)


def _fact(result, label, period, page=None):
    for fact in result.facts:
        if fact.raw_label == label and fact.period_label == period:
            if page is None:
                return fact
            location = result.location(fact.source_location_id)
            if location and location.page_number == page:
                return fact
    raise AssertionError(f"no fact {label!r} for {period}")


def _named(results, name_fragment):
    for result in results:
        if name_fragment in result.name:
            return result
    raise AssertionError(f"no check matching {name_fragment!r} in {[r.name for r in results]}")


def _rebuild(result):
    return build_schedules(build_statements(result, strict=False))


# --- what the filing supports, and what it does not -------------------------


def test_every_section_13_schedule_is_present_or_explained(schedules):
    """Rule 1.14. Seven schedules asked for; none silently missing."""
    assert len(schedules.all) == 9  # 13.7 is split into three
    assert {s.rule for s in schedules.all} == {
        "13.1",
        "13.2",
        "13.3",
        "13.4",
        "13.5",
        "13.6",
        "13.7",
    }
    for schedule in schedules.all:
        if schedule.availability is not Availability.AVAILABLE:
            assert schedule.reason, f"{schedule.key} gives no reason"


def test_the_two_the_chart_cannot_carry_say_so(schedules):
    """Item 73 and the share-count half of 75.

    13.3 used to be a third. Closing F-17 gave the chart `intangibles` and a
    separate `amortization` line, so the roll-forward has both of its sides and
    is built like the others -- see the test below for what it says on a filing
    that reports no intangibles, which is a different statement from "this
    system cannot build this".
    """
    assert {s.key for s in schedules.unavailable} == {
        "intangibles",
        "leases",
        "share_count",
    }
    assert "diluted" in schedules.by_key("share_count").reason

    # Neither is a chart-length problem any more, and both reasons say so
    # rather than implying the extension that closed F-17 simply missed them.
    # 13.5 has its ending balance and needs footnote extraction for the
    # movements; 13.7 needs a quantity, and this chart holds amounts.
    leases = schedules.by_key("leases").reason
    assert "footnote extraction, not more canonical lines" in leases
    assert "that half was finding F-17 and is closed" in leases
    assert "does not fix this one" in schedules.by_key("share_count").reason


def test_the_intangibles_schedule_is_built_now_and_says_the_filing_has_none(schedules):
    """13.3, and the difference between two kinds of absence.

    The schedule reported "this system has no intangibles line" for eleven
    phases. It now reports what is true of THIS filing: there is no opening
    intangibles balance to roll forward from. A reviewer who reads the first
    goes looking for a missing feature; one who reads the second goes looking
    at the balance sheet, which is where the answer is.
    """
    intangibles = schedules.by_key("intangibles")
    assert intangibles.rule == "13.3"
    assert intangibles.availability is Availability.UNAVAILABLE
    assert "no period has an opening" in intangibles.reason
    # The old reason -- a statement about the chart -- must not come back.
    assert "canonical chart has no" not in intangibles.reason
    # And it is a real roll-forward: it carries 13.3's formula and its caveats.
    assert "Amortization" in intangibles.formula
    assert any("unexplained difference" in c.text for c in intangibles.caveats)


def test_an_unavailable_schedule_cannot_be_built_without_a_reason():
    from apps.api.app.schedules.base import Schedule

    with pytest.raises(ValueError, match="must say why"):
        Schedule(
            key="x",
            title="X",
            rule="13.9",
            availability=Availability.UNAVAILABLE,
        )


# --- item 69: working capital (13.1) ----------------------------------------


def test_working_capital_is_the_operating_accounts_only(schedules):
    """13.1.c. Cash and debt are excluded by definition, not by judgement."""
    assert schedules.working_capital.excluded == ("cash", "debt")
    labels = {line.label for row in schedules.working_capital.years for line in row.assets}
    assert "cash" not in labels

    by_year = {row.year: row for row in schedules.working_capital.years}
    # 205,000 + 160,000 - 130,000; other current assets and liabilities are
    # absent from this filing and are named rather than treated as zero.
    assert by_year["2025A"].operating_current_assets == D("365000")
    assert by_year["2025A"].operating_current_liabilities == D("130000")
    assert by_year["2025A"].nwc == D("235000")
    assert by_year["2024A"].nwc == D("214500")
    assert by_year["2025A"].absent == ("other_current_assets", "other_current_liabilities")


#: 13.1.d, computed by hand from the fixture: balance / flow x 365.
GOLDEN_DRIVERS = {
    ("2024A", "DSO"): "59.9",  # 180,500 / 1,100,000
    ("2024A", "Inventory days"): "85.7",  # 155,000 /   660,000
    ("2024A", "DPO"): "66.9",  # 121,000 /   660,000
    ("2025A", "DSO"): "59.9",  # 205,000 / 1,250,000
    ("2025A", "Inventory days"): "77.9",  # 160,000 /   750,000
    ("2025A", "DPO"): "63.3",  # 130,000 /   750,000
}


@pytest.mark.parametrize("key,expected", sorted(GOLDEN_DRIVERS.items()))
def test_the_days_drivers(schedules, key, expected):
    year, name = key
    row = next(r for r in schedules.working_capital.years if r.year == year)
    driver = next(d for d in row.drivers if d.name == name)
    assert driver.days == D(expected)


def test_every_driver_states_its_denominator_and_day_count(schedules):
    """13.1.e asks for the convention, not just the number."""
    assert schedules.working_capital.days_in_year == D(365)
    for row in schedules.working_capital.years:
        for driver in row.drivers:
            assert "year-end balance" in driver.numerator
            assert "full year" in driver.denominator
            assert "365" in driver.convention
            assert "average" in driver.convention  # says why not averages


def test_the_change_in_working_capital_reconciles_to_the_cash_flow(schedules):
    """13.8, and the sign is the interesting half."""
    reconciliation = schedules.working_capital.reconciliations[0]
    assert reconciliation.year == "2025A"
    # NWC rose 20,500, which consumed 20,500 of cash.
    assert reconciliation.computed == D("-20500")
    assert reconciliation.reported == D("-20500")
    assert reconciliation.ties
    assert "consumes cash" in reconciliation.note


# --- items 70, 72, 75: the roll-forwards ------------------------------------

#: Every roll-forward, as printed in the fixture. One period: the filing
#: reports two years, and the first has no prior year to roll forward from.
GOLDEN_ROLLFORWARDS = {
    "ppe": (
        "588000",
        {"Capital expenditure": "107000", "Depreciation and amortization": "-75000"},
        "620000",
    ),
    "debt": ("425000", {"Borrowing": None, "Repayment": "-25000"}, "400000"),
    "retained_earnings": ("469500", {"Net income": "136500", "Dividends": "-36500"}, "569500"),
    "common_equity": (
        "50000",
        {"Share repurchases": None, "Stock-based compensation": None},
        "50000",
    ),
}


@pytest.mark.parametrize("key", sorted(GOLDEN_ROLLFORWARDS))
def test_the_golden_rollforward(schedules, key):
    beginning, movements, ending = GOLDEN_ROLLFORWARDS[key]
    schedule = schedules.by_key(key)
    assert len(schedule.years) == 1, "the filing reports two periods, so one rolls"
    row = schedule.years[0]
    assert (row.prior_year, row.year) == ("2024A", "2025A")
    assert row.beginning.value == D(beginning)
    assert {line.label: line.value for line in row.movements} == {
        label: None if value is None else D(value) for label, value in movements.items()
    }
    assert row.computed_ending == D(ending)
    assert row.reported_ending == D(ending)
    assert row.unexplained == 0


def test_capex_increases_ppe_although_it_is_stored_as_an_outflow(schedules):
    """The sign error worth exactly twice the amount.

    `model/accounts.py` stores CapEx negative, because it is summed into
    investing cash flow. PP&E goes UP when you buy some, so the roll-forward
    negates it -- and says so, rather than leaving a reader to work out why a
    line called CapEx is positive here and negative two screens away.
    """
    row = schedules.ppe.years[0]
    capex = next(line for line in row.movements if line.label == "Capital expenditure")
    assert capex.value == D("107000")
    assert "negative outflow" in capex.basis


def test_repayment_is_added_not_subtracted(schedules):
    """It arrives negative, so subtracting it would raise debt by the repayment."""
    row = schedules.debt.years[0]
    repayment = next(line for line in row.movements if line.label == "Repayment")
    assert repayment.value == D("-25000")
    assert "ADDED rather than subtracted" in repayment.basis


def test_a_movement_the_filing_does_not_report_is_named_not_zeroed(schedules):
    """STEP 5. Absent borrowing is absent, and the reconciliation says so."""
    row = schedules.debt.years[0]
    borrowing = next(line for line in row.movements if line.label == "Borrowing")
    assert borrowing.value is None
    assert "reports no 'debt_issuance'" in borrowing.absent_reason
    assert row.absent_movements == ("Borrowing",)
    assert "Borrowing" in schedules.debt.reconciliations[0].note
    assert schedules.debt.availability is Availability.PARTIAL


def test_the_ppe_schedule_names_what_it_cannot_see(schedules):
    """13.2's disposals and FX terms, and the combined D&A line."""
    text = " ".join(caveat.text for caveat in schedules.ppe.caveats)
    assert "amortizes nothing" in text
    assert "Disposals and FX have no canonical line" in text


# --- item 74: tax (13.6) ----------------------------------------------------


def test_the_effective_rate_is_exact(schedules):
    rates = {row.year: row.effective_rate for row in schedules.tax.years}
    assert rates == {"2024A": D("0.25"), "2025A": D("0.25")}
    assert schedules.tax.usable_rates() == rates


def test_the_tax_footnote_components_are_reported_missing(schedules):
    """13.6 asks for five things the face of a statement does not print."""
    assert schedules.tax.availability is Availability.PARTIAL
    assert "tax footnote" in schedules.tax.reason
    assert "deferred tax expense" in schedules.tax.missing_components
    assert "valuation allowances" in schedules.tax.missing_components


# --- 13.4's interest basis --------------------------------------------------


def test_both_interest_bases_are_computed_and_the_engines_is_marked(schedules):
    """13.4: state whether interest uses beginning, ending or average debt."""
    assert len(schedules.interest) == 1
    row = schedules.interest[0]
    assert row.interest_expense == D("18000")
    assert row.beginning_debt == D("425000")
    assert row.ending_debt == D("400000")

    beginning = row.on("beginning")
    average = row.on("average")
    assert beginning.rate == D("18000") / D("425000")
    assert average.rate == D("18000") / D("412500")
    assert beginning.rate != average.rate, "the two bases must not be conflated"
    assert beginning.is_engine_basis and not average.is_engine_basis
    assert ENGINE_BASIS == "beginning"


def test_the_engine_charges_interest_on_the_basis_this_schedule_reports():
    """If model/forecast.py changes basis, the historical rate stops matching."""
    import inspect

    from model import forecast

    source = inspect.getsource(forecast)
    assert "on beginning debt" in source, (
        "model/forecast.py no longer says it charges interest on beginning debt; "
        "schedules/interest.py:ENGINE_BASIS must be updated with it"
    )


# --- item 76: the reconciliation checks (13.8) ------------------------------


def test_every_schedule_check_passes_on_a_filing_that_ties(schedules):
    results = run_schedule_checks(schedules)
    assert summarize(results) == "7 passed, 0 failed, 0 skipped"


def test_an_unbuildable_schedule_skips_rather_than_passes(schedules):
    """Rule 1.14 again, this time about the checks themselves."""
    from apps.api.app.schedules.checks import reconcile
    from model.checks import Tolerance

    result = reconcile(schedules.by_key("leases"), Tolerance())
    assert result.status is Status.SKIP
    assert "nothing to reconcile" in result.detail


@pytest.mark.parametrize(
    "label,period,page,replacement,check,moved",
    [
        # PP&E: overstate CapEx. The balance sheet is untouched, so the
        # schedule now explains more movement than the balance sheet shows.
        (
            "Purchases of property and equipment",
            "2025",
            None,
            "-120000",
            "PP&E and depreciation",
            "13,000",
        ),
        # Debt: understate the repayment.
        ("Repayments of long-term debt", "2025", None, "-10000", "Debt and interest", "15,000"),
        # Retained earnings: change the dividend.
        ("Dividends paid", "2025", None, "-40000", "Retained earnings", "-3,500"),
        # Working capital: move a receivable, which changes the balance-sheet
        # change in NWC without touching the cash flow statement's own line.
        ("Accounts receivable, net", "2025", 3, "215000", "Working capital", "-30,500"),
    ],
)
def test_a_broken_schedule_is_reported_not_plugged(
    three_statements, label, period, page, replacement, check, moved
):
    """The tests that make 13.8 worth running.

    Each corrupts a different input, so no single bug can make them all pass.
    The assertion is on the *amount* of the difference, not merely on FAIL:
    a reconciliation that fails with the wrong number is still wrong.
    """
    fact = _fact(three_statements, label, period, page=page)
    broken = correct_fact(
        three_statements, fact.id, replacement, actor="owner", reason="deliberately wrong"
    )
    results = run_schedule_checks(_rebuild(broken))
    result = _named(results, check)
    assert result.status is Status.FAIL, result.detail
    assert moved in result.detail, result.detail
    assert "unexplained" in result.detail


def test_the_reported_balance_is_never_adjusted_to_match(three_statements):
    """12.5 and STEP 6. The schedule moves; the filing's figure does not."""
    fact = _fact(three_statements, "Purchases of property and equipment", "2025")
    broken = correct_fact(
        three_statements, fact.id, "-120000", actor="owner", reason="deliberately wrong"
    )
    schedule = _rebuild(broken).ppe
    row = schedule.years[0]
    assert row.reported_ending == D("620000"), "the balance sheet is untouched"
    assert row.computed_ending == D("633000")
    assert row.unexplained == D("13000")


# --- item 77: the screen ----------------------------------------------------


def test_the_working_capital_rows_do_not_recompute_anything(schedules):
    """The view reads the schedule; it does not do arithmetic of its own."""
    rows = working_capital_rows(schedules.working_capital)
    labels = [row.label for row in rows]
    assert labels[-1] == "Net working capital"
    assert labels[-2] == "Operating current liabilities"
    nwc = rows[-1]
    assert nwc.values == tuple(row.nwc for row in schedules.working_capital.years)
    assert nwc.is_total


def test_the_driver_rows_carry_the_reason_when_a_driver_is_absent(schedules):
    rows = driver_rows(schedules.working_capital)
    assert [row.name for row in rows] == ["DSO", "Inventory days", "DPO"]
    assert all(len(row.values) == len(schedules.years) for row in rows)
