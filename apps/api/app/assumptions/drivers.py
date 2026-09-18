"""What the forecast actually requires, and in what unit.

14.1: "No forecast may calculate until all required assumptions have a
status." That sentence needs a definition of *required*, and the only
authoritative one is the engine: `model/forecast.py` reads a structural driver
through `assumptions.get(...)`, which raises when it is absent, and a
discretionary one through `_optional(...)`, which defaults to zero because zero
is the meaningful "this did not happen" value for a buyback or an acquisition.

So the table below is a reading of the engine, not a wish list, and a test
asserts it stays one by checking every name here appears in
`model/forecast.py` and that no `assumptions.get` call there is missing from
here. Adding a driver to the forecast without adding it here would let the
14.1 gate pass a model that then halts.

**Units matter as much as names.** `dso` is a count of days; declaring it as a
ratio and handing 0.164 to `days_to_balance` gives a receivable four hundred
times too small, and nothing downstream looks wrong. 18.12 catches that only if
the assumption declares its unit, so every row here carries one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Driver:
    """One forecast input, its unit, and why the forecast needs it."""

    code: str
    name: str
    unit: str
    step: str
    #: A driver that may be satisfied by this OR by its alternative. STEP 14
    #: and 18 require one stated methodology per line, so declaring both is
    #: refused by the engine and by `missing_for` below.
    alternative: str = ""
    #: False for the discretionary flows `_optional` defaults to zero.
    required: bool = True
    #: Where the engine reads it from, when that is not the assumptions
    #: register. STEP 16's tax rate is the one case, and it is the case that
    #: matters: the engine halts on it, so a gate that does not demand it
    #: passes a model that then stops.
    supplied_via: str = "assumptions register"
    note: str = ""


#: STEP 13 to 19, as `model/forecast.py` reads them.
DRIVERS = (
    Driver("revenue_growth", "Revenue growth", "ratio", "STEP 13",
           note="Per-year, or one entry for every year. Segment-level growth is "
                "declared as revenue_growth.<segment>."),
    Driver("cogs_pct_revenue", "COGS as a share of revenue", "ratio", "STEP 14",
           alternative="cogs_amount"),
    Driver("cogs_amount", "COGS, stated absolutely", "currency", "STEP 14",
           alternative="cogs_pct_revenue"),
    Driver("opex_pct_revenue", "Operating expenses as a share of revenue", "ratio",
           "STEP 14", alternative="opex_amount",
           note="STEP 14 warns against assuming every expense stays a constant "
                "share of revenue; per-year entries are how that is avoided."),
    Driver("opex_amount", "Operating expenses, stated absolutely", "currency",
           "STEP 14", alternative="opex_pct_revenue"),
    Driver("depreciation_pct_beginning_ppe", "Depreciation on opening PP&E", "ratio",
           "STEP 18",
           note="STEP 18 forecasts depreciation and CapEx separately. Neither "
                "may default to the other."),
    Driver("capex_pct_revenue", "CapEx as a share of revenue", "ratio", "STEP 18",
           alternative="capex_amount"),
    Driver("capex_amount", "CapEx, stated absolutely", "currency", "STEP 18",
           alternative="capex_pct_revenue"),
    Driver("dso", "Days sales outstanding", "days", "STEP 17",
           note="A count of days, not a ratio. The historical value comes from "
                "the 13.1 working-capital schedule."),
    Driver("inventory_days", "Inventory days", "days", "STEP 17"),
    Driver("dpo", "Days payable outstanding", "days", "STEP 17"),
    Driver("other_current_assets_pct_revenue", "Other current assets on revenue",
           "ratio", "STEP 17"),
    Driver("other_current_liabilities_pct_revenue",
           "Other current liabilities on revenue", "ratio", "STEP 17"),
    Driver("interest_rate_on_debt", "Interest rate on beginning debt", "ratio",
           "STEP 19",
           note="Charged on BEGINNING debt. The historical implied rate on the "
                "same basis is in the 13.4 debt schedule."),
    Driver("tax_rate", "Effective tax rate", "ratio", "STEP 16",
           supplied_via="model/schedules.py:TaxSchedule, from valuation.yaml",
           note="The one required driver the engine does NOT read from the "
                "assumptions register: STEP 16 makes the model state which "
                "basis it uses -- statutory, historical effective or normalized "
                "effective -- so the rate arrives as part of a TaxSchedule that "
                "carries that basis. It is listed here because 14.1 asks whether "
                "the forecast may calculate, and without a tax rate it may not: "
                "running the engine without one halts with 'tax.source is "
                "required by STEP 16'."),
    # --- discretionary: zero is the meaningful default -----------------------
    Driver("ppe_disposals", "PP&E disposals", "currency", "STEP 18", required=False),
    Driver("debt_issuance", "New borrowing", "currency", "STEP 19", required=False),
    Driver("debt_repayment", "Debt repaid", "currency", "STEP 19", required=False),
    Driver("sbc_pct_revenue", "Stock compensation on revenue", "ratio", "STEP 20",
           required=False),
    Driver("share_repurchases", "Share repurchases", "currency", "STEP 21",
           required=False),
    Driver("dividends_amount", "Dividends, stated absolutely", "currency", "STEP 21",
           alternative="dividend_payout_ratio", required=False),
    Driver("dividend_payout_ratio", "Dividend payout ratio", "ratio", "STEP 21",
           alternative="dividends_amount", required=False),
    Driver("acquisitions", "Acquisitions", "currency", "STEP 18", required=False),
    Driver("other_income_expense", "Other income and expense", "currency", "STEP 15",
           required=False),
    Driver("other_operating", "Other operating cash flows", "currency", "STEP 22",
           required=False),
    Driver("other_investing", "Other investing cash flows", "currency", "STEP 22",
           required=False),
    Driver("other_financing", "Other financing cash flows", "currency", "STEP 22",
           required=False),
)

BY_CODE = {driver.code: driver for driver in DRIVERS}

#: The lines the forecast cannot produce without an answer. Each entry is the
#: set of codes any ONE of which satisfies it.
REQUIRED_CHOICES = tuple(
    frozenset({driver.code} | ({driver.alternative} if driver.alternative else set()))
    for driver in DRIVERS
    if driver.required
)
#: Deduplicated, because a pair appears once per member.
REQUIRED: tuple[frozenset[str], ...] = tuple(sorted(set(REQUIRED_CHOICES), key=sorted))


def driver(code: str) -> Driver:
    base = code.split(".")[0]  # revenue_growth.<segment>
    if base not in BY_CODE:
        raise KeyError(
            f"{code!r} is not a forecast driver. Known: {', '.join(sorted(BY_CODE))}"
        )
    return BY_CODE[base]


def describe_choice(choice: frozenset[str]) -> str:
    codes = sorted(choice)
    if len(codes) == 1:
        return codes[0]
    return " or ".join(codes) + " (one stated methodology per line, STEP 14/18)"
