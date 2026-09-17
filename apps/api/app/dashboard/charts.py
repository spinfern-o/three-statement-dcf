"""Item 126: charts, with the text summary and the data 6.5.f requires.

Two rules shape this module and neither is about drawing.

**6.5.f -- "Charts have text summaries and downloadable data."** So a chart is
never built without both. `LineChart` cannot be constructed without a summary
and a CSV, because a chart whose summary was added later is a chart that was
shipped without one. 6.6.h asks for screen-reader text for chart trends
specifically, so the summary states the direction and the size of the move
rather than repeating the title.

**6.2.e -- "Never rely on color alone to convey state."** The forecast half of
a series is dashed as well as differently coloured, and the summary says in
words where the actuals stop. A reader who cannot see the colour difference,
or who prints the page, still knows which half is a projection -- which for a
projection drawn beside an actual is not a nicety (1.19).

Drawn as inline SVG computed in Python. No charting library and no JavaScript:
the values are `Decimal`, and every charting library in the browser would take
them as floats, which 4.4 forbids in the authoritative path and which would
also make the rendered shape disagree with the stored number in the last
digits. Rounding to integer user-space coordinates happens once, here, at the
boundary where a number becomes a picture.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model.numeric import D, ZERO, quantize_for_display

#: SVG user-space geometry. A viewBox, so the page scales it.
WIDTH = D(720)
HEIGHT = D(240)
PAD_LEFT = D(72)
PAD_RIGHT = D(16)
PAD_TOP = D(16)
PAD_BOTTOM = D(32)

PERCENT_PLACES = 1


@dataclass(frozen=True)
class Point:
    label: str
    value: Decimal
    x: Decimal
    y: Decimal
    is_estimate: bool


@dataclass(frozen=True)
class LineChart:
    """One series over periods, with everything 6.5.f and 6.6.h require."""

    title: str
    unit: str
    points: "tuple[Point, ...]"
    actual_path: str
    estimate_path: str
    y_ticks: "tuple[tuple[Decimal, str], ...]"
    #: 6.6.h. Required, not optional.
    summary: str
    #: 6.5.f. Required, not optional.
    csv: str
    width: Decimal = WIDTH
    height: Decimal = HEIGHT

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError(
                f"chart {self.title!r} has no text summary. 6.5.f and 6.6.h "
                "require one, and a chart whose summary is added later is a "
                "chart that shipped without it."
            )
        if not self.csv.strip():
            raise ValueError(
                f"chart {self.title!r} has no downloadable data (6.5.f)."
            )


def _scale(value, low, high, lo_px, hi_px) -> Decimal:
    if high == low:
        return (lo_px + hi_px) / D(2)
    return lo_px + (value - low) * (hi_px - lo_px) / (high - low)


def _format(value: Decimal) -> str:
    return f"{value:,.0f}"


def _summary(title: str, points: "tuple[Point, ...]", unit: str) -> str:
    """6.6.h: the trend, in words, with the numbers a reader would want."""
    first, last = points[0], points[-1]
    actuals = [p for p in points if not p.is_estimate]
    estimates = [p for p in points if p.is_estimate]

    parts = [
        f"{title}, {len(points)} periods from {first.label} to {last.label}, "
        f"in {unit}."
    ]
    if actuals:
        parts.append(
            f"Reported: {actuals[0].label} {_format(actuals[0].value)} to "
            f"{actuals[-1].label} {_format(actuals[-1].value)}."
        )
    if estimates:
        parts.append(
            f"Projected from {estimates[0].label} to {estimates[-1].label}, "
            f"{_format(estimates[0].value)} to {_format(estimates[-1].value)}. "
            "Projected periods are drawn with a dashed line. A projection is "
            "not a fact (1.19)."
        )
    if first.value != ZERO:
        change = (last.value - first.value) / abs(first.value) * D(100)
        direction = "rose" if change > 0 else ("fell" if change < 0 else "was unchanged")
        parts.append(
            f"Over the whole span it {direction} "
            f"{quantize_for_display(abs(change), PERCENT_PLACES)} percent."
        )
    else:
        # 4.12: a relative measure against zero is undefined, not infinite.
        parts.append(
            "The first period is zero, so the change over the span is "
            "undefined rather than infinite (4.12)."
        )
    return " ".join(parts)


def _csv(title: str, points: "tuple[Point, ...]", unit: str) -> str:
    """6.5.f's downloadable data, at full stored precision.

    Not the displayed values. A downloaded series a reader recomputes from
    must be the number the model holds, not the number the axis had room for
    (4.18: calculation precision is shown separately from display precision).
    """
    lines = [f"period,{title.lower().replace(' ', '_')},unit,basis"]
    for point in points:
        basis = "estimate" if point.is_estimate else "actual"
        lines.append(f"{point.label},{point.value},{unit},{basis}")
    return "\n".join(lines) + "\n"


def line_chart(
    title: str,
    series: "tuple[tuple[str, Decimal], ...]",
    unit: str = "reporting units",
) -> LineChart:
    """Build a chart from `(period label, value)` pairs, actuals then estimates.

    A period ending in `E` is a projection, which is the same convention
    `Periods` enforces (15.2) rather than a second one invented here.
    """
    if len(series) < 2:
        raise ValueError(
            f"chart {title!r} needs at least two periods; a line through one "
            "point is a dot with a trend implied."
        )
    values = [D(value, what=f"{title} {label}") for label, value in series]
    low, high = min(values), max(values)
    # A flat series would otherwise scale to a division by zero; pad it so the
    # line sits in the middle of the plot rather than on its edge.
    if low == high:
        low, high = low - D(1), high + D(1)

    left, right = PAD_LEFT, WIDTH - PAD_RIGHT
    top, bottom = PAD_TOP, HEIGHT - PAD_BOTTOM
    step = (right - left) / D(len(series) - 1)

    points = tuple(
        Point(
            label=label,
            value=value,
            x=left + step * D(index),
            y=_scale(value, low, high, bottom, top),
            is_estimate=label.strip().upper().endswith("E"),
        )
        for index, ((label, _), value) in enumerate(zip(series, values))
    )

    actual = [p for p in points if not p.is_estimate]
    estimate = [p for p in points if p.is_estimate]
    # The dashed half starts at the last actual, so the two segments join
    # rather than leaving a gap the eye reads as missing data.
    if actual and estimate:
        estimate = [actual[-1]] + estimate

    def path(items) -> str:
        if len(items) < 2:
            return ""
        head = f"M {items[0].x:.2f} {items[0].y:.2f}"
        return head + "".join(f" L {p.x:.2f} {p.y:.2f}" for p in items[1:])

    ticks = tuple(
        (
            _scale(low + (high - low) * D(fraction) / D(4), low, high, bottom, top),
            _format(low + (high - low) * D(fraction) / D(4)),
        )
        for fraction in (0, 2, 4)
    )

    return LineChart(
        title=title,
        unit=unit,
        points=points,
        actual_path=path(actual),
        estimate_path=path(estimate),
        y_ticks=ticks,
        summary=_summary(title, points, unit),
        csv=_csv(title, points, unit),
    )
