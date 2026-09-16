# Formula catalogue

Specification 18.1 requires formulas be stored as **versioned definitions**.
This file is that catalogue in document form: every formula the engine in
[`model/`](../model) implements today, extracted by reading the code, plus the
formulas specification [Section 16](website-build-spec.md) requires that the
engine does not implement.

It is the source for the `FormulaDefinition` rows described in
[`data-dictionary.md`](data-dictionary.md) §9.11. **Nothing in `model/` reads
these codes yet** — the engine's formulas are Python expressions, not data. The
codes are assigned here so they are stable when the formula engine (Phase 8) is
built.

## Code scheme

`AREA-NAME-NN`, where `AREA` is one of:

| Area | Meaning | Source |
|---|---|---|
| `IS` | Income statement | STEP 5, 12.1 |
| `BS` | Balance sheet | STEP 6, 12.2 |
| `CF` | Cash flow statement | STEP 7, 12.3 |
| `SCH` | Supporting schedule | STEP 8, 17–19, Section 13 |
| `DCF` | Valuation | STEP 23–35, Section 16 |
| `SENS` | Sensitivity | STEP 36, 16.23 |
| `CHK` | Comparison used by a check | Section 17 |
| `NUM` | Numeric-context helper | Section 4 |

All codes are at `version 1` — the engine has never versioned a formula, so
there is no prior version to preserve. `effective_date` for every entry is the
date the engine reached its current form: **2026-09-16** (commit `f08715f`).

## Units

`output_unit` uses the vocabulary proposed in
[`data-dictionary.md`](data-dictionary.md) §9.10:
`currency`, `ratio`, `days`, `shares`, `multiple`, `years`, `percent`.

**`currency` means "the model's single declared reporting unit".** The engine
performs no scale normalization — `Units.multiplier` in
[`model/profile.py`](../model/profile.py) exists and is never called — so
every `currency` output below is expressed in whatever unit the modeller
declared under STEP 1. See the 4.6 note in
[`data-dictionary.md`](data-dictionary.md) §9.8.

## Rounding

**Every formula in this catalogue has the same rounding policy, and it is
"none".**

Specification 4.9 forbids rounding intermediate values, and the engine obeys
it literally: no formula in `model/` rounds. The global context declared in
[`model/numeric.py`](../model/numeric.py) is 50 significant digits with
`ROUND_HALF_EVEN` (satisfying 4.7 and 4.8), installed on import in
[`model/__init__.py`](../model/__init__.py), and that context governs the
*representation* of every result — but no `quantize` call occurs anywhere in
the calculation path.

The `Rounding` column below therefore records **where a result is inexact**,
which is the useful distinction:

| Marking | Meaning |
|---|---|
| **exact** | Composed only of decimal addition, subtraction, multiplication and integer exponentiation. Exact under specification 4.12's second clause. |
| **ctx** | Contains a division that may not terminate. Rounded to 50 significant digits, `ROUND_HALF_EVEN`, by the context — not by the formula. |

Two functions in [`model/numeric.py`](../model/numeric.py) exist for display
and error measurement. Both were called by nothing until #7; they are now
wired in (`quantize_for_display` as `report._fmt`'s rounding boundary,
`relative_error` in the discrepancy message),
`run_model.py` or `tests/`:

- `quantize_for_display(value, places=1)` — the intended 4.9/4.18 display
  boundary. [`model/report.py`](../model/report.py) instead formats with
  Python f-strings (`f"{value:,.1f}"`), which rounds the `Decimal` under the
  active context and so gives the same answer, but does not route through the
  declared helper and is not covered by a test.
- `relative_error(actual, expected)` — specification 4.10 exactly. The checks
  in [`model/checks.py`](../model/checks.py) use `Tolerance.close` (`CHK-TOL-01`)
  instead, which is a different comparison.

---

## 1. Income statement

Two families exist and they are not the same code path. `IS-*-D` are the
**derivation** rules in `accounts.DERIVED`, applied by
`Ledger.fill_derivable()` to historical years and used by `Ledger.cross_check()`
to compare a reported subtotal against its components (STEP 9). `IS-*-F` are the
**forecast** expressions in [`model/forecast.py`](../model/forecast.py).

### Derivations — `accounts.DERIVED`, `statements.Ledger._try_derive`

| Code | Expression | Inputs | Unit | Rounding | Step / spec |
|---|---|---|---|---|---|
| `IS-GP-D` | `gross_profit = revenue − cogs` | `revenue`, `cogs` | currency | exact | STEP 5; 12.1.c |
| `IS-EBIT-D` | `ebit = gross_profit − operating_expenses` | `gross_profit`, `operating_expenses` | currency | exact | STEP 5; 12.1.g |
| `IS-PTI-D` | `pretax_income = ebit + other_income_expense − interest_expense` | `ebit`, `other_income_expense`, `interest_expense` | currency | exact | STEP 5; 12.1.j; 12.4.d |
| `IS-NI-D` | `net_income = pretax_income − taxes` | `pretax_income`, `taxes` | currency | exact | STEP 5; 12.1.l; 12.4.e |

**Derivation is refused when a non-residual input is absent.** This is the
engine's central commitment and it implements rules 1.2 and 1.5 directly: an
absent account is `None`, not zero, and `_try_derive` returns `None` rather
than a partial subtotal. The one exception is
`accounts.OPTIONAL_IN_DERIVATION` = {`other_income_expense`, `other_operating`,
`other_investing`, `other_financing`, `acquisitions`} — residual "and anything
else" lines, where a filing's silence means nothing else happened rather than
the value being unknown.

Sign convention, declared once in [`model/accounts.py`](../model/accounts.py)
rather than per formula: `cogs`, `operating_expenses`, `interest_expense` and
`taxes` are **stored positive and subtracted** (`POSITIVE_AND_SUBTRACTED`);
`capex`, `acquisitions`, `debt_repayment`, `share_repurchases` and `dividends`
are **stored negative** and summed into their subtotal (`EXPECTED_NEGATIVE`).

**Both tuples are documentation, not enforcement.** Neither is read anywhere in
`model/` — they record the convention the formulas above were written to, and
nothing validates a supplied value against them. A filing transcribed with
CapEx positive would flow into `CF-CFI-D` with the wrong sign and be caught, if
at all, only by the balance check.

### Forecast — `forecast.build_forecast`

| Code | Expression | Inputs | Unit | Rounding | Step / spec |
|---|---|---|---|---|---|
| `IS-REV-F1` | `revenue_t = revenue_(t−1) × (1 + revenue_growth_t)` | prior `revenue`, `revenue_growth` | currency | exact | STEP 13; 15.3.a |
| `IS-REV-F2` | `revenue_t = Σ_s [ segment_revenue_(s,t−1) × (1 + revenue_growth.s_t) ]` | prior segment revenues, `revenue_growth.<segment>` | currency | exact | STEP 13; 15.3.b |
| `IS-COGS-F1` | `cogs_t = revenue_t × cogs_pct_revenue_t` | `revenue`, `cogs_pct_revenue` | currency | exact | STEP 14; 15.5 |
| `IS-COGS-F2` | `cogs_t = cogs_amount_t` | `cogs_amount` | currency | exact | STEP 14; 15.5 |
| `IS-GP-F` | `gross_profit_t = revenue_t − cogs_t` | `revenue`, `cogs` | currency | exact | STEP 14 |
| `IS-OPEX-F1` | `operating_expenses_t = revenue_t × opex_pct_revenue_t` | `revenue`, `opex_pct_revenue` | currency | exact | STEP 14; 15.6 |
| `IS-OPEX-F2` | `operating_expenses_t = opex_amount_t` | `opex_amount` | currency | exact | STEP 14; 15.6 |
| `IS-EBIT-F` | `ebit_t = revenue_t − cogs_t − operating_expenses_t` | `revenue`, `cogs`, `operating_expenses` | currency | exact | STEP 15; 15.9 |
| `IS-INT-F` | `interest_expense_t = debt_(t−1) × interest_rate_on_debt_t` | beginning `debt`, `interest_rate_on_debt` | currency | exact | STEP 19; 15.13 |
| `IS-OIE-F` | `other_income_expense_t = other_income_expense_t` (assumption, default 0) | `other_income_expense` | currency | exact | 12.1.i |
| `IS-PTI-F` | `pretax_income_t = ebit_t − interest_expense_t + other_income_expense_t` | `ebit`, `interest_expense`, `other_income_expense` | currency | exact | STEP 20 |
| `IS-TAX-F` | `taxes_t = pretax_income_t × tax_rate_t` | `pretax_income`, `TaxSchedule.rate` | currency | exact | STEP 16; 15.14 |
| `IS-NI-F` | `net_income_t = pretax_income_t − taxes_t` | `pretax_income`, `taxes` | currency | exact | STEP 20; 15.15 |

Three notes where the code and the obvious reading differ:

- **`IS-EBIT-F` is not `IS-EBIT-D`.** The forecast computes EBIT from
  `revenue − cogs − opex` rather than `gross_profit − opex`. Arithmetically
  identical over exact decimals; textually a second definition of the same
  quantity, which is exactly what 18.1's versioned definitions are meant to
  prevent. Both are catalogued because both exist.
- **`IS-TAX-F` taxes pre-tax income; `DCF-NOPAT-01` taxes EBIT.** Both come
  from the workflow (STEP 16 gives `NOPAT = EBIT × (1 − t)`; STEP 20 gives net
  income after tax on pre-tax income) and both are correct in their place — the
  first is an unlevered valuation quantity, the second the actual tax line. The
  same `tax_rate_t` is used for both. A reviewer should know they are two
  applications of one rate, not one calculation.
- **`IS-INT-F` uses *beginning* debt**, per STEP 19's requirement that the
  interest method be stated. Specification 13.4 requires exactly this
  disclosure: "Interest must state whether it uses beginning, ending, or
  average debt." The engine's answer is **beginning**, hardcoded — there is no
  option, and no assumption selects it.

### Driver selection — `forecast._pick_driver`

Not a formula but a rule with teeth: for `cogs`, `opex` and `capex`, declaring
**both** the `*_pct_revenue` and the `*_amount` driver for the same line in the
same year raises `ProvenanceError`. Declaring **neither** also raises. This
implements STEP 14/18's "state the selected methodology explicitly" and 14.5's
"do not hide assumptions inside formulas" as a refusal rather than a precedence
rule.

---

## 2. Balance sheet

| Code | Expression | Inputs | Unit | Rounding | Step / spec |
|---|---|---|---|---|---|
| `BS-TA-D` | `total_assets = cash + accounts_receivable + inventory + other_current_assets + ppe_net + other_noncurrent_assets` | the six asset accounts | currency | exact | STEP 6; 12.2 |
| `BS-TL-D` | `total_liabilities = accounts_payable + other_current_liabilities + debt + other_noncurrent_liabilities` | the four liability accounts | currency | exact | STEP 6; 12.2 |
| `BS-TE-D` | `total_equity = common_equity + retained_earnings` | the two equity accounts | currency | exact | STEP 6; 12.2.l |
| `BS-CASH-F` | `cash_t = cash_(t−1) + CFO_t + CFI_t + CFF_t` | prior `cash`, `CFO`, `CFI`, `CFF` | currency | exact | STEP 22; 15.19 |
| `BS-AR-F` | `accounts_receivable_t = revenue_t × dso_t / 365` | `revenue`, `dso` | currency | **ctx** | STEP 17; 13.1.d |
| `BS-INV-F` | `inventory_t = cogs_t × inventory_days_t / 365` | `cogs`, `inventory_days` | currency | **ctx** | STEP 17; 13.1.d |
| `BS-AP-F` | `accounts_payable_t = cogs_t × dpo_t / 365` | `cogs`, `dpo` | currency | **ctx** | STEP 17; 13.1.d |
| `BS-OCA-F` | `other_current_assets_t = revenue_t × other_current_assets_pct_revenue_t` | `revenue`, driver | currency | exact | STEP 17 |
| `BS-OCL-F` | `other_current_liabilities_t = revenue_t × other_current_liabilities_pct_revenue_t` | `revenue`, driver | currency | exact | STEP 17 |
| `BS-PPE-F` | `ppe_net_t = SCH-PPE-01 ending balance` | PP&E schedule | currency | exact | STEP 18; 15.8 |
| `BS-DEBT-F` | `debt_t = SCH-DEBT-01 ending balance` | debt schedule | currency | exact | STEP 19; 15.12 |
| `BS-RE-F` | `retained_earnings_t = SCH-RE-01 ending balance` | RE schedule | currency | exact | STEP 21; 15.16 |
| `BS-CE-F` | `common_equity_t = common_equity_(t−1) + sbc_t − share_repurchases_t` | prior balance, `sbc`, `share_repurchases` | currency | exact | 13.7 |
| `BS-ONCA-F` | `other_noncurrent_assets_t = other_noncurrent_assets_(t−1) − other_investing_t` | prior balance, `other_investing` | currency | exact | STEP 21 |
| `BS-ONCL-F` | `other_noncurrent_liabilities_t = other_noncurrent_liabilities_(t−1) + other_operating_t + other_financing_t` | prior balance, `other_operating`, `other_financing` | currency | exact | STEP 21 |

**`BS-CASH-F` is the load-bearing one.** Cash is produced by the cash flow
statement and *then* placed on the balance sheet. Nothing solves for cash to
make the sheet balance, so `CHK-BAL-01` is a genuine test rather than an
identity arranged in advance. This is STEP 6's "Do not use a plug simply to
force the model to balance" honoured structurally.

**The day-count basis is 365**, declared once as
`forecast.DAYS_IN_YEAR = D(365)` rather than as three literals. Specification
13.1.e requires the day-count convention be explained; 365 is the engine's
answer and it is not configurable. `schedules.days_to_balance` accepts a
`days_in_year` parameter, but every call site passes `DAYS_IN_YEAR`.

**`BS-ONCA-F` / `BS-ONCL-F` are the reason the sheet closes.** The three
residual cash-flow lines each route to a balance-sheet account so every cash
movement has a matching balance movement. All three default to zero and must
be declared as assumptions to be non-zero.

---

## 3. Cash flow statement

| Code | Expression | Inputs | Unit | Rounding | Step / spec |
|---|---|---|---|---|---|
| `CF-CFO-D` | `CFO = net_income + depreciation_amortization + stock_based_compensation + change_in_nwc + other_operating` | the five operating items | currency | exact | STEP 7; 12.3.d |
| `CF-CFI-D` | `CFI = capex + acquisitions + other_investing` | the three investing items | currency | exact | STEP 7 |
| `CF-CFF-D` | `CFF = debt_issuance + debt_repayment + share_repurchases + dividends + other_financing` | the five financing items | currency | exact | STEP 7 |
| `CF-NWC-F` | `change_in_nwc (CF line) = −(NWC_t − NWC_(t−1))` | working-capital schedule | currency | exact | STEP 17; 12.3.c |
| `CF-CAPEX-F` | `capex (CF line) = −capex_t` | `capex` | currency | exact | STEP 18; 12.3.e |
| `CF-DA-F` | `depreciation_amortization (CF line) = depreciation_t` from `SCH-PPE-01` | PP&E schedule | currency | exact | STEP 22; 15.8 |
| `CF-SBC-F` | `stock_based_compensation_t = revenue_t × sbc_pct_revenue_t` | `revenue`, `sbc_pct_revenue` | currency | exact | 12.3.b |
| `CF-DIV-F1` | `dividends_t = dividend_payout_ratio_t × max(net_income_t, 0)` | `dividend_payout_ratio`, `net_income` | currency | exact | 12.3.j |
| `CF-DIV-F2` | `dividends_t = dividends_amount_t` (overrides `CF-DIV-F1` when declared) | `dividends_amount` | currency | exact | 12.3.j |

**Sign discipline.** `CF-CFO-D`, `CF-CFI-D` and `CF-CFF-D` are pure sums; the
sign lives in the stored value. `CF-NWC-F` and `CF-CAPEX-F` exist as separate
entries precisely because the sign flips between the schedule and the statement
line — an NWC build consumes cash, so the cash-flow line is the negative of the
change. `DCF-FCFF-01` then re-reads `abs(capex)` out of the statement, which is
why `FCFFYear.capex` is positive while the cash-flow line is negative.

**`CF-DIV-F1` / `CF-DIV-F2` is a precedence rule, not a refusal**, and it is
the one place the engine departs from `_pick_driver`'s stance: declaring both
`dividend_payout_ratio` and `dividends_amount` for the same year silently
prefers `dividends_amount`. For `cogs`, `opex` and `capex` the same situation
raises. Recorded as a finding in [`decision-ledger.md`](decision-ledger.md);
not changed here.

**`max(net_income, 0)`** in `CF-DIV-F1` means a loss year pays no ratio-based
dividend. That is a modelling choice with no workflow or specification
mandate behind it.

**Not implemented: `fx_effect_on_cash`** (12.3.l). The engine's cash
roll-forward has no FX term, and there is no such account.

---

## 4. Supporting schedules

| Code | Expression | Inputs | Unit | Rounding | Step / spec |
|---|---|---|---|---|---|
| `SCH-PPE-01` | `ending_ppe = beginning_ppe + capex − depreciation − disposals` | `capex`, `depreciation`, `ppe_disposals` | currency | exact | STEP 8/18; 13.2 |
| `SCH-DEP-01` | `depreciation_t = ppe_(t−1) × depreciation_pct_beginning_ppe_t` | beginning `ppe_net`, driver | currency | exact | STEP 18; 15.8 |
| `SCH-DEBT-01` | `ending_debt = beginning_debt + debt_issuance − debt_repayment` | `debt_issuance`, `debt_repayment` | currency | exact | STEP 8/19; 13.4 |
| `SCH-RE-01` | `ending_re = beginning_re + net_income − dividends` | `net_income`, `dividends` | currency | exact | STEP 8; 13.7 |
| `SCH-WC-OCA` | `operating_current_assets = accounts_receivable + inventory + other_current_assets` | three accounts | currency | exact | STEP 17; 13.1.a |
| `SCH-WC-OCL` | `operating_current_liabilities = accounts_payable + other_current_liabilities` | two accounts | currency | exact | STEP 17; 13.1.b |
| `SCH-WC-NWC` | `nwc = operating_current_assets − operating_current_liabilities` | the two above | currency | exact | STEP 17; 16.3 |
| `SCH-WC-DNWC` | `change_in_nwc_t = nwc_t − nwc_(t−1)` | `nwc` for two periods | currency | exact | STEP 17; 16.4 |
| `SCH-DAYS-01` | `balance = driver_amount × days / days_in_year` | driver, days, 365 | currency | **ctx** | STEP 17; 13.1.d/e |

`SCH-PPE-01`, `SCH-DEBT-01` and `SCH-RE-01` are all instances of one
`RollForward` class. It enforces chaining: adding a year whose beginning
balance does not equal the prior year's ending balance raises
`ProvenanceError` rather than accepting a break. The comparison is relative at
`1e-9` with a floor of 1 (`abs(prior.ending − beginning) > 1e-9 ×
max(|prior.ending|, |beginning|, 1)`).

`SCH-DEBT-01` additionally refuses a negative ending balance — repaying more
than is outstanding is an input error, not a negative liability.

**`SCH-DEP-01` and `capex` are structurally independent.** STEP 18 is emphatic
that depreciation must not be assumed equal to CapEx; the engine uses
different drivers on different bases (depreciation on beginning PP&E, CapEx on
revenue or as an amount), and `tests/test_model.py::test_depreciation_is_not_capex`
asserts they differ.

### `NWC` policy, stated explicitly

`accounts.OPERATING_CURRENT_ASSETS` = (`accounts_receivable`, `inventory`,
`other_current_assets`);
`accounts.OPERATING_CURRENT_LIABILITIES` = (`accounts_payable`,
`other_current_liabilities`);
`accounts.EXCLUDED_FROM_NWC` = (`cash`, `debt`).

This satisfies 13.1.c ("Exclude cash, debt, and non-operating accounts unless
policy says otherwise"). It is a **fixed** policy — 16.3 says "using the
approved account policy", and no approval mechanism exists.

### Tax schedule

`schedules.TaxSchedule` requires `basis ∈ {statutory, historical_effective,
normalized_effective}` (STEP 16) and one rate per forecast year, each validated
to `[0, 1)`. It is a **rate table with a stated basis**, not a tax
reconciliation: there is no current/deferred split, no NOL usage and no
valuation allowance, all of which 13.6 requires "when relevant and available".
Check 17.14 therefore has nothing to reconcile.

---

## 5. DCF

| Code | Expression | Inputs | Unit | Rounding | Step / spec |
|---|---|---|---|---|---|
| `DCF-NOPAT-01` | `NOPAT_t = ebit_t × (1 − tax_rate_t)` | `ebit`, `tax_rate` | currency | exact | STEP 16/23; **16.2** |
| `DCF-FCFF-01` | `FCFF_t = NOPAT_t + d_and_a_t − capex_t − change_in_nwc_t` | `DCF-NOPAT-01`, `d_and_a`, `capex`, `change_in_nwc` | currency | exact | STEP 23/24; **16.5** |
| `DCF-KE-01` | `cost_of_equity = risk_free_rate + beta × equity_risk_premium` | three sourced inputs | ratio | exact | STEP 25; **16.6** |
| `DCF-KDAT-01` | `after_tax_cost_of_debt = pretax_cost_of_debt × (1 − tax_rate)` | `pretax_cost_of_debt`, `tax_rate` | ratio | exact | STEP 26; **16.7** |
| `DCF-WE-01` | `weight_equity = market_value_equity / (market_value_debt + market_value_equity)` | two market values | ratio | **ctx** | STEP 27; 16.8 |
| `DCF-WD-01` | `weight_debt = market_value_debt / (market_value_debt + market_value_equity)` | two market values | ratio | **ctx** | STEP 27; 16.8 |
| `DCF-WACC-01` | `WACC = weight_equity × cost_of_equity + weight_debt × after_tax_cost_of_debt` | the four above | ratio | **ctx** | STEP 28; **16.9** |
| `DCF-T-01` | `t = index of year in the forecast tuple + 1` | `Periods.forecast` | years | exact | STEP 29; **see 16.12 below** |
| `DCF-DF-01` | `discount_factor_t = 1 / (1 + WACC)^t`, integer `t` | `WACC`, `DCF-T-01` | ratio | **ctx** | STEP 29; **16.13** |
| `DCF-PV-01` | `PV_FCFF_t = FCFF_t × discount_factor_t` | `DCF-FCFF-01`, `DCF-DF-01` | currency | exact | STEP 29; **16.14** |
| `DCF-TFCFF-01` | `terminal_fcff = FCFF_N × (1 + terminal_growth)` | final-year FCFF, `g` | currency | exact | STEP 30; **16.15** |
| `DCF-TV-01` | `terminal_value = terminal_fcff / (WACC − terminal_growth)` | `DCF-TFCFF-01`, `WACC`, `g` | currency | **ctx** | STEP 31; **16.15** |
| `DCF-PVTV-01` | `pv_terminal_value = terminal_value / (1 + WACC)^N` | `DCF-TV-01`, `WACC`, `N` | currency | **ctx** | STEP 32; **16.17** |
| `DCF-EV-01` | `enterprise_value = Σ_t PV_FCFF_t + pv_terminal_value` | `DCF-PV-01`, `DCF-PVTV-01` | currency | exact | STEP 33; **16.18** |
| `DCF-EQ-01` | `equity_value = EV + cash − debt + non_operating_investments − minority_interest − preferred_stock − pension_obligations − other_claims` | `DCF-EV-01`, seven bridge inputs | currency | exact | STEP 34; **16.19** |
| `DCF-PS-01` | `implied_share_price = equity_value / diluted_shares` | `DCF-EQ-01`, `diluted_shares` | currency | **ctx** | STEP 35; **16.20** |
| `DCF-TVSH-01` | `tv_share_of_ev = pv_terminal_value / enterprise_value` | `DCF-PVTV-01`, `DCF-EV-01` | ratio | **ctx** | **16.21** |

### Guards the engine enforces

- **`WACC > g`** — `run_dcf` raises `ProvenanceError` before any terminal
  value is computed. This is STEP 31 and specification **16.16** ("Block
  calculation when WACC <= g") and rule 1.18. It is the only place in the
  engine where a specification rule is implemented as a hard block rather than
  as a reported check, and `CHK-WACCG-01` reports on a valuation that already
  passed it.
- **`diluted_shares > 0` and a non-empty `shares_source`** — enforced in
  `run_dcf` (STEP 35, 16.20, check 17.26). Supplying shares without a source
  raises; supplying neither yields `implied_share_price = None` and the report
  says so.
- **Every cost-of-capital input requires a source string** — `CostOfCapital`
  refuses construction unless all six of `risk_free_rate`, `beta`,
  `equity_risk_premium`, `pretax_cost_of_debt`, `market_value_equity`,
  `market_value_debt` have non-empty source text (STEP 25–27). The strings are
  **not parsed** and dates are **not separately required**, so check 17.23
  ("WACC components are dated and sourced") is half-met: sourced yes, dated no.
- **`market_value_equity > 0`** — STEP 27's "do not automatically use book
  equity for market capitalization" is not machine-checkable, so the engine
  checks what it can.
- **`tv_share_of_ev` returns `None` rather than dividing by zero** when
  enterprise value is zero (17.27). `report.valuation_block` then formats it
  with `f"{...:.1%}"`, which raises `TypeError` on `None` — the guard exists
  and its only consumer does not honour it. Recorded as a finding; narrow, and
  not fixed here.

### `DCF-FCFF-01` reads back out of the statements

`ForecastResult.fcff_inputs(year)` pulls `ebit` from the forecast income
statement, `d_and_a` and `capex` from the forecast cash flow statement, the tax
rate from the `TaxSchedule`, and `change_in_nwc` from the working-capital
schedule. FCFF is not assembled from loose inputs. That is what specification
**16.5** and acceptance criterion **24.9** ("FCFF comes from the forecast
model") ask for, and it is genuinely met.

`CHK-FCFF-01` then *re-reads the same function* — see
[`validation-policy.md`](validation-policy.md) for why that check is weaker
than its name suggests.

### Section 16 formulas the engine does not implement

| Spec | Requirement | Status |
|---|---|---|
| **16.12** | "Calculate the exact time fraction from valuation date to cash-flow date" | **Not implemented.** `DCF-T-01` is an ordinal index, not a duration. There is no valuation date (9.8) and no period dates (9.9) anywhere in the engine. 2.5.a is answered (valuation date = release date), so what remains is implementation: adding dates to `Periods`. |
| **16.11** | Select and document year-end or mid-year discounting | **Year-end only.** `numeric.power()` requires an `int` exponent and raises on anything else, so a half-period exponent cannot be evaluated by the current helper. 2.4.h: **year-end**, which is what this implements. Mid-year would need a fractional exponent the helper deliberately refuses. |
| **16.10** | "If preferred stock or another capital class exists, add it explicitly" to WACC | **Not implemented.** `DCF-WACC-01` has two terms, E and D. Preferred stock appears only as an equity-bridge subtraction in `DCF-EQ-01`, which is a different treatment. |
| **16.19** | "− Lease liabilities if policy treats them as debt" | **No lease line in the bridge.** `EquityBridge` has seven fields and none is leases. 2.4.j: leases **are** debt in the bridge when disclosed, so this is a real gap to implement rather than an open question. |
| **16.24** | Exit-multiple terminal value, kept separate and sourced | **Not implemented.** Gordon Growth only. 2.4.i: **Gordon Growth only**, so this is out of scope by decision rather than unanswered. |
| **16.25** | Never average terminal methods without explicit approval | **Vacuously satisfied** — there is only one method to average. |
| **16.22** | Warn when terminal value exceeds a configurable review threshold | **Not implemented.** `DCF-TVSH-01` computes and prints the share, but there is no threshold and no warning. |
| **16.5 (2nd ¶)** | Other operating non-cash/investment items in the FCFF bridge "only when explicitly defined, sourced, and shown" | **Not implemented.** `DCF-FCFF-01` has exactly four terms. Notably **stock-based compensation is added back in `CF-CFO-D` but does not appear in FCFF** — a real modelling position, and one that 2.4.k settles: SBC is expensed in EBIT, added back as non-cash in CFO, and credited to equity — it is deliberately not removed again in FCFF. |
| **16.3** | Operating NWC "using the approved account policy" | **Fixed policy, no approval mechanism.** See `SCH-WC-NWC`. |

---

## 6. Sensitivity

| Code | Expression | Inputs | Unit | Rounding | Step / spec |
|---|---|---|---|---|---|
| `SENS-GRID-01` | For each (`WACC`, `g`) pair, re-run `DCF-EV-01`/`DCF-EQ-01`/`DCF-PS-01` with the same FCFF series | FCFF series, WACC list, g list | currency | **ctx** | STEP 36; **16.23** |
| `SENS-KE-01` | `implied_ke = (target_wacc − weight_debt × after_tax_cost_of_debt) / weight_equity` | target WACC, base weights, `kd` | ratio | **ctx** | STEP 36 |
| `SENS-ERP-01` | `implied_erp = (implied_ke − risk_free_rate) / beta` | `SENS-KE-01`, `rf`, `beta` | ratio | **ctx** | STEP 36 |

The grid varies the discount rate **as a rate**, which is what STEP 36 asks
for. `sensitivity._shift_wacc` achieves a target WACC by solving backwards
through `DCF-WACC-01` and `DCF-KE-01` for an equity risk premium, then labels
the substitution in `CostOfCapital.sources`. Cells where `WACC ≤ g` are
returned with a note rather than omitted, so an empty corner explains itself.

**`SENS-ERP-01` has a silent failure mode when `beta = 0`.** The code reads
`implied_erp = (implied_ke − rf) / beta if beta else ZERO`. With `beta = 0`,
cost of equity equals the risk-free rate regardless of the ERP, so the target
WACC cannot be reached — and the cell is nonetheless labelled with the target
WACC it did not achieve. Verified by direct construction: a base with
`beta = 0` and `wacc = 0.0392` shifted to a target of `0.12` returns a
`CostOfCapital` whose `wacc` is still `0.0392`. `beta = 0` is an unusual
input, but the failure is silent, which is the class of thing this repository
exists to prevent. Recorded as a finding in
[`decision-ledger.md`](decision-ledger.md); not fixed here.

---

## 7. Comparisons used by checks

| Code | Expression | Unit | Rounding | Spec |
|---|---|---|---|---|
| `CHK-TOL-01` | `close(a, b) ⟺ abs(a − b) ≤ max(rel × max(abs(a), abs(b)), abs_floor)` | ratio | **ctx** | 4.13 (both absolute and relative tolerances) |
| `NUM-RELERR-01` | `relative_error_percent = abs(actual − expected) / abs(expected) × 100` | percent | **ctx** | **4.10** — implemented in `numeric.relative_error`; wired into `Discrepancy.__str__` in #7 |
| `NUM-POW-01` | `power(base, n) = base ** n`, integer `n` only | ratio | **ctx** | 4.13 |
| `NUM-QUANT-01` | `quantize_for_display(v, places)` — `ROUND_HALF_EVEN` | as input | half-even | 4.9, 4.18 — `report._fmt` rounds through it as of #7 |

`CHK-TOL-01` defaults to `rel = 1e-9`, `abs_floor = 0`
([`model/checks.py`](../model/checks.py)). `Ledger.cross_check` uses a looser
default of `rel = 1e-6`, deliberately: both sides of that comparison are
transcribed from a filing that rounds its own figures.

**Tolerances are relative, not absolute**, because STEP 1 makes the reporting
unit the modeller's choice and an absolute bound would silently change
strictness with a units change. The reasoning is set out at length in
[`README.md`](../README.md) and in `checks.py` itself.

`NUM-RELERR-01` is specification 4.10 verbatim, and its absence from the check
path means **no runtime code measures relative error in the specification's
terms**. `tests/test_precision.py` does the equivalent comparison
independently; check 17.28 is discussed in
[`validation-policy.md`](validation-policy.md).

---

## 8. Decimal context — the policy all of the above runs under

Required by Phase 2 item 22 ("Define Decimal context and rounding policy") and
declared in [`model/numeric.py`](../model/numeric.py):

| Setting | Value | Specification |
|---|---|---|
| Precision | **50** significant digits | 4.7 requires ≥ 28 |
| Rounding | **`ROUND_HALF_EVEN`** | 4.8 names it as the default |
| Traps | `InvalidOperation`, `DivisionByZero`, `Overflow` | 17.27 (no NaN/Infinity in a released calculation); 18.13 (reject division by zero with a visible diagnostic) |
| Boundary | `D()` **refuses** `float`, `bool` and `None` | 1.15, 4.4; 4.2 (decimal strings at the boundary) |
| YAML | numeric scalars preserved as written | 4.2 — `model/yaml_exact.py`; `yaml.safe_load` would have resolved them to floats during parsing |
| Installation | context set on import in `model/__init__.py` | Prevents mixed-precision arithmetic between an explicit 50-digit block and Python's 28-digit default |

**Where exactness ends.** Decimal is exact for addition, subtraction,
multiplication and integer exponentiation. It is not exact for a division that
repeats — every row marked **ctx** above. `x / 365` and `x / 6` are rounded at
50 significant digits, so two mathematically equal sums built in a different
order can differ by one unit in the last place. The measured worst case across
the repository's randomized sweep is **1E-46 absolute, 3.4e-50 relative**.

`tests/test_precision.py` is written to that distinction: exact equality is
asserted where no division is involved (`SCH-PPE-01`, `SCH-DEBT-01`,
`SCH-RE-01`), and a precision-derived bound where it is.

---

## 9. What 18.x still requires that no formula here provides

Section 18 is the formula *engine*, not the formula *list*, and the engine in
`model/` is a procedural Python program rather than a graph evaluator. Stated
plainly:

| Spec | Requirement | Status in `model/` |
|---|---|---|
| 18.1 | Store formulas as versioned definitions | **No.** Formulas are code. This file is the first written catalogue. |
| 18.2–18.3 | Approved operators only; never evaluate user code | **Vacuously satisfied** — there is no expression evaluator, so there is nothing to sandbox. |
| 18.4 | Parse formulas into a dependency graph | **No.** Dependencies are Python statement order. |
| 18.5 | Topologically order calculations | **By hand.** `build_forecast` executes in a fixed sequence that happens to be a valid topological order. `Ledger.fill_derivable()` iterates to a fixed point, which is a partial substitute for the historical side. |
| 18.6 | Detect cycles before evaluation | **No, and none can occur** — straight-line code cannot cycle. Check 17.21 has nothing to detect. |
| 18.7 | Hash inputs and formula version | **No.** No fingerprints. |
| 18.8 | Recalculate only affected descendants | **No.** The whole model is rebuilt every run. |
| 18.9 | Preserve the prior calculated model version | **No.** Nothing is persisted. |
| 18.10 | Human-readable formula for every calculated cell | **Yes** — `Cell.basis`, as prose, on every derived and forecast cell. |
| 18.11 | Exact input values used for every calculation | **Partial.** `Cell.basis` embeds the numbers in its text (e.g. `"revenue_growth = 0.0800 on 2025A revenue 1,200.0"`), but they are not separately addressable. |
| 18.12 | Unit checking | **No.** Assumptions carry no unit (see [`data-dictionary.md`](data-dictionary.md) §9.10); units are a naming convention. |
| 18.13 | Reject division by zero with a visible diagnostic | **Yes** — via the context trap, plus explicit guards on `days_in_year`, `total_capital`, `diluted_shares` and `tv_share_of_ev`. |
| 18.14 | Reject missing inputs; do not coerce to zero | **Yes, thoroughly.** `Ledger.require`, `Assumptions.get` and `provenance.require` all raise. This is the engine's strongest property. |
| 18.15–18.16 | Server-side authoritative calculation | **Not implemented** — there is no server yet. No longer blocked: 2.2.a is answered *private hosted* (2026-09-16), so a server exists in the target design and the calculation must run on it. |

---

## Related documents

- [`website-build-spec.md`](website-build-spec.md) — Sections 16 and 18, authoritative
- [`data-dictionary.md`](data-dictionary.md) — §9.11 `FormulaDefinition`
- [`validation-policy.md`](validation-policy.md) — the checks these formulas feed
- [`decision-ledger.md`](decision-ledger.md) — the OPEN decisions cited above
- [`WORKFLOW.md`](WORKFLOW.md) — the 37 steps mapped to the code
- [`three_statement_model_to_dcf_step_by_step.txt`](../three_statement_model_to_dcf_step_by_step.txt) — the workflow the engine implements
