"""Numerical precision: independent recomputation, and a randomized sweep.

Two different questions are asked here.

`test_independent_recomputation` asks whether the engine implements the
formulas the workflow specifies. It rebuilds all seven years from the raw
YAML using plain Decimal arithmetic that shares no code with `model/` --
specification 4.15 requires that the primary engine and the benchmark not
call the same helper, so this file parses the YAML with its own loader and
builds its own Decimals rather than importing `model.numeric.D` or
`model.yaml_exact`.

`test_randomized_identity_sweep` asks whether the structural identities
survive inputs the fixture never exercises -- nine orders of magnitude of
reporting scale, negative growth, zero debt, zero inventory days.

Both now run on exact decimal arithmetic (specification 1.15, 4.4), so the
expected result is not "within tolerance" but *exact equality*. The
tolerances below are retained as a ceiling, and the tests assert the
stronger property where it holds.
"""

from __future__ import annotations

import random
from decimal import Decimal

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

# Specification 4.11: the contract is 0.0001%, expressed as a percentage.
REQUIRED_REL_TOL_PERCENT = Decimal("0.0001")

# Decimal is exact for addition, subtraction, multiplication, and for any
# division that terminates. It is NOT exact for a division that repeats:
# `x / 365` and `x / 6` are rounded to the context's 50 significant digits,
# so two mathematically equal sums built in a different order can differ by
# one unit in the last place. Measured worst case in this sweep is 1E-46
# absolute, 3.4e-50 relative.
#
# So the identity tests below assert a bound derived from the context
# precision rather than bitwise equality. It is still forty orders of
# magnitude inside the 0.0001% the specification requires, and any real
# modelling error is many orders larger than this floor.
CONTEXT_FLOOR_REL_PERCENT = Decimal("1e-38")


# --- the benchmark's own infrastructure, deliberately not the engine's -----
class _BenchmarkLoader(yaml.SafeLoader):
    """Keeps numeric scalars as written, so the benchmark parses exactly.

    Duplicated rather than imported from `model.yaml_exact`: 4.15 requires
    the benchmark not to share the engine's helpers.
    """


def _verbatim(loader, node):
    return loader.construct_scalar(node)


_BenchmarkLoader.add_constructor("tag:yaml.org,2002:int", _verbatim)
_BenchmarkLoader.add_constructor("tag:yaml.org,2002:float", _verbatim)


def _load(path):
    return yaml.load(path.read_text(), Loader=_BenchmarkLoader)


def _d(value) -> Decimal:
    """The benchmark's own Decimal construction, not `model.numeric.D`."""
    return Decimal(str(value))


def _rel_percent(actual: Decimal, expected: Decimal) -> Decimal:
    if expected == 0:
        return abs(actual) * Decimal(100)
    return abs(actual - expected) / abs(expected) * Decimal(100)


def test_independent_recomputation(loaded, forecast, fcff_years, valuation):
    """Recompute all seven years from the YAML, sharing no code with model/."""
    raw = _load(FIXTURES / "raw_historical.yaml")
    asm = _load(FIXTURES / "assumptions.yaml")
    val = _load(FIXTURES / "valuation.yaml")

    drivers = {(d["name"], d.get("year")): _d(d["value"]) for d in asm["drivers"]}

    def drv(name, year):
        if (name, year) in drivers:
            return drivers[(name, year)]
        return drivers[(name, None)]

    def opt(name, year, default=Decimal(0)):
        try:
            return drv(name, year)
        except KeyError:
            return default

    tax = {k: _d(v) for k, v in asm["tax"]["rates"].items()}
    fy = list(loaded["periods"].forecast)
    bs = {a: {y: _d(v) for y, v in blk["values"].items()} for a, blk in raw["balance_sheet"].items()}
    ist = {a: {y: _d(v) for y, v in blk["values"].items()} for a, blk in raw["income_statement"].items()}

    one = Decimal(1)
    days = Decimal(365)

    prev = dict(
        revenue=ist["revenue"]["2025A"], ppe=bs["ppe_net"]["2025A"], debt=bs["debt"]["2025A"],
        re=bs["retained_earnings"]["2025A"], cash=bs["cash"]["2025A"],
        common=bs["common_equity"]["2025A"],
        onca=bs["other_noncurrent_assets"]["2025A"], oncl=bs["other_noncurrent_liabilities"]["2025A"],
        nwc=(bs["accounts_receivable"]["2025A"] + bs["inventory"]["2025A"] + bs["other_current_assets"]["2025A"])
            - (bs["accounts_payable"]["2025A"] + bs["other_current_liabilities"]["2025A"]),
    )

    worst = Decimal(0)
    compared = 0
    inexact = []

    def check(label, mine, theirs):
        nonlocal worst, compared
        assert theirs is not None, f"{label}: engine produced nothing, expected {mine!r}"
        assert isinstance(theirs, Decimal), f"{label}: engine returned {type(theirs).__name__}, not Decimal"
        compared += 1
        if mine != theirs:
            inexact.append(f"{label}: benchmark {mine} vs engine {theirs}")
        r = _rel_percent(theirs, mine)
        worst = max(worst, r)

    # historical derivations (STEP 5)
    for year in loaded["periods"].historical:
        gp = ist["revenue"][year] - ist["cogs"][year]
        ebit_h = gp - ist["operating_expenses"][year]
        pretax_h = ebit_h - ist["interest_expense"][year]
        check(f"hist {year}.gross_profit", gp, loaded["income"].get(A.GROSS_PROFIT, year))
        check(f"hist {year}.ebit", ebit_h, loaded["income"].get(A.EBIT, year))
        check(f"hist {year}.pretax", pretax_h, loaded["income"].get(A.PRETAX_INCOME, year))
        check(f"hist {year}.net_income", pretax_h - ist["taxes"][year],
              loaded["income"].get(A.NET_INCOME, year))

    for year in fy:
        rev = prev["revenue"] * (one + drv("revenue_growth", year))
        cogs = rev * drv("cogs_pct_revenue", year)
        opex = rev * drv("opex_pct_revenue", year)
        ebit = rev - cogs - opex
        dep = prev["ppe"] * drv("depreciation_pct_beginning_ppe", year)
        capex = rev * drv("capex_pct_revenue", year)
        disposals = opt("ppe_disposals", year)
        ppe = prev["ppe"] + capex - dep - disposals

        ar = rev * drv("dso", year) / days
        inv = cogs * drv("inventory_days", year) / days
        ap = cogs * drv("dpo", year) / days
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
        dividends = opt("dividend_payout_ratio", year) * max(net_income, Decimal(0))
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
        check(f"BS {year}.other_ca", oca, forecast.balance.get(A.OTHER_CURRENT_ASSETS, year))
        check(f"BS {year}.other_cl", ocl, forecast.balance.get(A.OTHER_CURRENT_LIABILITIES, year))
        check(f"BS {year}.ppe", ppe, forecast.balance.get(A.PPE_NET, year))
        check(f"BS {year}.debt", debt, forecast.balance.get(A.DEBT, year))
        check(f"BS {year}.retained_earnings", retained, forecast.balance.get(A.RETAINED_EARNINGS, year))
        check(f"BS {year}.common_equity", common, forecast.balance.get(A.COMMON_EQUITY, year))
        check(f"BS {year}.other_nca", onca, forecast.balance.get(A.OTHER_NONCURRENT_ASSETS, year))
        check(f"BS {year}.other_ncl", oncl, forecast.balance.get(A.OTHER_NONCURRENT_LIABILITIES, year))
        check(f"BS {year}.total_assets", cash + ar + inv + oca + ppe + onca,
              forecast.balance.get(A.TOTAL_ASSETS, year))
        check(f"BS {year}.total_liabilities", ap + ocl + debt + oncl,
              forecast.balance.get(A.TOTAL_LIABILITIES, year))
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
        nopat = terms["ebit"] * (one - terms["tax_rate"])
        check(f"FCFF {year}.nopat", nopat, fcff_years[i].nopat)
        check(f"FCFF {year}", nopat + terms["d_and_a"] - terms["capex"] - terms["change_in_nwc"],
              fcff_years[i].fcff)

    coc = val["cost_of_capital"]
    ke = _d(coc["risk_free_rate"]) + _d(coc["beta"]) * _d(coc["equity_risk_premium"])
    kd = _d(coc["pretax_cost_of_debt"]) * (one - _d(coc["tax_rate"]))
    e, dbt = _d(coc["market_value_equity"]), _d(coc["market_value_debt"])
    wacc = (e / (e + dbt)) * ke + (dbt / (e + dbt)) * kd
    g = _d(val["terminal_growth"]["value"])

    engine_coc = loaded["valuation_inputs"]["cost_of_capital"]
    check("cost_of_equity", ke, engine_coc.cost_of_equity)
    check("after_tax_cost_of_debt", kd, engine_coc.after_tax_cost_of_debt)
    check("wacc", wacc, valuation.wacc)

    pv = Decimal(0)
    for i, item in enumerate(fcff_years):
        factor = one / (one + wacc) ** (i + 1)
        check(f"PV {fy[i]}", item.fcff * factor, valuation.discounted[i].present_value)
        pv += item.fcff * factor

    terminal = fcff_years[-1].fcff * (one + g)
    tv = terminal / (wacc - g)
    pvtv = tv / (one + wacc) ** len(fy)
    check("terminal_fcff", terminal, valuation.terminal_fcff)
    check("terminal_value", tv, valuation.terminal_value)
    check("pv_terminal_value", pvtv, valuation.pv_terminal_value)
    check("enterprise_value", pv + pvtv, valuation.enterprise_value)
    check("equity_value",
          pv + pvtv + _d(val["equity_bridge"]["cash"]) - _d(val["equity_bridge"]["debt"]),
          valuation.equity_value)

    assert compared >= 180, f"expected a broad comparison, only made {compared}"
    # Exact decimal arithmetic on both sides: the engine should agree exactly,
    # not merely within tolerance.
    assert inexact == [], f"{len(inexact)} value(s) not exactly equal: {inexact[:5]}"
    assert worst <= REQUIRED_REL_TOL_PERCENT


def _random_case(rng: random.Random, scale: Decimal):
    """A balanced historical sheet at an arbitrary scale, plus random drivers."""
    periods = Periods(("2024A", "2025A"), ("2026E", "2027E", "2028E", "2029E", "2030E"))

    def r(lo, hi) -> Decimal:
        return Decimal(str(round(rng.uniform(lo, hi), 6)))

    rev = Decimal(1000) * scale
    cogs = rev * r(0.35, 0.75)
    opex = rev * r(0.10, 0.30)
    parts = dict(
        cash=rev * r(0.05, 0.40), accounts_receivable=rev * r(0.05, 0.30),
        inventory=cogs * r(0.05, 0.35), other_current_assets=rev * r(0.0, 0.05),
        ppe_net=rev * r(0.20, 1.50), other_noncurrent_assets=rev * r(0.0, 0.20),
        accounts_payable=cogs * r(0.05, 0.25),
        other_current_liabilities=rev * r(0.0, 0.08),
        debt=rev * r(0.0, 0.80), other_noncurrent_liabilities=rev * r(0.0, 0.10),
    )
    assets = sum((parts[k] for k in A.ASSET_ACCOUNTS), Decimal(0))
    liabs = sum((parts[k] for k in A.LIABILITY_ACCOUNTS), Decimal(0))
    parts["common_equity"] = (assets - liabs) * r(0.2, 0.8)
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
        add("revenue_growth", r(-0.25, 0.45), year)
        add("cogs_pct_revenue", r(0.30, 0.80), year)
    add("opex_pct_revenue", r(0.05, 0.30))
    add("dso", r(0.0, 180.0))
    add("inventory_days", r(0.0, 200.0))
    add("dpo", r(0.0, 150.0))
    add("other_current_assets_pct_revenue", r(0.0, 0.06))
    add("other_current_liabilities_pct_revenue", r(0.0, 0.10))
    add("depreciation_pct_beginning_ppe", r(0.02, 0.35))
    add("capex_pct_revenue", r(0.0, 0.25))
    add("interest_rate_on_debt", r(0.0, 0.18))
    add("sbc_pct_revenue", r(0.0, 0.06))
    add("dividend_payout_ratio", r(0.0, 0.7))
    add("share_repurchases", rev * r(0.0, 0.03))
    add("debt_repayment", parts["debt"] / Decimal(6))
    add("ppe_disposals", parts["ppe_net"] * r(0.0, 0.02))
    for name in ("other_operating", "other_investing", "other_financing"):
        add(name, rev * r(-0.02, 0.02))
    taxes = TaxSchedule("statutory", {y: r(0.0, 0.45) for y in periods.forecast})
    return periods, income, balance, cashflow, assumptions, taxes


@pytest.mark.parametrize("scale", ["0.001", "0.1", "1", "100", "10000", "1000000"])
def test_randomized_identity_sweep(scale):
    """The structural identities hold exactly, at every reporting scale.

    This is the test that a plug would fail. Cash is derived from the cash
    flow statement, so `Assets = Liabilities + Equity` only holds if every
    movement was routed consistently. On exact decimal arithmetic the
    identities are not merely close -- they are equal.
    """
    scale_d = Decimal(scale)
    rng = random.Random(hash(("sweep", scale)) & 0xFFFFFFFF)
    models = 0
    breaks = []
    worst = Decimal(0)

    def note(label, a, b):
        """Flag only differences larger than the division-rounding floor."""
        nonlocal worst
        r = _rel_percent(a, b)
        worst = max(worst, r)
        if r > CONTEXT_FLOOR_REL_PERCENT:
            breaks.append(f"{label}: {a} vs {b} (rel {r:.3e}%)")

    for trial in range(25):
        periods, income, balance, cashflow, assumptions, taxes = _random_case(rng, scale_d)
        forecast = build_forecast(periods, income, balance, cashflow, assumptions, taxes)
        fcff_years = build_fcff(forecast)
        models += 1

        prev_cash = balance.get(A.CASH, periods.last_actual)
        for year in periods.forecast:
            total_a = forecast.balance.get(A.TOTAL_ASSETS, year)
            total_l = forecast.balance.get(A.TOTAL_LIABILITIES, year)
            total_e = forecast.balance.get(A.TOTAL_EQUITY, year)
            note(f"A=L+E trial {trial} {year}", total_a, total_l + total_e)

            flows = sum((forecast.cashflow.get(k, year) for k in (A.CFO, A.CFI, A.CFF)), Decimal(0))
            note(f"cash trial {trial} {year}", prev_cash + flows, forecast.balance.get(A.CASH, year))
            prev_cash = forecast.balance.get(A.CASH, year)

            # These three involve no division, so they must be exactly equal.
            assert forecast.ppe.ending(year) == forecast.balance.get(A.PPE_NET, year)
            assert forecast.debt.ending(year) == forecast.balance.get(A.DEBT, year)
            assert forecast.retained_earnings.ending(year) == forecast.balance.get(A.RETAINED_EARNINGS, year)

        for i, year in enumerate(periods.forecast):
            terms = forecast.fcff_inputs(year)
            expected = (terms["ebit"] * (Decimal(1) - terms["tax_rate"]) + terms["d_and_a"]
                        - terms["capex"] - terms["change_in_nwc"])
            note(f"fcff trial {trial} {year}", expected, fcff_years[i].fcff)

        sources = {k: "sweep" for k in CostOfCapital.REQUIRED_SOURCES}
        coc = CostOfCapital("0.04", "1.0", "0.06", "0.05", "0.25",
                            Decimal(1000) * scale_d, Decimal(200) * scale_d, sources)
        result = run_dcf(fcff_years, coc, Decimal("0.02"),
                         EquityBridge(cash=Decimal(10) * scale_d, debt=Decimal(20) * scale_d), periods)
        rebuilt = sum((d.fcff * d.discount_factor for d in result.discounted), Decimal(0)) + result.pv_terminal_value
        note(f"ev trial {trial}", rebuilt, result.enterprise_value)

    assert models == 25
    assert breaks == [], f"at scale {scale}, {len(breaks)} identity break(s): {breaks[:5]}"
    # And the floor itself is astronomically inside the contract (4.11).
    assert worst < REQUIRED_REL_TOL_PERCENT, f"worst {worst:.3e}% at scale {scale}"


def test_no_float_survives_in_the_calculation_path(forecast, fcff_years, valuation):
    """Specification 1.15 / 4.4: every released value is an exact Decimal."""
    for ledger in (forecast.income, forecast.balance, forecast.cashflow):
        for year in forecast.periods.all_years:
            for account in ledger.accounts_present(year):
                value = ledger.get(account, year)
                assert isinstance(value, Decimal), (
                    f"{ledger.statement.value}.{account} {year} is "
                    f"{type(value).__name__}, not Decimal"
                )
    for item in fcff_years:
        assert isinstance(item.fcff, Decimal)
        assert isinstance(item.nopat, Decimal)
    for name in ("wacc", "enterprise_value", "equity_value", "terminal_value", "pv_terminal_value"):
        assert isinstance(getattr(valuation, name), Decimal), f"{name} is not Decimal"
    assert isinstance(valuation.implied_share_price, Decimal)


def test_tolerance_is_relative_not_absolute():
    """An absolute tolerance would be a different test at every scale."""
    from model.checks import DEFAULT_REL_TOL, Tolerance

    tol = Tolerance()
    assert DEFAULT_REL_TOL <= Decimal("1e-9")

    for magnitude in ("1", "1e3", "1e6", "1e9", "1e12"):
        m = Decimal(magnitude)
        assert tol.close(m, m * (Decimal(1) + DEFAULT_REL_TOL / Decimal(2)))
        assert not tol.close(m, m * (Decimal(1) + DEFAULT_REL_TOL * Decimal(10)))


def test_decimal_context_meets_specification_4_7_and_4_8():
    """Precision at least 28 digits, ROUND_HALF_EVEN, no NaN or Infinity."""
    import decimal

    from model.numeric import CALCULATION_CONTEXT, MINIMUM_PRECISION

    assert CALCULATION_CONTEXT.prec >= MINIMUM_PRECISION == 28
    assert CALCULATION_CONTEXT.rounding == decimal.ROUND_HALF_EVEN
    for trap in (decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow):
        assert CALCULATION_CONTEXT.traps[trap], f"{trap.__name__} must trap (17.27, 18.13)"
    # and the context is actually installed by importing the package
    assert decimal.getcontext().prec == CALCULATION_CONTEXT.prec
