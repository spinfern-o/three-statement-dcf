"""One display precision, across every screen and every export (4.18, 4.19, 21.8).

Found by item 143. Before this module the same figure was displayed three
different ways depending on which screen it appeared on, and two of those ways
rounded with no tooltip -- which 4.19 requires without exception.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.app.display import (
    ABSENT,
    FILTERS,
    PLACES,
    display,
    exact,
    is_rounded,
    money,
    tooltip,
)

TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "api" / "templates"


def test_a_figure_displays_the_same_way_whatever_asks_for_it():
    value = Decimal("2873867.4410713814952939494840074741304606143072043")
    assert money(value) == display(value, "currency") == "2,873,867"


def test_every_unit_kind_has_a_stated_precision():
    assert set(PLACES) == {
        "currency",
        "percent",
        "ratio",
        "days",
        "integer",
        "factor",
    }
    for kind, places in PLACES.items():
        assert places >= 0, kind


@pytest.mark.parametrize(
    "value, kind, expected",
    [
        (Decimal("1234567.89"), "currency", "1,234,568"),
        (Decimal("-1234567.89"), "currency", "-1,234,568"),
        (Decimal("0"), "currency", "0"),
        (Decimal("12.345"), "percent", "12.3"),
        (Decimal("0.0930328"), "ratio", "0.0930"),
        (Decimal("45.67"), "days", "45.7"),
        (None, "currency", ABSENT),
    ],
)
def test_each_unit_displays_at_its_own_precision(value, kind, expected):
    assert display(value, kind) == expected


def test_rounding_is_half_even_like_every_other_rounding_here():
    """4.7's ROUND_HALF_EVEN, not the half-up a naive formatter would use."""
    assert display(Decimal("0.5"), "currency") == "0"
    assert display(Decimal("1.5"), "currency") == "2"
    assert display(Decimal("2.5"), "currency") == "2"


def test_an_absent_value_is_an_em_dash_and_never_a_zero():
    """Rule 1.3. A blank reads as an oversight; a zero is a claim."""
    assert money(None) == ABSENT != "0"


# --- 4.19: every rounded value owes a tooltip -------------------------------


def test_a_rounded_value_is_labelled_with_its_full_stored_value():
    value = Decimal("2873867.4410713814952939")
    assert is_rounded(value, "currency")
    assert exact(value) in tooltip(value, "currency")
    assert "4.19" in tooltip(value, "currency")


def test_a_value_that_displays_losslessly_gets_no_tooltip():
    """A tooltip repeating what is on screen teaches a reader to ignore them,
    and the next one -- the one carrying a hidden figure -- goes unread."""
    assert not is_rounded(Decimal("1234"), "currency")
    assert tooltip(Decimal("1234"), "currency") == ""


def test_exact_never_rounds():
    value = Decimal("0.1") / Decimal("3")
    assert exact(value) == str(value)
    assert len(exact(value)) > 20


# --- the templates all reach the same formatter -----------------------------

#: Any thousands-separated or fixed-decimal format applied in a template. The
#: separator forms are only ever used on money here, and `%.Nf` on anything but
#: an SVG coordinate is a second display precision.
FORMATTER = re.compile(r"""["']%?\{?:?,[^"']*\}?["']\s*\|?\s*\.?\s*format\(""")
FIXED = re.compile(r'"%\.\d+f"\s*\|\s*format\(\s*(?!point\.|y\b|chart\.)')


def test_no_template_formats_a_financial_number_by_itself():
    """The defect this module fixed, asserted so it cannot come back.

    A template that formats its own numbers is a second display precision, and
    21.8 cannot be met against a website that disagrees with itself.

    SVG geometry is deliberately exempt: `index.html` formats chart coordinates
    to two decimals, and a pixel position is not a figure a reader reads.
    """
    offenders = []
    for path in sorted(TEMPLATES.glob("*.html")):
        body = path.read_text()
        if FORMATTER.search(body) or FIXED.search(body):
            offenders.append(path.name)
    assert offenders == [], f"these templates format numbers themselves: {offenders}"


def test_the_filters_are_registered_on_the_environment(forecast_client):
    environment = forecast_client.app.state.templates.env
    for name in FILTERS:
        assert name in environment.filters, name
        assert environment.filters[name] is FILTERS[name]


@pytest.mark.parametrize("screen", ("/forecast", "/valuation"))
def test_every_screen_that_rounds_a_figure_labels_it(forecast_client, screen):
    """4.19 on the rendered page, not in a helper nobody called.

    Only the two screens that actually round on this fixture. The historical
    statements report whole figures the filing printed, so nothing rounds and
    no tooltip is owed -- asserting one there would be asserting that this
    filing has fractional cents, which it does not.
    """
    page = forecast_client.get(f"/documents/{forecast_client.document_id}{screen}").text
    assert "Full stored value:" in page, f"{screen} rounds without a 4.19 tooltip"
    assert "(4.19)" in page


@pytest.mark.parametrize(
    "screen",
    ("/statements", "/schedules", "/formulas", "/assumptions", "/forecast", "/valuation"),
)
def test_no_screen_shows_a_rounded_figure_without_offering_its_tooltip(forecast_client, screen):
    """Structural, so a screen that happens not to round today stays covered.

    Every template printing a figure emits the tooltip conditionally beside it,
    so a value that later needs one gets one without anybody remembering.
    """
    name = {
        "/statements": "statements",
        "/schedules": "schedules",
        "/formulas": "formulas",
        "/assumptions": "assumptions",
        "/forecast": "forecast",
        "/valuation": "valuation",
    }[screen]
    body = (TEMPLATES / f"{name}.html").read_text()
    printed = body.count("| money }}")
    labelled = body.count("| tooltip %}")
    assert printed, f"{name}.html prints no figures; this test proved nothing"
    assert labelled >= printed, (
        f"{name}.html prints {printed} figure(s) and offers {labelled} tooltip(s)"
    )


def test_the_tooltip_carries_digits_the_page_does_not_show(forecast_client):
    page = forecast_client.get(f"/documents/{forecast_client.document_id}/valuation").text
    shown = re.findall(r"Full stored value: ([0-9.\-]+) \(4\.19\)", page)
    assert shown, "no 4.19 tooltip on the valuation screen"
    for value in shown:
        assert Decimal(value) != Decimal(money(Decimal(value)).replace(",", ""))
