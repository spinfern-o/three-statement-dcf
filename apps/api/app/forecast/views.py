"""The 7.8 Forecast Statements screen, as rows a template can iterate.

7.8 asks for five things:

  a-c. the three forecast statements
  d.   actual versus estimate labels
  e.   scenario comparison

**(d) is not decoration.** Rule 1.19 -- "never describe a scenario forecast as
a fact or guarantee" -- is a rule about presentation, and a table where 2025
and 2026E sit side by side in the same typeface is the fastest way to break it.
Every column here carries its A/E label and every projected cell carries the
driver that produced it, so a reader cannot mistake one for the other by
glancing.

**(e) is what makes 15.20 legible.** A single-scenario screen hides the case
15.20 exists for: a Base that balances and a Downside that does not. The
comparison puts one line across every scenario, and names the driver
differences that produce the gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.accounts import Statement
from model.numeric import ZERO, quantize_for_display

from ..mapping.chart import CHART
from .build import ScenarioForecast, forecast_ledger

#: Growth is shown to one decimal, as on the historical statements screen.
PERCENT_PLACES = 1


@dataclass(frozen=True)
class Column:
    """One period, and whether it is an actual or an estimate (7.8.d, 15.2)."""

    year: str

    @property
    def is_estimate(self) -> bool:
        return self.year.endswith("E")

    @property
    def label(self) -> str:
        return self.year

    @property
    def kind(self) -> str:
        return "Estimate" if self.is_estimate else "Actual"


@dataclass(frozen=True)
class Cell:
    value: Decimal | None
    origin: str
    #: The driver that produced it, or the citation it was transcribed from.
    basis: str

    @property
    def is_present(self) -> bool:
        return self.value is not None

    @property
    def is_projected(self) -> bool:
        return self.origin in ("forecast", "derived")


@dataclass(frozen=True)
class Row:
    code: str
    label: str
    definition: str
    is_subtotal: bool
    cells: "tuple[Cell, ...]"
    #: Year-on-year growth per column, and why it is undefined where it is.
    growth: "tuple[tuple[Decimal | None, str], ...]"

    @property
    def any_present(self) -> bool:
        return any(cell.is_present for cell in self.cells)


#: Which canonical lines each statement shows, in the chart's order.
_ORDER = {item.canonical_code: index for index, item in enumerate(CHART)}
_ACCOUNTS = {
    Statement.INCOME: accounts.INCOME_ACCOUNTS,
    Statement.BALANCE: accounts.BALANCE_ACCOUNTS,
    Statement.CASHFLOW: accounts.CASHFLOW_ACCOUNTS,
}
_SUBTOTALS = frozenset(accounts.DERIVED)


def _growth(values: "tuple[Cell, ...]") -> "tuple[tuple[Decimal | None, str], ...]":
    out = [(None, "no prior period in this model")]
    for index in range(1, len(values)):
        prior, current = values[index - 1].value, values[index].value
        if prior is None or current is None:
            out.append((None, "one of the two periods has no figure"))
        elif prior == ZERO:
            # 4.12: a relative measure against zero is undefined, not infinite.
            out.append((None, "the prior period is zero, so growth is undefined (4.12)"))
        else:
            out.append(
                (
                    quantize_for_display(
                        (current - prior) / abs(prior) * Decimal(100), PERCENT_PLACES
                    ),
                    "",
                )
            )
    return tuple(out)


def statement_rows(
    forecast: ScenarioForecast, statement: Statement
) -> "tuple[Row, ...]":
    """7.8.a-c for one statement, across every period actual and estimate."""
    ledger = forecast_ledger(forecast, statement)
    years = forecast.periods.all_years
    chart = {item.canonical_code: item for item in CHART}

    rows = []
    for code in _ACCOUNTS[statement]:
        cells = []
        for year in years:
            cell = ledger.cell(code, year)
            cells.append(
                Cell(None, "", "")
                if cell is None
                else Cell(cell.value, cell.origin, cell.cite())
            )
        item = chart.get(code)
        row = Row(
            code=code,
            label=item.display_name if item else code,
            definition=item.definition if item else "",
            is_subtotal=code in _SUBTOTALS,
            cells=tuple(cells),
            growth=_growth(tuple(cells)),
        )
        if row.any_present:
            rows.append(row)
    rows.sort(key=lambda row: _ORDER.get(row.code, len(_ORDER)))
    return tuple(rows)


def columns(forecast: ScenarioForecast) -> "tuple[Column, ...]":
    """7.8.d: every period labelled actual or estimate, never by inference."""
    return tuple(Column(year) for year in forecast.periods.all_years)


@dataclass(frozen=True)
class ComparisonRow:
    """One line across every scenario, for 7.8.e."""

    scenario_id: str
    #: The driver values that differ from the base scenario's.
    differences: "tuple[tuple[str, Decimal | None, Decimal], ...]"
    values: "tuple[Decimal | None, ...]"
    forecast_ready: bool


def comparison(
    forecasts: "tuple[ScenarioForecast, ...]",
    statement: Statement,
    code: str,
    readiness=None,
    scenarios=None,
) -> "tuple[ComparisonRow, ...]":
    """7.8.e: one line, every scenario, with the driver differences beside it.

    The differences are the point. Two revenue lines that diverge tell a reader
    that something changed; the driver that changed tells them what, and 14.5
    is the requirement that it be visible rather than inferable.
    """
    out = []
    for forecast in forecasts:
        ledger = forecast_ledger(forecast, statement)
        checks = readiness.for_scenario(forecast.scenario_id) if readiness else None
        out.append(
            ComparisonRow(
                scenario_id=forecast.scenario_id,
                differences=(
                    scenarios.differences(forecast.scenario_id) if scenarios else ()
                ),
                values=tuple(
                    ledger.get(code, year) for year in forecast.periods.all_years
                ),
                forecast_ready=bool(checks and checks.is_forecast_ready),
            )
        )
    return tuple(out)


@dataclass(frozen=True)
class DriverRow:
    """15.4: each driver and its formula, by period."""

    code: str
    scope: str
    value: Decimal
    status: str
    step: str


def driver_rows(forecast: ScenarioForecast) -> "tuple[DriverRow, ...]":
    """15.4 -- "show each revenue driver and formula by period"."""
    from ..assumptions.drivers import BY_CODE

    return tuple(
        DriverRow(
            code=code,
            scope=scope,
            value=value,
            status=status,
            step=BY_CODE[code.split(".")[0]].step if code.split(".")[0] in BY_CODE else "",
        )
        for code, scope, value, status in forecast.drivers
    )
