"""STEP 1-3 and STEP 12: identification, source map, and periods.

STEP 1 ends with "Do not begin modeling until each item is identified."
`CompanyProfile` therefore has no defaults at all -- every field must be
supplied, including the units, because a model that silently assumes
thousands when the filing reports millions is wrong by 1000x and looks
entirely plausible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .provenance import ProvenanceError

YEAR_RE = re.compile(r"^(\d{4})(A|E)$")


class Units(str, Enum):
    """STEP 1: whether figures are shown in dollars, thousands, or millions."""

    DOLLARS = "dollars"
    THOUSANDS = "thousands"
    MILLIONS = "millions"

    @property
    def multiplier(self) -> int:
        """Scale factor to the base currency unit.

        Specification 4.6 requires normalizing every value to one base unit
        while retaining the source unit for exact reconstruction. That is NOT
        implemented: the engine holds a single document whose figures share
        one scale (STEP 1), so it calculates in the reporting units as filed
        and never converts.

        This multiplier is therefore correct and unused. It exists because
        normalization becomes necessary the moment decision 2.3.a permits
        more than one source document, or 2.4.a a second currency, and a
        wrong multiplier discovered at that point would be a 1000x error.
        `tests/test_model.py` pins the values.
        """
        return {"dollars": 1, "thousands": 1_000, "millions": 1_000_000}[self.value]


@dataclass(frozen=True)
class CompanyProfile:
    """STEP 1 -- receive and identify the PDF."""

    company_name: str
    reporting_period: str
    fiscal_year_end: str
    reporting_currency: str
    units: Units
    audited: bool

    def __post_init__(self) -> None:
        for name in ("company_name", "reporting_period", "fiscal_year_end", "reporting_currency"):
            value = getattr(self, name)
            if not value or not str(value).strip():
                raise ProvenanceError(
                    f"CompanyProfile.{name} is required by STEP 1. "
                    "Do not begin modeling until each item is identified."
                )
        if not isinstance(self.units, Units):
            raise ProvenanceError(
                f"CompanyProfile.units must be one of "
                f"{[u.value for u in Units]} (STEP 1), got {self.units!r}"
            )
        if not isinstance(self.audited, bool):
            raise ProvenanceError("CompanyProfile.audited must be true or false (STEP 1)")

    def describe(self) -> str:
        audit = "audited" if self.audited else "UNAUDITED"
        return (
            f"{self.company_name} | {self.reporting_period} | FYE {self.fiscal_year_end} | "
            f"{self.reporting_currency} in {self.units.value} | {audit}"
        )


# STEP 2 requires an exact PDF page for each of these.
REQUIRED_SOURCE_MAP_KEYS = (
    "income_statement",
    "balance_sheet",
    "cash_flow_statement",
    "statement_of_shareholders_equity",
    "revenue_notes",
    "ppe_depreciation_notes",
    "debt_notes",
    "tax_notes",
    "lease_notes",
    "stock_compensation_notes",
    "share_count_eps_notes",
    "mdna",
)


@dataclass
class SourceMap:
    """STEP 2 -- record the exact PDF page for each required section."""

    document: str
    pages: dict[str, int | None] = field(default_factory=dict)

    def missing(self) -> list[str]:
        """Keys with no recorded page. Reported, never silently tolerated."""
        return [k for k in REQUIRED_SOURCE_MAP_KEYS if self.pages.get(k) is None]

    def page_for(self, key: str) -> int:
        if key not in REQUIRED_SOURCE_MAP_KEYS:
            raise KeyError(f"{key!r} is not a STEP 2 source-map key. Expected one of {REQUIRED_SOURCE_MAP_KEYS}")
        page = self.pages.get(key)
        if page is None:
            raise ProvenanceError(f"STEP 2: no PDF page recorded for {key!r}. Record it before modeling.")
        return page


@dataclass(frozen=True)
class Periods:
    """STEP 3 (historical) and STEP 12 (forecast).

    STEP 3: "Use only the historical years actually provided by the company.
    Do not invent missing historical years." Nothing here generates a year;
    both lists are supplied and validated for the A/E suffix convention.
    """

    historical: tuple[str, ...]
    forecast: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.historical:
            raise ProvenanceError("STEP 3: at least one historical year is required.")
        if not self.forecast:
            raise ProvenanceError("STEP 12: at least one forecast year is required.")
        for year in self.historical:
            m = YEAR_RE.match(year)
            if not m or m.group(2) != "A":
                raise ProvenanceError(f"Historical year {year!r} must be formatted like '2025A' (A = Actual, STEP 12)")
        for year in self.forecast:
            m = YEAR_RE.match(year)
            if not m or m.group(2) != "E":
                raise ProvenanceError(f"Forecast year {year!r} must be formatted like '2026E' (E = Estimate, STEP 12)")
        # Every label was validated against YEAR_RE above, so `match` cannot
        # be None here -- but `_year_of` says that in code rather than leaving
        # it as something a reader has to verify by scrolling up.
        hist = [_year_of(y) for y in self.historical]
        fore = [_year_of(y) for y in self.forecast]
        if hist != sorted(hist) or fore != sorted(fore):
            raise ProvenanceError("Historical and forecast years must each be in ascending order.")
        if len(set(hist)) != len(hist) or len(set(fore)) != len(fore):
            raise ProvenanceError("Duplicate years supplied.")
        # Each list must be consecutive. A hole would make every
        # period-over-period change (change in NWC, every roll-forward)
        # silently span two years while being labeled as one.
        for label, seq, raw in (("historical", hist, self.historical), ("forecast", fore, self.forecast)):
            gaps = [
                f"{raw[i]} -> {raw[i + 1]}"
                for i in range(len(seq) - 1)
                if seq[i + 1] != seq[i] + 1
            ]
            if gaps:
                raise ProvenanceError(
                    f"{label.capitalize()} years are not consecutive: {', '.join(gaps)}. "
                    "STEP 3: use the years the company actually provides, and do not "
                    "invent missing ones -- but a gap silently misstates every "
                    "year-over-year change built on top of it."
                )
        if fore[0] != hist[-1] + 1:
            raise ProvenanceError(
                f"Forecast must begin the year after the last actual: last actual is "
                f"{self.historical[-1]}, first forecast is {self.forecast[0]}. "
                "A gap would silently skip a year of compounding."
            )

    @property
    def all_years(self) -> tuple[str, ...]:
        return self.historical + self.forecast

    @property
    def last_actual(self) -> str:
        return self.historical[-1]

    @property
    def terminal_year(self) -> str:
        """The last explicit forecast year -- the TV anchor in STEP 30-32."""
        return self.forecast[-1]

    def prior(self, year: str) -> str | None:
        seq = self.all_years
        i = seq.index(year)
        return seq[i - 1] if i > 0 else None

    def discount_period(self, year: str) -> int:
        """STEP 29: t in 1/(1+WACC)^t, counting from the last actual year."""
        if year not in self.forecast:
            raise KeyError(f"{year!r} is not a forecast year")
        return self.forecast.index(year) + 1


def _year_of(label: str) -> int:
    """The four-digit year out of a validated period label."""
    match = YEAR_RE.match(label)
    if match is None:
        raise ProvenanceError(
            f"{label!r} is not a period label; it should have been refused "
            "before reaching here"
        )
    return int(match.group(1))
