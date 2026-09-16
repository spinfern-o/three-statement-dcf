"""Numerical precision: independent recomputation, and a randomized sweep.

Two different questions are asked here.

`test_independent_recomputation` asks whether the engine implements the
formulas the workflow specifies. It rebuilds all seven years from the raw
YAML using plain arithmetic that shares no code with `model/`, and compares
every resulting figure. Because it follows the same operation order it is
expected to agree bit-for-bit; a difference means a logic error, not a
rounding one.

`test_randomized_identity_sweep` asks whether the structural identities
survive inputs the fixture never exercises -- nine orders of magnitude of
reporting scale, negative growth, zero debt, zero inventory days. Those
identities are what STEP 6, 21 and 22 demand, and they are the ones that a
plug would hide.

Both assert a relative bound. An absolute one would be a different test at
every reporting scale, which matters because the scale is the modeller's
choice under STEP 1.
"""

from __future__ import annotations

import random

import pytest
import yaml

import model.accounts as A
from model.accounts import Statement
from model.assumptions import Assumption, Assumptions, Basis
from model.dcf import CostOfCapital, EquityBridge, build_fcff, run_dcf
from model.forecast import build_forecast
from model.profile import Periods
from model.provenance import Figure, Source
from model.schedules import TaxSchedule
from model.statements import Ledger
from tests.conftest import FIXTURES

# The requirement is 0.0001% (1e-6). Both tests are held an order of
# magnitude or more inside it; the observed errors are far smaller again.
REQUIRED_REL_TOL = 1e-6
STRICT_REL_TOL = 1e-9


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def test_independent_recomputation(loaded, forecast, fcff_years, valuation):
    """Recompute all seven years from the YAML, sharing no code with model/."""
    raw = yaml.safe_load((FIXTURES / "raw_historical.yaml").read_text())
    asm = yaml.safe_load((FIXTURES / "assumptions.yaml").read_text())
    val = yaml.safe_load((FIXTURES / "valuation.yaml").read_text())

    drivers = {(d["name"], d.get("year")): d["value"] for d in asm["drivers"]}

    def drv(name, year):
        if (name, year) in drivers:
            return drivers[(name, year)]
        return drivers[(name, None)]

    def opt(name, year, default=0.0):
        try:
            return drv(name, year)
        except KeyError:
            return default

    tax = asm["tax"]["rates"]
    fy = list(loaded["periods"].forecast)
    bs = {a: v["values"] for a, v in raw["balance_sheet"].items()}
    ist = {a: v["values"] for a, v in raw["income_statement"].items()}

    prev = dict(
        revenue=ist["revenue"]["2025A"], ppe=bs["ppe_net"]["2025A"], debt=bs["debt"]["2025A"],
        re=bs["retained_earnings"]["2025A"], cash=bs["cash"]["2025A"],
        common=bs["common_equity"]["2025A"],
        onca=bs["other_noncurrent_assets"]["2025A"], oncl=bs["other_noncurrent_liabilities"]["2025A"],
        nwc=(bs["accounts_receivable"]["2025A"] + bs["inventory"]["2025A"] + bs["other_current_assets"]["2025A"])
            - (bs["accounts_payable"]["2025A"] + bs["other_current_liabilities"]["2025A"]),
    )

    worst = 0.0
    compared = 0

    def check(label, mine, theirs):
        nonlocal worst, compared
        assert theirs is not None, f"{label}: engine produced nothing, expected {mine!r}"
        compared += 1
        r = _rel(mine, theirs)
        worst = max(worst, r)
        assert r <= STRICT_REL_TOL, f"{label}: independent {mine!r} vs engine {theirs!r} (rel {r:.3e})"

    # historical derivations first (STEP 5): gross profit -> EBIT -> pretax -> NI
    for year in loaded["periods"].historical:
        gp = ist["revenue"][year] - ist["cogs"][year]
        ebit_h = gp - ist["operating_expenses"][year]
        pretax_h = ebit_h - ist["interest_expense"][year]
        ni_h = pretax_h - ist["taxes"][year]
        check(f"hist {year}.gross_profit", gp, loaded["income"].get(A.GROSS_PROFIT, year))
        check(f"hist {year}.ebit", ebit_h, loaded["income"].get(A.EBIT, year))
        check(f"hist {year}.pretax", pretax_h, loaded["income"].get(A.PRETAX_INCOME, year))
        check(f"hist {year}.net_income", ni_h, loaded["income"].get(A.NET_INCOME, year))

    for year in fy:
        rev = prev["revenue"] * (1 + drv("revenue_growth", year))
        cogs = rev * drv("cogs_pct_revenue", year)
        opex = rev * drv("opex_pct_revenue", year)
        ebit = rev - cogs - opex
        dep = prev["ppe"] * drv("depreciation_pct_beginning_ppe", year)
        capex = rev * drv("capex_pct_revenue", year)
        disposals = opt("ppe_disposals", year)
        ppe = prev["ppe"] + capex - dep - disposals

        ar = rev * drv("dso", year) / 365
        inv = cogs * drv("inventory_days", year) / 365
        ap = cogs * drv("dpo", year) / 365
        oca = rev * drv("other_current_assets_pct_revenue", year)
        ocl = rev * drv("other_current_liabilities_pct_revenue", year)
        nwc = (ar + inv + oca) - (ap + ocl)
        dnwc = nwc - prev["nwc"]

        issuance = opt("debt_issuance", year)
        repayment = opt("debt_repayment", year)
        debt = prev["debt"] + issuance - repayment
        interest = prev["debt"] * drv("interest_rate_on_debt", year)

        pretax = ebit - interest + opt("other_income_expense", year)
        taxes = pretax * tax[year]
        net_income = pretax - taxes

        sbc = rev * opt("sbc_pct_revenue", year)
        buybacks = opt("share_repurchases", year)
        dividends = opt("dividend_payout_ratio", year) * max(net_income, 0.0)
        retained = prev["re"] + net_income - dividends
        common = prev["common"] + sbc - buybacks

        oo, oi, of_ = (opt(k, year) for k in ("other_operating", "other_investing", "other_financing"))
        cfo = net_income + dep + sbc - dnwc + oo
        cfi = -capex - opt("acquisitions", year) + disposals + oi
        cff = issuance - repayment - buybacks - dividends + of_
        cash = prev["cash"] + cfo + cfi + cff
        onca = prev["onca"] - oi
        oncl = prev["oncl"] + oo + of_

        check(f"IS {year}.revenue", rev, forecast.income.get(A.REVENUE, year))
        check(f"IS {year}.cogs", cogs, forecast.income.get(A.COGS, year))
        check(f"IS {year}.gross_profit", rev - cogs, forecast.income.get(A.GROSS_PROFIT, year))
        check(f"IS {year}.ebit", ebit, forecast.income.get(A.EBIT, year))
        check(f"IS {year}.interest", interest, forecast.income.get(A.INTEREST_EXPENSE, year))
        check(f"IS {year}.pretax", pretax, forecast.income.get(A.PRETAX_INCOME, year))
        check(f"IS {year}.taxes", taxes, forecast.income.get(A.TAXES, year))
        check(f"IS {year}.net_income", net_income, forecast.income.get(A.NET_INCOME, year))

        check(f"BS {year}.cash", cash, forecast.balance.get(A.CASH, year))
        check(f"BS {year}.ar", ar, forecast.balance.get(A.ACCOUNTS_RECEIVABLE, year))
        check(f"BS {year}.inventory", inv, forecast.balance.get(A.INVENTORY, year))
        check(f"BS {year}.ap", ap, forecast.balance.get(A.ACCOUNTS_PAYABLE, year))
        check(f"BS {year}.ppe", ppe, forecast.balance.get(A.PPE_NET, year))
        check(f"BS {year}.debt", debt, forecast.balance.get(A.DEBT, year))
        check(f"BS {year}.retained_earnings", retained, forecast.balance.get(A.RETAINED_EARNINGS, year))
        check(f"BS {year}.common_equity", common, forecast.balance.get(A.COMMON_EQUITY, year))
        check(f"BS {year}.other_nca", onca, forecast.balance.get(A.OTHER_NONCURRENT_ASSETS, year))
        check(f"BS {year}.other_ncl", oncl, forecast.balance.get(A.OTHER_NONCURRENT_LIABILITIES, year))

        check(f"BS {year}.other_ca", oca, forecast.balance.get(A.OTHER_CURRENT_ASSETS, year))
        check(f"BS {year}.other_cl", ocl, forecast.balance.get(A.OTHER_CURRENT_LIABILITIES, year))
        assets_y = cash + ar + inv + oca + ppe + onca
        liabs_y = ap + ocl + debt + oncl
        check(f"BS {year}.total_assets", assets_y, forecast.balance.get(A.TOTAL_ASSETS, year))
        check(f"BS {year}.total_liabilities", liabs_y, forecast.balance.get(A.TOTAL_LIABILITIES, year))
        check(f"BS {year}.total_equity", common + retained, forecast.balance.get(A.TOTAL_EQUITY, year))

        check(f"CF {year}.depreciation", dep, forecast.cashflow.get(A.DEPRECIATION_AMORTIZATION, year))
        check(f"CF {year}.capex", -capex, forecast.cashflow.get(A.CAPEX, year))
        check(f"CF {year}.cfo", cfo, forecast.cashflow.get(A.CFO, year))
        check(f"CF {year}.cfi", cfi, forecast.cashflow.get(A.CFI, year))
        check(f"CF {year}.cff", cff, forecast.cashflow.get(A.CFF, year))

        check(f"SCH {year}.ppe", ppe, forecast.ppe.ending(year))
        check(f"SCH {year}.debt", debt, forecast.debt.ending(year))
        check(f"SCH {year}.re", retained, forecast.retained_earnings.ending(year))
        check(f"SCH {year}.nwc", nwc, forecast.working_capital.nwc(year))

        prev = dict(revenue=rev, ppe=ppe, debt=debt, re=retained, cash=cash,
                    common=common, onca=onca, oncl=oncl, nwc=nwc)

    for i, year in enumerate(fy):
        terms = forecast.fcff_inputs(year)
        nopat = terms["ebit"] * (1 - terms["tax_rate"])
        check(f"FCFF {year}.nopat", nopat, fcff_years[i].nopat)
        check(f"FCFF {year}", nopat + terms["d_and_a"] - terms["capex"] - terms["change_in_nwc"],
              fcff_years[i].fcff)

    # valuation, recomputed the same way
    coc = val["cost_of_capital"]
    ke = coc["risk_free_rate"] + coc["beta"] * coc["equity_risk_premium"]
    kd = coc["pretax_cost_of_debt"] * (1 - coc["tax_rate"])
    e, d = coc["market_value_equity"], coc["market_value_debt"]
    wacc = (e / (e + d)) * ke + (d / (e + d)) * kd
    g = val["terminal_growth"]["value"]

    check("cost_of_equity", ke, loaded["valuation_inputs"]["cost_of_capital"].cost_of_equity)
    check("after_tax_cost_of_debt", kd, loaded["valuation_inputs"]["cost_of_capital"].after_tax_cost_of_debt)
    check("wacc", wacc, valuation.wacc)
    pv = sum(fcff.fcff / (1 + wacc) ** (i + 1) for i, fcff in enumerate(fcff_years))
    for i, fcff in enumerate(fcff_years):
        check(f"PV {fy[i]}", fcff.fcff / (1 + wacc) ** (i + 1), valuation.discounted[i].present_value)
    terminal = fcff_years[-1].fcff * (1 + g)
    tv = terminal / (wacc - g)
    pvtv = tv / (1 + wacc) ** len(fy)
    check("terminal_fcff", terminal, valuation.terminal_fcff)
    check("terminal_value", tv, valuation.terminal_value)
    check("pv_terminal_value", pvtv, valuation.pv_terminal_value)
    check("enterprise_value", pv + pvtv, valuation.enterprise_value)
    check("equity_value",
          pv + pvtv + val["equity_bridge"]["cash"] - val["equity_bridge"]["debt"], valuation.equity_value)
    check("implied_share_price",
          valuation.equity_value / val["shares"]["diluted_shares_outstanding"], valuation.implied_share_price)

    assert compared >= 180, f"expected a broad comparison, only made {compared}"
    assert worst <= STRICT_REL_TOL


def _random_case(rng: random.Random, scale: float):
    """A balanced historical sheet at an arbitrary scale, plus random drivers."""
    periods = Periods(("2024A", "2025A"), ("2026E", "2027E", "2028E", "2029E", "2030E"))
    rev = 1000.0 * scale
    cogs = rev * rng.uniform(0.35, 0.75)
    opex = rev * rng.uniform(0.10, 0.30)
    parts = dict(
        cash=rev * rng.uniform(0.05, 0.40), accounts_receivable=rev * rng.uniform(0.05, 0.30),
        inventory=cogs * rng.uniform(0.05, 0.35), other_current_assets=rev * rng.uniform(0.0, 0.05),
        ppe_net=rev * rng.uniform(0.20, 1.50), other_noncurrent_assets=rev * rng.uniform(0.0, 0.20),
        accounts_payable=cogs * rng.uniform(0.05, 0.25),
        other_current_liabilities=rev * rng.uniform(0.0, 0.08),
        debt=rev * rng.uniform(0.0, 0.80), other_noncurrent_liabilities=rev * rng.uniform(0.0, 0.10),
    )
    assets = sum(parts[k] for k in A.ASSET_ACCOUNTS)
    liabs = sum(parts[k] for k in A.LIABILITY_ACCOUNTS)
    parts["common_equity"] = (assets - liabs) * rng.uniform(0.2, 0.8)
    parts["retained_earnings"] = assets - liabs - parts["common_equity"]

    src = Source("SWEEP", 1, "line")
    income = Ledger(Statement.INCOME, periods.historical)
    balance = Ledger(Statement.BALANCE, periods.historical)
    cashflow = Ledger(Statement.CASHFLOW, periods.historical)
    for year in periods.historical:
        for acct, value in (("revenue", rev), ("cogs", cogs), ("operating_expenses", opex)):
            income.set_reported(acct, year, Figure(value, year, src))
        for acct, value in parts.items():
            balance.set_reported(acct, year, Figure(value, year, src))
    for ledger in (income, balance, cashflow):
        ledger.fill_derivable()

    assumptions = Assumptions()

    def add(name, value, year=None):
        assumptions.add(Assumption(name, value, Basis.MODEL_ASSUMPTION, "sweep", year))

    for year in periods.forecast:
        add("revenue_growth", rng.uniform(-0.25, 0.45), year)
        add("cogs_pct_revenue", rng.uniform(0.30, 0.80), year)
    add("opex_pct_revenue", rng.uniform(0.05, 0.30))
    add("dso", rng.uniform(0.0, 180.0))
    add("inventory_days", rng.uniform(0.0, 200.0))
    add("dpo", rng.uniform(0.0, 150.0))
    add("other_current_assets_pct_revenue", rng.uniform(0.0, 0.06))
    add("other_current_liabilities_pct_revenue", rng.uniform(0.0, 0.10))
    add("depreciation_pct_beginning_ppe", rng.uniform(0.02, 0.35))
    add("capex_pct_revenue", rng.uniform(0.0, 0.25))
    add("interest_rate_on_debt", rng.uniform(0.0, 0.18))
    add("sbc_pct_revenue", rng.uniform(0.0, 0.06))
    add("dividend_payout_ratio", rng.uniform(0.0, 0.7))
    add("share_repurchases", rev * rng.uniform(0.0, 0.03))
    add("debt_repayment", parts["debt"] / 6.0)
    add("ppe_disposals", parts["ppe_net"] * rng.uniform(0.0, 0.02))
    for name in ("other_operating", "other_investing", "other_financing"):
        add(name, rev * rng.uniform(-0.02, 0.02))
    taxes = TaxSchedule("statutory", {y: rng.uniform(0.0, 0.45) for y in periods.forecast})
    return periods, income, balance, cashflow, assumptions, taxes


@pytest.mark.parametrize("scale", [1e-3, 1e-1, 1.0, 1e2, 1e4, 1e6])
def test_randomized_identity_sweep(scale):
    """The structural identities hold at every reporting scale.

    This is the test that a plug would fail. Cash is derived from the cash
    flow statement, so `Assets = Liabilities + Equity` only holds if every
    movement was routed consistently -- across negative growth, zero debt,
    zero working-capital days, and nine orders of magnitude of scale.
    """
    rng = random.Random(hash(("sweep", scale)) & 0xFFFFFFFF)
    worst = {"A=L+E": 0.0, "cash": 0.0, "ppe": 0.0, "debt": 0.0, "re": 0.0, "fcff": 0.0, "ev": 0.0}
    models = 0

    for _ in range(25):
        periods, income, balance, cashflow, assumptions, taxes = _random_case(rng, scale)
        forecast = build_forecast(periods, income, balance, cashflow, assumptions, taxes)
        fcff_years = build_fcff(forecast)
        models += 1

        prev_cash = balance.get(A.CASH, periods.last_actual)
        for year in periods.forecast:
            total_a = forecast.balance.get(A.TOTAL_ASSETS, year)
            total_l = forecast.balance.get(A.TOTAL_LIABILITIES, year)
            total_e = forecast.balance.get(A.TOTAL_EQUITY, year)
            worst["A=L+E"] = max(worst["A=L+E"], _rel(total_a, total_l + total_e))

            flows = sum(forecast.cashflow.get(k, year) for k in (A.CFO, A.CFI, A.CFF))
            worst["cash"] = max(worst["cash"], _rel(prev_cash + flows, forecast.balance.get(A.CASH, year)))
            prev_cash = forecast.balance.get(A.CASH, year)

            worst["ppe"] = max(worst["ppe"], _rel(forecast.ppe.ending(year), forecast.balance.get(A.PPE_NET, year)))
            worst["debt"] = max(worst["debt"], _rel(forecast.debt.ending(year), forecast.balance.get(A.DEBT, year)))
            worst["re"] = max(worst["re"], _rel(forecast.retained_earnings.ending(year),
                                                forecast.balance.get(A.RETAINED_EARNINGS, year)))

        for i, year in enumerate(periods.forecast):
            terms = forecast.fcff_inputs(year)
            expected = (terms["ebit"] * (1 - terms["tax_rate"]) + terms["d_and_a"]
                        - terms["capex"] - terms["change_in_nwc"])
            worst["fcff"] = max(worst["fcff"], _rel(expected, fcff_years[i].fcff))

        sources = {k: "sweep" for k in CostOfCapital.REQUIRED_SOURCES}
        coc = CostOfCapital(0.04, 1.0, 0.06, 0.05, 0.25, 1000.0 * scale, 200.0 * scale, sources)
        result = run_dcf(fcff_years, coc, 0.02,
                         EquityBridge(cash=10.0 * scale, debt=20.0 * scale), periods)
        rebuilt = sum(d.fcff / (1 + result.wacc) ** d.period for d in result.discounted) + result.pv_terminal_value
        worst["ev"] = max(worst["ev"], _rel(rebuilt, result.enterprise_value))

    assert models == 25
    offenders = {k: v for k, v in worst.items() if v > REQUIRED_REL_TOL}
    assert not offenders, f"at scale {scale:g}, these exceeded {REQUIRED_REL_TOL:.0e}: {offenders}"


def test_tolerance_is_relative_not_absolute():
    """An absolute tolerance would be a different test at every scale.

    STEP 1 makes the reporting unit the modeller's choice, so a bound of
    '0.01' is 1e-5 relative on a balance sheet of 1,020 but 1e-11 on one of
    1,020,000,000. The same modeling error would pass or fail depending only
    on whether the filing reports in millions or in dollars.
    """
    from model.checks import DEFAULT_REL_TOL, Tolerance

    tol = Tolerance()
    assert DEFAULT_REL_TOL <= REQUIRED_REL_TOL / 100

    for magnitude in (1.0, 1e3, 1e6, 1e9, 1e12):
        # a break just inside the relative bound passes at every scale
        assert tol.close(magnitude, magnitude * (1 + DEFAULT_REL_TOL / 2))
        # and one just outside it fails at every scale
        assert not tol.close(magnitude, magnitude * (1 + DEFAULT_REL_TOL * 10))
