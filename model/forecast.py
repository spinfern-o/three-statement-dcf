"""STEP 12-22: the forecast three-statement model.

Structure of a forecast year, in the order the workflow builds it:

  revenue (13) -> operating costs (14) -> EBIT (15) -> schedules (17-19)
  -> interest -> taxes (16) -> net income (20) -> balance sheet (21)
  -> cash flow statement (22)

The one architectural commitment worth stating plainly: **cash is not a
plug**. Ending cash is produced by the cash flow statement
(begin + CFO + CFI + CFF) and then placed on the balance sheet. Assets =
Liabilities + Equity is therefore a real test of whether every flow was
modeled consistently, which is what STEP 21 and STEP 37 are asking for.
STEP 6's "Do not use a plug simply to force the model to balance" is
honored structurally rather than by intent.

For that identity to close, every cash movement must correspond to a
balance-sheet movement. The three residual "other" lines are linked
explicitly:

  other_operating  -> other_noncurrent_liabilities   (+)
  other_investing  -> other_noncurrent_assets        (-)
  other_financing  -> other_noncurrent_liabilities   (+)

All three default to zero and must be declared as assumptions to be
non-zero, so nothing enters the model unnamed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from . import accounts as A
from .assumptions import Assumptions
from .numeric import ONE, ZERO, D
from .profile import Periods
from .provenance import ProvenanceError
from .schedules import (
    RollForward,
    TaxSchedule,
    WorkingCapitalRow,
    WorkingCapitalSchedule,
    days_to_balance,
    debt_schedule,
    ppe_schedule,
    retained_earnings_schedule,
)
from .statements import Ledger

#: STEP 17 / specification 13.1.e: the day-count convention, stated once
#: rather than buried as a literal 365 inside three separate formulas.
DAYS_IN_YEAR = D(365)


@dataclass
class ForecastResult:
    periods: Periods
    income: Ledger
    balance: Ledger
    cashflow: Ledger
    ppe: RollForward
    debt: RollForward
    retained_earnings: RollForward
    working_capital: WorkingCapitalSchedule
    taxes: TaxSchedule
    segment_revenue: dict[str, dict[str, Decimal]] = field(default_factory=dict)

    def fcff_inputs(self, year: str) -> dict[str, Decimal]:
        """The four STEP 23 terms, read back out of the built statements."""
        prior = self.periods.prior(year)
        return {
            "ebit": self.income.require(A.EBIT, year, "STEP 23 (FCFF)"),
            "tax_rate": self.taxes.rate(year),
            "d_and_a": self.cashflow.require(A.DEPRECIATION_AMORTIZATION, year, "STEP 23 (FCFF)"),
            "capex": abs(self.cashflow.require(A.CAPEX, year, "STEP 23 (FCFF)")),
            "change_in_nwc": self.working_capital.change_in_nwc(year, prior),
        }


def _pick_driver(
    assumptions: Assumptions,
    year: str,
    pct_name: str,
    pct_of: Decimal,
    amount_name: str,
    label: str,
) -> tuple[Decimal, str]:
    """STEP 14/18: the methodology must be chosen explicitly, not inferred.

    An absolute amount and a percentage driver for the same line in the same
    year is an ambiguity, so it is rejected rather than silently ranked.
    """
    has_pct = assumptions.has(pct_name, year)
    has_amt = assumptions.has(amount_name, year)
    if has_pct and has_amt:
        raise ProvenanceError(
            f"{label} for {year} has both {pct_name!r} and {amount_name!r} declared. "
            "STEP 14/18 require one stated methodology per line -- remove one."
        )
    if has_amt:
        value = assumptions.get(amount_name, year)
        return value, f"{amount_name} (absolute) = {value:,.1f}"
    if has_pct:
        pct = assumptions.get(pct_name, year)
        return pct_of * pct, f"{pct_name} = {pct:.4f} x driver {pct_of:,.1f}"
    raise ProvenanceError(
        f"{label} for {year} has no driver. Declare either {pct_name!r} or "
        f"{amount_name!r} in the assumptions section (STEP 10)."
    )


def _optional(assumptions: Assumptions, name: str, year: str, default: Decimal = ZERO) -> Decimal:
    """Zero only where zero is the meaningful 'this did not happen' value.

    Used for discretionary flows (buybacks, acquisitions, the residual
    'other' lines). Structural drivers never route through here.
    """
    return assumptions.get(name, year) if assumptions.has(name, year) else default


def _total(balance: Ledger, accounts: tuple[str, ...], year: str) -> Decimal:
    """Sum the accounts of one section that this forecast actually set.

    An absent account contributes nothing rather than a zero (rule 1.3): a
    company with no goodwill has none, and `_carry_forward` leaves it absent
    rather than writing zero into every forecast year.
    """
    total = D(0)
    for account in accounts:
        value = balance.get(account, year)
        if value is not None:
            total += value
    return total


#: 12.2.e, 12.2.i and 12.2.k. Balances that exist on the historical balance
#: sheet and that **no assumption in this model drives**.
#:
#: Each is held at its last reported value, with that said in the basis string
#: rather than left for a reader to infer from a flat line. Holding a balance
#: flat is a forecast decision, and STEP 10 forbids hiding one inside a
#: formula; it is the defensible default here because the alternatives are
#: worse. Growing goodwill means forecasting acquisitions the company has not
#: announced. Amortizing intangibles needs the 13.3 schedule, which needs an
#: amortization line separate from depreciation -- available now, but a
#: schedule rather than a carry-forward. Running leases down needs a payment
#: schedule (13.5). Growing minority interest means forecasting the
#: subsidiaries' earnings separately from the parent's.
#:
#: **Absent stays absent** (rule 1.3). A company with no goodwill has none to
#: project, and writing a zero here would turn "does not have it" into "has
#: zero of it" for every forecast year.
CARRIED_FORWARD = (
    A.GOODWILL,
    A.INTANGIBLES,
    A.LEASE_LIABILITIES,
    A.MINORITY_INTEREST,
)


def _carry_forward(
    historical_balance: Ledger, balance: Ledger, year: str, last_actual: str
) -> None:
    """Hold each `CARRIED_FORWARD` balance at its last reported value."""
    for account in CARRIED_FORWARD:
        opening = historical_balance.get(account, last_actual)
        if opening is None:
            continue
        balance.set_forecast(
            account,
            year,
            opening,
            f"held at the {last_actual} balance: no assumption in this model drives it",
        )


def build_forecast(
    periods: Periods,
    historical_income: Ledger,
    historical_balance: Ledger,
    historical_cashflow: Ledger,
    assumptions: Assumptions,
    taxes: TaxSchedule,
    segments: dict[str, Decimal] | None = None,
) -> ForecastResult:
    """Build the projected income statement, balance sheet and cash flow."""

    years = periods.all_years
    income = historical_income.extended_to(years)
    balance = historical_balance.extended_to(years)
    cashflow = historical_cashflow.extended_to(years)

    ppe = ppe_schedule()
    debt = debt_schedule()
    retained = retained_earnings_schedule()
    wc = WorkingCapitalSchedule()

    last_actual = periods.last_actual

    # The last actual year anchors every roll-forward and the first change
    # in NWC (STEP 17), so its balances must be present before forecasting.
    base_ppe = historical_balance.require(A.PPE_NET, last_actual, "STEP 18 (PP&E schedule)")
    base_debt = historical_balance.require(A.DEBT, last_actual, "STEP 19 (debt schedule)")
    base_re = historical_balance.require(A.RETAINED_EARNINGS, last_actual, "STEP 8 (RE schedule)")
    base_cash = historical_balance.require(A.CASH, last_actual, "STEP 22 (cash roll-forward)")
    base_common = historical_balance.require(A.COMMON_EQUITY, last_actual, "STEP 21 (equity)")
    base_other_nca = historical_balance.require(
        A.OTHER_NONCURRENT_ASSETS, last_actual, "STEP 21 (balance sheet)"
    )
    base_other_ncl = historical_balance.require(
        A.OTHER_NONCURRENT_LIABILITIES, last_actual, "STEP 21 (balance sheet)"
    )

    wc.add(
        WorkingCapitalRow(
            year=last_actual,
            accounts_receivable=historical_balance.require(
                A.ACCOUNTS_RECEIVABLE, last_actual, "STEP 17"
            ),
            inventory=historical_balance.require(A.INVENTORY, last_actual, "STEP 17"),
            other_current_assets=historical_balance.require(
                A.OTHER_CURRENT_ASSETS, last_actual, "STEP 17"
            ),
            accounts_payable=historical_balance.require(A.ACCOUNTS_PAYABLE, last_actual, "STEP 17"),
            other_current_liabilities=historical_balance.require(
                A.OTHER_CURRENT_LIABILITIES, last_actual, "STEP 17"
            ),
        )
    )

    prev_ppe, prev_debt, prev_re = base_ppe, base_debt, base_re
    prev_cash, prev_common = base_cash, base_common
    prev_other_nca, prev_other_ncl = base_other_nca, base_other_ncl

    segment_revenue: dict[str, dict[str, Decimal]] = {}
    prev_segments = dict(segments) if segments else {}

    for year in periods.forecast:
        prior = periods.prior(year)
        assert prior is not None  # guaranteed by Periods' contiguity check

        # -- STEP 13: revenue ---------------------------------------------
        if prev_segments:
            total = ZERO
            for name, prior_value in sorted(prev_segments.items()):
                growth = assumptions.get(f"revenue_growth.{name}", year)
                value = prior_value * (ONE + growth)
                segment_revenue.setdefault(name, {})[year] = value
                total += value
            prev_segments = {n: segment_revenue[n][year] for n in prev_segments}
            revenue = total
            revenue_basis = "sum of segment revenues (STEP 13)"
        else:
            prior_revenue = income.require(A.REVENUE, prior, "STEP 13 (revenue growth)")
            growth = assumptions.get("revenue_growth", year)
            revenue = prior_revenue * (ONE + growth)
            revenue_basis = f"revenue_growth = {growth:.4f} on {prior} revenue {prior_revenue:,.1f}"
        income.set_forecast(A.REVENUE, year, revenue, revenue_basis)

        # -- STEP 14: operating costs -------------------------------------
        cogs, cogs_basis = _pick_driver(
            assumptions, year, "cogs_pct_revenue", revenue, "cogs_amount", "COGS"
        )
        income.set_forecast(A.COGS, year, cogs, cogs_basis)
        income.set_forecast(
            A.GROSS_PROFIT, year, revenue - cogs, "gross_profit = revenue - cogs (STEP 14)"
        )

        opex, opex_basis = _pick_driver(
            assumptions, year, "opex_pct_revenue", revenue, "opex_amount", "Operating expenses"
        )
        income.set_forecast(A.OPERATING_EXPENSES, year, opex, opex_basis)

        # -- STEP 15: EBIT, kept clear of financing items ------------------
        ebit = revenue - cogs - opex
        income.set_forecast(
            A.EBIT, year, ebit, "ebit = revenue - cogs - operating_expenses (STEP 15)"
        )

        # -- STEP 18: depreciation and CapEx, forecast separately ----------
        dep_pct = assumptions.get("depreciation_pct_beginning_ppe", year)
        depreciation = prev_ppe * dep_pct
        capex, capex_basis = _pick_driver(
            assumptions, year, "capex_pct_revenue", revenue, "capex_amount", "CapEx"
        )
        disposals = _optional(assumptions, "ppe_disposals", year)
        ppe.add_year(
            year,
            prev_ppe,
            {"CapEx": capex},
            {"Depreciation": depreciation, "Disposals": disposals},
        )
        ending_ppe = ppe.ending(year)

        # -- STEP 17: working capital, account by account ------------------
        ar = days_to_balance(revenue, assumptions.get("dso", year), DAYS_IN_YEAR)
        inventory = days_to_balance(cogs, assumptions.get("inventory_days", year), DAYS_IN_YEAR)
        ap = days_to_balance(cogs, assumptions.get("dpo", year), DAYS_IN_YEAR)
        other_ca = revenue * assumptions.get("other_current_assets_pct_revenue", year)
        other_cl = revenue * assumptions.get("other_current_liabilities_pct_revenue", year)
        wc.add(WorkingCapitalRow(year, ar, inventory, other_ca, ap, other_cl))
        change_in_nwc = wc.change_in_nwc(year, prior)

        # -- STEP 19: debt and interest, interest linked to debt ----------
        issuance = _optional(assumptions, "debt_issuance", year)
        repayment = _optional(assumptions, "debt_repayment", year)
        debt.add_year(year, prev_debt, {"New Borrowing": issuance}, {"Repayment": repayment})
        ending_debt = debt.ending(year)
        if ending_debt < 0:
            raise ProvenanceError(
                f"Debt schedule for {year} repays more than is outstanding "
                f"(ending debt {ending_debt:,.1f}). Check debt_repayment (STEP 19)."
            )
        rate = assumptions.get("interest_rate_on_debt", year)
        interest = prev_debt * rate
        income.set_forecast(
            A.INTEREST_EXPENSE,
            year,
            interest,
            f"interest_rate_on_debt = {rate:.4f} on beginning debt {prev_debt:,.1f} (STEP 19)",
        )

        # -- STEP 16 / 20: taxes and net income ---------------------------
        other_inc = _optional(assumptions, "other_income_expense", year)
        income.set_forecast(
            A.OTHER_INCOME_EXPENSE, year, other_inc, "other_income_expense assumption"
        )
        pretax = ebit - interest + other_inc
        income.set_forecast(
            A.PRETAX_INCOME,
            year,
            pretax,
            "pretax = ebit - interest + other_income_expense (STEP 20)",
        )
        tax_rate = taxes.rate(year)
        tax = pretax * tax_rate
        income.set_forecast(A.TAXES, year, tax, f"{taxes.basis} tax rate {tax_rate:.4f} (STEP 16)")
        net_income = pretax - tax
        income.set_forecast(A.NET_INCOME, year, net_income, "net_income = pretax - taxes (STEP 20)")

        # -- equity movements ---------------------------------------------
        sbc = revenue * _optional(assumptions, "sbc_pct_revenue", year)
        buybacks = _optional(assumptions, "share_repurchases", year)
        # One stated method per line, as STEP 14/18 require of every other
        # driver. Declaring both a payout ratio and an amount used to prefer
        # the amount silently.
        has_ratio = assumptions.has("dividend_payout_ratio", year)
        has_amount = assumptions.has("dividends_amount", year)
        if has_ratio and has_amount:
            raise ProvenanceError(
                f"Dividends for {year} have both 'dividend_payout_ratio' and "
                f"'dividends_amount' declared. One stated methodology per line -- "
                f"remove one (STEP 10, STEP 14)."
            )
        if has_amount:
            dividends = assumptions.get("dividends_amount", year)
        else:
            dividends = _optional(assumptions, "dividend_payout_ratio", year) * max(
                net_income, ZERO
            )
        retained.add_year(year, prev_re, {"Net Income": net_income}, {"Dividends": dividends})
        ending_re = retained.ending(year)
        ending_common = prev_common + sbc - buybacks

        # -- STEP 22: cash flow statement ---------------------------------
        other_op = _optional(assumptions, "other_operating", year)
        other_inv = _optional(assumptions, "other_investing", year)
        other_fin = _optional(assumptions, "other_financing", year)

        cashflow.set_forecast(
            A.NET_INCOME, year, net_income, "from projected income statement (STEP 22)"
        )
        cashflow.set_forecast(
            A.DEPRECIATION_AMORTIZATION, year, depreciation, "non-cash add-back, from PP&E schedule"
        )
        cashflow.set_forecast(A.STOCK_BASED_COMP, year, sbc, "non-cash add-back, sbc_pct_revenue")
        cashflow.set_forecast(
            A.CHANGE_IN_NWC,
            year,
            -change_in_nwc,
            "-(NWC_t - NWC_t-1); an NWC build consumes cash (STEP 17)",
        )
        cashflow.set_forecast(
            A.OTHER_OPERATING, year, other_op, "other_operating -> other_noncurrent_liabilities"
        )
        cfo = net_income + depreciation + sbc - change_in_nwc + other_op
        cashflow.set_derived(A.CFO, year, cfo, "sum of operating items (STEP 22)")

        cashflow.set_forecast(A.CAPEX, year, -capex, capex_basis + " (cash outflow)")
        cashflow.set_forecast(
            A.ACQUISITIONS,
            year,
            -_optional(assumptions, "acquisitions", year),
            "acquisitions assumption",
        )
        cashflow.set_forecast(
            A.OTHER_INVESTING,
            year,
            disposals + other_inv,
            "disposal proceeds at book value + other_investing",
        )
        cfi = -capex - _optional(assumptions, "acquisitions", year) + disposals + other_inv
        cashflow.set_derived(A.CFI, year, cfi, "sum of investing items (STEP 22)")

        cashflow.set_forecast(A.DEBT_ISSUANCE, year, issuance, "from debt schedule (STEP 19)")
        cashflow.set_forecast(A.DEBT_REPAYMENT, year, -repayment, "from debt schedule (STEP 19)")
        cashflow.set_forecast(A.SHARE_REPURCHASES, year, -buybacks, "share_repurchases assumption")
        cashflow.set_forecast(
            A.DIVIDENDS, year, -dividends, "from retained earnings schedule (STEP 8)"
        )
        cashflow.set_forecast(
            A.OTHER_FINANCING, year, other_fin, "other_financing -> other_noncurrent_liabilities"
        )
        cff = issuance - repayment - buybacks - dividends + other_fin
        cashflow.set_derived(A.CFF, year, cff, "sum of financing items (STEP 22)")

        ending_cash = prev_cash + cfo + cfi + cff

        # -- STEP 21: projected balance sheet ------------------------------
        ending_other_nca = prev_other_nca - other_inv
        ending_other_ncl = prev_other_ncl + other_op + other_fin

        balance.set_forecast(
            A.CASH, year, ending_cash, "beginning cash + CFO + CFI + CFF (STEP 22)"
        )
        balance.set_forecast(
            A.ACCOUNTS_RECEIVABLE,
            year,
            ar,
            f"dso = {assumptions.get('dso', year):.1f} days (STEP 17)",
        )
        balance.set_forecast(A.INVENTORY, year, inventory, "inventory_days on COGS (STEP 17)")
        balance.set_forecast(
            A.OTHER_CURRENT_ASSETS, year, other_ca, "other_current_assets_pct_revenue"
        )
        balance.set_forecast(A.PPE_NET, year, ending_ppe, "from PP&E schedule (STEP 18)")
        _carry_forward(historical_balance, balance, year, last_actual)
        balance.set_forecast(
            A.OTHER_NONCURRENT_ASSETS, year, ending_other_nca, "prior balance less other_investing"
        )

        balance.set_forecast(A.ACCOUNTS_PAYABLE, year, ap, "dpo on COGS (STEP 17)")
        balance.set_forecast(
            A.OTHER_CURRENT_LIABILITIES, year, other_cl, "other_current_liabilities_pct_revenue"
        )
        balance.set_forecast(A.DEBT, year, ending_debt, "from debt schedule (STEP 19)")
        balance.set_forecast(
            A.OTHER_NONCURRENT_LIABILITIES,
            year,
            ending_other_ncl,
            "prior balance plus other_operating/other_financing",
        )

        balance.set_forecast(
            A.COMMON_EQUITY, year, ending_common, "prior balance + SBC - share repurchases"
        )
        balance.set_forecast(
            A.RETAINED_EARNINGS, year, ending_re, "from retained earnings schedule (STEP 8)"
        )

        # Summed FROM THE CHART rather than by hand. The hand-written version
        # was `ending_cash + ar + inventory + ...`, which was correct for the
        # accounts that existed when it was written and silently wrong the
        # moment 12.2.e's goodwill was added to `ASSET_ACCOUNTS`: the line was
        # forecast, and left out of the total, so A = L + E broke by exactly
        # the goodwill. A total that reads its own membership cannot drift
        # from the chart.
        assets = _total(balance, A.ASSET_ACCOUNTS, year)
        liabilities = _total(balance, A.LIABILITY_ACCOUNTS, year)
        equity = _total(balance, A.EQUITY_ACCOUNTS, year)
        balance.set_derived(A.TOTAL_ASSETS, year, assets, "sum of asset accounts")
        balance.set_derived(A.TOTAL_LIABILITIES, year, liabilities, "sum of liability accounts")
        balance.set_derived(A.TOTAL_EQUITY, year, equity, "sum of equity accounts")

        prev_ppe, prev_debt, prev_re = ending_ppe, ending_debt, ending_re
        prev_cash, prev_common = ending_cash, ending_common
        prev_other_nca, prev_other_ncl = ending_other_nca, ending_other_ncl

    return ForecastResult(
        periods=periods,
        income=income,
        balance=balance,
        cashflow=cashflow,
        ppe=ppe,
        debt=debt,
        retained_earnings=retained,
        working_capital=wc,
        taxes=taxes,
        segment_revenue=segment_revenue,
    )
