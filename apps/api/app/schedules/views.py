"""The 7.6 Supporting Schedules screen, as rows a template can iterate.

Everything here is presentation: the arithmetic happened in the schedule
modules, and none of it is repeated. The split exists so the template holds
no logic that could disagree with the checks -- a screen that computes its
own totals is a second implementation, and the one nobody tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model import accounts

from .working_capital import Driver, WorkingCapitalSchedule


@dataclass(frozen=True)
class Row:
    label: str
    values: tuple
    is_total: bool = False
    absent_reason: str = ""


def working_capital_rows(schedule: WorkingCapitalSchedule) -> "tuple[Row, ...]":
    """One row per operating account, plus the two subtotals and NWC."""
    rows: list[Row] = []

    for index, name in enumerate(accounts.OPERATING_CURRENT_ASSETS):
        rows.append(
            Row(
                label=name.replace("_", " ").capitalize(),
                values=tuple(row.assets[index].value for row in schedule.years),
                absent_reason=f"the filing reports no {name!r} for this period",
            )
        )
    rows.append(
        Row(
            "Operating current assets",
            tuple(row.operating_current_assets for row in schedule.years),
            is_total=True,
        )
    )
    for index, name in enumerate(accounts.OPERATING_CURRENT_LIABILITIES):
        rows.append(
            Row(
                label=name.replace("_", " ").capitalize(),
                values=tuple(row.liabilities[index].value for row in schedule.years),
                absent_reason=f"the filing reports no {name!r} for this period",
            )
        )
    rows.append(
        Row(
            "Operating current liabilities",
            tuple(row.operating_current_liabilities for row in schedule.years),
            is_total=True,
        )
    )
    rows.append(
        Row(
            "Net working capital",
            tuple(row.nwc for row in schedule.years),
            is_total=True,
        )
    )
    return tuple(rows)


@dataclass(frozen=True)
class DriverRow:
    name: str
    numerator: str
    denominator: str
    values: "tuple[Driver, ...]"


def driver_rows(schedule: WorkingCapitalSchedule) -> "tuple[DriverRow, ...]":
    """One row per driver, across the periods, in the order 13.1.d lists them."""
    if not schedule.years:
        return ()
    first = schedule.years[0]
    return tuple(
        DriverRow(
            name=driver.name,
            numerator=driver.numerator,
            denominator=driver.denominator,
            values=tuple(row.drivers[index] for row in schedule.years),
        )
        for index, driver in enumerate(first.drivers)
    )


def total_unexplained(schedule) -> Decimal | None:
    """The sum of a roll-forward's unexplained differences, or None if any is.

    A single number for the top of a screen. None when any period could not be
    reconciled, because a sum over the periods that could is not the total and
    should not be shown as one.
    """
    if not getattr(schedule, "years", ()):
        return None
    deltas = [row.unexplained for row in schedule.years]
    if any(delta is None for delta in deltas):
        return None
    return sum(deltas)
