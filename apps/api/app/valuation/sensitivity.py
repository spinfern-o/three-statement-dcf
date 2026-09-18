"""Item 119 / 16.23: the WACC-and-growth grid, with its steps stated.

16.23 asks for "explicit step sizes and displayed assumptions". Both halves
matter and the second is the one usually skipped: a grid whose rows read 7%,
8%, 9% tells a reader nothing about whether 8% is the model's WACC or a
midpoint somebody picked, and a sensitivity centred somewhere other than the
base case is a different claim entirely.

So the axes are generated from the valuation's own WACC and growth rate, by a
stated step, and the centre cell is asserted to be the base valuation. If it
were not, the grid would be showing the sensitivity of a model nobody built.

The grid runs through `model/sensitivity.py`, which runs the full `run_dcf` per
cell rather than scaling the base answer -- because the terminal value is not
linear in either axis, and a scaled approximation would be wrong in exactly the
corner a reader looks at.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model.numeric import D
from model.sensitivity import SensitivityCell, sensitivity_grid

from .build import ScenarioValuation

#: 16.23's "explicit step sizes". A quarter of a point on WACC and a quarter on
#: growth: small enough that the neighbouring cells are plausible alternatives
#: rather than different companies.
DEFAULT_WACC_STEP = D("0.0025")
DEFAULT_GROWTH_STEP = D("0.0025")
DEFAULT_STEPS_EACH_WAY = 2


@dataclass(frozen=True)
class Grid:
    """The grid, its axes, and the assumptions 16.23 requires be displayed."""

    wacc_values: tuple[Decimal, ...]
    growth_values: tuple[Decimal, ...]
    rows: tuple[tuple[SensitivityCell, ...], ...]
    base_wacc: Decimal
    base_growth: Decimal
    wacc_step: Decimal
    growth_step: Decimal
    #: The timing convention every cell was discounted on (16.11).
    timing_basis: str

    @property
    def centre(self) -> SensitivityCell:
        return self.rows[len(self.rows) // 2][len(self.growth_values) // 2]

    @property
    def blocked(self) -> tuple[SensitivityCell, ...]:
        """16.16's corners, shown with their reason rather than left blank."""
        return tuple(cell for row in self.rows for cell in row if cell.note)

    def describe(self) -> str:
        return (
            f"WACC {self.base_wacc} +/- {self.wacc_step} per step, terminal "
            f"growth {self.base_growth} +/- {self.growth_step} per step. "
            f"Discounting: {self.timing_basis}"
        )


def _axis(centre: Decimal, step: Decimal, each_way: int) -> tuple[Decimal, ...]:
    return tuple(centre + step * D(offset) for offset in range(-each_way, each_way + 1))


def build_grid(
    valuation: ScenarioValuation,
    *,
    wacc_step: Decimal = DEFAULT_WACC_STEP,
    growth_step: Decimal = DEFAULT_GROWTH_STEP,
    each_way: int = DEFAULT_STEPS_EACH_WAY,
) -> Grid:
    """16.23, centred on the valuation it is a sensitivity of."""
    base_wacc = valuation.valuation.wacc
    base_growth = valuation.valuation.terminal_growth
    wacc_values = _axis(base_wacc, D(wacc_step), each_way)
    growth_values = _axis(base_growth, D(growth_step), each_way)

    rows = sensitivity_grid(
        fcff_years=list(valuation.fcff_years),
        base_cost_of_capital=valuation.cost_of_capital,
        bridge=valuation.bridge,
        periods=valuation.valuation.periods,
        wacc_values=list(wacc_values),
        growth_values=list(growth_values),
        diluted_shares=valuation.valuation.diluted_shares,
        shares_source=valuation.valuation.shares_source,
        schedule=valuation.schedule,
    )
    return Grid(
        wacc_values=wacc_values,
        growth_values=growth_values,
        rows=tuple(tuple(row) for row in rows),
        base_wacc=base_wacc,
        base_growth=base_growth,
        wacc_step=D(wacc_step),
        growth_step=D(growth_step),
        timing_basis=valuation.schedule.basis,
    )
