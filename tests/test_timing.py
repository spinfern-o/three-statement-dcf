"""Specification 16.11-16.14: the timing convention and its precision policy.

Three claims are made in `model/timing.py`'s docstring, and each is tested
here, because a precision policy that is only asserted in prose is a precision
policy nobody has checked.

  1. The year-end path is UNCHANGED. Adopting Section 16's options must not
     move a valuation that did not ask for them.
  2. An integer exponent stays exact. It goes through repeated multiplication
     and never touches a transcendental function.
  3. A fractional exponent carries a few units in the last place of fifty
     digits -- forty orders of magnitude inside 4.11's 0.0001% contract.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from model.numeric import ONE, power
from model.provenance import ProvenanceError
from model.timing import (
    DAYS_IN_YEAR,
    Timing,
    build_schedule,
    discount_factor,
)

D = Decimal

YEARS = ("2026E", "2027E", "2028E", "2029E", "2030E")
#: 4.11's contract. Every bound below is stated against it.
CONTRACT = D("0.0001")


# --- 16.11: the three conventions -------------------------------------------

def test_year_end_is_the_engines_own_convention():
    """STEP 29: t = 1, 2, 3, counting from the last actual year."""
    schedule = build_schedule(YEARS, Timing.YEAR_END)
    assert list(schedule.fractions) == [D(1), D(2), D(3), D(4), D(5)]
    assert schedule.terminal == D(5)


def test_mid_year_puts_the_average_pound_halfway_through_the_year():
    schedule = build_schedule(YEARS, Timing.MID_YEAR)
    assert list(schedule.fractions) == [
        D("0.5"), D("1.5"), D("2.5"), D("3.5"), D("4.5")
    ]


def test_mid_year_raises_every_present_value():
    """Stated in the docstring, so it is asserted rather than assumed."""
    wacc = D("0.09")
    year_end = build_schedule(YEARS, Timing.YEAR_END)
    mid_year = build_schedule(YEARS, Timing.MID_YEAR)
    for index in range(len(YEARS)):
        assert discount_factor(wacc, mid_year.fractions[index]) > discount_factor(
            wacc, year_end.fractions[index]
        )


def test_the_terminal_value_uses_the_same_convention_as_the_flows():
    """16.17. A terminal value on a different basis is a different valuation."""
    for timing in (Timing.YEAR_END, Timing.MID_YEAR):
        schedule = build_schedule(YEARS, timing)
        assert schedule.terminal == schedule.fractions[-1]


def test_every_convention_describes_itself(): 
    """16.11 asks that the choice be DOCUMENTED, not merely made."""
    for timing in Timing:
        assert len(timing.description.split()) >= 15
    schedule = build_schedule(YEARS, Timing.MID_YEAR)
    assert "RAISES every present value" in schedule.basis


# --- 16.12: the exact time fraction -----------------------------------------

def test_the_exact_fraction_counts_real_days():
    """A June 30 valuation is 184 days from a December 31 year end."""
    schedule = build_schedule(
        ("2026E",), Timing.EXACT_DATE,
        valuation_date=date(2026, 6, 30), fiscal_year_end=date(2025, 12, 31),
    )
    assert schedule.fractions[0] == D(184) / DAYS_IN_YEAR


def test_a_leap_day_inside_the_span_is_counted():
    """2028 is a leap year, so the third year is one day further out than
    three times the first would suggest."""
    schedule = build_schedule(
        ("2026E", "2027E", "2028E"), Timing.EXACT_DATE,
        valuation_date=date(2026, 6, 30), fiscal_year_end=date(2025, 12, 31),
    )
    first, second, third = schedule.fractions
    assert (second - first) * DAYS_IN_YEAR == D(365)
    assert (third - second) * DAYS_IN_YEAR == D(366), "2028 has 366 days"


def test_a_non_december_fiscal_year_end_is_honoured():
    schedule = build_schedule(
        ("2026E",), Timing.EXACT_DATE,
        valuation_date=date(2026, 1, 1), fiscal_year_end=date(2025, 6, 30),
    )
    assert schedule.fractions[0] == D((date(2026, 6, 30) - date(2026, 1, 1)).days) / DAYS_IN_YEAR


def test_a_february_29_year_end_falls_back_in_a_common_year():
    """Refusing would mean a model that cannot value a leap-day filer."""
    schedule = build_schedule(
        ("2026E", "2028E"), Timing.EXACT_DATE,
        valuation_date=date(2025, 12, 31), fiscal_year_end=date(2024, 2, 29),
    )
    assert schedule.fractions[0] > 0
    assert "2026-02-28" in schedule.basis
    assert "2028-02-29" in schedule.basis


def test_a_cash_flow_before_the_valuation_date_is_refused():
    """A negative fraction would COMPOUND a cash flow rather than discount it."""
    with pytest.raises(ProvenanceError, match="BEFORE the valuation date"):
        build_schedule(
            ("2026E",), Timing.EXACT_DATE,
            valuation_date=date(2027, 1, 1), fiscal_year_end=date(2025, 12, 31),
        )


def test_the_exact_convention_needs_a_date_to_count_from():
    with pytest.raises(ProvenanceError, match="needs a valuation date"):
        build_schedule(YEARS, Timing.EXACT_DATE)


def test_the_basis_names_every_cash_flow_date():
    """16.11: documented. A reader must be able to check the arithmetic."""
    schedule = build_schedule(
        ("2026E", "2027E"), Timing.EXACT_DATE,
        valuation_date=date(2026, 6, 30), fiscal_year_end=date(2025, 12, 31),
    )
    assert "2026-06-30" in schedule.basis
    assert "2026-12-31" in schedule.basis and "2027-12-31" in schedule.basis
    assert str(DAYS_IN_YEAR) in schedule.basis


# --- 16.13: the precision policy --------------------------------------------

@pytest.mark.parametrize("rate", ["0", "0.01", "0.09", "0.35", "1.5"])
def test_an_integer_exponent_is_exactly_the_multiplicative_result(rate):
    """Claim 2: no transcendental step on the integer path."""
    wacc = D(rate)
    for exponent in (1, 2, 5, 12):
        assert discount_factor(wacc, D(exponent)) == ONE / power(ONE + wacc, exponent)


@pytest.mark.parametrize("rate", ["0.01", "0.09", "0.35"])
@pytest.mark.parametrize("fraction", ["0.5", "1.5", "4.5", "2.5068493150684931"])
def test_a_fractional_factor_inverts_to_the_rate_it_came_from(rate, fraction):
    """Claim 3, stated as a round trip: (1/df)^(1/t) should return 1 + rate.

    Raising the reciprocal to the reciprocal power composes two transcendental
    steps, so the residual bounds both of them at once.
    """
    wacc = D(rate)
    factor = discount_factor(wacc, D(fraction))
    recovered = discount_factor(ONE / (ONE + wacc) ** 0, D(0))  # 1, exactly
    assert recovered == ONE
    round_trip = (ONE / factor) ** (ONE / D(fraction))
    relative = abs(round_trip - (ONE + wacc)) / (ONE + wacc) * D(100)
    assert relative < D("1e-40"), f"{relative} is not inside the stated policy"
    assert relative < CONTRACT


def test_a_half_power_squared_returns_the_base():
    """The cleanest statement of the policy: sqrt(1+w) squared is 1+w."""
    for rate in ("0.01", "0.09", "0.35"):
        wacc = D(rate)
        half = discount_factor(wacc, D("0.5"))
        assert abs((ONE / half) ** 2 - (ONE + wacc)) < D("1e-45")


def test_the_two_paths_agree_where_they_overlap():
    """A fractional exponent that happens to be whole must not disagree with
    the integer path by more than the policy allows."""
    wacc = D("0.09")
    exact = discount_factor(wacc, D(3))
    # Force the transcendental path with a value that is whole but not stored
    # as an integral Decimal... it IS integral, so compute it directly instead.
    import decimal

    from model.numeric import CALCULATION_CONTEXT

    with decimal.localcontext(CALCULATION_CONTEXT):
        transcendental = ONE / (D(3) * (ONE + wacc).ln()).exp()
    relative = abs(transcendental - exact) / exact * D(100)
    assert relative < D("1e-40")
    assert relative < CONTRACT


def test_a_rate_at_or_below_minus_one_hundred_percent_is_refused():
    with pytest.raises(ProvenanceError, match="not a discount rate"):
        discount_factor(D("-1"), D("0.5"))


def test_a_zero_fraction_discounts_by_nothing():
    """A cash flow on the valuation date is worth its face amount."""
    assert discount_factor(D("0.09"), D(0)) == ONE


# --- the year-end path must not have moved ----------------------------------

def test_adopting_the_option_did_not_move_the_default(loaded, valuation):
    """Claim 1, on the real fixture model rather than in the abstract."""
    wacc = valuation.wacc
    for index, item in enumerate(valuation.discounted, start=1):
        assert item.period == D(index)
        assert item.discount_factor == ONE / power(ONE + wacc, index)
