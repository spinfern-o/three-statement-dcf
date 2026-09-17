"""Items 123-128: the navigation shell, the charts, and the metric cards.

The chart tests are the ones worth reading. 6.5.f says charts have text
summaries and downloadable data, and the interesting question is not whether
a summary exists but whether it can be *omitted* -- so the first test asserts
a chart cannot be constructed without one.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.dashboard.cards import STATUS_LEGEND, portfolio_cards
from apps.api.app.dashboard.charts import LineChart, line_chart
from apps.api.app.dashboard.navigation import REQUIRES, SECTIONS, nav_items
from apps.api.app.dashboard.status import ModelStatus, Standing

D = Decimal

SERIES = (
    ("2024A", D("1800000")),
    ("2025A", D("2000000")),
    ("2026E", D("2160000")),
    ("2027E", D("2332800")),
)


# --- item 126: charts (6.5.f, 6.6.h, 6.2.e) ---------------------------------

def test_a_chart_cannot_be_built_without_a_text_summary():
    """6.5.f and 6.6.h. A summary added later is a summary that shipped late."""
    with pytest.raises(ValueError, match="no text summary"):
        LineChart(
            title="Revenue", unit="thousands", points=(), actual_path="",
            estimate_path="", y_ticks=(), summary="  ", csv="period,revenue\n",
        )


def test_a_chart_cannot_be_built_without_downloadable_data():
    with pytest.raises(ValueError, match="no downloadable data"):
        LineChart(
            title="Revenue", unit="thousands", points=(), actual_path="",
            estimate_path="", y_ticks=(), summary="a summary", csv="",
        )


def test_the_summary_names_the_trend_and_its_size():
    """6.6.h asks for screen-reader text for chart TRENDS, not for a title."""
    chart = line_chart("Revenue", SERIES, "thousands of USD")
    assert "2024A to 2027E" in chart.summary
    assert "rose 29.6 percent" in chart.summary
    assert "thousands of USD" in chart.summary


def test_the_summary_says_in_words_where_the_projection_starts():
    """6.2.e: never rely on colour alone. 1.19: a projection is not a fact."""
    chart = line_chart("Revenue", SERIES, "thousands")
    assert "Reported: 2024A" in chart.summary
    assert "Projected from 2026E" in chart.summary
    assert "not a fact (1.19)" in chart.summary


def test_the_projected_half_is_dashed_as_well_as_coloured():
    """The two paths are separate elements, so CSS can dash one of them."""
    chart = line_chart("Revenue", SERIES, "thousands")
    assert chart.actual_path and chart.estimate_path
    # The dashed segment starts at the last actual, so the halves join.
    assert chart.estimate_path.startswith(
        "M " + chart.actual_path.rsplit("L ", 1)[-1].strip()
    )


def test_the_csv_carries_the_stored_value_not_the_displayed_one():
    """4.18: calculation precision is separate from display precision."""
    chart = line_chart(
        "Revenue", (("2024A", D("1800000.123456")), ("2025A", D("2000000"))), "units"
    )
    assert "1800000.123456" in chart.csv
    assert "actual" in chart.csv and "estimate" not in chart.csv


def test_a_series_of_one_point_is_refused():
    with pytest.raises(ValueError, match="at least two periods"):
        line_chart("Revenue", (("2025A", D(1)),))


def test_a_flat_series_does_not_divide_by_zero():
    chart = line_chart("Revenue", (("2024A", D(100)), ("2025A", D(100))), "units")
    assert "was unchanged" in chart.summary
    assert all(point.y == chart.points[0].y for point in chart.points)


def test_growth_from_zero_is_undefined_rather_than_infinite():
    """4.12, in the one place a dashboard would otherwise print an infinity."""
    chart = line_chart("Revenue", (("2024A", D(0)), ("2025A", D(100))), "units")
    assert "undefined rather than infinite (4.12)" in chart.summary


def test_a_float_value_is_refused():
    """4.4, at the boundary where a number becomes a picture."""
    from model.numeric import PrecisionError

    with pytest.raises(PrecisionError):
        line_chart("Revenue", (("2024A", 1.5), ("2025A", 2.0)))


# --- item 123: the navigation shell -----------------------------------------

def test_the_portfolio_alone_has_no_document_sections():
    items = nav_items(None)
    assert [item.label for item in items] == ["Portfolio"]


def test_every_section_is_present_for_a_document():
    items = nav_items("doc-1")
    assert [item.label for item in items] == ["Portfolio"] + [
        label for label, _, _ in SECTIONS
    ]


def test_a_section_with_nothing_behind_it_is_dimmed_and_still_reachable():
    """6.5.i: an absent link explains nothing, so nothing is hidden."""
    items = {item.label: item for item in nav_items("doc-1", status=ModelStatus.NEEDS_REVIEW)}
    assert not items["Valuation"].available
    assert items["Valuation"].href == "/documents/doc-1/valuation"
    assert "cost-of-capital" in items["Valuation"].unavailable_reason
    assert items["Source room"].available


def test_everything_is_reachable_once_a_model_is_valuation_ready():
    items = nav_items("doc-1", status=ModelStatus.VALUATION_READY)
    assert all(item.available for item in items)


def test_no_status_means_no_dimming():
    """Inner pages do not recompute the standing, so they do not dim anything."""
    assert all(item.available for item in nav_items("doc-1"))


def test_the_current_section_is_marked():
    items = {item.label: item for item in nav_items("doc-1", current="schedules")}
    assert items["Schedules"].current
    assert not items["Statements"].current


def test_every_gated_section_has_a_reason():
    from apps.api.app.dashboard.navigation import REASONS

    for label in REQUIRES:
        assert REASONS.get(label), f"{label} is gated and gives no reason"


# --- items 125, 7.1.b: statuses and cards -----------------------------------

def test_the_seven_statuses_are_exactly_7_1_bs():
    assert [s.value for s in ModelStatus] == [
        "Draft", "Extracting", "Needs Review", "Validated",
        "Forecast Ready", "Valuation Ready", "Archived",
    ]


def test_every_status_has_a_written_meaning():
    """A status a reader cannot interpret is a badge."""
    covered = {status for status, _ in STATUS_LEGEND}
    assert covered == set(ModelStatus)
    for _, meaning in STATUS_LEGEND:
        assert len(meaning.split()) >= 8


def test_archived_is_never_inferred():
    """A model nobody touched is not the same as a model somebody finished."""
    meaning = dict(STATUS_LEGEND)[ModelStatus.ARCHIVED]
    assert "never inferred" in meaning


def test_every_card_carries_period_scenario_source_and_status():
    """Item 125 lists four labels, and the reason is 1.19."""
    standing = Standing(
        status=ModelStatus.VALIDATED, source_date="2025-12-31",
        valuation_date="2025-12-31", owner="larry", unresolved=("one thing",),
        blocked_by="something", gates=(),
    )
    cards = portfolio_cards((("doc", standing),))
    assert len(cards) == 4
    for card in cards:
        assert card.label and card.value
        assert card.period, f"{card.label} has no period label"
        assert card.source, f"{card.label} does not say where it came from"
        assert card.status


def test_the_cards_count_what_the_standings_say():
    def standing(status, unresolved=()):
        return Standing(
            status=status, source_date="", valuation_date="", owner="",
            unresolved=unresolved, blocked_by="", gates=(),
        )

    cards = {
        card.label: card.value
        for card in portfolio_cards((
            ("a", standing(ModelStatus.VALUATION_READY)),
            ("b", standing(ModelStatus.NEEDS_REVIEW, ("x", "y"))),
            ("c", standing(ModelStatus.VALIDATED, ("z",))),
        ))
    }
    assert cards["Models"] == "3"
    assert cards["Valuation ready"] == "1"
    assert cards["Needs review"] == "1"
    assert cards["Unresolved items"] == "3"
