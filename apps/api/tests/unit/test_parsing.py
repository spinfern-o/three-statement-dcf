"""Item 35, and rule 1.5 -- the rule most likely to be violated by accident.

> Never treat a blank, dash, em dash, "N/A," or missing table cell as zero
> unless the source explicitly defines it as zero or a reviewer confirms it.

Every test that asserts `value is None` is asserting the absence of a bug that
would be invisible in the output: a zero where a company reported nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.extraction.parsing import (
    NumberLocale,
    SignSource,
    UnitMarker,
    parse_reported_value,
)
from apps.api.app.extraction.reasons import ReasonCode

US = NumberLocale.DOT_DECIMAL
EU = NumberLocale.COMMA_DECIMAL


# --- rule 1.5 ---------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, code",
    [
        ("", ReasonCode.BLANK_CELL),
        ("   ", ReasonCode.BLANK_CELL),
        ("-", ReasonCode.DASH_AMBIGUOUS),
        ("–", ReasonCode.DASH_AMBIGUOUS),
        ("—", ReasonCode.DASH_AMBIGUOUS),
        ("−", ReasonCode.DASH_AMBIGUOUS),
        ("$—", ReasonCode.DASH_AMBIGUOUS),
        ("(—)", ReasonCode.DASH_AMBIGUOUS),
        ("N/A", ReasonCode.NOT_APPLICABLE),
        ("n/a", ReasonCode.NOT_APPLICABLE),
        ("Not applicable", ReasonCode.NOT_APPLICABLE),
        ("n/m", ReasonCode.NOT_APPLICABLE),
    ],
)
def test_nothing_ambiguous_becomes_zero(raw, code):
    parsed = parse_reported_value(raw, locale=US)
    assert parsed.value is None, f"{raw!r} produced a number"
    assert code in parsed.reason_codes
    assert parsed.needs_review


def test_none_is_not_zero_and_says_so():
    parsed = parse_reported_value("—", locale=US)
    assert parsed.value is None
    assert "not zero" in parsed.note


@pytest.mark.parametrize("raw", ["nil", "none", "NIL", "-0-", "zero"])
def test_a_written_zero_is_a_zero(raw):
    """source-policy.md §6: the one exit that does not need a reviewer."""
    parsed = parse_reported_value(raw, locale=US)
    assert parsed.value == Decimal("0")
    assert ReasonCode.WRITTEN_ZERO in parsed.reason_codes
    assert not parsed.needs_review


def test_the_raw_string_is_always_retained():
    parsed = parse_reported_value("(1,234)", locale=US)
    assert parsed.raw_value == "(1,234)"
    assert parsed.value == Decimal("-1234")


# --- 10.27, separator ambiguity ---------------------------------------------

def test_an_ambiguous_number_is_refused_while_the_locale_is_unconfirmed():
    parsed = parse_reported_value("1,234")
    assert parsed.value is None
    assert ReasonCode.SEPARATOR_AMBIGUOUS in parsed.reason_codes
    assert "1.234" in parsed.note and "1234" in parsed.note


@pytest.mark.parametrize(
    "raw, locale, expected",
    [
        ("1,234", US, "1234"),
        ("1,234", EU, "1.234"),
        ("1,234.56", US, "1234.56"),
        ("1.234,56", EU, "1234.56"),
        ("1 234,56", EU, "1234.56"),
        ("1'234.56", US, "1234.56"),
    ],
)
def test_a_confirmed_locale_resolves_it(raw, locale, expected):
    assert parse_reported_value(raw, locale=locale).value == Decimal(expected)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234,567", "1234567"),   # two comma groups: only dot-decimal reads this
        ("1.234.567", "1234567"),   # two dot groups: only comma-decimal reads this
        ("1,234.56", "1234.56"),
        ("1.234,56", "1234.56"),
        ("1,23", "1.23"),           # a US group must be exactly three digits
        ("12", "12"),               # both readings agree, so it is not ambiguous
        (".5", "0.5"),
    ],
)
def test_unambiguous_numbers_parse_without_a_confirmed_locale(raw, expected):
    parsed = parse_reported_value(raw)
    assert parsed.value == Decimal(expected), parsed.note


def test_a_number_inconsistent_with_the_confirmed_locale_is_refused():
    parsed = parse_reported_value("1.234,56", locale=US)
    assert parsed.value is None
    assert ReasonCode.SEPARATOR_AMBIGUOUS in parsed.reason_codes
    assert "comma_decimal" in parsed.note


@pytest.mark.parametrize("raw", ["abc", "1..2", "1,234.", "1,23,456", "12/31/2025"])
def test_things_that_are_not_numbers_are_refused(raw):
    parsed = parse_reported_value(raw, locale=US)
    assert parsed.value is None
    assert ReasonCode.NOT_NUMERIC in parsed.reason_codes or ReasonCode.SEPARATOR_AMBIGUOUS in parsed.reason_codes


# --- 10.16, signs -----------------------------------------------------------

@pytest.mark.parametrize(
    "raw, value, source",
    [
        ("(1,234)", "-1234", SignSource.PARENTHESES),
        ("-1,234", "-1234", SignSource.LEADING_MINUS),
        ("−1,234", "-1234", SignSource.LEADING_MINUS),
        ("1,234-", "-1234", SignSource.TRAILING_MINUS),
        ("+1,234", "1234", SignSource.LEADING_PLUS),
        ("1,234", "1234", SignSource.POSITIVE_AS_PRINTED),
    ],
)
def test_the_sign_and_its_evidence_are_both_recorded(raw, value, source):
    parsed = parse_reported_value(raw, locale=US)
    assert parsed.value == Decimal(value)
    assert parsed.sign_source is source


def test_contradictory_sign_markers_are_refused():
    """Parentheses and a minus are a contradiction, not a double negative."""
    parsed = parse_reported_value("(-1,234)", locale=US)
    assert parsed.value is None
    assert ReasonCode.SIGN_UNRESOLVED in parsed.reason_codes


# --- 10.18, footnote markers ------------------------------------------------

@pytest.mark.parametrize(
    "raw, value, marker",
    [
        ("1,234¹", "1234", "¹"),
        ("1,234(2)", "1234", "(2)"),
        ("(12,000)¹", "-12000", "¹"),
        ("(1,234)(2)", "-1234", "(2)"),
        ("1,234*", "1234", "*"),
    ],
)
def test_a_footnote_marker_is_removed_from_the_value_and_kept(raw, value, marker):
    parsed = parse_reported_value(raw, locale=US)
    assert parsed.value == Decimal(value)
    assert marker in parsed.footnote_markers
    assert ReasonCode.FOOTNOTE_MARKER_STRIPPED in parsed.reason_codes


def test_a_superscript_is_not_silently_turned_into_a_digit():
    """NFKC normalization would make 1,234 + superscript one into 12341."""
    parsed = parse_reported_value("1,234¹", locale=US)
    assert parsed.value == Decimal("1234")


def test_a_parenthesized_number_alone_is_negative_not_a_footnote():
    assert parse_reported_value("(1)", locale=US).value == Decimal("-1")


# --- units ------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, symbol",
    [("$1,234", "$"), ("1,234 USD", "USD"), ("USD 1,234", "USD"), ("€1.234", "€")],
)
def test_currency_symbols_are_stripped_and_recorded(raw, symbol):
    parsed = parse_reported_value(raw, locale=US if symbol != "€" else EU)
    assert parsed.currency_symbol == symbol
    assert parsed.unit_marker is UnitMarker.CURRENCY


def test_a_percentage_is_marked_and_not_divided():
    parsed = parse_reported_value("12.5%", locale=US)
    assert parsed.value == Decimal("12.5")
    assert parsed.unit_marker is UnitMarker.PERCENT


def test_three_uppercase_letters_alone_are_not_a_currency():
    parsed = parse_reported_value("NET", locale=US)
    assert parsed.currency_symbol is None
    assert parsed.value is None


# --- 4.14, source precision --------------------------------------------------

@pytest.mark.parametrize("raw, decimals", [("1,234", 0), ("1,234.5", 1), ("1,234.50", 2)])
def test_the_printed_precision_is_recorded(raw, decimals):
    assert parse_reported_value(raw, locale=US).decimals == decimals


def test_trailing_zeros_are_preserved_exactly():
    """1,234.50 is not 1234.5 to a reader reconciling to the source (4.14)."""
    assert str(parse_reported_value("1,234.50", locale=US).value) == "1234.50"


# --- full-width forms --------------------------------------------------------

def test_full_width_digits_are_folded():
    assert parse_reported_value("１，２３４", locale=US).value == Decimal("1234")


def test_a_value_is_never_a_float():
    parsed = parse_reported_value("1,234.56", locale=US)
    assert isinstance(parsed.value, Decimal)
