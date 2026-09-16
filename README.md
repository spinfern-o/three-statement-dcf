# three-statement-dcf

Builds an integrated three-statement financial model from a company filing and
values it with a DCF.

Two documents govern this repository, and they are different things:

| Document | What it is | Status |
|---|---|---|
| [`three_statement_model_to_dcf_step_by_step.txt`](three_statement_model_to_dcf_step_by_step.txt) | The 37-step modelling workflow | **Implemented** |
| [`docs/website-build-spec.md`](docs/website-build-spec.md) | The specification for a web application around it | **Not started** |

## Status, stated plainly

**What works today:** a Python calculation engine and a command-line runner. It
takes transcribed filing data as YAML, builds the historical and forecast
statements, runs a FCFF DCF, and reports the 37-step workflow's twelve PASS/FAIL
checks. All arithmetic is exact decimal. 69 tests pass on Python 3.10–3.13.

**What does not exist yet:** the website. No PDF upload, no extraction, no OCR,
no browser interface, no exports, no API, no database. `docs/website-build-spec.md`
describes all of it; none of it is built.

**The calculation path uses exact decimal arithmetic.** Specification rules
1.15 and 4.4 prohibit binary floating point here, so the engine runs on
`Decimal` under a declared 50-digit `ROUND_HALF_EVEN` context, and a `float`
is *refused* rather than converted — converting one preserves its error
instead of removing it. This was finding F-1 in the
[decision ledger](docs/decision-ledger.md), now resolved.

**37 of 37 Section 2 decisions are still OPEN.** Product name, hosting model,
authentication, currency, valuation date, and every market assumption are
unanswered. Specification Section 2 forbids inferring them, so work depending on
them has not begun.

## The design premise

Almost every instruction in the workflow is negative:

> Do not invent missing historical years. · If the company does not report a
> line such as COGS or gross profit separately, do not invent it. · Do not use
> a plug simply to force the model to balance. · Never hide assumptions inside
> formulas. · Do not assume Depreciation = CapEx. · Do not automatically use
> book equity for market capitalization. · Do not silently ignore these items.

A spreadsheet cannot enforce any of that — the discipline lives in the
modeller's head, and a single `=0` typed into a gap looks identical to a sourced
figure six months later. So the organizing idea is that **the model refuses
rather than defaults**. There is no code path that substitutes a zero for a
number nobody supplied.

Three commitments carry most of the weight:

1. **A figure cannot exist without provenance.** `Figure` requires a value, a
   year, a PDF page, and the company's own line-item wording (STEP 4).

2. **Absent is a real state, distinct from zero.** The statements are *sparse*.
   `ledger.get(COGS, "2025A")` returns `None` when the company does not report
   COGS, and that `None` propagates into the checks instead of silently changing
   a subtotal. Every cell also records whether it was `reported`, `derived`, or
   `forecast`, which is what lets STEP 37 detect a hardcode pasted into a
   forecast year.

3. **Cash is not a plug.** Ending cash is produced by the cash flow statement
   (`beginning + CFO + CFI + CFF`) and *then* placed on the balance sheet. So
   `Assets = Liabilities + Equity` is a genuine test of whether every flow was
   modeled consistently — not an identity you arranged in advance.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

See a complete worked model, using the fictional test fixture:

```bash
python3 run_model.py --inputs tests/fixtures
```

See what it does with missing data:

```bash
python3 run_model.py
```

```
MODEL HALTED
company.units is required by STEP 1 and is blank. Fill it in -- do not leave it
to a default.

The workflow stops rather than substituting a value. Fix the input and re-run.
```

That is the intended behaviour, and it is how you fill in the model: run it,
read what it says is missing, supply that, run it again. Exit codes are `0` (all
checks pass), `1` (a STEP 37 check failed), `2` (an input is missing), so it
drops into CI unmodified.

## Filling in your company

Four files in `inputs/`, corresponding to the workflow's four input phases:

| File | Steps | What goes in it |
|---|---|---|
| `company_profile.yaml` | 1–3, 12 | Company, period, currency, **units**, audited; the 12-section source map; historical and forecast years |
| `raw_historical.yaml` | 4–7 | Transcribed figures, each with its PDF page and reported line-item name |
| `assumptions.yaml` | 10–11, 13–19 | Every forecast driver, each with a basis and a source; resolved source conflicts; the tax basis |
| `valuation.yaml` | 25–36 | CAPM inputs, market values, terminal growth, the equity bridge, share count, sensitivity ranges |

All four ship blank, and a test asserts they stay that way
(`test_shipped_templates_contain_no_company_data`) — a number committed into
`inputs/` would look like real data to whoever opens the file next.

Notes on the parts that most often go wrong:

- **Units** (STEP 1) are mandatory because getting them wrong is a 1000× error
  that looks entirely plausible.
- **Subtotals** are optional. Omit `gross_profit` and it is derived from revenue
  and COGS. Supply it *as well* and the model cross-checks the two and reports
  any disagreement rather than preferring one (STEP 9).
- **A line the company does not report** should be left out entirely, not set
  to `0`.
- **One driver per line per year.** Declaring both `capex_pct_revenue` and
  `capex_amount` for the same year is rejected — STEP 18 wants the methodology
  stated, not inferred.
- **Cost of capital inputs each require their own source string** (STEP 25–27).

## What comes out

One report, in workflow order: identification and source-map status →
assumptions grouped by basis → the three statements across all years →
supporting schedules → FCFF → cost of capital → discounting and value →
sensitivity table → the STEP 37 check panel.

```
STEP 37 -- FINAL MODEL CHECKS
==============================================================================
judged at relative 1e-09

Historical balance sheet balances            PASS 2 year(s) balance
Forecast balance sheet balances              PASS 5 year(s) balance
Historical cash flow reconciliation          PASS 1 year(s) reconcile
Forecast cash flow reconciliation            PASS 15 subtotal(s) match their components
Net income linkage (IS -> CF)                PASS 6 year(s) tie
PP&E schedule linkage                        PASS 5 year(s) tie
Debt schedule linkage                        PASS 5 year(s) tie
Retained earnings linkage                    PASS 5 year(s) tie
Ending cash linkage                          PASS 5 year(s) reconcile
No unintended forecast hardcodes             PASS every forecast cell carries a driver
WACC > terminal growth rate                  PASS WACC 0.0983 > g 0.0250
FCFF matches three-statement forecast        PASS 5 year(s) rebuilt from the statements and tie
Reported subtotals reconcile (17.10)         PASS every reported subtotal agrees with its components
------------------------------------------------------------------------------
13 PASS   0 FAIL   0 SKIP
```

Thirteen, not twelve: STEP 37 lists twelve, and specification 17.10 requires a
reported-subtotal reconciliation that STEP 37 does not list. Every check tests
something different — two of the original twelve ran the same comparison with
identical arguments, so the panel reported twelve results from eleven tests.

`SKIP` is reported separately from `PASS` and deliberately so: a check that could
not run because its inputs were absent has not verified anything, and a model
that appears to pass because the data was never supplied is worse than one that
fails honestly.

### Tolerances are relative

The checks compare at a **relative** tolerance, defaulting to `1e-9`. An absolute
bound would be a different test at every scale: `0.01` against a balance sheet of
1,020 is `1e-5`, but against one of 1,020,000,000 it is `1e-11`. Since STEP 1
makes the reporting unit the modeller's choice, an absolute bound would silently
change strictness when a filing reports in dollars rather than millions.

Override with `--rel-tol`; `--abs-tol` sets a floor for accounts legitimately at
zero. The panel prints whichever tolerance it judged at.

### What "exact" does and does not mean

Decimal is exact for addition, subtraction, multiplication, and any division
that terminates. It is **not** exact for a division that repeats: `x / 365` is
rounded at 50 significant digits, so two mathematically equal sums built in a
different order can differ by one unit in the last place. Measured worst case
across the randomized sweep is `1E-46` absolute, `3.4e-50` relative.

The tests are written to that distinction: exact equality is asserted where no
division is involved (the PP&E, debt and retained-earnings schedules), and a
precision-derived bound where it is. The independent recomputation of the
fixture agrees with the engine **exactly**, across all 192 compared values.

## Layout

| Path | Steps | What it does |
|---|---|---|
| `model/numeric.py` | — | The Decimal context (50 digits, ROUND_HALF_EVEN); `D()` refuses floats |
| `model/yaml_exact.py` | — | YAML loader that keeps numeric scalars as written, so parsing cannot lose precision |
| `model/provenance.py` | 4 | `Figure` and `Source`; no figure without a page and a line item |
| `model/accounts.py` | 5–7 | The account vocabulary; sign conventions; which subtotals are derivable |
| `model/profile.py` | 1–3, 12 | Identification, source map, period validation |
| `model/statements.py` | 5–7, 9 | The sparse `Ledger`; derivation and reported-vs-derived cross-checks |
| `model/schedules.py` | 8, 16–19 | Roll-forwards that refuse to break their chain; working capital; tax |
| `model/assumptions.py` | 10–11 | The assumptions register; basis and source enforcement; conflicts |
| `model/forecast.py` | 12–22 | The projected three statements |
| `model/dcf.py` | 23–35 | FCFF, CAPM, WACC, terminal value, enterprise and equity value |
| `model/sensitivity.py` | 36 | The WACC × terminal-growth grid |
| `model/checks.py` | 9, 37 | The twelve PASS/FAIL checks |
| `model/loader.py` | — | YAML → model objects, failing with the step that requires each field |
| `model/report.py` | — | Text rendering; no calculation |
| `run_model.py` | — | CLI |

Documentation:

| Path | What it is |
|---|---|
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | Each of the 37 steps mapped to the code implementing it |
| [`docs/website-build-spec.md`](docs/website-build-spec.md) | The web application specification, verbatim |
| [`docs/decision-ledger.md`](docs/decision-ledger.md) | The 37 OPEN decisions, and findings F-1 to F-10 |

Specification Phase 2 contract documents. These are **definitions for the
website, not descriptions of the engine** — each one states plainly where the
engine already does the thing, where it does something different, and where it
does nothing at all:

| Path | What it is |
|---|---|
| [`docs/data-dictionary.md`](docs/data-dictionary.md) | Every entity and field in specification Section 9, cross-referenced against `model/accounts.py` |
| [`docs/formula-catalog.md`](docs/formula-catalog.md) | Every formula the engine implements, with a stable code, inputs, unit and rounding, plus the Section 16 formulas it does not |
| [`docs/source-policy.md`](docs/source-policy.md) | Section 10 ingestion and verification as a reviewable policy: what makes a fact verified, and the confidence/reason-code model |
| [`docs/validation-policy.md`](docs/validation-policy.md) | Checks 17.1–17.30 with codes and severities, mapped against the twelve the engine runs |
| [`docs/security-model.md`](docs/security-model.md) | Section 20, marked throughout for what is decidable now versus blocked on the hosting decision |

## Tests

```bash
python3 -m pytest tests/ -q
```

69 tests, no network and no API key. Four groups worth knowing about:

- `tests/test_refusals.py` — each of the workflow's "do not" rules, as an
  executable test. These matter most: the engine's value is that it *stops*, and
  a refusal that quietly stopped working would be invisible in the output of an
  otherwise passing model. Also holds the regressions for the post-port bugs,
  each verified to fail against the code before its fix.
- `tests/test_model.py` — the arithmetic, plus two tests that deliberately
  corrupt a sound model to confirm the checks report `FAIL` and `SKIP` instead of
  papering over it.
- `tests/test_end_to_end.py` — the CLI and its exit codes, the no-company-data
  guard on `inputs/`, and a test asserting all 37 steps are referenced in code.
- `tests/test_precision.py` — `test_independent_recomputation` rebuilds all seven
  years from the raw YAML with its own loader and its own Decimal construction,
  sharing no helper with `model/` as specification 4.15 requires, and compares
  192 values; all agree exactly. The randomized sweep builds 150 further models
  across nine orders of magnitude of reporting scale.

CI runs the suite on Python 3.10, 3.11, 3.12 and 3.13 for every pull request.
It is **not** a required status check, so it does not block a merge (finding F-3).

`tests/fixtures/` holds a small fictional manufacturer, generated from an
internally consistent set of balances so the fixture cannot drift out of balance.
It is labeled `FICTIONAL` in every file and is not derived from any filing.

## Scope

The workflow starts at STEP 1 with a PDF already in hand, and so does the current
engine. Parsing the PDF is not implemented — transcription is STEP 4's manual,
page-cited step. Automating it is what `docs/website-build-spec.md` Sections 10
and 11 specify, with mandatory human review of every extracted value.

The forecast covers the accounts in `model/accounts.py`. A company needing
something outside that set — capitalized leases modeled separately, equity method
investments, multi-tranche debt with distinct rates — needs the account added and
its movement routed into the cash flow statement, or the balance check will
correctly fail.

---

## Disclaimer

This model is an analytical tool, not investment, accounting, tax, or legal
advice. Historical information may contain extraction or classification errors
until reviewed. Forecasts and valuations depend on assumptions and are inherently
uncertain. Verify all source data, assumptions, and outputs before relying on
them.
