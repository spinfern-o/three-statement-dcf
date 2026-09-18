"""Assemble every Section 13 schedule from a built historical model.

The input is `BuiltStatements` -- the three engine ledgers Phase 6 fills from
a verified, mapped filing -- and the output is one `ScheduleSet` carrying all
seven schedules 13.1 to 13.7, including the three that cannot be built.

Order matters only for reading: 7.6 lists them working capital, PP&E,
intangibles, debt, leases, tax, equity, and this follows that so the screen
and the object agree.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..statements.build import BuiltStatements
from .base import Availability, Schedule
from .interest import InterestYear, implied_interest_rates
from .rollforward import (
    RollForwardSchedule,
    common_equity_schedule,
    debt_schedule,
    intangibles_schedule,
    ppe_schedule,
    retained_earnings_schedule,
)
from .tax import TaxScheduleView, tax_schedule
from .unavailable import lease_schedule, share_count_schedule
from .working_capital import WorkingCapitalSchedule, working_capital_schedule


@dataclass(frozen=True)
class ScheduleSet:
    """Every supporting schedule for one filing, in 7.6's order."""

    years: tuple[str, ...]
    working_capital: WorkingCapitalSchedule
    ppe: RollForwardSchedule
    intangibles: Schedule
    debt: RollForwardSchedule
    interest: tuple[InterestYear, ...]
    leases: Schedule
    tax: TaxScheduleView
    retained_earnings: RollForwardSchedule
    common_equity: RollForwardSchedule
    share_count: Schedule

    @property
    def all(self) -> tuple[Schedule, ...]:
        return (
            self.working_capital,
            self.ppe,
            self.intangibles,
            self.debt,
            self.leases,
            self.tax,
            self.retained_earnings,
            self.common_equity,
            self.share_count,
        )

    @property
    def available(self) -> tuple[Schedule, ...]:
        return tuple(s for s in self.all if s.is_available)

    @property
    def unavailable(self) -> tuple[Schedule, ...]:
        return tuple(s for s in self.all if not s.is_available)

    def by_key(self, key: str) -> Schedule:
        for schedule in self.all:
            if schedule.key == key:
                return schedule
        raise KeyError(f"no schedule {key!r}; known: {[s.key for s in self.all]}")

    def describe(self) -> str:
        counts = dict.fromkeys(Availability, 0)
        for schedule in self.all:
            counts[schedule.availability] += 1
        return (
            f"  years: {', '.join(self.years) or '(none)'}\n"
            f"  {counts[Availability.AVAILABLE]} available, "
            f"{counts[Availability.PARTIAL]} partial, "
            f"{counts[Availability.UNAVAILABLE]} unavailable"
        )


def build_schedules(built: BuiltStatements) -> ScheduleSet:
    """13.1-13.7 for every period the filing reports."""
    ledgers, years = built.ledgers, built.years
    return ScheduleSet(
        years=years,
        working_capital=working_capital_schedule(ledgers, years),
        ppe=ppe_schedule(ledgers, years),
        intangibles=intangibles_schedule(ledgers, years),
        debt=debt_schedule(ledgers, years),
        interest=implied_interest_rates(ledgers, years),
        leases=lease_schedule(),
        tax=tax_schedule(ledgers, years),
        retained_earnings=retained_earnings_schedule(ledgers, years),
        common_equity=common_equity_schedule(ledgers, years),
        share_count=share_count_schedule(),
    )
