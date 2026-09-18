"""STEP 10-11: the assumptions register.

"Every forecast assumption must have a visible source or explanation" and
"Never hide assumptions inside formulas." Both are enforced rather than
recommended: an Assumption cannot be constructed without a Basis and a
non-empty source string, and the forecast engine reads every driver
through this register, so there is nowhere else for a number to enter.

STEP 11 adds conflict handling: when two sources disagree, record both
with their dates and state which one the model uses. `Conflict` does that,
and an unresolved conflict is a hard error, not a warning.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .numeric import D, PrecisionError
from .provenance import ProvenanceError


class Basis(str, Enum):
    """STEP 10's three categories, kept distinct in every report."""

    COMPANY_GUIDANCE = "company_guidance"
    EXTERNAL_RESEARCH = "external_research"
    MODEL_ASSUMPTION = "model_assumption"

    @property
    def label(self) -> str:
        return {
            "company_guidance": "Company guidance",
            "external_research": "External research",
            "model_assumption": "Model assumption",
        }[self.value]


@dataclass(frozen=True)
class Assumption:
    name: str
    value: Decimal
    basis: Basis
    source: str
    year: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ProvenanceError("Assumption.name is required")
        if not isinstance(self.basis, Basis):
            raise ProvenanceError(
                f"Assumption {self.name!r}: basis must be one of "
                f"{[b.value for b in Basis]} (STEP 10), got {self.basis!r}"
            )
        if not self.source or not self.source.strip():
            raise ProvenanceError(
                f"Assumption {self.name!r} has no source. STEP 10: every forecast "
                "assumption must have a visible source or explanation."
            )
        try:
            object.__setattr__(self, "value", D(self.value, what=f"Assumption {self.name!r} value"))
        except PrecisionError as exc:
            raise ProvenanceError(str(exc)) from None

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.name, self.year)

    def describe(self) -> str:
        scope = self.year or "all years"
        note = f" -- {self.note}" if self.note else ""
        return f"{self.name} [{scope}]: {self.value} -- {self.basis.label}: {self.source}{note}"


@dataclass(frozen=True)
class Conflict:
    """STEP 11: two sources disagree. Record both, date both, choose one."""

    topic: str
    source_a: str
    date_a: str
    value_a: str
    source_b: str
    date_b: str
    value_b: str
    chosen: str  # must equal source_a or source_b
    rationale: str

    def __post_init__(self) -> None:
        if self.chosen not in (self.source_a, self.source_b):
            raise ProvenanceError(
                f"Conflict {self.topic!r}: 'chosen' must be exactly one of the two recorded "
                f"sources ({self.source_a!r} or {self.source_b!r}), got {self.chosen!r}. "
                "STEP 11 requires explicitly choosing which one the model uses."
            )
        if not self.rationale.strip():
            raise ProvenanceError(f"Conflict {self.topic!r}: a rationale for the choice is required (STEP 11)")

    def describe(self) -> str:
        return (
            f"{self.topic}: {self.source_a} ({self.date_a}) says {self.value_a}; "
            f"{self.source_b} ({self.date_b}) says {self.value_b}. "
            f"Model uses {self.chosen} -- {self.rationale}"
        )


class Assumptions:
    """The single gate every forecast driver passes through."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str | None], Assumption] = {}
        self.conflicts: list[Conflict] = []
        self._used: set[tuple[str, str | None]] = set()

    def add(self, assumption: Assumption) -> None:
        if assumption.key in self._items:
            raise ProvenanceError(
                f"Duplicate assumption {assumption.name!r} for {assumption.year or 'all years'}. "
                "Two values for the same driver means one is silently losing."
            )
        self._items[assumption.key] = assumption

    def add_conflict(self, conflict: Conflict) -> None:
        self.conflicts.append(conflict)

    def get(self, name: str, year: str | None = None) -> Decimal:
        """Year-specific value if present, else the all-years value.

        Raises when neither exists. There is no fallback default -- a driver
        the modeller never set is a question to answer, not a zero.
        """
        for key in ((name, year), (name, None)):
            if key in self._items:
                self._used.add(key)
                return self._items[key].value
        scope = f" for {year}" if year else ""
        raise ProvenanceError(
            f"No assumption named {name!r}{scope}. STEP 10 requires it to be declared "
            "explicitly in the assumptions section before it can be used."
        )

    def has(self, name: str, year: str | None = None) -> bool:
        return (name, year) in self._items or (name, None) in self._items

    def explain(self, name: str, year: str | None = None) -> str:
        for key in ((name, year), (name, None)):
            if key in self._items:
                return self._items[key].describe()
        raise ProvenanceError(f"No assumption named {name!r}")

    def unused(self) -> list[str]:
        """Declared but never read -- usually a typo or a stale driver."""
        return sorted(f"{n} [{y or 'all years'}]" for (n, y) in self._items if (n, y) not in self._used)

    def by_basis(self) -> dict[Basis, list[Assumption]]:
        """STEP 10: report the three categories separately."""
        out: dict[Basis, list[Assumption]] = {b: [] for b in Basis}
        for item in self._items.values():
            out[item.basis].append(item)
        for items in out.values():
            items.sort(key=lambda a: (a.name, a.year or ""))
        return out

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Assumption]:
        return iter(sorted(self._items.values(), key=lambda a: (a.name, a.year or "")))
