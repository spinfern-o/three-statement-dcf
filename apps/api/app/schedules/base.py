"""Shared vocabulary for the supporting schedules (specification 13).

A schedule here is a *historical* one: it is derived from the statements a
filing actually printed, and its job is to explain how a balance moved
between the periods the filing covers. That is a different object from the
forecast schedules in `model/schedules.py`, which project a balance forward
from drivers a person supplies. The two meet in Phase 8 and later, where a
historical driver becomes the starting point for a forecast assumption.

Three conventions run through every schedule in this package, and each one
exists because the obvious alternative quietly produces a wrong number.

**A roll-forward is built from disclosed components only.** 13.2 writes the
PP&E schedule as `Beginning + CapEx + Acquisitions - Depreciation - Disposals
+/- FX and Other`. A filing of the kind this system ingests discloses the
first three and almost never the rest on the face of the statements. The
tempting move is to solve for the remainder and label it "other", which makes
the schedule tie every time and therefore makes the reconciliation in 13.8
meaningless. So nothing here plugs: the computed ending is the sum of what was
disclosed, the reported ending comes from the balance sheet, and the gap
between them is reported as `unexplained`. Specification 12.5 and STEP 6 both
say it in the same words -- keep differences visible.

**Absent is not zero.** A component the filing does not report is recorded as
an absent line with the reason, and it is named in the reconciliation when the
schedule does not tie. `model/statements.py` makes the same distinction for
the same reason (STEP 5).

**A schedule that cannot be built says so.** `Availability.UNAVAILABLE`
carries the sentence explaining what is missing and where it would come from.
An empty table implies the filing had nothing to show, which is a different
claim and usually a false one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from model.numeric import ZERO


class Availability(str, Enum):
    """Whether a schedule could be built from this filing's canonical lines."""

    AVAILABLE = "available"
    #: Built, but some part 13 asks for is missing -- e.g. the tax schedule's
    #: effective rate without its current/deferred split.
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ScheduleLine:
    """One labelled amount inside a schedule, or one that is absent.

    `basis` is the sentence a reviewer reads to know where the number came
    from: which canonical line, on which statement, and what was done to its
    sign. 14.x and rule 1.10 both ask that nothing be hidden inside a formula,
    and a roll-forward that adds CapEx without saying CapEx is stored as a
    negative cash outflow is hiding exactly that.
    """

    label: str
    value: Decimal | None
    basis: str
    #: Set when `value is None`: what the filing did not report.
    absent_reason: str = ""

    @property
    def is_present(self) -> bool:
        return self.value is not None

    def __post_init__(self) -> None:
        if self.value is None and not self.absent_reason:
            raise ValueError(
                f"ScheduleLine {self.label!r} has no value and no reason. "
                "An absent line must say what is missing (STEP 5)."
            )


@dataclass(frozen=True)
class Caveat:
    """Something true about the schedule that its numbers do not show.

    Distinct from an absent line: a caveat is about a figure that *is*
    present and may not mean what the schedule uses it for. The combined
    depreciation-and-amortization line is the standing example -- it is
    present, it is used as the PP&E schedule's depreciation, and that is
    only right if the company amortizes nothing.
    """

    rule: str  # the specification clause or step it comes from
    text: str


@dataclass(frozen=True)
class Reconciliation:
    """13.8: a schedule's own closing figure against the statement's.

    `difference` is `computed - reported`. It is never applied to anything.
    """

    year: str
    #: The canonical line and statement this reconciles against, in words.
    statement_line: str
    computed: Decimal | None
    reported: Decimal | None
    note: str = ""

    @property
    def difference(self) -> Decimal | None:
        if self.computed is None or self.reported is None:
            return None
        return self.computed - self.reported

    @property
    def ties(self) -> bool | None:
        """Exact equality. The tolerance question belongs to the checks."""
        delta = self.difference
        return None if delta is None else delta == ZERO


@dataclass(frozen=True, kw_only=True)
class Schedule:
    """What every schedule in this package has in common.

    Subclasses add the rows; this carries identity, availability and the
    reconciliation 13.8 requires for every period.
    """

    key: str          # "working_capital", "ppe", ...
    title: str        # "Working capital"
    rule: str         # "13.1"
    availability: Availability
    #: Why, when availability is not AVAILABLE. Required in that case.
    reason: str = ""
    caveats: tuple[Caveat, ...] = field(default_factory=tuple)
    reconciliations: tuple[Reconciliation, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.availability is not Availability.AVAILABLE and not self.reason:
            raise ValueError(
                f"Schedule {self.key!r} is {self.availability.value} and must say why "
                f"({self.rule}). A schedule shown as unavailable without a reason is "
                "indistinguishable from one nobody built."
            )

    @property
    def is_available(self) -> bool:
        return self.availability is not Availability.UNAVAILABLE
