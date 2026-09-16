# Validation policy

Specification [Section 17](website-build-spec.md) defines a severity system and
lists thirty required checks. This file is the check registry: a stable code
for each, its severity, what it compares, and whether the engine in
[`model/`](../model) implements it today.

> **Updated 2026-09-16 (#7).** The panel is now **thirteen** checks, all
> distinct, and 17.10 is wired in. The duplicate this document reported is
> fixed. The aggregate tallies in §5 were counted before that change and are
> therefore understated by the 17.10 wiring; the individual rows below are
> current.

The short answer on coverage as first surveyed: **the engine's twelve-check panel covered ten of
the thirty specification checks, of which eight do what their name says.
Thirteen of the thirty have some mechanism behind them; ten have none.** The
per-check detail is in §4 and the accounting is in §5.

---

## 1. Severity

Section 17 defines four levels:

| Severity | Specification wording | Consequence |
|---|---|---|
| **CRITICAL** | "calculation/export blocked" | The calculation or export does not run. Not a result — a stop. |
| **ERROR** | "model cannot be released" | The model computes, but 19.18 release and Phase 13 item 137 must refuse it. |
| **WARNING** | "model may be released only with acknowledged rationale" | Release requires an explicit, recorded acknowledgement. |
| **INFO** | "informational" | No gate. |

Rule **1.14** binds all of them: *"Never allow an unresolved critical
validation error to appear as PASS."*

### Severity assignment is a proposal, not a transcription

**Section 17 supplies the four levels and the list of thirty checks. It does
not say which level each check carries.** The `Severity` column in §4 is
therefore marked in two ways:

- **Bold** — forced by a rule elsewhere in the specification, with the citation
  given. These are not judgement calls.
- Plain — **a proposal requiring the owner's confirmation.** Not confirmed,
  not inferred from anything authoritative.

Only four are forced:

| Check | Severity | Forced by |
|---|---|---|
| `VAL-017-024` WACC > g | **CRITICAL** | 16.16 "Block calculation when WACC <= g"; rule 1.18 |
| `VAL-017-026` diluted shares nonzero and sourced | **CRITICAL** | 16.20 "only when diluted shares are verified" — the per-share value must not be computed |
| `VAL-017-027` no NaN/Infinity/null in a released calculation | **CRITICAL** | 17.27's own wording, and the traps 4.4 requires |
| `VAL-017-028` benchmark meets Section 4 tolerance | **ERROR** | 4.20 "Never claim less than 0.0001% error until the benchmark suite passes" |

Everything else is open. Recorded as a new blocked item in
[`decision-ledger.md`](decision-ledger.md) — it is not a Section 2 decision, so
it does not belong in that file's Section 2 tables, but it does block Phase 13
item 137 ("prevent release when CRITICAL/ERROR checks remain"), which cannot be
built without knowing which checks are which.

### Statuses

Three, not two:

| Status | Meaning |
|---|---|
| `PASS` | The check ran and the condition held. |
| `FAIL` | The check ran and the condition did not hold. |
| `SKIP` | **The check could not run because its inputs were absent.** |

`SKIP` is the engine's contribution and it should survive into the website.
A check that silently passes because the data was never supplied is worse than
one that fails honestly, and collapsing SKIP into PASS is precisely the failure
rule 1.14 exists to prevent. [`model/checks.py`](../model/checks.py) reports
the three separately and `run_model.py` prints
`13 PASS   0 FAIL   0 SKIP` as three counts.

**A SKIP is never evidence of correctness.** For release gating, a SKIP on a
CRITICAL or ERROR check must be treated as unresolved.

---

## 2. Tolerance

Comparisons use `CHK-TOL-01` from
[`formula-catalog.md`](formula-catalog.md):

```
close(a, b)  ⟺  abs(a − b) ≤ max(rel × max(abs(a), abs(b)), abs_floor)
```

Defaults in the engine: `rel = 1e-9`, `abs_floor = 0`.

**Relative, not absolute**, and the reasoning is worth keeping: STEP 1 makes
the reporting unit the modeller's choice, so an absolute bound of `0.01` is a
`1e-5` test against a balance sheet of 1,020 and a `1e-11` test against one of
1,020,000,000. An absolute bound would silently change strictness when a filing
reports in dollars rather than millions.

This satisfies 4.13 ("use both absolute and relative tolerances so tiny values
do not produce misleading relative errors"), with the absolute term acting as a
floor for accounts legitimately at zero. It is **not** specification 4.10's
`relative_error_percent`, which is implemented in
[`model/numeric.py`](../model/numeric.py) as `relative_error()` and **called by
nothing**.

`abs_floor` defaults to zero deliberately: STEP 6 says a balance sheet that
does not balance is an error to find, not a difference to absorb. Raising it is
a visible act — the panel prints whichever tolerance it judged at.

**4.14 limits what any of this can prove.** If a PDF reports in millions with
no decimals, a difference smaller than one full currency unit cannot be
verified from that PDF. That is a *disclosure-precision limit*, and it must be
reported as such rather than as a calculation success.

---

## 3. The engine's thirteen checks

`checks.run_all_checks` returns these, in this order — the order STEP 37 lists
them:

| # | Name in the panel | Function | Maps to |
|---|---|---|---|
| 1 | Historical balance sheet balances | `_balance_check` | `VAL-017-008` |
| 2 | Forecast balance sheet balances | `_balance_check` | `VAL-017-016` |
| 3 | Historical cash flow reconciliation | `_cashflow_reconciliation` | `VAL-017-009` |
| 4 | Forecast cash flow reconciliation | `_cashflow_reconciliation` | `VAL-017-017` |
| 5 | Net income linkage (IS → CF) | `_net_income_linkage` | no 17.x equivalent; supports `VAL-017-010` |
| 6 | PP&E schedule linkage | `_schedule_linkage` | `VAL-017-011` |
| 7 | Debt schedule linkage | `_schedule_linkage` | `VAL-017-013` |
| 8 | Retained earnings linkage | `_schedule_linkage` | `VAL-017-015` (partially) |
| 9 | Ending cash linkage | `_cashflow_reconciliation` | `VAL-017-017` (**duplicate of #4**) |
| 10 | No unintended forecast hardcodes | `_no_forecast_hardcodes` | `VAL-017-020` |
| 11 | WACC > terminal growth rate | `_wacc_above_growth` | `VAL-017-024` |
| 12 | FCFF matches three-statement forecast | `_fcff_matches_forecast` | `VAL-017-022` |

Three observations a reviewer should have before reading §4, because they make
the coverage count smaller than twelve:

### 3a. Checks 4 and 9 are the same check

Both call `_cashflow_reconciliation(forecast.balance, forecast.cashflow,
periods, periods.forecast, tol)` with **identical arguments**; only the display
name differs. Both test `cash_(t−1) + CFO_t + CFI_t + CFF_t = cash_t` over the
forecast years.

The panel is faithful to STEP 37, which does list "Forecast cash flow
reconciliation" and "Ending cash linkage" as separate items — but they are one
identity, tested twice. Two PASSes here are one piece of evidence.

### 3b. Check 12 is a recomputation check, not a bridge check

`dcf.build_fcff` constructs each `FCFFYear` from
`ForecastResult.fcff_inputs(year)`. `_fcff_matches_forecast` then calls
**`ForecastResult.fcff_inputs(year)` again** and compares the results to the
`FCFFYear` fields.

It therefore verifies that nothing mutated between construction and checking.
It does **not** verify what its name and 17.22 suggest — that an independently
assembled DCF agrees with the three-statement bridge — because there is no
independent assembly to disagree with.

This is not a defect in the model's *architecture*: FCFF genuinely does come
from the forecast (`DCF-FCFF-01` in
[`formula-catalog.md`](formula-catalog.md)), which is what acceptance criterion
24.9 asks for, and that is a real and unusual property. It is a defect in the
*check's* evidentiary value. `tests/test_precision.py::test_independent_recomputation`
is the thing that actually provides independent verification, and it is a test,
not a runtime check.

### 3c. Check 8 covers retained earnings, not equity

17.15 asks that the **equity schedule** reconcile. The engine checks
`SCH-RE-01` against the `retained_earnings` balance-sheet account only. Share
issuance, repurchases, stock compensation and diluted shares — all of which
13.7 puts in the equity schedule — are forecast (`BS-CE-F`) but never
reconciled against anything.

---

## 4. The registry: checks 17.1 – 17.30

`Severity` in **bold** is forced by a cited rule; plain is a proposal awaiting
the owner. `Engine` is what [`model/`](../model) does today.

### Source and mapping (17.1–17.7)

| Code | Spec | What it compares | Severity | Engine |
|---|---|---|---|---|
| `VAL-017-001` | 17.1 | A `SourceDocument.immutable_hash` exists and matches a rehash of the stored bytes | ERROR | **No.** No document, no hash. `Source.document` is a free-text label |
| `VAL-017-002` | 17.2 | Every required metadata field is CONFIRMED, not UNCONFIRMED (10.11–10.13) | ERROR | **Different mechanism.** Nothing is detected, so nothing is UNCONFIRMED; `loader.load_profile` instead refuses a blank field, naming the STEP that requires it. Equivalent in effect for the fields it covers; no state machine |
| `VAL-017-003` | 17.3 | Every period resolves to one unambiguous basis and date range (1.7, 10.24) | ERROR | **No.** `Periods` validates the `A`/`E` suffix, ascending order, no duplicates, consecutiveness, and that the forecast starts the year after the last actual — which is strong *structural* validation, but there are no dates and no cadence, so ambiguity of basis cannot arise or be detected |
| `VAL-017-004` | 17.4 | `reporting_currency` and `displayed_scale` are confirmed for every document (1.9, 1.10) | ERROR | **Partial.** Both are required non-blank on `CompanyProfile`, and `units` must parse to the `Units` enum. But they are per-model, not per-document, and never normalized (4.6) |
| `VAL-017-005` | 17.5 | Every critical fact has `verification_status = VERIFIED` per [`source-policy.md`](source-policy.md) §9 | **CRITICAL** (1.14 — this is what "unresolved critical" refers to) | **No.** No verification status exists; every transcribed figure is treated as equally authoritative |
| `VAL-017-006` | 17.6 | Every `FactMapping` has `approved_by` set (11.10–11.11) | ERROR | **No.** No mapping entity; the input file fuses fact and mapping |
| `VAL-017-007` | 17.7 | No source fact contributes to a subtotal both directly and through a component (11.6) | ERROR | **No as a check**, but **prevented by construction**: `accounts.DERIVED` names each subtotal's components exactly once, and rule 1.6's error mode — a subtotal treated as an additional component — cannot be expressed in the account vocabulary |

### Historical statements and schedules (17.8–17.15)

| Code | Spec | What it compares | Severity | Engine |
|---|---|---|---|---|
| `VAL-017-008` | 17.8 | `total_assets = total_liabilities + total_equity`, every historical period | ERROR | **Yes** — check #1. SKIPs when any of the three totals is absent for every year. Reports the delta per year and appends "find the mapping error, do not plug it" (STEP 6) |
| `VAL-017-009` | 17.9 | `cash_(t−1) + CFO + CFI + CFF = cash_t`, historical | ERROR | **Yes** — check #3 |
| `VAL-017-010` | 17.10 | Every reported subtotal equals its mapped components (11.7, 12.4.i) | ERROR | **Implemented and wired in as of #7.** `Ledger.cross_check()` compares a *reported* subtotal against its derived value and returns `Discrepancy` objects without correcting them; it is now the panel's thirteenth check, "Reported subtotals reconcile (17.10)", and the discrepancy message carries 4.10's relative error. Before #7 it was called only by `tests/test_model.py`, so a discrepancy never reached the panel |
| `VAL-017-011` | 17.11 | `SCH-PPE-01` ending balance = `ppe_net` on the balance sheet | ERROR | **Yes** — check #6, forecast years only. Historical PP&E is not rolled forward |
| `VAL-017-012` | 17.12 | `SCH-INTANGIBLES` ending balance = intangibles on the balance sheet (13.3) | ERROR | **No, and not possible.** The chart of accounts has no `goodwill` or `intangibles` line (12.2.e) and there is no intangibles schedule |
| `VAL-017-013` | 17.13 | `SCH-DEBT-01` ending balance = `debt` on the balance sheet | ERROR | **Yes** — check #7, forecast years only |
| `VAL-017-014` | 17.14 | Tax schedule reconciles where data permits (13.6) | WARNING | **No, and not possible.** `TaxSchedule` is a rate table with a stated basis; there is no current/deferred split, no NOL usage, no valuation allowance. Nothing to reconcile |
| `VAL-017-015` | 17.15 | Equity schedule reconciles (13.7) | ERROR | **Partial** — check #8 reconciles `SCH-RE-01` against `retained_earnings` only. Share issuance, repurchases, SBC and diluted shares are unreconciled. See §3c |

### Forecast (17.16–17.21)

| Code | Spec | What it compares | Severity | Engine |
|---|---|---|---|---|
| `VAL-017-016` | 17.16 | `total_assets = total_liabilities + total_equity`, every forecast period | ERROR | **Yes** — check #2. Genuinely meaningful here: cash is produced by the cash flow statement and then placed on the sheet (`BS-CASH-F`), so this is a real test of flow consistency rather than an arranged identity |
| `VAL-017-017` | 17.17 | `cash_(t−1) + CFO + CFI + CFF = cash_t`, forecast | ERROR | **Yes** — checks #4 **and** #9, identically. See §3a |
| `VAL-017-018` | 17.18 | No required forecast assumption is missing (14.1) | **CRITICAL** (14.1: "No forecast may calculate until all required assumptions have a status") | **Different mechanism.** A missing driver raises `ProvenanceError` during `build_forecast` and the run halts with exit code 2 — a stop, not a check result. That is *stronger* than a check for blocking purposes and *weaker* for diagnostics: the reviewer sees the first missing driver, not all of them. 14.1's actual requirement is about *status*, which does not exist |
| `VAL-017-019` | 17.19 | No assumption with `status = Rejected` is used (14.2) | ERROR | **No.** Assumptions have no status; nothing can be Rejected |
| `VAL-017-020` | 17.20 | No hardcoded number inside a forecast formula (1.17) | ERROR | **Yes** — check #10, and it is a genuinely good implementation. Every `Cell` records its `origin`; `Ledger.hardcodes_in(forecast_years)` returns any forecast-year cell whose origin is `reported`. `Ledger.set_forecast` additionally refuses a blank `basis`, so a forecast cell cannot exist without a named driver |
| `VAL-017-021` | 17.21 | The formula graph contains no cycles (18.4–18.6) | ERROR | **No, and vacuously satisfied.** There is no formula graph; `build_forecast` is straight-line Python, which cannot cycle. Nothing to detect and nothing detecting it |

### DCF (17.22–17.26)

| Code | Spec | What it compares | Severity | Engine |
|---|---|---|---|---|
| `VAL-017-022` | 17.22 | DCF FCFF equals the three-statement FCFF bridge | ERROR | **Yes in form, weak in substance** — check #12. Recomputes from the same function it was built from. See §3b |
| `VAL-017-023` | 17.23 | Every WACC component has a source **and a date** | ERROR | **Half.** `CostOfCapital` refuses construction unless all six components have non-empty source strings (STEP 25–27) — that half is enforced. The strings are free text, never parsed, and **no date is separately required or validated**, so the "dated" half is unmet. **OPEN (2.5.b–f)** supply the sources and dates a real model would need |
| `VAL-017-024` | 17.24 | `WACC > terminal_growth` | **CRITICAL** (16.16, 1.18) | **Yes, twice.** `run_dcf` raises before computing any terminal value — the correct CRITICAL behaviour — and check #11 reports on a valuation that already passed that gate. `sensitivity_grid` returns `WACC ≤ g` cells with an explanatory note rather than omitting them |
| `VAL-017-025` | 17.25 | Every enterprise-to-equity adjustment is sourced (16.19) | ERROR | **No.** `EquityBridge` takes seven bare `Decimal`s with **no source fields at all**. Every line is printed, zero or not — which satisfies STEP 34's "do not silently ignore these items" — but nothing is sourced. The bridge also has **no lease line** (16.19), blocked on **OPEN (2.4.j)** |
| `VAL-017-026` | 17.26 | Diluted shares are nonzero and sourced before per-share value is shown | **CRITICAL** (16.20) | **Yes, as a hard block.** `run_dcf` raises if `diluted_shares ≤ 0`, and raises if shares are supplied without a non-empty `shares_source`. With no share count, `implied_share_price` is `None` and the report says "not calculated — no diluted share count supplied". Not reported as a check result |

### Release integrity (17.27–17.30)

| Code | Spec | What it compares | Severity | Engine |
|---|---|---|---|---|
| `VAL-017-027` | 17.27 | No NaN, Infinity or null in a released calculation | **CRITICAL** (17.27; 4.4) | **Partial, and well done as far as it goes.** The Decimal context traps `InvalidOperation`, `DivisionByZero` and `Overflow`, so a NaN or Infinity raises rather than propagating; `D()` rejects a non-finite `Decimal` outright; `tv_share_of_ev` returns `None` instead of dividing by zero. What is missing is the *scan*: nothing enumerates released values and asserts the property. And `report.valuation_block` formats `tv_share_of_ev` with `:.1%`, which raises `TypeError` when the guard returns `None` — the guard's only consumer does not honour it |
| `VAL-017-028` | 17.28 | Primary and independent benchmark results meet the Section 4 tolerance (4.15–4.16) | **ERROR** (4.20) | **Implemented as a test, not a check.** `tests/test_precision.py::test_independent_recomputation` rebuilds all seven years with its own loader and its own Decimal construction, sharing no helper with `model/` as 4.15 requires, and compares 192 values — all agreeing exactly. `test_randomized_identity_sweep` covers 150 further models across nine orders of magnitude. It runs in CI, not at model-release time, and produces no `ValidationResult`. **4.16 coverage gap: EBITDA** is named among the benchmarked outputs and the model has no EBITDA line — already recorded in [`decision-ledger.md`](decision-ledger.md) F-1 |
| `VAL-017-029` | 17.29 | Every displayed rounded value ties to its full-precision stored value (4.18, 4.19) | ERROR | **Partial as of #7.** `report._fmt` now rounds through `numeric.quantize_for_display`, the declared 4.9/4.18 boundary, so display rounding has a single place rather than scattered f-strings. Still **no check** asserts the tie, and 4.19's full-decimal tooltip has no CLI analogue |
| `VAL-017-030` | 17.30 | Every released output has source and formula lineage (24.12) | ERROR | **Partial.** Every `Cell` carries `origin` plus either a `Source` (page + the company's own line-item wording) or a prose `basis` naming its driver, so the lineage *data* exists for every cell. There is no lineage **query, export or check** — 7.10.d's dependency graph and 19.17's lineage endpoint do not exist |

---

## 5. Coverage summary

Every one of the thirty codes appears in exactly one bucket below, and the
buckets sum to 30.

| Bucket | Count | Codes |
|---|---|---|
| **A — result reaches a reviewer in the STEP 37 panel** | 10 | `008`, `009`, `011`, `013`, `015`, `016`, `017`, `020`, `022`, `024` |
| **B — enforced by a hard block or by construction; no check result** | 4 | `002`, `007`, `018`, `026` |
| **C — implemented but not surfaced at run time** | 2 | `010` (`Ledger.cross_check`, wired only into tests), `028` (`tests/test_precision.py`) |
| **D — partial: some of what the check requires** | 4 | `004`, `023`, `027`, `030` |
| **E — not implemented** | 10 | `001`, `003`, `005`, `006`, `012`, `014`, `019`, `021`, `025`, `029` |

Read carefully, because bucket A is not ten pieces of independent evidence:

- `017` is checked **twice** under two names (§3a), so the panel's twelve
  results cover **ten** distinct specification checks.
- `015` is **partial** within bucket A — retained earnings only, not the equity
  schedule (§3c).
- `022` is **weak** within bucket A — a recomputation, not an independent
  bridge comparison (§3b).
- `024` also appears as a hard block in `run_dcf`, which is the behaviour
  16.16 actually requires; the panel entry reports on a valuation that already
  passed that gate.

So: **the number of Section 17 checks whose result a reviewer sees, and which
do what their name says, is 8** — `008`, `009`, `011`, `013`, `016`, `017`,
`020`, `024`. Ten distinct codes are covered by the panel; thirteen have some
mechanism behind them across buckets A–C; seventeen have none or only part.
None of these numbers should be rounded up.

**Ten of the thirty cannot be implemented without work that is blocked or
absent:** `001`, `005`, `006` need the ingestion pipeline (Phase 3–5);
`012` needs an intangibles account and schedule; `014` needs a real tax
reconciliation rather than a rate table; `019` needs assumption statuses
(14.2); `025` needs sourced bridge lines and the lease decision
(**OPEN 2.4.j**); `003` needs period dates and a cadence (**OPEN 2.4.f**);
`021` and `029` need the formula engine (Phase 8).

## 6. Release gating

Phase 13 item 137 requires release be prevented when CRITICAL or ERROR checks
remain, and 19.18 makes release a locking operation. Stated as a rule:

1. **Any CRITICAL not PASS** — calculation and export are blocked (17's own
   definition). Rule 1.14: it may never be displayed as PASS.
2. **Any ERROR not PASS** — release is refused. The model may be viewed and
   computed.
3. **Any WARNING not PASS** — release requires a recorded acknowledgement
   naming the check, the person and the rationale.
4. **A `SKIP` on a CRITICAL or ERROR check counts as not PASS.** This is the
   rule that keeps §1's SKIP honest.
5. INFO never gates.

**This cannot be built yet**, because §1 establishes that only four of the
thirty severities are settled. Gating on a proposed severity assignment would
make a guess load-bearing.

`run_model.py` implements the nearest available thing: exit code `1` if any of
the thirteen checks FAILs, `2` if an input is missing, `0` otherwise. SKIP does
not affect the exit code — which is right for a CLI that prints the three
counts side by side, and would be wrong for a release gate.

---

## 7. What a `ValidationResult` must record

Per [`data-dictionary.md`](data-dictionary.md) §9.13, and worth restating as
policy because the engine gets it half right:

Every check result stores `check_code`, `severity`, `status`, `message`, and —
where the check is a comparison — `expected_value`, `actual_value`,
`difference` and `tolerance`, **as decimals, not as prose**.

The engine folds all four numbers into the `detail` string
(`"2027E: out by 0.0004"`). The numbers are visible to a human reading the
panel and invisible to anything else: a diagnostics page (7.10) cannot sort by
magnitude, threshold on difference, or chart drift across versions. 12.4's
requirement that an unresolved difference remain "an error with a visible
amount and source trail" is met for the amount and not for the trail.

---

## Related documents

- [`website-build-spec.md`](website-build-spec.md) — Section 17, authoritative
- [`formula-catalog.md`](formula-catalog.md) — the formulas these checks compare, and `CHK-TOL-01`
- [`data-dictionary.md`](data-dictionary.md) — §9.13 `ValidationResult`
- [`source-policy.md`](source-policy.md) — what checks 17.1–17.7 are testing compliance with
- [`decision-ledger.md`](decision-ledger.md) — the OPEN decisions and the severity-assignment gap
- [`WORKFLOW.md`](WORKFLOW.md) — the twelve STEP 37 checks as the engine orders them
