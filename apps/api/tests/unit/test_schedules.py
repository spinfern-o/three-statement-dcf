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


# --- item 71 / 13.3: the intangibles roll-forward, buildable at last --------


YEARS = ("2024A", "2025A")


def test_the_intangibles_roll_forward_runs_on_a_filing_that_discloses_both_sides():
    """13.3, on the shape it was written for (F-17).

    Opening 400, amortization 60, closing 340: the roll-forward ties exactly
    and there is nothing unexplained, because this filer added and impaired
    nothing in the period.
    """
    from apps.api.app.schedules.rollforward import intangibles_schedule

    books = ledgers(
        YEARS,
        balance={accounts.INTANGIBLES: {"2024A": "400", "2025A": "340"}},
        cashflow={accounts.AMORTIZATION: {"2025A": "60"}},
    )
    schedule = intangibles_schedule(books, YEARS)

    assert schedule.availability is Availability.AVAILABLE, schedule.reason
    row = schedule.years[0]
    assert row.year == "2025A"
    assert row.beginning.value == D("400")
    assert row.computed_ending == D("340")
    assert row.reported_ending == D("340")
    assert schedule.reconciliations[0].difference == D("0")


def test_an_addition_the_filing_does_not_quantify_lands_in_the_difference():
    """Not plugged, and not solved for.

    This filer's intangibles went UP by 90 while amortizing 60, so it added
    150 of something. The cash flow statement does not say so on its face, and
    the schedule reports a difference of 150 rather than inventing an
    additions line to absorb it. That difference is the finding.
    """
    from apps.api.app.schedules.rollforward import intangibles_schedule

    books = ledgers(
        YEARS,
        balance={accounts.INTANGIBLES: {"2024A": "400", "2025A": "490"}},
        cashflow={accounts.AMORTIZATION: {"2025A": "60"}},
    )
    schedule = intangibles_schedule(books, YEARS)

    row = schedule.years[0]
    assert row.computed_ending == D("340")
    assert row.reported_ending == D("490")
    # `difference` is computed minus reported, so an unquantified ADDITION
    # reads negative: the schedule explains 150 less than the balance sheet
    # carries.
    assert schedule.reconciliations[0].difference == D("-150")


def test_combined_d_and_a_is_not_charged_against_intangibles():
    """The mistake the schedule refuses to make.

    A filing reporting one combined `depreciation_amortization` figure has no
    separable amortization charge. Using the combined line here would be wrong
    by the whole of depreciation -- and the PP&E schedule is already charging
    that same figure, so the two would double count it.
    """
    from apps.api.app.schedules.rollforward import intangibles_schedule

    books = ledgers(
        YEARS,
        balance={accounts.INTANGIBLES: {"2024A": "400", "2025A": "340"}},
        cashflow={accounts.DEPRECIATION_AMORTIZATION: {"2025A": "260"}},
    )
    schedule = intangibles_schedule(books, YEARS)

    row = schedule.years[0]
    # The amortization movement is absent, not 260.
    assert row.movements[0].value is None
    assert row.computed_ending == D("400")
    assert schedule.availability is Availability.PARTIAL
    assert any("combined" in c.text for c in schedule.caveats)


def test_goodwill_is_named_and_deliberately_not_rolled_forward():
    """It is not amortized, so it has no charge to roll against."""
    from apps.api.app.schedules.rollforward import intangibles_schedule

    books = ledgers(
        YEARS,
        balance={
            accounts.INTANGIBLES: {"2024A": "400", "2025A": "340"},
            accounts.GOODWILL: {"2024A": "900", "2025A": "900"},
        },
        cashflow={accounts.AMORTIZATION: {"2025A": "60"}},
    )
    schedule = intangibles_schedule(books, YEARS)

    assert any("not amortized" in c.text for c in schedule.caveats)
    # And the balance it rolls is the intangibles one, untouched by goodwill.
    assert schedule.years[0].beginning.value == D("400")


def test_the_ppe_schedule_prefers_a_disclosed_depreciation_line():
    """12.1.e. Charging combined D&A against PP&E is right only if the company
    amortizes nothing, and a filer that discloses the split has said otherwise."""
    books = ledgers(
        YEARS,
        balance={accounts.PPE_NET: {"2024A": "1000", "2025A": "1100"}},
        cashflow={
            accounts.CAPEX: {"2025A": "-300"},
            accounts.DEPRECIATION: {"2025A": "200"},
            accounts.AMORTIZATION: {"2025A": "60"},
        },
    )
    schedule = ppe_schedule(books, YEARS)

    labels = [line.label for line in schedule.years[0].movements]
    assert "Depreciation" in labels
    assert "Depreciation and amortization" not in labels
    # 1000 + 300 - 200 = 1100, and the amortization is not charged here.
    assert schedule.years[0].computed_ending == D("1100")
    assert not any("combined" in c.text for c in schedule.caveats)


def test_the_ppe_schedule_says_so_when_it_must_use_the_combined_line():
    """And the caveat is what tells a reader which of the two they have."""
    books = ledgers(
        YEARS,
        balance={accounts.PPE_NET: {"2024A": "1000", "2025A": "1040"}},
        cashflow={
            accounts.CAPEX: {"2025A": "-300"},
            accounts.DEPRECIATION_AMORTIZATION: {"2025A": "260"},
        },
    )
    schedule = ppe_schedule(books, YEARS)

    labels = [line.label for line in schedule.years[0].movements]
    assert "Depreciation and amortization" in labels
    assert schedule.years[0].computed_ending == D("1040")
    assert any("combined" in c.text for c in schedule.caveats)
