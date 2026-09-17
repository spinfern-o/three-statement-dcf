"""7.7.a: historical driver analysis, as proposed assumptions.

The assumptions screen asks for "historical driver analysis" beside the
forecast assumptions, and Phase 7 already computed every historical driver
this model can support: DSO, inventory days and DPO from the working-capital
schedule, the implied interest rate from the debt schedule on the basis the
forecast charges interest on, the effective tax rate from the tax schedule,
and depreciation as a share of opening PP&E from the PP&E roll-forward.

So this does not recompute them. It turns them into `Assumption` objects in
the `Draft` status, with `SourceType.HISTORICAL_DRIVER` and
`evidence.measured_over` filled in with the periods they were measured over --
which is precisely what the schema demands of a historical driver, and
precisely what a hand-entered one usually omits.

**They are proposals, not answers.** Every one arrives as `Draft`, which
`Status.blocks_calculation` refuses to forecast on, and every rationale says
that last year's driver is a measurement rather than a forecast. STEP 14 is
blunt about this: "Do not assume every expense should remain a constant
percentage of revenue." A proposal that arrived Approved would be that
assumption, made silently, for every driver at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model.numeric import ZERO

from ..schedules.build import ScheduleSet
from ..schedules.interest import ENGINE_BASIS
from .schema import Assumption, Evidence, SourceType, Status


@dataclass(frozen=True)
class Proposal:
    """A historical driver, and what it would mean to forecast with it."""

    assumption: Assumption
    #: The schedule it came out of, by its specification clause.
    schedule: str
    #: What the reviewer has to decide, in a sentence.
    caution: str


def _driver(
    code: str, name: str, value: Decimal, unit: str, periods: "tuple[str, ...]",
    rationale: str, owner: str,
) -> Assumption:
    return Assumption(
        code=code,
        name=name,
        value=value,
        unit=unit,
        source_type=SourceType.HISTORICAL_DRIVER,
        evidence=Evidence(measured_over=periods),
        rationale=rationale,
        owner=owner,
        status=Status.DRAFT,
    )


HOLDING_CONSTANT = (
    "This is what the filing did, not what the company will do. STEP 14: do "
    "not assume every expense stays a constant share of revenue."
)


def propose_from_schedules(schedules: ScheduleSet, owner: str) -> "tuple[Proposal, ...]":
    """Every forecast driver the historical schedules can measure.

    Only the periods that actually produced a figure are cited; a driver the
    filing does not support is not proposed at all, rather than proposed at
    zero.
    """
    out: "list[Proposal]" = []

    # --- 13.1: the working-capital days drivers -----------------------------
    for name, code in (("DSO", "dso"), ("Inventory days", "inventory_days"), ("DPO", "dpo")):
        measured = tuple(
            row.year
            for row in schedules.working_capital.years
            for item in row.drivers
            if item.name == name and item.days is not None
        )
        if not measured:
            continue
        latest = schedules.working_capital.years[-1]
        driver = next(item for item in latest.drivers if item.name == name)
        if driver.days is None:
            continue
        out.append(
            Proposal(
                assumption=_driver(
                    code, name, driver.days, "days", measured,
                    f"{name} was {driver.days} days at {latest.year} year end, on a "
                    f"365-day convention over the full-year flow (13.1.e). "
                    + HOLDING_CONSTANT,
                    owner,
                ),
                schedule="13.1",
                caution=(
                    "A year-end balance over a full-year flow. In a year with an "
                    "acquisition or a sharp change in trading late in the period "
                    "this describes neither the year nor the year end well."
                ),
            )
        )

    # --- 13.4: the interest rate, on the basis the forecast charges it ------
    for row in schedules.interest:
        rate = row.on(ENGINE_BASIS)
        if rate is None or rate.rate is None:
            continue
        out.append(
            Proposal(
                assumption=_driver(
                    "interest_rate_on_debt", "Interest rate on beginning debt",
                    rate.rate, "ratio", (row.year,),
                    f"Interest expense for {row.year} over BEGINNING debt -- the "
                    f"balance at {row.prior_year} year end -- giving {rate.rate}. "
                    "Beginning debt is the basis model/forecast.py charges "
                    "interest on (STEP 19), so this rate carries forward without "
                    "changing convention mid-model. " + HOLDING_CONSTANT,
                    owner,
                ),
                schedule="13.4",
                caution=(
                    "One blended rate over all borrowings. A refinancing, a "
                    "floating-rate tranche or a maturity inside the forecast "
                    "makes the historical rate the wrong forward rate."
                ),
            )
        )
        break  # the most recent period with a rate

    # --- 13.6: the effective tax rate ---------------------------------------
    usable = schedules.tax.usable_rates()
    if usable:
        latest_year = sorted(usable)[-1]
        out.append(
            Proposal(
                assumption=_driver(
                    "tax_rate", "Effective tax rate", usable[latest_year], "ratio",
                    tuple(sorted(usable)),
                    f"The effective rate for {latest_year} was {usable[latest_year]}, "
                    "measured as tax expense over pretax income. STEP 16 requires "
                    "the basis be stated: this is `historical_effective`, and the "
                    "statutory and normalized bases exist for the years it "
                    "misreads. " + HOLDING_CONSTANT,
                    owner,
                ),
                schedule="13.6",
                caution=(
                    "An effective rate over one or two periods carries whatever "
                    "was unusual in them -- a settlement, a rate change, a one-off "
                    "benefit. STEP 16 offers two other bases for exactly that."
                ),
            )
        )

    # --- 13.2: depreciation as a share of opening PP&E ----------------------
    for row in schedules.ppe.years:
        opening = row.beginning.value
        depreciation = next(
            (
                -line.value
                for line in row.movements
                if line.label.startswith("Depreciation") and line.value is not None
            ),
            None,
        )
        if opening is None or depreciation is None or opening == ZERO:
            continue
        out.append(
            Proposal(
                assumption=_driver(
                    "depreciation_pct_beginning_ppe", "Depreciation on opening PP&E",
                    depreciation / opening, "ratio", (row.year,),
                    f"Depreciation of {depreciation:,} in {row.year} against "
                    f"opening PP&E of {opening:,}. STEP 18 forecasts depreciation "
                    "and CapEx separately, and neither may default to the other. "
                    + HOLDING_CONSTANT,
                    owner,
                ),
                schedule="13.2",
                caution=(
                    "The chart carries one combined depreciation and amortization "
                    "line, so this rate includes any amortization the company "
                    "charged. It is a rate on PP&E only if the company amortizes "
                    "nothing."
                ),
            )
        )
        break

    return tuple(out)


def unproposable(schedules: ScheduleSet) -> "dict[str, str]":
    """Required drivers no schedule can measure, and why.

    Named so the screen does not simply omit them. Revenue growth is the
    clearest case: STEP 13 forecasts it, and no schedule measures it, because
    last year's growth is not evidence about next year's.
    """
    reasons = {
        "revenue_growth": (
            "No schedule measures it. Historical growth is arithmetic on two "
            "reported revenues and is not evidence about the next period; STEP "
            "13 wants guidance, a segment build-up or a stated rationale."
        ),
        "cogs_pct_revenue / cogs_amount": (
            "Measurable from the income statement, and deliberately not "
            "proposed: STEP 14 warns against assuming every expense stays a "
            "constant share of revenue, and a proposal is the fastest way to "
            "make that assumption without noticing."
        ),
        "opex_pct_revenue / opex_amount": (
            "The same as COGS, and for the same reason."
        ),
        "capex_pct_revenue / capex_amount": (
            "The PP&E schedule reports CapEx as an amount, not as a policy. "
            "Whether next year's CapEx follows revenue, follows a stated "
            "programme or follows nothing is a decision, not a measurement."
        ),
        "other_current_assets_pct_revenue": (
            "This filing reports no other current assets, so there is nothing "
            "to measure (and zero is a different claim from absent)."
        ),
        "other_current_liabilities_pct_revenue": (
            "This filing reports no other current liabilities."
        ),
    }
    latest = schedules.working_capital.years[-1] if schedules.working_capital.years else None
    if latest is not None and "other_current_assets" not in latest.absent:
        reasons.pop("other_current_assets_pct_revenue", None)
    if latest is not None and "other_current_liabilities" not in latest.absent:
        reasons.pop("other_current_liabilities_pct_revenue", None)
    return reasons
