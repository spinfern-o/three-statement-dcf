"""7.1.b: the seven statuses a model can be in, computed rather than declared.

    Draft -> Extracting -> Needs Review -> Validated -> Forecast Ready
                                                     -> Valuation Ready
    (and Archived, from any of them)

**Nothing sets these.** Every one is derived from what the model actually
contains, because a status somebody typed is a status that goes stale the
moment anything else changes -- and this one is the first thing a reader sees
on the portfolio screen, so a stale one is the most expensive kind.

The order is the order of the work, and each step is the gate of the one
before it: you cannot review what was not extracted, cannot validate what was
not reviewed, cannot forecast what did not validate, and cannot value what did
not forecast. So the status is the *furthest* stage whose gate is satisfied,
and `blocked_by` names what is stopping the next one -- which is the part a
reader can act on.

`Archived` is deliberately absent from the computation. It is a decision
somebody makes about a model, not a fact about its contents, and inferring it
would mean guessing that a model nobody touched recently is finished rather
than abandoned. It is carried as a state the enum can hold and nothing here
assigns.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelStatus(str, Enum):
    """7.1.b's seven, and no others."""

    DRAFT = "Draft"
    EXTRACTING = "Extracting"
    NEEDS_REVIEW = "Needs Review"
    VALIDATED = "Validated"
    FORECAST_READY = "Forecast Ready"
    VALUATION_READY = "Valuation Ready"
    ARCHIVED = "Archived"

    @property
    def rank(self) -> int:
        order = {
            "Draft": 0, "Extracting": 1, "Needs Review": 2, "Validated": 3,
            "Forecast Ready": 4, "Valuation Ready": 5, "Archived": 6,
        }
        return order[self.value]

    @property
    def tone(self) -> str:
        """6.1's colour roles. 6.2.e: never colour alone -- the label is the
        primary signal and this only decides the badge behind it."""
        return {
            "Draft": "neutral",
            "Extracting": "neutral",
            "Needs Review": "warning",
            "Validated": "success",
            "Forecast Ready": "success",
            "Valuation Ready": "success",
            "Archived": "neutral",
        }[self.value]


@dataclass(frozen=True)
class Standing:
    """A model's status, what it rests on, and what is stopping the next step."""

    status: ModelStatus
    #: 7.1.c: the last source date, the valuation date, the owner.
    source_date: str
    valuation_date: str
    owner: str
    #: 7.1.c: unresolved errors, counted and named.
    unresolved: tuple[str, ...]
    #: What the next status needs, in a sentence a reader can act on.
    blocked_by: str
    #: How each gate answered, for the drill-down.
    gates: tuple[tuple[str, bool, str], ...]

    @property
    def unresolved_count(self) -> int:
        return len(self.unresolved)
