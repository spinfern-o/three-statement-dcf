"""STEP 5-7: standardized historical statements.

The central object is a sparse `Ledger`: account x year -> Cell. Sparse is
the point. STEP 5 forbids inventing a line the company does not report, so
an absent account stays absent all the way through to the checks, instead
of being defaulted to zero and quietly changing a subtotal.

Each cell records its `origin`:
  reported -- transcribed from the filing, carries a Source (STEP 4)
  derived  -- arithmetic from other cells (e.g. gross profit = revenue - COGS)
  forecast -- produced by a driver in STEP 13-22

Deriving gross profit from a reported revenue and a reported COGS is
arithmetic, not invention; deriving it when COGS is absent is invention,
and does not happen. The distinction is also what lets STEP 37 detect an
unintended hardcode in a forecast year.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from .accounts import DERIVED, OPTIONAL_IN_DERIVATION, Statement, validate_account
from .numeric import D, ZERO
from .provenance import Figure, ProvenanceError, Source


@dataclass(frozen=True)
class Cell:
    value: Decimal
    origin: str  # "reported" | "derived" | "forecast"
    source: Source | None = None
    basis: str | None = None  # for derived/forecast: how it was produced

    def cite(self) -> str:
        if self.origin == "reported" and self.source is not None:
            return self.source.cite()
        return f"{self.origin}: {self.basis or 'unspecified'}"


@dataclass(frozen=True)
class Discrepancy:
    """A reported subtotal that disagrees with its own components."""

    account: str
    year: str
    reported: Decimal
    derived: Decimal

    @property
    def delta(self) -> Decimal:
        return self.reported - self.derived

    def __str__(self) -> str:
        return (
            f"{self.account} {self.year}: reported {self.reported:,.1f} vs "
            f"derived {self.derived:,.1f} (delta {self.delta:,.1f})"
        )


class Ledger:
    """Sparse account x year store for one statement."""

    def __init__(self, statement: Statement, years: tuple[str, ...]):
        self.statement = statement
        self.years = tuple(years)
        self._cells: dict[tuple[str, str], Cell] = {}

    # -- writing ----------------------------------------------------------
    def _check_year(self, year: str) -> str:
        if year not in self.years:
            raise KeyError(f"{year!r} is not a year in this ledger ({', '.join(self.years)})")
        return year

    def set_reported(self, account: str, year: str, figure: Figure) -> None:
        """STEP 4-7: place a transcribed figure into the standardized model."""
        validate_account(self.statement, account)
        self._check_year(year)
        if figure.year != year:
            raise ProvenanceError(
                f"Figure is tagged year {figure.year!r} but is being written to {year!r}. "
                "Transcription years must match (STEP 4)."
            )
        self._cells[(account, year)] = Cell(figure.value, "reported", figure.source)

    def set_forecast(self, account: str, year: str, value: Decimal, basis: str) -> None:
        """STEP 13-22: a driver-produced value. `basis` names the driver."""
        validate_account(self.statement, account)
        self._check_year(year)
        if not basis or not basis.strip():
            raise ProvenanceError(
                f"Forecast {account} {year} needs a stated basis. "
                "STEP 10: never hide assumptions inside formulas."
            )
        self._cells[(account, year)] = Cell(D(value, what=f"{account} {year}"), "forecast", None, basis)

    def set_derived(self, account: str, year: str, value: Decimal, basis: str) -> None:
        validate_account(self.statement, account)
        self._check_year(year)
        self._cells[(account, year)] = Cell(D(value, what=f"{account} {year}"), "derived", None, basis)

    # -- reading ----------------------------------------------------------
    def cell(self, account: str, year: str) -> Cell | None:
        return self._cells.get((account, year))

    def get(self, account: str, year: str) -> Decimal | None:
        """Value, or None if the company does not report it. Never zero."""
        cell = self._cells.get((account, year))
        return None if cell is None else cell.value

    def require(self, account: str, year: str, step: str) -> Decimal:
        value = self.get(account, year)
        if value is None:
            raise ProvenanceError(
                f"{self.statement.value}.{account} is missing for {year}, and {step} needs it. "
                "Supply it from the filing or change the approach -- do not substitute zero."
            )
        return value

    def has(self, account: str, year: str) -> bool:
        return (account, year) in self._cells

    def accounts_present(self, year: str) -> list[str]:
        return sorted(a for (a, y) in self._cells if y == year)

    def origin_of(self, account: str, year: str) -> str | None:
        cell = self._cells.get((account, year))
        return None if cell is None else cell.origin

    # -- derivation and cross-checking (STEP 9) ---------------------------
    def _try_derive(self, account: str, year: str) -> Decimal | None:
        rule = DERIVED.get(account)
        if rule is None:
            return None
        plus, minus = rule
        total = ZERO
        contributed = False
        for term in plus:
            v = self.get(term, year)
            if v is None:
                if term in OPTIONAL_IN_DERIVATION:
                    continue  # residual line; its absence means zero, not unknown
                return None
            total += v
            contributed = True
        for term in minus:
            v = self.get(term, year)
            if v is None:
                if term in OPTIONAL_IN_DERIVATION:
                    continue
                return None
            total -= v
            contributed = True
        return total if contributed else None

    def fill_derivable(self) -> list[str]:
        """Compute absent subtotals whose components are all present.

        Iterates to a fixed point because subtotals feed each other
        (gross profit -> EBIT -> pretax -> net income). Returns the list of
        accounts it filled, so the caller can report exactly what was
        computed rather than transcribed.
        """
        filled: list[str] = []
        changed = True
        while changed:
            changed = False
            for year in self.years:
                for account in DERIVED:
                    if self.has(account, year):
                        continue
                    value = self._try_derive(account, year)
                    if value is not None:
                        plus, minus = DERIVED[account]
                        terms = " + ".join(plus) + ("" if not minus else " - " + " - ".join(minus))
                        self.set_derived(account, year, value, f"{account} = {terms}")
                        filled.append(f"{account} {year}")
                        changed = True
        return filled

    def cross_check(self, rel_tol: Decimal | str = "1e-6", abs_tol: Decimal | str = "0") -> list[Discrepancy]:
        """STEP 9: where a subtotal is BOTH reported and derivable, compare.

        A mismatch means an extraction or mapping error. It is surfaced, not
        corrected -- STEP 6 forbids plugging a difference away.

        The default here is looser than the forecast checks (1e-6 rather than
        1e-9) because both sides are transcribed from a filing that rounds its
        own figures, so a disagreement in the last printed digit is the
        company's rounding rather than a mapping error. Tighten it with
        `rel_tol` if the filing reports to full precision.
        """
        rel = D(rel_tol, what="cross_check rel_tol")
        absolute = D(abs_tol, what="cross_check abs_tol")
        out: list[Discrepancy] = []
        for year in self.years:
            for account in DERIVED:
                cell = self._cells.get((account, year))
                if cell is None or cell.origin != "reported":
                    continue
                derived = self._try_derive(account, year)
                if derived is None:
                    continue
                if abs(cell.value - derived) > max(rel * max(abs(cell.value), abs(derived)), absolute):
                    out.append(Discrepancy(account, year, cell.value, derived))
        return out

    def hardcodes_in(self, years: tuple[str, ...]) -> list[str]:
        """STEP 37: forecast cells that were pasted in rather than driven."""
        return sorted(
            f"{a} {y}"
            for (a, y), c in self._cells.items()
            if y in years and c.origin == "reported"
        )

    def extended_to(self, years: tuple[str, ...]) -> "Ledger":
        """Copy this ledger onto a wider year axis (historical -> full model)."""
        out = Ledger(self.statement, years)
        for (account, year), cell in self._cells.items():
            if year in years:
                out._cells[(account, year)] = replace(cell)
        return out
