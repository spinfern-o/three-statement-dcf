# three-statement-dcf

Builds an integrated three-statement financial model from a company filing and
values it with a DCF, following the 37-step workflow in
[`three_statement_model_to_dcf_step_by_step.txt`](three_statement_model_to_dcf_step_by_step.txt).

That file is the specification. This code exists to enforce it.

## The design premise

Almost every instruction in the workflow is negative:

> Do not invent missing historical years. · If the company does not report a
> line such as COGS or gross profit separately, do not invent it. · Do not use
> a plug simply to force the model to balance. · Never hide assumptions inside
> formulas. · Do not assume Depreciation = CapEx. · Do not automatically use
> book equity for market capitalization. · Do not silently ignore these items.

A spreadsheet cannot enforce any of that — the discipline lives in the
modeller's head, and a single `=0` typed into a gap looks identical to a
sourced figure six months later. So the organizing idea here is that **the
model refuses rather than defaults**. There is no code path that substitutes a
zero for a number nobody supplied.

Three commitments carry most of the weight:

1. **A figure cannot exist without provenance.** `Figure` requires a value, a
   year, a PDF page, and the company's own line-item wording (STEP 4). There is
   no constructor that skips it.

2. **Absent is a real state, distinct from zero.** The statements are *sparse*.
   `ledger.get(COGS, "2025A")` returns `None` when the company does not report
   COGS, and that `None` propagates into the checks instead of silently
   changing a subtotal. Every cell also records whether it was `reported`,
   `derived`, or `forecast`, which is what lets STEP 37 detect a hardcode
   pasted into a forecast year.

3. **Cash is not a plug.** Ending cash is produced by the cash flow statement
   (`beginning + CFO + CFI + CFF`) and *then* placed on the balance sheet. So
   `Assets = Liabilities + Equity` is a genuine test of whether every flow was
   modeled consistently — not an identity you arranged in advance. STEP 6's
   no-plug rule is satisfied structurally rather than by intention.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Run it against the fictional test fixture to see a complete model:

```bash
python3 run_model.py --inputs tests/fixtures
```

Run it against the blank templates to see what it does with missing data:

```bash
python3 run_model.py
```

```
MODEL HALTED
company.name is required by STEP 1 and is blank. Fill it in -- do not leave it
to a default.

The workflow stops rather than substituting a value. Fix the input and re-run.
```

That is the intended behaviour, and it is how you fill in the model: run it,
read what it says is missing, supply that, run it again. Exit codes are `0`
(all checks pass), `1` (a STEP 37 check failed), `2` (an input is missing), so
it drops into CI unmodified.

## Filling in your company

Four files in `inputs/`, corresponding to the workflow's four input phases:

| File | Steps | What goes in it |
|---|---|---|
| `company_profile.yaml` | 1–3, 12 | Company, period, currency, **units**, audited; the 12-section source map; historical and forecast years |
| `raw_historical.yaml` | 4–7 | Transcribed figures, each with its PDF page and reported line-item name |
| `assumptions.yaml` | 10–11, 13–19 | Every forecast driver, each with a basis and a source; resolved source conflicts; the tax basis |
| `valuation.yaml` | 25–36 | CAPM inputs, market values, terminal growth, the equity bridge, share count, sensitivity ranges |

All four ship blank. There is a test asserting they stay that way
(`test_shipped_templates_contain_no_company_data`) — a number committed into
`inputs/` would look like real data to whoever opens the file next.

Notes on the parts that most often go wrong:

- **Units** (STEP 1) are mandatory because getting them wrong is a 1000x error
  that looks entirely plausible.
- **Subtotals** are optional. Omit `gross_profit` and it is derived from
  revenue and COGS. Supply it *as well* and the model cross-checks the two and
  reports any disagreement rather than preferring one (STEP 9).
- **A line the company does not report** should be left out entirely, not set
  to `0`.
- **One driver per line per year.** Declaring both `capex_pct_revenue` and
  `capex_amount` for the same year is rejected — STEP 18 wants the methodology
  stated, not inferred.
- **Cost of capital inputs each require their own source string** (STEP 25–27).
  They are facts about the company's securities, not about its statements, and
  the model will not compute a WACC out of unsourced inputs.

## What comes out

One report, in workflow order: identification and source-map status →
assumptions grouped by basis → the three statements across all years →
supporting schedules → FCFF → cost of capital → discounting and value →
sensitivity table → the STEP 37 check panel.

```
STEP 37 -- FINAL MODEL CHECKS
==============================================================================
Historical balance sheet balances            PASS 2 year(s) balance
Forecast balance sheet balances              PASS 5 year(s) balance
Historical cash flow reconciliation          PASS 1 year(s) reconcile
Forecast cash flow reconciliation            PASS 5 year(s) reconcile
Net income linkage (IS -> CF)                PASS 6 year(s) tie
PP&E schedule linkage                        PASS 5 year(s) tie
Debt schedule linkage                        PASS 5 year(s) tie
Retained earnings linkage                    PASS 5 year(s) tie
Ending cash linkage                          PASS 5 year(s) reconcile
No unintended forecast hardcodes             PASS every forecast cell carries a driver
WACC > terminal growth rate                  PASS WACC 0.0983 > g 0.0250
FCFF matches three-statement forecast        PASS 5 year(s) tie to the model
------------------------------------------------------------------------------
12 PASS   0 FAIL   0 SKIP
```

### Tolerances are relative

The checks compare at a **relative** tolerance, defaulting to `1e-9`. An
absolute bound would be a different test at every scale: `0.01` against a
balance sheet of 1,020 is `1e-5`, but against one of 1,020,000,000 it is
`1e-11`. Since STEP 1 makes the reporting unit the modeller's choice, an
absolute bound would silently change strictness when a filing reports in
dollars rather than millions.

`1e-9` is a thousand times stricter than 0.0001%, and the randomized sweep puts
the worst drift actually observed at `3.4e-13`. Override with `--rel-tol`, and
`--abs-tol` sets a floor for accounts legitimately at zero. The panel prints
whichever tolerance it judged at.

`SKIP` is reported separately from `PASS` and deliberately so: a check that
could not run because its inputs were absent has not verified anything, and a
model that appears to pass because the data was never supplied is worse than
one that fails honestly.

## Layout

| Path | Steps | What it does |
|---|---|---|
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

See [`docs/WORKFLOW.md`](docs/WORKFLOW.md) for the step-by-step map into the code.

## Tests

```bash
python3 -m pytest tests/ -q
```

61 tests, no network and no API key. Four groups worth knowing about:

- `tests/test_refusals.py` — each of the workflow's "do not" rules, as an
  executable test. These matter most: the engine's value is that it *stops*,
  and a refusal that quietly stopped working would be invisible in the output
  of an otherwise passing model.
- `tests/test_model.py` — the arithmetic, plus two tests that deliberately
  corrupt a sound model to confirm the checks report `FAIL` and `SKIP` instead
  of papering over it.
- `tests/test_end_to_end.py` — the CLI and its exit codes, the no-company-data
  guard on `inputs/`, and a test asserting all 37 steps are referenced in code.
- `tests/test_precision.py` — numerical accuracy. `test_independent_recomputation`
  rebuilds all seven years from the raw YAML in plain arithmetic sharing no code
  with `model/`, and compares 192 values; it agrees exactly. The randomized
  sweep builds 150 further models across nine orders of magnitude of reporting
  scale — negative growth, zero debt, zero working-capital days — and checks
  that the structural identities survive all of them.

`tests/fixtures/` holds a small fictional manufacturer, generated from an
internally consistent set of balances so the fixture cannot drift out of
balance. It is labeled `FICTIONAL` in every file and is not derived from any
filing.

## Scope

The workflow starts at STEP 1 with a PDF already in hand, and so does this.
Parsing the PDF is not implemented — transcription is STEP 4's manual,
page-cited step, and automating it would remove exactly the provenance the rest
of the model depends on.

The forecast covers the accounts in `model/accounts.py`. A company needing
something outside that set — capitalized leases modeled separately, equity
method investments, multi-tranche debt with distinct rates — needs the account
added and its movement routed into the cash flow statement, or the balance
check will correctly fail.
