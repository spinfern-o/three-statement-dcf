# three-statement-dcf

Builds an integrated three-statement financial model from a company filing and
values it with a DCF.

Two documents govern this repository, and they are different things:

| Document | What it is | Status |
|---|---|---|
| [`three_statement_model_to_dcf_step_by_step.txt`](three_statement_model_to_dcf_step_by_step.txt) | The 37-step modelling workflow | **Implemented** |
| [`docs/website-build-spec.md`](docs/website-build-spec.md) | The specification for a web application around it | **Phases 2, 3 and 4 of 17** |

## Status, stated plainly

**What works today:** three programs, sharing one Decimal core.

1. **The calculation engine** (`run_model.py`). Takes verified filing data as
   YAML, builds the historical and forecast statements, runs a FCFF DCF, and
   reports the 37-step workflow's thirteen PASS/FAIL checks.
2. **PDF ingestion** (`ingest_pdf.py`) — specification Phase 3, items 26–38.
   Takes a filing PDF and produces located, parsed, scored facts: signature
   validation, SHA-256 custody, write-once storage, page classification,
   text and table extraction with page geometry, metadata detection in the
   UNCONFIRMED state, and a deterministic parser that refuses every ambiguous
   cell rather than guessing.
3. **The source-review room** (`review_server.py`) — specification Phase 4,
   items 39–49. A browser interface showing the PDF page beside the values
   read from it, with every extracted number boxed on the page it came from,
   and accept / correct / reject actions that each require a written reason
   and each write an audit entry.

343 tests pass on Python 3.10–3.13, including a keyboard-and-screen-reader
suite driven through a real browser. All arithmetic is exact decimal.

**What does not exist yet:** the mapping between the two halves, and most of
the website. No database, no exports, no dashboard, no forecast or valuation
screens. Nothing yet carries an extracted fact into the calculation engine —
that is the mapping stage, Phase 5.

**And no extracted fact is ever `VERIFIED`.** Verification is a seven-part
conjunction (`docs/source-policy.md` §9) whose seventh condition is a
human-approved mapping to a normalized line item. A fully reviewed document is
reviewed, not verified. The application evaluates all seven conditions
separately and reports zero verified facts on every page, because rule 1.14
says an unresolved requirement must never appear as PASS.

**The calculation path uses exact decimal arithmetic.** Specification rules
1.15 and 4.4 prohibit binary floating point here, so the engine runs on
`Decimal` under a declared 50-digit `ROUND_HALF_EVEN` context, and a `float`
is *refused* rather than converted — converting one preserves its error
instead of removing it. This was finding F-1 in the
[decision ledger](docs/decision-ledger.md), now resolved.

**All 37 Section 2 decisions are now answered.** Two by the owner directly
(private hosted; single user), the rest delegated to the implementing agent and
recorded with their reasoning in the [decision ledger](docs/decision-ledger.md).
The delegation covers *policy* — which method, which source, which convention.
It does not cover *values*: a risk-free rate, a beta, a fiscal year-end and a
share count are facts about a specific filing on a specific date, and the engine
still refuses to run without each one supplied and cited.

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

Ingest a PDF filing, using the fictional fixture:

```bash
python3 ingest_pdf.py apps/api/tests/fixtures/text_native_statements.pdf
```

It reports 50 facts, every one of them blocked, because every metadata field
starts UNCONFIRMED (10.11). Add `--confirm-metadata` to accept the detected
values and watch 47 of them clear — what remains is exactly the three cells
that print an em dash, an en dash and `N/A`, which rule 1.5 says a human must
resolve.

Review what it extracted, in a browser:

```bash
python3 ingest_pdf.py apps/api/tests/fixtures/text_native_statements.pdf --store var/sources
python3 review_server.py --store var/sources        # http://127.0.0.1:8000/
```

The page appears on the left with every extracted value boxed on it, and the
values on the right with what was printed beside what was parsed. Confirm the
document's metadata and 47 of the 50 facts clear at once; the three that
remain are the cells printing an em dash, an en dash and `N/A`, which rule 1.5
says a human must resolve. Every decision needs a typed reason, and the audit
log at the bottom of the page shows what was recorded.

It binds to localhost and **has no authentication** — decision 2.2.c requires
it and it is not built (finding F-15).

See what the engine does with missing data:

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
| `model/checks.py` | 9, 37 | The thirteen PASS/FAIL checks |
| `model/loader.py` | — | YAML → model objects, failing with the step that requires each field |
| `model/report.py` | — | Text rendering; no calculation |
| `run_model.py` | — | CLI |

PDF ingestion (specification Phase 3, items 26–38):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/extraction/signature.py` | 26 | PDF by signature, not filename; version, `%%EOF`, size limit |
| `apps/api/app/extraction/hashing.py` | 27 | SHA-256 on the bytes as received; duplicate detection |
| `apps/api/app/extraction/storage.py` | 28, 38 | Write-once content-addressed store; `O_EXCL`, re-hashed after writing |
| `apps/api/app/extraction/jobs.py` | 29 | The job state machine and its legal transitions |
| `apps/api/app/extraction/scan.py` | — | Structural scan (10.4): encryption, JavaScript, launch actions |
| `apps/api/app/extraction/pages.py` | 31 | Text-native / image-only / mixed; image-only **refuses** (2.3.c) |
| `apps/api/app/extraction/text_native.py` | 30, 33 | Tables, cells, captions, periods, facts |
| `apps/api/app/extraction/geometry.py` | 32 | Bounding boxes as decimal strings — the one float boundary |
| `apps/api/app/extraction/metadata.py` | 34 | The ten 10.10 fields, every one UNCONFIRMED |
| `apps/api/app/extraction/parsing.py` | 35 | Locale, sign, units, and rule 1.5 |
| `apps/api/app/extraction/reasons.py` | 36 | Blocking and advisory codes; the confidence model |
| `apps/api/app/extraction/records.py` | 33 | Section 9.3–9.5 and 9.14 entities; metadata confirmation |
| `apps/api/app/extraction/pipeline.py` | — | The ten steps in the order the policy requires |
| `apps/api/app/persistence/json_store.py` | 33 | Records to JSON; PostgreSQL (3.2.d) is Phase 15/17 |
| `ingest_pdf.py` | — | CLI |

Source review (specification Phase 4, items 39–49):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/review/actions.py` | 45, 46, 47 | Accept, correct, reject — each needs a reason, each writes an audit entry |
| `apps/api/app/review/progress.py` | 48 | Progress, the unresolved count, and §9's seven conditions evaluated one by one |
| `apps/api/app/api/routes.py` | 39, 44 | Navigation, metadata confirmation, and the decision endpoints |
| `apps/api/app/api/rendering.py` | 40 | Page images, rendered from the re-hashed stored bytes |
| `apps/api/app/api/bookmarks.py` | 41 | Statement bookmarks, labelled system-proposed |
| `apps/api/app/api/templates/` | 42, 43 | The split view, the box overlay, raw beside parsed |
| `packages/design-tokens/` | — | Section 6.4 tokens, with their contrast ratios tested |
| `review_server.py` | — | Launcher |

Documentation:

| Path | What it is |
|---|---|
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | Each of the 37 steps mapped to the code implementing it |
| [`docs/website-build-spec.md`](docs/website-build-spec.md) | The web application specification, verbatim |
| [`docs/decision-ledger.md`](docs/decision-ledger.md) | All 37 Section 2 decisions, and findings F-1 to F-13 |

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
python3 -m pytest -q
```

343 tests, no network and no API key. Two trees: `tests/` is the calculation
engine, `apps/api/tests/` is the website backend — ingestion and review.

Four groups in the engine's suite worth knowing about:

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

And in the ingestion suite:

- `apps/api/tests/unit/test_parsing.py` — 65 tests on the cell parser, most of
  them asserting that something did **not** become a zero. A blank, a dash, an
  em dash and `N/A` each produce `None` with a blocking code, because a zero
  substituted here would be invisible in every downstream statement.
- `apps/api/tests/integration/test_pipeline.py` — each refusal against a real
  PDF, the full extraction of a three-page filing, and item 38: the uploaded
  bytes are re-hashed after the whole pipeline and still match.
- `apps/api/tests/fixtures/` — eight generated PDFs, committed, hash-pinned,
  and rebuildable with `build_fixtures.py`. They cover a text-native filing
  with em dashes and footnote markers, a comma-decimal filing, a scan, a
  part-scanned filing, a mixed page, an encrypted file, a truncated file, and a
  GIF named `.pdf`.

And in the review suite:

- `apps/api/tests/integration/test_review.py` — the reviewer actions and their
  refusals. Accepting a fact whose cell held an em dash is refused, because
  rule 1.5 lets a dash become zero only when someone says so in words; that is
  a *correction*, with a different audit entry. A decision with no reason is
  refused in the domain, not only in the form.
- `apps/api/tests/integration/test_web.py` — the source room over HTTP,
  including the structural accessibility checks: landmarks, one `h1`, no
  skipped heading level, a label for every control, and no status conveyed by
  colour alone.
- `apps/api/tests/integration/test_accessibility.py` — specification 22.7,
  driven through Chromium: a keyboard-only walk from page load to a recorded
  decision, focus order, a visible focus ring, accessible names, no sideways
  scroll at 200% zoom, and reduced motion. It has its own CI job, which fails
  if every test in it skipped — a skip that never un-skips is not a test.
- `apps/api/tests/unit/test_design_tokens.py` — parses
  `packages/design-tokens/tokens.css` and computes every contrast ratio the
  application renders. A colour edited to something prettier that fails WCAG
  breaks the build.

CI runs the suite on Python 3.10, 3.11, 3.12 and 3.13 for every pull request.
It is **not** a required status check, so it does not block a merge (finding F-3).

`tests/fixtures/` holds a small fictional manufacturer, generated from an
internally consistent set of balances so the fixture cannot drift out of balance.
It is labeled `FICTIONAL` in every file and is not derived from any filing.

## Scope

The workflow starts at STEP 1 with a PDF already in hand. `ingest_pdf.py` now
reads that PDF, but the two halves are **not connected**: extraction produces
`UNVERIFIED` facts with company line-item wording, and the engine consumes
verified figures mapped to a canonical chart of accounts. The mapping between
them, with the human review specification Section 11 requires, is Phase 5.
Until then, STEP 4 transcription remains manual, and ingestion is a separate
tool that tells you what a filing says and what about it needs checking.

OCR is deliberately out of scope (decision 2.3.c). A scanned page refuses the
document rather than being read badly — see finding F-11, which proposes
narrowing that to scanned pages inside the mapped statement range.

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
