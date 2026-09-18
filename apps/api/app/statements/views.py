"""Items 62, 63 and 64: the ways of looking at a built statement.

63 asks for reported and normalized views. 64 asks for common-size and
growth. 62 asks for an equity statement "when available", and the honest
answer is that it is not -- see `equity_statement_status`.

Two arithmetic rules, both from Section 4 and both easy to get wrong in a
percentage:

**A ratio against zero is undefined, not zero.** 4.12 says so for relative
error and the same reasoning applies here: growth from a zero base is not
infinite and it is not 100%, it is a question the arithmetic cannot answer.
Every function here returns `None` with a reason rather than a number.

**Percentages are Decimal, and rounded only for display.** 4.9 forbids
rounding intermediates. A common-size figure is computed at full precision
and quantized at the boundary, so the same value shown to one decimal place
and exported to four is the same value.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.numeric import D, quantize_for_display
from model.statements import Cell

from ..mapping.chart import CHART, NormalizedLineItem, StatementType, line_item
from .build import BuiltStatements

#: What each statement's lines are shown as a percentage of. 12.x's convention.
COMMON_SIZE_BASE = {
    accounts.Statement.INCOME: accounts.REVENUE,
    accounts.Statement.BALANCE: accounts.TOTAL_ASSETS,
    #: A cash-flow line as a percentage of revenue is the usual reading: it
    #: answers "how much of a year's sales turned into operating cash".
    accounts.Statement.CASHFLOW: accounts.REVENUE,
}

#: Decimal places for a displayed percentage. 4.18 keeps this separate from
#: the calculation precision, which is 50 digits and is not rounded (4.9).
PERCENT_PLACES = 1


@dataclass(frozen=True)
class CellView:
    """One cell, in every view at once. 63, 64."""

    year: str
    value: Decimal | None
    cell: Cell | None
    #: 63: the string the filing printed, before parsing or sign normalization.
    reported: str = ""
    common_size: Decimal | None = None
    common_size_note: str = ""
    growth: Decimal | None = None
    growth_note: str = ""

    @property
    def is_present(self) -> bool:
        return self.value is not None

    def cite(self) -> str:
        return self.cell.cite() if self.cell else "(absent)"


@dataclass(frozen=True)
class StatementRow:
    item: NormalizedLineItem
    cells: tuple[CellView, ...]

    @property
    def any_present(self) -> bool:
        return any(c.is_present for c in self.cells)


def _reported_strings(result, cell: Cell | None) -> str:
    """63's reported view: what was printed, not what was stored."""
    if cell is None or cell.source is None:
        return ""
    return cell.source.line_item


def statement_view(
    built: BuiltStatements,
    statement: accounts.Statement,
    *,
    raw_values: dict[tuple[str, str], str] | None = None,
) -> tuple[StatementRow, ...]:
    """Every canonical line of one statement, in chart order, with all views.

    `raw_values` maps (canonical_code, year) to the string the filing printed,
    which is what makes the reported view *reported* rather than a reformatted
    normalized one. It is optional because the engine's ledger does not carry
    it; `apps/api/app/statements/reported.py` builds it from the facts.
    """
    ledger = built.ledgers[statement]
    base_code = COMMON_SIZE_BASE[statement]
    # The base may live on a different ledger: a cash-flow line is shown as a
    # percentage of revenue, and revenue is on the income statement.
    base_ledger = built.ledgers[
        {
            StatementType.INCOME: accounts.Statement.INCOME,
            StatementType.BALANCE: accounts.Statement.BALANCE,
            StatementType.CASHFLOW: accounts.Statement.CASHFLOW,
        }[line_item(base_code).statement_types[0]]
    ]
    rows: list[StatementRow] = []

    for item in CHART:
        if _chart_statement(statement) not in item.statement_types:
            continue
        cells: list[CellView] = []
        for index, year in enumerate(built.years):
            value = ledger.get(item.canonical_code, year)
            cell = ledger._cells.get((item.canonical_code, year))
            size, size_note = _common_size(value, base_ledger.get(base_code, year), base_code)
            prior = ledger.get(item.canonical_code, built.years[index - 1]) if index else None
            change, change_note = _growth(value, prior, index)
            cells.append(
                CellView(
                    year=year,
                    value=value,
                    cell=cell,
                    reported=(raw_values or {}).get((item.canonical_code, year), ""),
                    common_size=size,
                    common_size_note=size_note,
                    growth=change,
                    growth_note=change_note,
                )
            )
        row = StatementRow(item=item, cells=tuple(cells))
        if row.any_present:
            rows.append(row)
    return tuple(rows)


def _chart_statement(statement: accounts.Statement) -> StatementType:
    return {
        accounts.Statement.INCOME: StatementType.INCOME,
        accounts.Statement.BALANCE: StatementType.BALANCE,
        accounts.Statement.CASHFLOW: StatementType.CASHFLOW,
    }[statement]


def _common_size(
    value: Decimal | None, base: Decimal | None, base_code: str
) -> tuple[Decimal | None, str]:
    """Item 64. `value / base`, as a percentage, or a reason it is undefined."""
    if value is None:
        return None, ""
    if base is None:
        return None, f"{base_code} is not reported for this year"
    if base == 0:
        return None, f"{base_code} is zero, so a percentage of it is undefined (4.12)"
    return quantize_for_display(value / base * D(100), PERCENT_PLACES), ""


def _growth(
    value: Decimal | None, prior: Decimal | None, index: int
) -> tuple[Decimal | None, str]:
    """Item 64. Period-on-period change, or a reason it is undefined."""
    if index == 0:
        return None, "no prior year in this filing"
    if value is None or prior is None:
        return None, "absent in one of the two years"
    if prior == 0:
        return None, "the prior year is zero, so growth from it is undefined (4.12)"
    return quantize_for_display((value - prior) / abs(prior) * D(100), PERCENT_PLACES), ""


# --- item 62 ----------------------------------------------------------------

def equity_statement_status() -> str:
    """12.2.l and 7.5.d ask for a statement of equity "when available".

    It is not available, and this says why rather than rendering an empty
    table. The chart has no `equity` statement type: the engine models
    shareholders' equity as two balance-sheet lines and a retained-earnings
    roll-forward, which is enough for the DCF and is not a statement of
    changes in equity. Adding one means adding the statement type, its lines
    and its checks to `model/accounts.py` -- recorded as finding F-17's
    neighbour rather than faked here.
    """
    return (
        "Not available. This chart has no equity statement type (12.2.l): "
        "shareholders' equity is modelled as two balance-sheet lines "
        "(common_equity, retained_earnings) plus a retained-earnings "
        "roll-forward, which serves the valuation and is not a statement of "
        "changes in equity. Showing an empty table would imply the filing did "
        "not present one."
    )


def summarize_views(rows: tuple[StatementRow, ...]) -> str:
    lines = []
    for row in rows:
        parts = []
        for cell in row.cells:
            shown = "absent" if cell.value is None else f"{cell.value:,}"
            size = f" ({cell.common_size}%)" if cell.common_size is not None else ""
            growth = f" {cell.growth:+}%" if cell.growth is not None else ""
            parts.append(f"{cell.year} {shown}{size}{growth}")
        lines.append(f"  {row.item.canonical_code:30} " + "   ".join(parts))
    return "\n".join(lines)
