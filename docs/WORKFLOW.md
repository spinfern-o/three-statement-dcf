# Step-by-step map into the code

Every step of
[`three_statement_model_to_dcf_step_by_step.txt`](../three_statement_model_to_dcf_step_by_step.txt),
and where it is implemented. `tests/test_end_to_end.py` asserts that all 37
steps are referenced somewhere in `model/`.

## Extraction and standardization

| Step | Requirement | Where |
|---|---|---|
| 1 | Identify company, period, FYE, currency, units, audited | `profile.CompanyProfile` — every field mandatory, `units` is an enum |
| 2 | Record the exact PDF page for 12 sections | `profile.SourceMap`; `missing()` is printed in the report |
| 3 | Use only the historical years the company provides | `profile.Periods` — validates the `A` suffix, ordering, and that years are consecutive |
| 4 | Transcribe exactly; record figure, year, page, line item | `provenance.Figure` / `provenance.Source` — no constructor omits them |
| 5 | Standardize the income statement; do not invent absent lines | `statements.Ledger` is sparse; `accounts.INCOME_ACCOUNTS` are all optional |
| 6 | Standardize the balance sheet; `A = L + E`; no plug | `checks._balance_check` reports the delta and leaves it alone |
| 7 | Standardize the cash flow statement into CFO/CFI/CFF | `accounts.OPERATING_ITEMS` / `INVESTING_ITEMS` / `FINANCING_ITEMS` |
| 8 | Build supporting schedules before forecasting | `model/schedules.py` — `ppe_schedule`, `debt_schedule`, `retained_earnings_schedule` (forecast); `apps/api/app/schedules/` — the same roll-forwards over the periods a filing reports, reconciled to it (13.8) |
| 9 | Verify every historical linkage before forecasting | `Ledger.cross_check` (reported vs derived) and `checks.run_all_checks` |

## Assumptions and research

| Step | Requirement | Where |
|---|---|---|
| 10 | Every assumption visibly sourced, in three categories | `assumptions.Assumption` requires a `Basis` and non-empty `source`; `Assumptions.by_basis()` |
| 11 | On conflicting sources, record both and choose | `assumptions.Conflict` — `chosen` must equal one of the two recorded sources |
| 12 | Define the forecast period; `A` = Actual, `E` = Estimate | `profile.Periods`; forecast must start the year after the last actual |

## Forecast

| Step | Requirement | Where |
|---|---|---|
| 13 | Forecast revenue; segment-level where possible | `forecast.build_forecast` — `revenue_growth`, or `revenue_growth.<segment>` |
| 14 | Pick the right driver per line; not everything is a % of revenue | `forecast._pick_driver`; per-year assumptions are the mechanism |
| 15 | EBIT, kept separate from financing items | `forecast` sets `EBIT` before interest is touched |
| 16 | State the tax basis; NOPAT = EBIT × (1 − t) | `schedules.TaxSchedule`; `dcf.FCFFYear.nopat` |
| 17 | Forecast working capital account by account | `schedules.WorkingCapitalSchedule`, `days_to_balance`; NWC excludes cash and debt |
| 18 | Forecast depreciation and CapEx separately | Distinct drivers; `test_depreciation_is_not_capex` asserts they differ |
| 19 | Debt schedule; link interest to debt | `schedules.debt_schedule`; interest = rate × **beginning** debt |
| 20 | Complete the projected income statement | `forecast.build_forecast` |
| 21 | Complete the projected balance sheet; verify `A = L + E` | `forecast.build_forecast`; `checks._balance_check` |
| 22 | Complete the projected cash flow statement; ending cash ties | Ending cash is computed from CFO+CFI+CFF, then placed on the sheet |

## Valuation

| Step | Requirement | Where |
|---|---|---|
| 23 | Use FCFF for an enterprise-value DCF | `dcf.FCFFYear.fcff` |
| 24 | Calculate FCFF for every forecast year | `dcf.build_fcff` — reads back out of the built statements |
| 25 | Cost of equity via CAPM, externally sourced | `dcf.CostOfCapital.cost_of_equity`; sources are mandatory |
| 26 | After-tax cost of debt | `dcf.CostOfCapital.after_tax_cost_of_debt` |
| 27 | Capital structure at market values | `market_value_equity` / `market_value_debt`, both required and sourced |
| 28 | WACC | `dcf.CostOfCapital.wacc` |
| 29 | Discount each year; show factor and PV separately | `dcf.DiscountedYear`; `report.valuation_block` prints all four columns |
| 30 | Terminal-year cash flow | `dcf.run_dcf` — `terminal_fcff` |
| 31 | Terminal value; require WACC > g | `dcf.run_dcf` raises when violated |
| 32 | Discount the terminal value | `pv_terminal_value` |
| 33 | Enterprise value | `Valuation.enterprise_value` |
| 34 | Bridge to equity value; do not ignore non-operating items | `dcf.EquityBridge` — every line printed, zero or not |
| 35 | Implied value per share; state the share-count source | `Valuation.implied_share_price`; `None` when no share count is supplied |
| 36 | Sensitivity across WACC and terminal growth | `sensitivity.sensitivity_grid` — WACC ≤ g cells flagged, not dropped |
| 37 | Display PASS/FAIL checks | `checks.run_all_checks` — all twelve, in the order the step lists them |

## The twelve STEP 37 checks

In order, as `checks.run_all_checks` returns them:

1. Historical balance sheet balances
2. Forecast balance sheet balances
3. Historical cash flow reconciliation
4. Forecast cash flow reconciliation
5. Net income linkage (IS → CF)
6. PP&E schedule linkage
7. Debt schedule linkage
8. Retained earnings linkage
9. Ending cash linkage
10. No unintended forecast hardcodes
11. WACC > terminal growth rate
12. FCFF matches the three-statement forecast

Each returns `PASS`, `FAIL`, or `SKIP`. `SKIP` means the check could not run
because its inputs were absent — it is reported separately from `PASS` and
never counted as one.

Comparisons use a **relative** tolerance (`checks.Tolerance`, default `1e-9`),
not an absolute one, because STEP 1 makes the reporting unit the modeller's
choice and an absolute bound would change strictness with it. `tests/
test_precision.py` verifies the engine against an independent recomputation and
across nine orders of magnitude of scale.

## The complete model flow

As the workflow diagrams it, and as `run_model.py` executes it:

```
Company PDF
  -> Raw Historical Data          loader.load_historical
  -> Historical Income Statement  statements.Ledger (INCOME)
  -> Historical Balance Sheet     statements.Ledger (BALANCE)
  -> Historical Cash Flow         statements.Ledger (CASHFLOW)
  -> Supporting Schedules         schedules.py
  -> Forecast Assumptions         assumptions.py
  -> Forecast Income Statement    forecast.build_forecast
  -> Forecast Balance Sheet       forecast.build_forecast
  -> Forecast Cash Flow Statement forecast.build_forecast
  -> FCFF                         dcf.build_fcff
  -> WACC                         dcf.CostOfCapital
  -> Terminal Value               dcf.run_dcf
  -> Enterprise Value             dcf.run_dcf
  -> Equity Value                 dcf.EquityBridge
  -> Implied Share Price          dcf.Valuation.implied_share_price
```
