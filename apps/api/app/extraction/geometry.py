"""Item 32: page geometry and source locations.

**This module contains the only float-to-Decimal conversion in the
repository.** It is deliberate, it is confined here, and it is worth the
paragraph.

`model/numeric.py` refuses floats outright, because a monetary value that
arrived as a float has already lost exactness and converting it preserves the
error rather than removing it. Page coordinates are a different kind of
quantity and the argument does not carry over:

  * They are not financial values and never enter a calculation. A fact's
    number comes from its `raw_value` string through `parsing.py`. A bounding
    box is used to draw a highlight over a PDF page (10.31) and for nothing
    else.
  * They arrive as binary floats from the PDF parser, which is how PyMuPDF's
    API reports them. There is no exact form to ask for.

So the conversion happens once, here, at the boundary, via `str()` -- which
gives the shortest decimal that round-trips to the same float -- and the
result is quantized to 0.001 PDF points. At 72 points to the inch that is
about a third of a micron, which is far below anything a highlight rectangle
needs and well inside the precision the coordinates carried in the first
place.

Rotation (22.3.g): a page's `/Rotate` value is recorded alongside the box
rather than baked into it. PyMuPDF reports coordinates in the rotated,
displayed space, so a stored box lines up with what a reviewer sees; the
rotation is kept so that a future consumer working in unrotated user space can
undo it, and so that a rotated page is visible as a fact about the source.
"""

from __future__ import annotations

import decimal
import math
from dataclasses import dataclass
from decimal import Decimal

#: Coordinates are quantized to this. See the module note.
COORDINATE_PRECISION = Decimal("0.001")


class GeometryError(ValueError):
    """A coordinate could not be represented."""


def from_parser_number(value: object, *, what: str = "coordinate") -> Decimal:
    """Convert one coordinate from the PDF parser into a quantized Decimal.

    Accepts the float or int the parser produced. Refuses bool, None, strings
    and non-finite values -- a NaN coordinate means the parser could not place
    the item, and silently storing it would put a highlight nowhere.
    """
    if isinstance(value, bool) or value is None:
        raise GeometryError(f"{what} is {value!r}, which is not a coordinate")
    if isinstance(value, int):
        return Decimal(value).quantize(COORDINATE_PRECISION)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise GeometryError(
                f"{what} is {value}, so the parser could not place this item on "
                f"the page. It is not stored -- a highlight at a non-finite "
                f"coordinate points nowhere."
            )
        # str() gives the shortest decimal that round-trips to this float.
        return Decimal(str(value)).quantize(COORDINATE_PRECISION, rounding=decimal.ROUND_HALF_EVEN)
    if isinstance(value, Decimal):
        return value.quantize(COORDINATE_PRECISION)
    raise GeometryError(f"{what} is a {type(value).__name__}, which is not a coordinate")


@dataclass(frozen=True)
class BoundingBox:
    """A rectangle in PDF user space, as four decimal strings. 9.4.

    The origin and axis direction are PyMuPDF's: y grows downward from the top
    left of the displayed (rotation-applied) page. That is recorded here rather
    than left to be rediscovered, because a box interpreted against the wrong
    origin highlights the wrong row.
    """

    x0: Decimal
    y0: Decimal
    x1: Decimal
    y1: Decimal

    @classmethod
    def from_parser(cls, rect: tuple[object, object, object, object]) -> BoundingBox:
        """Build from the 4-tuple the parser reports, normalizing the corners."""
        x0, y0, x1, y1 = (from_parser_number(v, what=n) for v, n in zip(rect, ["x0", "y0", "x1", "y1"]))
        # A PDF rectangle may be given with its corners in either order.
        return cls(x0=min(x0, x1), y0=min(y0, y1), x1=max(x0, x1), y1=max(y0, y1))

    @property
    def width(self) -> Decimal:
        return self.x1 - self.x0

    @property
    def height(self) -> Decimal:
        return self.y1 - self.y0

    def as_strings(self) -> tuple[str, str, str, str]:
        """The stored form: four decimal strings (9.4, 4.2)."""
        return (str(self.x0), str(self.y0), str(self.x1), str(self.y1))

    def contains(self, other: BoundingBox) -> bool:
        return (
            self.x0 <= other.x0
            and self.y0 <= other.y0
            and self.x1 >= other.x1
            and self.y1 >= other.y1
        )


@dataclass(frozen=True)
class PageGeometry:
    """The page a box is measured against."""

    page_number: int
    width: Decimal
    height: Decimal
    #: The page's /Rotate value, normalized to 0, 90, 180 or 270.
    rotation: int

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise GeometryError(f"page numbers are 1-based; got {self.page_number}")
        if self.rotation not in (0, 90, 180, 270):
            raise GeometryError(f"unexpected page rotation {self.rotation}")

    @property
    def is_rotated(self) -> bool:
        return self.rotation != 0
