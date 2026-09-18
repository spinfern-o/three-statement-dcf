"""The shape every export renders, and the two things a cell has to carry.

A `Table` is deliberately dull: a name, a title, an optional note, typed
columns, and rows of `Cell`. Four formats render it; none of them decides
anything.

**A cell carries its exact value and its displayed string, separately.** 4.18
keeps stored precision and display precision apart, and 21.8 requires the
export to equal the website "at the same model version and display precision" --
which is a requirement about *both*. A CSV that rounded would lose the first; a
CSV that printed fifty digits where the screen shows one would break the
second. So `Cell.value` is the Decimal the model holds and `Cell.display` is
the string the screen shows, and a format picks the one its reader needs: XLSX
writes the exact value into the cell and the display string into the number
format, CSV writes the exact value with the display beside it.

**A cell says whether it was calculated.** 21.2 asks that XLSX hardcodes and
formulas be visually distinguishable, and a renderer cannot tell them apart
after the fact -- by the time a number reaches a spreadsheet, a figure a human
typed and a figure the engine derived look identical. `Cell.origin` is set at
gather time, from the ledger's own `origin`, so the distinction survives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

#: 21.2's three origins, from `model/statements.py:Cell.origin` plus the case
#: the ledger has no opinion about (a label, a note, a status word).
REPORTED = "reported"
DERIVED = "derived"
FORECAST = "forecast"
TEXT = "text"

#: Which origins are "formula" for 21.2's purposes. A derived subtotal and a
#: forecast cell were both computed; a reported figure was transcribed.
CALCULATED = (DERIVED, FORECAST)


@dataclass(frozen=True)
class Column:
    """One column, and what kind of thing is under it."""

    key: str
    title: str
    #: "text", "currency", "percent", "ratio", "days", "integer", "date".
    kind: str = "text"

    @property
    def is_numeric(self) -> bool:
        return self.kind in ("currency", "percent", "ratio", "days", "integer")


@dataclass(frozen=True)
class Cell:
    """One value, twice: exactly, and as the screen shows it."""

    display: str
    value: Decimal | None = None
    origin: str = TEXT
    #: Set when the model has no value here. Absent is not zero (rule 1.3).
    absent: bool = False
    #: Why it is absent, when it is. An empty cell with no reason is a gap
    #: nobody can act on.
    note: str = ""

    @property
    def is_calculated(self) -> bool:
        return self.origin in CALCULATED

    @classmethod
    def text(cls, value: object, *, note: str = "") -> Cell:
        return cls(display="" if value is None else str(value), note=note)

    @classmethod
    def missing(cls, note: str) -> Cell:
        """Rule 1.3: an absent figure is shown as absent, with its reason."""
        return cls(display="", absent=True, note=note)

    @classmethod
    def number(
        cls, value: Decimal | None, *, origin: str = REPORTED, note: str = "",
        kind: str = "currency",
    ) -> Cell:
        """One figure, displayed the way the website displays it.

        The display string comes from `app/display.py`, which every template
        also calls. 21.8 requires the export to equal the website at the same
        display precision, and the only way to be sure of that is for both to
        ask the same function -- a second formatter that happens to agree today
        is a divergence waiting for the first value that rounds.
        """
        from ..display import display as format_value

        if value is None:
            return cls.missing(note or "not reported")
        return cls(
            display=format_value(value, kind),
            value=value,
            origin=origin,
            note=note,
        )


@dataclass(frozen=True)
class Table:
    """One 21.1 tab, one CSV file, one JSON array, one PDF section."""

    name: str
    title: str
    columns: tuple[Column, ...]
    rows: tuple[tuple[Cell, ...], ...] = ()
    #: Shown above the table. Where an unavailable schedule says why.
    note: str = ""
    #: True when the table could not be built at all, `note` saying why.
    unavailable: bool = False

    def __post_init__(self) -> None:
        width = len(self.columns)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(
                    f"table {self.name!r} row {index} has {len(row)} cells for "
                    f"{width} columns -- a ragged table exports as a shifted one"
                )

    @property
    def is_empty(self) -> bool:
        return not self.rows


@dataclass(frozen=True)
class ExportModel:
    """Everything the four formats render, gathered once."""

    document_id: str
    company: str
    scenario_id: str
    version_id: str
    generated_at: str
    currency: str
    units: str
    valuation_date: str
    tables: tuple[Table, ...] = ()
    #: 21.6's limitations section, and the reason it is not optional.
    limitations: tuple[str, ...] = ()
    version_components: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def table(self, name: str) -> Table:
        for candidate in self.tables:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(table.name for table in self.tables)
