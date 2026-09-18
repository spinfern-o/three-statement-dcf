"""Item 77's unit half: the edges the fixture filing cannot reach.

The three-statement fixture is a well-behaved filing -- two consecutive
periods, every driver's denominator present and non-zero, every roll-forward
tying exactly. That is what makes it a good golden fixture and a poor test of
the refusals, so those are tested here against ledgers built by hand.

The ledgers are built with `set_derived` rather than `set_reported` because
these tests are about arithmetic and absence, not provenance; Phase 6's tests
cover the citation trail.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.schedules.base import (
    Availability,
    Reconciliation,
    Schedule,
    ScheduleLine,
)
from apps.api.app.schedules.checks import reconcile
from apps.api.app.schedules.interest import implied_interest_rates
from apps.api.app.schedules.rollforward import (
    Movement,
    debt_schedule,
    ppe_schedule,
    retained_earnings_schedule,
)
from apps.api.app.schedules.tax import tax_schedule
from apps.api.app.schedules.views import total_unexplained
from apps.api.app.schedules.working_capital import working_capital_schedule
from model import accounts
from model.accounts import Statement
from model.checks import Status, Tolerance
from model.statements import Ledger

D = Decimal


def ledgers(years, **values):
    """`ledgers(("2024A",), income={"revenue": {"2024A": "100"}})`."""
    out = {
        Statement.INCOME: Ledger(Statement.INCOME, years),
        Statement.BALANCE: Ledger(Statement.BALANCE, years),
        Statement.CASHFLOW: Ledger(Statement.CASHFLOW, years),
    }
    names = {
        "income": Statement.INCOME,
        "balance": Statement.BALANCE,
        "cashflow": Statement.CASHFLOW,
    }
    for key, cells in values.items():
        ledger = out[names[key]]
        for account, by_year in cells.items():
            for year, value in by_year.items():
                ledger.set_derived(account, year, D(value), "unit test fixture")
    return out


# --- base types -------------------------------------------------------------


def test_an_absent_line_must_say_what_is_missing():
    with pytest.raises(ValueError, match="no value and no reason"):
        ScheduleLine("Borrowing", None, "cash flow statement")


def test_a_movement_must_declare_its_sign_explicitly():
    with pytest.raises(ValueError, match=r"multiplier must be \+1 or -1"):
        Movement(
            account=accounts.CAPEX,
            statement=Statement.CASHFLOW,
            multiplier=0,
            label="CapEx",
            basis="",
        )


def test_a_reconciliation_with_a_missing_side_neither_ties_nor_differs():
    reconciliation = Reconciliation(
        year="2025A", statement_line="balance_sheet.debt", computed=D(1), reported=None
    )
    assert reconciliation.difference is None
    assert reconciliation.ties is None


def test_a_reconciliation_ties_only_on_exact_equality():
    close = Reconciliation("2025A", "balance_sheet.debt", D("100.0001"), D("100"))
    assert close.ties is False
    assert close.difference == D("0.0001")


# --- roll-forwards: what a single-period filing can support ------------------

ONE_YEAR = ("2025A",)


def test_a_one_period_filing_has_no_roll_forward():
    """STEP 3: do not invent the missing historical year."""
    schedule = ppe_schedule(ledgers(ONE_YEAR, balance={"ppe_net": {"2025A": "1000"}}), ONE_YEAR)
    assert schedule.availability is Availability.UNAVAILABLE
    assert "two consecutive periods" in schedule.reason
    assert schedule.years == ()


def test_no_opening_balance_means_nothing_to_roll_forward():
    """Starting at zero would report the whole closing balance as a movement."""
    years = ("2024A", "2025A")
    schedule = debt_schedule(
        ledgers(
            years,
            balance={"debt": {"2025A": "400"}},
            cashflow={"debt_repayment": {"2025A": "-25"}},
        ),
        years,
    )
    assert schedule.availability is Availability.UNAVAILABLE
    assert "opening" in schedule.reason
    assert schedule.years[0].computed_ending is None
    assert schedule.years[0].unexplained is None


def test_a_roll_forward_with_no_disclosed_movements_reports_the_whole_gap():
    """The honest answer when a balance moved and the filing does not say how."""
    years = ("2024A", "2025A")
    schedule = retained_earnings_schedule(
        ledgers(years, balance={"retained_earnings": {"2024A": "100", "2025A": "150"}}),
        years,
    )
    row = schedule.years[0]
    assert row.computed_ending == D("100")
    assert row.unexplained == D("-50")
    assert row.absent_movements == ("Net income", "Dividends")
    assert schedule.availability is Availability.PARTIAL


def test_the_reconciliation_fails_and_names_the_absent_movements():
    years = ("2024A", "2025A")
    schedule = retained_earnings_schedule(
        ledgers(years, balance={"retained_earnings": {"2024A": "100", "2025A": "150"}}),
        years,
    )
    result = reconcile(schedule, Tolerance())
    assert result.status is Status.FAIL
    assert "unexplained -50" in result.detail
    assert "Net income" in result.detail and "Dividends" in result.detail


def test_total_unexplained_refuses_to_sum_over_a_period_it_could_not_reconcile():
    years = ("2024A", "2025A")
    schedule = debt_schedule(ledgers(years, balance={"debt": {"2025A": "400"}}), years)
    assert total_unexplained(schedule) is None


# --- working capital --------------------------------------------------------


def test_a_days_driver_against_zero_is_undefined_not_infinite():
    """4.12: relative measures against zero are reported as undefined."""
    years = ("2025A",)
    schedule = working_capital_schedule(
        ledgers(
            years,
            balance={"accounts_receivable": {"2025A": "100"}},
            income={"revenue": {"2025A": "0"}},
        ),
        years,
    )
    dso = next(d for d in schedule.years[0].drivers if d.name == "DSO")
    assert dso.days is None
    assert "undefined (4.12)" in dso.unavailable_reason


def test_a_days_driver_with_no_denominator_says_which_one():
    years = ("2025A",)
    schedule = working_capital_schedule(
        ledgers(years, balance={"inventory": {"2025A": "100"}}), years
    )
    inventory_days = next(d for d in schedule.years[0].drivers if d.name == "Inventory days")
    assert inventory_days.days is None
    assert "cost of goods sold" in inventory_days.unavailable_reason


def test_working_capital_is_unknown_when_a_whole_side_is_absent():
    """Not zero. A filing reporting no payables at all has not reported zero."""
    years = ("2025A",)
    schedule = working_capital_schedule(
        ledgers(years, balance={"accounts_receivable": {"2025A": "100"}}), years
    )
    row = schedule.years[0]
    assert row.operating_current_assets == D("100")
    assert row.operating_current_liabilities is None
    assert row.nwc is None


def test_the_change_in_working_capital_skips_rather_than_guessing():
    years = ("2024A", "2025A")
    schedule = working_capital_schedule(
        ledgers(years, balance={"accounts_receivable": {"2024A": "90", "2025A": "100"}}),
        years,
    )
    assert schedule.reconciliations[0].computed is None
    result = reconcile(schedule, Tolerance())
    assert result.status is Status.SKIP


# --- tax --------------------------------------------------------------------


@pytest.mark.parametrize(
    "pretax,taxes,rate,usable,fragment",
    [
        ("200", "50", "0.25", True, ""),
        ("0", "5", None, False, "undefined (4.12)"),
        ("-100", "10", "-0.1", False, "tax benefit rate"),
        ("100", "140", "1.4", False, "outside the [0%, 100%) range"),
    ],
)
def test_the_effective_rate_reports_the_year_it_actually_had(pretax, taxes, rate, usable, fragment):
    """STEP 16 wants the basis stated, not a rate smoothed into range."""
    years = ("2025A",)
    schedule = tax_schedule(
        ledgers(years, income={"pretax_income": {"2025A": pretax}, "taxes": {"2025A": taxes}}),
        years,
    )
    row = schedule.years[0]
    assert row.effective_rate == (None if rate is None else D(rate))
    assert row.usable_as_assumption is usable
    assert fragment in row.reason
    assert schedule.usable_rates() == ({"2025A": D(rate)} if usable else {})


def test_an_absent_tax_line_names_which_one_is_missing():
    years = ("2025A",)
    schedule = tax_schedule(ledgers(years, income={"pretax_income": {"2025A": "100"}}), years)
    assert schedule.years[0].effective_rate is None
    assert "tax expense" in schedule.years[0].reason


# --- interest ---------------------------------------------------------------


def test_a_rate_on_zero_debt_is_undefined_on_both_bases():
    years = ("2024A", "2025A")
    rows = implied_interest_rates(
        ledgers(
            years,
            balance={"debt": {"2024A": "0", "2025A": "0"}},
            income={"interest_expense": {"2025A": "5"}},
        ),
        years,
    )
    for rate in rows[0].rates:
        assert rate.rate is None
        assert "undefined (4.12)" in rate.unavailable_reason


def test_no_interest_expense_means_no_implied_rate():
    years = ("2024A", "2025A")
    rows = implied_interest_rates(
        ledgers(years, balance={"debt": {"2024A": "100", "2025A": "100"}}), years
    )
    assert rows[0].on("beginning").rate is None
    assert "no interest expense" in rows[0].on("beginning").unavailable_reason


def test_the_two_bases_differ_whenever_debt_moved():
    years = ("2024A", "2025A")
    rows = implied_interest_rates(
        ledgers(
            years,
            balance={"debt": {"2024A": "1000", "2025A": "500"}},
            income={"interest_expense": {"2025A": "60"}},
        ),
        years,
    )
    assert rows[0].on("beginning").rate == D("0.06")  # 60 / 1000
    assert rows[0].on("average").rate == D("60") / D("750")  # 60 / 750
    assert rows[0].on("ending") is None, "13.4's third basis is not offered"


# --- the checks themselves --------------------------------------------------


def test_a_schedule_with_nothing_to_reconcile_skips():
    schedule = Schedule(key="x", title="X", rule="13.9", availability=Availability.AVAILABLE)
    result = reconcile(schedule, Tolerance())
    assert result.status is Status.SKIP
    assert "covers no period" in result.detail


def test_a_tolerance_wide_enough_to_pass_still_reports_the_difference():
    """The tolerance decides PASS or FAIL. It never edits a number, and a
    period inside it is not reported as one that tied -- otherwise a rounding
    difference and a missing disposal read identically."""
    years = ("2024A", "2025A")
    schedule = ppe_schedule(
        ledgers(
            years,
            balance={"ppe_net": {"2024A": "1000", "2025A": "1100"}},
            cashflow={"capex": {"2025A": "-100"}, "depreciation_amortization": {"2025A": "0.001"}},
        ),
        years,
    )
    assert schedule.years[0].unexplained == D("-0.001")
    assert reconcile(schedule, Tolerance()).status is Status.FAIL

    lenient = reconcile(schedule, Tolerance(rel=D("1e-3")))
    assert lenient.status is Status.PASS
    assert "0 period(s) tie exactly" in lenient.detail
    assert "within" in lenient.detail and "not exact" in lenient.detail
    assert "unexplained -0.001" in lenient.detail
