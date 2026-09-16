"""Item 32, and the one float boundary in the repository."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.extraction.geometry import (
    BoundingBox,
    GeometryError,
    PageGeometry,
    from_parser_number,
)


def test_a_coordinate_becomes_an_exact_decimal():
    value = from_parser_number(700.123456)
    assert isinstance(value, Decimal)
    assert value == Decimal("700.123")


def test_corners_are_normalized():
    box = BoundingBox.from_parser((300.5, 712.0, 72.0, 700.0))
    assert (box.x0, box.y0, box.x1, box.y1) == (
        Decimal("72.000"), Decimal("700.000"), Decimal("300.500"), Decimal("712.000")
    )


def test_boxes_are_stored_as_decimal_strings():
    """9.4: four decimal strings, so the highlight reconstructs exactly."""
    box = BoundingBox.from_parser((72, 700, 300, 712))
    assert box.as_strings() == ("72.000", "700.000", "300.000", "712.000")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_coordinate_is_refused(bad):
    """A highlight at a non-finite coordinate points nowhere."""
    with pytest.raises(GeometryError):
        from_parser_number(bad)


@pytest.mark.parametrize("bad", [True, None, "72", [1]])
def test_things_that_are_not_coordinates_are_refused(bad):
    with pytest.raises(GeometryError):
        from_parser_number(bad)


def test_rotation_is_recorded_not_baked_in():
    page = PageGeometry(1, Decimal("612"), Decimal("792"), 90)
    assert page.is_rotated


@pytest.mark.parametrize("rotation", [45, 360, -90])
def test_an_unexpected_rotation_is_refused(rotation):
    with pytest.raises(GeometryError):
        PageGeometry(1, Decimal("612"), Decimal("792"), rotation)


def test_page_numbers_are_one_based():
    with pytest.raises(GeometryError):
        PageGeometry(0, Decimal("612"), Decimal("792"), 0)


def test_containment():
    outer = BoundingBox.from_parser((0, 0, 100, 100))
    inner = BoundingBox.from_parser((10, 10, 20, 20))
    assert outer.contains(inner) and not inner.contains(outer)
