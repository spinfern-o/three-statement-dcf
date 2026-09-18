"""The 7.9 DCF Valuation screen, as rows a template can iterate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .build import ScenarioValuation


@dataclass(frozen=True)
class FlowRow:
    """7.9.a and 7.9.c on one line: EBIT through to present value.

    Shown as one row rather than two tables because the bridge and the
    discounting are the same story, and splitting them is how a reader loses
    track of which year's FCFF became which present value.
    """

    year: str
    ebit: Decimal
    nopat: Decimal
    d_and_a: Decimal
    capex: Decimal
    change_in_nwc: Decimal
    fcff: Decimal
    period: Decimal
    discount_factor: Decimal
    present_value: Decimal


def flow_rows(valuation: ScenarioValuation) -> tuple[FlowRow, ...]:
    """16.5's bridge beside 16.14's discounting, year by year."""
    discounted = {item.year: item for item in valuation.valuation.discounted}
    rows = []
    for item in valuation.fcff_years:
        year = discounted[item.year]
        rows.append(
            FlowRow(
                year=item.year,
                ebit=item.ebit,
                nopat=item.nopat,
                d_and_a=item.d_and_a,
                capex=item.capex,
                change_in_nwc=item.change_in_nwc,
                fcff=item.fcff,
                period=year.period,
                discount_factor=year.discount_factor,
                present_value=year.present_value,
            )
        )
    return tuple(rows)
