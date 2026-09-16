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

---

# Website expansion specification

THREE-STATEMENT MODEL + DCF WEBSITE
COMPLETE, NON-INFERENTIAL BUILD SPECIFICATION
Version: 1.0
Prepared: 2026-09-16

======================================================================
0. PURPOSE OF THIS FILE
======================================================================

This file is the authoritative implementation brief for building a website that:

1. Accepts a company-provided financial PDF.
2. Extracts and preserves the PDF's historical financial data.
3. Requires review of every extracted value instead of silently guessing.
4. Builds an integrated historical and forecast three-statement model.
5. Builds a Free Cash Flow to the Firm (FCFF) discounted cash flow valuation.
6. Displays the entire process, every source, every formula, every assumption,
   every warning, and every model check in a web interface.
7. Uses an original interface inspired by the visual principles of findash.ai,
   without copying FinDash's name, logo, text, source code, or proprietary assets.
8. Produces reproducible calculations and exports.
9. Meets the numerical-accuracy contract defined in Section 4.

This file does NOT promise that predicted future cash flows will be accurate to
0.0001%. No truthful model can guarantee that. Future results depend on uncertain
business and market assumptions. The 0.0001% requirement applies only to
deterministic arithmetic compared with an independently calculated benchmark,
after the source data and assumptions have been verified.

The attached file named "Homework 2 (1)(1).png" appears unrelated to this
financial-model website and MUST NOT be used as a financial source. If the user
intended it to be used, stop and ask what role it should have.

======================================================================
1. NON-NEGOTIABLE RULES
======================================================================

1.1 Never invent a financial value.
1.2 Never silently fill a missing PDF value with zero.
1.3 Never silently map an ambiguous PDF line item to a model line.
1.4 Never silently choose a currency, unit, fiscal year-end, tax rate, WACC,
    terminal growth rate, forecast period, or valuation date.
1.5 Never treat a blank, dash, em dash, "N/A," or missing table cell as zero
    unless the source explicitly defines it as zero or a reviewer confirms it.
1.6 Never treat a subtotal as an additional component of that subtotal.
1.7 Never mix annual, quarterly, year-to-date, and trailing-twelve-month data.
1.8 Never mix reported and adjusted/non-GAAP figures without a labeled bridge.
1.9 Never mix thousands, millions, and full currency units.
1.10 Never mix currencies without an explicit dated exchange-rate source.
1.11 Never mix consolidated and segment-level values.
1.12 Never overwrite an uploaded source document.
1.13 Never alter a verified historical value without creating an audit entry.
1.14 Never allow an unresolved critical validation error to appear as PASS.
1.15 Never use floating-point JavaScript Number arithmetic for authoritative
     financial calculations.
1.16 Never round intermediate calculations merely to match the displayed value.
1.17 Never use a hardcoded forecast value inside a formula cell.
1.18 Never allow WACC to be less than or equal to terminal growth in a Gordon
     Growth terminal-value calculation.
1.19 Never describe a scenario forecast as a fact or guarantee.
1.20 Never claim the website is investment advice.

======================================================================
2. REQUIRED DECISIONS BEFORE IMPLEMENTATION
======================================================================

Create a file named docs/decision-ledger.md. Record each answer, date, person,
and reason. Do not begin the affected work until each required answer exists.

2.1 Product identity
    a. Product name.
    b. Logo or text-only wordmark.
    c. Company/owner name for footer and exports.

2.2 Use and access
    a. Local-only application, private hosted application, or public website.
    b. Single user or multi-user.
    c. Whether authentication is required.
    d. If multi-user, required roles: owner, analyst, reviewer, read-only.

2.3 Source documents
    a. One PDF per company or multiple PDFs.
    b. Annual reports only, or annual and quarterly reports.
    c. Text-native PDFs only, or scanned PDFs too.
    d. Whether public filings/XBRL may be used to cross-check the supplied PDF.
    e. Whether external market data may be retrieved.

2.4 Model policy
    a. Reporting currency.
    b. Display unit: units, thousands, or millions.
    c. Fiscal year-end.
    d. Number of historical periods.
    e. Number of forecast periods.
    f. Annual, quarterly, monthly, or mixed model cadence.
    g. FCFF or FCFE. Default recommendation: FCFF, but require confirmation.
    h. Year-end or mid-year discounting convention.
    i. Gordon Growth, exit multiple, or both terminal-value methods.
    j. Whether leases are treated as debt in the valuation bridge.
    k. Treatment of stock-based compensation.
    l. Treatment of minority interest, pensions, associates, and investments.
    m. Treatment of tax-loss carryforwards and deferred taxes.

2.5 Market assumptions
    a. Valuation date.
    b. Risk-free rate source and observation date.
    c. Beta source, type, and observation date.
    d. Equity risk premium source and observation date.
    e. Pre-tax cost of debt source and observation date.
    f. Target or current capital structure.
    g. Terminal growth rate source and justification.
    h. Diluted shares source and measurement date.

2.6 Export and retention
    a. Required exports: XLSX, CSV, PDF, JSON, or all.
    b. Required retention period for uploaded PDFs and extracted data.
    c. Whether an administrator may permanently delete data.
    d. Required backup and restore policy.

If an answer is unavailable, display it as OPEN in the decision ledger. Build only
parts that do not depend on it. Do not replace OPEN with an inferred answer.

======================================================================
3. RECOMMENDED TECHNICAL BASELINE
======================================================================

This is an explicit recommendation, not a hidden assumption. If the repository
already has a supported stack, preserve it and document the deviation.

3.1 Front end
    a. Next.js with TypeScript.
    b. React Server Components only where they do not complicate financial state.
    c. Tailwind CSS or CSS Modules with design tokens.
    d. Recharts, ECharts, or another accessible chart library.
    e. TanStack Table for large statement tables.
    f. Zod for runtime schema validation.

3.2 Back end
    a. Python FastAPI service for PDF extraction and model orchestration.
    b. Pydantic schemas for every request, response, and stored model object.
    c. Python Decimal for all authoritative financial calculations.
    d. PostgreSQL for persistent hosted use; SQLite is acceptable only for a
       documented single-user local prototype.
    e. Object storage for immutable PDFs and generated exports.
    f. A job queue for OCR and extraction jobs that may exceed request timeouts.

3.3 PDF and table processing
    a. PyMuPDF or pdfplumber for text and geometry.
    b. Camelot/Tabula only when their extraction mode is validated for the file.
    c. OCRmyPDF plus Tesseract, or a specifically approved OCR provider, for scans.
    d. Preserve page coordinates and raw text for source traceability.
    e. Do not use an LLM result as an authoritative number without deterministic
       validation and human approval.

3.4 Testing
    a. Pytest for calculation and extraction tests.
    b. Vitest/Jest for front-end unit tests.
    c. Playwright for end-to-end browser tests.
    d. Axe for automated accessibility checks.
    e. Golden-file fixtures for known PDFs and expected normalized outputs.

3.5 Infrastructure
    a. Docker Compose for reproducible local development.
    b. Separate development, test, staging, and production environments.
    c. CI must run lint, type checks, unit tests, integration tests, end-to-end
       smoke tests, dependency audit, and a production build.

======================================================================
4. NUMERICAL ACCURACY CONTRACT
======================================================================

4.1 Define three different kinds of accuracy.

    SOURCE ACCURACY:
    A value exactly matches the verified source document, including sign, period,
    currency, unit, scope, and restatement status.

    COMPUTATIONAL ACCURACY:
    A deterministic formula matches an independently computed benchmark.

    FORECAST ACCURACY:
    A future prediction matches the eventual real-world result. This cannot be
    guaranteed and is NOT covered by the 0.0001% contract.

4.2 Store monetary inputs as decimal strings at API boundaries.
4.3 Convert decimal strings to arbitrary-precision Decimal values before math.
4.4 Prohibit binary floating point in the authoritative calculation engine.
4.5 Store each value with currency, scale, source unit, period, and sign metadata.
4.6 Normalize all values to one base unit for calculation, while retaining the
    source value and source unit for exact reconstruction.
4.7 Use at least 28 significant decimal digits in the calculation context.
4.8 Use ROUND_HALF_EVEN unless the company's reporting policy requires another
    rounding rule. Record any different policy.
4.9 Do not round intermediate values. Round only for display or explicitly defined
    report outputs.
4.10 Define relative arithmetic error for a nonzero expected value as:

     relative_error_percent =
       abs(actual - expected) / abs(expected) * 100

4.11 The calculation passes the requested tolerance only when:

     relative_error_percent < 0.0001%

4.12 Relative error is undefined when expected equals zero. For zero benchmarks,
     require absolute error <= 0.00000001 in the normalized base currency unit,
     or exact equality when the operation is composed only of exact decimal
     addition, subtraction, multiplication, and integer exponentiation.
4.13 Use both absolute and relative tolerances in tests so tiny values do not
     produce misleading relative errors.
4.14 Reconcile statements to the precision available in the source document.
     Example: if a PDF reports in millions with no decimals, a difference smaller
     than one full currency unit cannot be verified from that PDF. Mark it as a
     disclosure-precision limit, not a calculation success.
4.15 Build an independent benchmark implementation for core formulas. The primary
     engine and benchmark must not call the same helper function.
4.16 Compare at least these outputs against the independent benchmark:
     revenue, gross profit, EBITDA, EBIT, EBT, taxes, net income, total assets,
     total liabilities, equity, CFO, CFI, CFF, ending cash, NOPAT, change in NWC,
     FCFF, discount factors, terminal value, enterprise value, equity value, and
     implied value per share.
4.17 Test extreme values, negatives, zeros, very small decimals, very large values,
     mixed source scales, and repeating-decimal rates.
4.18 Display calculation precision separately from display precision.
4.19 Label every displayed rounded value with a tooltip showing its full stored
     decimal and formula.
4.20 Never claim "less than 0.0001% error" until the benchmark suite passes and
     the test report identifies the exact dataset and formulas tested.

======================================================================
5. REPOSITORY AND FILE STRUCTURE
======================================================================

Use the existing repository named three-statement-dcf if present. Do not create a
second repository. Inspect and preserve existing user files before editing.

Required structure, adjusted only when the existing stack requires it:

three-statement-dcf/
  README.md
  LICENSE                         # only if the owner selects a license
  .gitignore
  .editorconfig
  .env.example                    # names only; never real secrets
  docker-compose.yml
  docs/
    decision-ledger.md
    data-dictionary.md
    formula-catalog.md
    source-policy.md
    validation-policy.md
    security-model.md
    deployment.md
    user-guide.md
  apps/
    web/
      app/
      components/
      features/
      lib/
      public/
      styles/
      tests/
    api/
      app/
        api/
        core/
        extraction/
        mapping/
        models/
        calculations/
        validation/
        exports/
        persistence/
      tests/
        unit/
        integration/
        fixtures/
        golden/
  packages/
    schemas/
    design-tokens/
  scripts/
    dev
    test
    verify
  .github/workflows/ci.yml

Each directory must contain only files used by the application or documentation.
Do not add placeholder packages that are never imported.

======================================================================
6. ORIGINAL DESIGN SYSTEM INSPIRED BY FINDASH.AI
======================================================================

The implementation may adopt broad visual principles observed on findash.ai as of
2026-09-16, but it must remain an original product. Do not copy their DOM, CSS,
marketing text, logo, illustrations, videos, or exact dashboard arrangement.

6.1 Visual direction
    a. Warm off-white application background.
    b. Dark navy/charcoal primary text.
    c. Emerald green for primary actions and positive statuses.
    d. Royal blue for important financial totals.
    e. Muted gray-blue for supporting copy.
    f. Soft red for destructive actions and failed checks.
    g. Amber for unresolved or review-required states.
    h. White cards with subtle neutral borders and restrained shadows.
    i. Generous whitespace and a dense-but-readable financial table mode.

6.2 Typography
    a. Use an open-source editorial serif for page titles and major financial
       figures. Recommended candidates: Source Serif 4 or Libre Baskerville.
    b. Use an open-source sans serif for navigation, tables, controls, labels,
       and body copy. Recommended candidate: Inter.
    c. Use tabular numerals for all financial values.
    d. Right-align numeric table cells and decimal points where practical.
    e. Never rely on color alone to convey state.

6.3 Layout
    a. Desktop: persistent left navigation plus top context bar.
    b. Tablet: collapsible left navigation.
    c. Mobile: bottom or drawer navigation, single-column cards, sticky actions.
    d. Dashboard: responsive 12-column grid of movable but deterministic widgets.
    e. Statement pages: frozen first column, frozen period headers, horizontal
       scrolling, visible units, and accessible row hierarchy.
    f. Source-review pages: split view with PDF page on the left and extracted
       value/formula panel on the right.

6.4 Core tokens
    Define tokens rather than scattering literal styles. The exact color values
    must pass contrast testing and be recorded in packages/design-tokens.

    --color-canvas
    --color-surface
    --color-surface-muted
    --color-text-primary
    --color-text-secondary
    --color-accent-primary
    --color-accent-financial
    --color-success
    --color-warning
    --color-danger
    --color-border
    --radius-card
    --radius-control
    --shadow-card
    --space-1 through --space-12

6.5 Interaction rules
    a. Primary action is visually obvious but not oversized.
    b. Every mutation provides pending, success, and failure feedback.
    c. Unsaved assumption edits remain visibly marked.
    d. Keyboard focus is always visible.
    e. Tables support keyboard navigation.
    f. Charts have text summaries and downloadable data.
    g. Tooltips are optional aids, never the only location of critical content.
    h. Loading states use skeletons; financial values must not flash fake zeros.
    i. Empty states explain what source or decision is missing.

6.6 Accessibility
    a. Target WCAG 2.2 AA.
    b. Minimum 4.5:1 contrast for normal text.
    c. Logical heading order.
    d. Semantic landmarks and table markup.
    e. Labels for every form control.
    f. Error summary and field-level errors.
    g. Reduced-motion support.
    h. Screen-reader text for chart trends and status icons.

======================================================================
7. REQUIRED WEBSITE NAVIGATION
======================================================================

7.1 Portfolio/Home
    a. List companies and models.
    b. Show status: Draft, Extracting, Needs Review, Validated, Forecast Ready,
       Valuation Ready, or Archived.
    c. Show last source date, valuation date, model owner, and unresolved errors.

7.2 New Model
    a. Upload PDF.
    b. Enter only metadata known by the user.
    c. Display detected metadata separately from confirmed metadata.
    d. Require confirmation before model creation continues.

7.3 Source Room
    a. Original PDF viewer.
    b. Page index and statement/footnote bookmarks.
    c. OCR/text layer toggle.
    d. Extracted tables.
    e. Source citations and bounding boxes.
    f. Duplicate-source and restatement warnings.

7.4 Mapping Review
    a. Raw reported line item.
    b. Proposed normalized line item.
    c. Period, currency, units, sign, scope, page, confidence.
    d. Accept, edit, split, combine, or reject.
    e. Reviewer note required for any manual change.

7.5 Historical Statements
    a. Income statement.
    b. Balance sheet.
    c. Cash flow statement.
    d. Statement of equity when available.
    e. Reported view and normalized view.
    f. Common-size and growth views.

7.6 Supporting Schedules
    a. Working capital.
    b. PP&E and depreciation.
    c. Intangibles and amortization.
    d. Debt and interest.
    e. Leases.
    f. Taxes.
    g. Equity and diluted shares.
    h. Other company-specific schedules explicitly selected by the reviewer.

7.7 Assumptions
    a. Historical driver analysis.
    b. Forecast assumptions by scenario.
    c. Source, date, owner, rationale, and confidence for every assumption.
    d. Base, upside, downside, and custom scenarios.
    e. No hidden assumptions inside formulas.

7.8 Forecast Statements
    a. Forecast income statement.
    b. Forecast balance sheet.
    c. Forecast cash flow statement.
    d. Actual versus estimate labels.
    e. Scenario comparison.

7.9 DCF Valuation
    a. FCFF bridge.
    b. WACC build.
    c. Discounted cash flows.
    d. Terminal value.
    e. Enterprise-to-equity bridge.
    f. Implied value per share, if applicable.
    g. WACC/growth sensitivity table.
    h. Optional exit-multiple sensitivity when explicitly enabled.

7.10 Diagnostics
    a. All validation checks.
    b. Errors, warnings, and informational notices.
    c. Formula dependency graph.
    d. Source lineage.
    e. Change log.
    f. Benchmark-accuracy report.

7.11 Reports and Exports
    a. Full model workbook.
    b. PDF valuation report.
    c. Normalized data CSV/JSON.
    d. Source-to-output audit report.
    e. Calculation-test report.

7.12 Settings
    a. Model policies.
    b. Display units and precision.
    c. Permissions.
    d. Retention and deletion controls.
    e. Data-source configuration.

======================================================================
8. DASHBOARD WIDGETS
======================================================================

Show only values that have a clear period and scenario label.

8.1 Enterprise value.
8.2 Equity value.
8.3 Implied share value, when a valid diluted share count exists.
8.4 Revenue and revenue growth.
8.5 Gross margin, only if gross profit can be validly calculated.
8.6 EBITDA and EBITDA margin, only when the model defines EBITDA.
8.7 EBIT margin.
8.8 Net income and net margin.
8.9 Operating cash flow.
8.10 FCFF.
8.11 Net debt.
8.12 WACC and terminal growth.
8.13 Historical-to-forecast revenue/EBITDA/FCFF chart.
8.14 Three-statement validation status.
8.15 Source verification progress.
8.16 DCF sensitivity preview.
8.17 Key forecast assumptions.
8.18 Latest changes and reviewer notes.

Each widget must show:
    a. Metric name.
    b. Value and unit.
    c. Period/scenario.
    d. Formula or direct-source indicator.
    e. Source/lineage link.
    f. Validation status.
    g. Comparison basis for any percentage change.

======================================================================
9. DATA MODEL
======================================================================

Create explicit schemas for at least these entities.

9.1 User
    id, name, email, role, created_at, disabled_at.

9.2 Company
    id, legal_name, display_name, ticker_optional, reporting_currency,
    fiscal_year_end, industry_optional, created_at, updated_at.

9.3 SourceDocument
    id, company_id, immutable_hash, original_filename, mime_type, byte_size,
    page_count, reporting_period_start, reporting_period_end, filing_type,
    reporting_currency, displayed_scale, audited_status, uploaded_at,
    extraction_status, verification_status.

9.4 SourceLocation
    id, document_id, page_number, bounding_box, raw_text, table_id_optional,
    row_label_optional, column_label_optional.

9.5 ReportedFact
    id, source_location_id, raw_label, raw_value, parsed_decimal_optional,
    currency, source_scale, normalized_value_optional, period_start,
    period_end, instant_date_optional, scope, segment_optional,
    sign_convention, confidence, verification_status, reviewer_id_optional.

9.6 NormalizedLineItem
    id, canonical_code, display_name, statement_type, parent_code_optional,
    expected_sign, cash_or_non_cash, operating_or_financing, definition.

9.7 FactMapping
    id, reported_fact_id, normalized_line_item_id, mapping_type,
    allocation_formula_optional, reviewer_note, approved_by, approved_at.

9.8 ModelVersion
    id, company_id, name, version_number, status, valuation_date,
    reporting_currency, calculation_scale, created_by, created_at,
    locked_at_optional, parent_version_id_optional.

9.9 ModelPeriod
    id, model_version_id, start_date, end_date, label, actual_or_estimate,
    cadence, sort_order.

9.10 Assumption
    id, model_version_id, scenario_id, code, period_id_optional, decimal_value,
    unit, source_type, source_document_id_optional, source_url_optional,
    source_date, rationale, owner, status, created_at, updated_at.

9.11 FormulaDefinition
    id, code, version, expression, description, input_codes, output_unit,
    rounding_policy, effective_date.

9.12 CalculatedValue
    id, model_version_id, scenario_id, period_id, line_item_code, decimal_value,
    formula_definition_id, input_fingerprint, calculated_at.

9.13 ValidationResult
    id, model_version_id, scenario_id_optional, check_code, severity,
    status, expected_value_optional, actual_value_optional, difference_optional,
    tolerance_optional, message, created_at.

9.14 AuditEvent
    id, actor_id, model_version_id, entity_type, entity_id, action,
    old_value_json, new_value_json, reason, timestamp.

Use immutable versioning for approved source facts, formulas, and model releases.

======================================================================
10. PDF INGESTION AND SOURCE VERIFICATION STEPS
======================================================================

10.1 Verify the upload is a PDF by MIME signature, not filename alone.
10.2 Calculate and store a SHA-256 hash.
10.3 Refuse exact duplicate uploads unless the user explicitly creates a linked
     duplicate record.
10.4 Scan the file using the approved security process.
10.5 Record filename, byte size, page count, and upload timestamp.
10.6 Detect whether each page is text-native, image-only, or mixed.
10.7 Extract embedded text and coordinates from text-native pages.
10.8 OCR image-only pages.
10.9 Preserve the original page number for every text span and table cell.
10.10 Detect document title, company name, reporting period, fiscal year-end,
      currency, scale, audited status, and accounting standard.
10.11 Mark detected metadata as UNCONFIRMED.
10.12 Present each detected metadata field to a reviewer.
10.13 Require confirmation or correction of every required metadata field.
10.14 Build a source map for the income statement, balance sheet, cash flow
      statement, statement of equity, and all relevant notes.
10.15 Detect repeated table headers and remove them only in normalized table data;
      retain the raw extraction.
10.16 Preserve parentheses as negative-sign evidence.
10.17 Distinguish hyphens used as zero, blank, unavailable, or punctuation.
10.18 Detect footnote markers without including the marker in the numeric value.
10.19 Detect columns with different dates or periods.
10.20 Detect restated and originally reported columns.
10.21 Prefer the latest explicitly restated historical value and retain both.
10.22 Detect continuing versus discontinued operations.
10.23 Detect consolidated versus segment tables.
10.24 Detect annual, quarterly, YTD, and TTM periods.
10.25 Extract values as raw strings before numeric parsing.
10.26 Parse values deterministically based on locale, currency, unit, and sign.
10.27 Reject ambiguous decimal/thousands separators for manual review.
10.28 Assign each extracted fact a confidence score and reason codes.
10.29 Require manual review for every low-confidence fact.
10.30 Require manual review for every value that fails a subtotal or cross-statement
      reconciliation.
10.31 Display the highlighted PDF cell beside the extracted fact.
10.32 Allow correction only with a reviewer note.
10.33 Record every acceptance, correction, split, combination, and rejection in
      the audit log.
10.34 Lock verified source facts in a versioned snapshot.
10.35 Re-run all dependent mappings and calculations after an approved change.

======================================================================
11. NORMALIZATION AND MAPPING STEPS
======================================================================

11.1 Create a canonical chart of accounts; do not force every company to use every
     canonical line.
11.2 Preserve every original company label.
11.3 Map one raw line to one normalized line only when definitions align.
11.4 When one raw line contains multiple concepts, keep it combined unless the
     PDF notes provide a defensible split.
11.5 When multiple raw lines map to one normalized line, show the aggregation.
11.6 Prevent double counting of components and subtotals.
11.7 Preserve reported totals as separate validation targets.
11.8 Record sign normalization separately from source sign.
11.9 Record operating, investing, financing, non-cash, and non-operating tags.
11.10 Record whether each mapping is system-proposed or human-approved.
11.11 Require human approval of all mappings before the historical model is
      labeled Verified.
11.12 Version the mapping set and invalidate dependent model results when changed.

======================================================================
12. HISTORICAL THREE-STATEMENT BUILD
======================================================================

12.1 Income statement
     a. Revenue.
     b. COGS only when reported or defensibly mapped.
     c. Gross profit only when revenue and COGS are valid.
     d. Operating expenses by disclosed category.
     e. D&A with source and classification.
     f. EBITDA only when the precise bridge is visible.
     g. EBIT/operating income.
     h. Interest income and expense.
     i. Other income/expense.
     j. Pre-tax income.
     k. Taxes.
     l. Net income, including attribution when disclosed.

12.2 Balance sheet
     a. Cash and cash equivalents.
     b. Operating current assets.
     c. Other current assets.
     d. PP&E.
     e. Goodwill and intangibles.
     f. Other non-current assets.
     g. Operating current liabilities.
     h. Short- and long-term debt.
     i. Lease liabilities when applicable.
     j. Other non-current liabilities.
     k. Minority interest when applicable.
     l. Equity accounts.

12.3 Cash flow statement
     a. Net income starting point or company-reported alternative.
     b. Non-cash adjustments.
     c. Working-capital changes.
     d. Operating cash flow.
     e. Capital expenditures.
     f. Acquisitions and disposals.
     g. Other investing cash flows.
     h. Debt issuance and repayment.
     i. Equity issuance and repurchase.
     j. Dividends.
     k. Other financing cash flows.
     l. FX effect on cash.
     m. Net change in cash.

12.4 Historical checks
     a. Assets = liabilities + equity.
     b. Reported gross profit equals revenue minus COGS, when applicable.
     c. Reported operating income equals modeled operating bridge.
     d. Pre-tax income equals EBIT plus net interest plus other non-operating items.
     e. Net income equals pre-tax income minus taxes, subject to disclosed items.
     f. Ending cash equals beginning cash plus CFO plus CFI plus CFF plus FX/other
        cash effects.
     g. Cash flow ending cash equals balance sheet cash for the same scope/date.
     h. Statement of equity rolls forward.
     i. All reported subtotals reconcile to mapped components.

Do not use a plug to force a historical balance. An unresolved difference remains
an error with a visible amount and source trail.

======================================================================
13. SUPPORTING SCHEDULES
======================================================================

13.1 Working capital schedule
     a. Define operating current assets.
     b. Define operating current liabilities.
     c. Exclude cash, debt, and non-operating accounts unless policy says otherwise.
     d. Calculate DSO, inventory days, DPO, and other relevant drivers.
     e. Explain denominators and day-count convention.

13.2 PP&E schedule
     Ending PP&E = Beginning PP&E + CapEx + Acquisitions - Depreciation
                   - Disposals +/- FX and Other Adjustments

13.3 Intangibles schedule
     Ending Intangibles = Beginning Intangibles + Additions + Acquisitions
                          - Amortization - Impairments +/- Other Adjustments

13.4 Debt schedule
     Ending Debt = Beginning Debt + Borrowing - Repayment +/- FX/Other
     Interest must state whether it uses beginning, ending, or average debt.

13.5 Lease schedule
     Track additions, payments, interest, current/non-current reclassification,
     and ending liability when material and disclosed.

13.6 Tax schedule
     Separate current tax, deferred tax, cash tax, NOL usage, and valuation
     allowances when relevant and available.

13.7 Equity schedule
     Ending Retained Earnings = Beginning Retained Earnings + Net Income
                                - Dividends +/- Other Adjustments
     Track share issuance, repurchases, stock compensation, and diluted shares.

13.8 Every schedule must reconcile to its related statement line for every period.

======================================================================
14. ASSUMPTION SYSTEM
======================================================================

14.1 No forecast may calculate until all required assumptions have a status.
14.2 Allowed statuses: Draft, Needs Source, Reviewed, Approved, Rejected.
14.3 Allowed source types: Company Guidance, Company Filing, External Market Data,
     Historical Driver, Analyst Assumption, Scenario Override.
14.4 Every assumption must contain:
     a. Code and clear name.
     b. Decimal value and unit.
     c. Applicable period(s).
     d. Applicable scenario.
     e. Source type.
     f. Source document/page or URL.
     g. Source publication/observation date.
     h. Rationale.
     i. Owner and reviewer.
     j. Status and timestamps.
14.5 Do not hide assumptions inside formulas.
14.6 Provide Base, Upside, and Downside scenarios only after their differences are
     explicitly entered.
14.7 A copied scenario must retain inherited assumption lineage.
14.8 Changing one assumption must show all affected outputs before saving.
14.9 Scenario names must not imply probability unless probability is explicitly
     modeled and sourced.

======================================================================
15. FORECAST THREE-STATEMENT STEPS
======================================================================

15.1 Create forecast periods immediately after the last verified actual period.
15.2 Label all periods A for actual or E for estimate.
15.3 Forecast revenue using an explicitly selected method:
     a. Top-down growth.
     b. Segment growth.
     c. Price times volume.
     d. Customer count times revenue per customer.
     e. Another documented operational driver.
15.4 Show each revenue driver and formula by period.
15.5 Forecast COGS using a documented margin or operating driver.
15.6 Forecast operating expenses line by line using documented drivers.
15.7 Calculate EBITDA only from the model's defined components.
15.8 Forecast D&A from the PP&E/intangibles schedules, not a disconnected input.
15.9 Calculate EBIT.
15.10 Forecast working-capital balances account by account.
15.11 Forecast CapEx from a documented assumption or project schedule.
15.12 Forecast debt issuance/repayment from the debt schedule and cash policy.
15.13 Calculate interest from the debt schedule and documented interest method.
15.14 Forecast taxes from the tax schedule and documented tax policy.
15.15 Calculate net income.
15.16 Roll net income and dividends into retained earnings.
15.17 Build the forecast balance sheet.
15.18 Build the forecast cash flow statement.
15.19 Link ending cash to the forecast balance sheet.
15.20 Run all three-statement checks for every scenario and forecast period.
15.21 Do not label the model Forecast Ready until every critical check passes.

======================================================================
16. DCF CALCULATION STEPS
======================================================================

16.1 Default method recommendation: FCFF. Require decision-ledger confirmation.
16.2 Calculate NOPAT:

     NOPAT_t = EBIT_t * (1 - TaxRate_t)

16.3 Calculate operating net working capital using the approved account policy.
16.4 Calculate change in operating NWC:

     DeltaNWC_t = NWC_t - NWC_(t-1)

16.5 Calculate FCFF for every explicit forecast period:

     FCFF_t = NOPAT_t + D&A_t - CapEx_t - DeltaNWC_t

     Add or subtract other operating non-cash/investment items only when explicitly
     defined, sourced, and shown in the bridge.

16.6 Build cost of equity using the approved method, normally CAPM:

     CostOfEquity = RiskFreeRate + Beta * EquityRiskPremium

16.7 Build pre-tax and after-tax cost of debt:

     AfterTaxCostOfDebt = PreTaxCostOfDebt * (1 - TaxRate)

16.8 Determine debt and equity market values on the stated valuation date.
16.9 Calculate WACC:

     WACC = E/(D+E) * CostOfEquity
            + D/(D+E) * PreTaxCostOfDebt * (1 - TaxRate)

16.10 If preferred stock or another capital class exists, add it explicitly.
16.11 Select and document year-end or mid-year discounting.
16.12 Calculate the exact time fraction from valuation date to cash-flow date.
16.13 Calculate each discount factor using Decimal-compatible exponentiation with
      a tested precision policy.
16.14 Present value each FCFF:

      PV_FCFF_t = FCFF_t / (1 + WACC)^(time_fraction_t)

16.15 For Gordon Growth terminal value, calculate:

      TerminalFCFF = FinalYearFCFF * (1 + g)
      TerminalValue = TerminalFCFF / (WACC - g)

16.16 Block calculation when WACC <= g.
16.17 Discount terminal value using the same timing convention.
16.18 Calculate enterprise value:

      EnterpriseValue = Sum(PV_FCFF) + PV_TerminalValue

16.19 Build an explicit enterprise-to-equity bridge:

      + Cash and approved non-operating assets
      - Debt
      - Lease liabilities if policy treats them as debt
      - Preferred stock
      - Minority interest
      - Unfunded pensions or other approved claims
      +/- Other explicitly approved adjustments
      = Equity Value

16.20 Calculate implied share value only when diluted shares are verified:

      ImpliedShareValue = EquityValue / DilutedShares

16.21 Show terminal value as a percentage of enterprise value.
16.22 Warn when terminal value exceeds a configurable review threshold; do not
      automatically fail solely because it is high.
16.23 Build WACC/g sensitivity with explicit step sizes and displayed assumptions.
16.24 If exit multiple is enabled, keep its terminal value separate and source the
      metric, multiple, date, and comparable set.
16.25 Never average terminal methods unless the user explicitly approves a policy.

======================================================================
17. VALIDATION AND DIAGNOSTICS
======================================================================

Create a severity system:
CRITICAL = calculation/export blocked.
ERROR = model cannot be released.
WARNING = model may be released only with acknowledged rationale.
INFO = informational.

Required checks:

17.1 Source file hash exists.
17.2 Required metadata confirmed.
17.3 All periods unambiguous.
17.4 Currency and units confirmed.
17.5 All critical facts verified.
17.6 All mappings approved.
17.7 No duplicate-counted source facts.
17.8 Historical balance sheet balances.
17.9 Historical cash reconciles.
17.10 Historical subtotals reconcile.
17.11 PP&E schedule reconciles.
17.12 Intangibles schedule reconciles.
17.13 Debt schedule reconciles.
17.14 Tax schedule reconciles where data permits.
17.15 Equity schedule reconciles.
17.16 Forecast balance sheet balances.
17.17 Forecast cash reconciles.
17.18 No missing required forecast assumptions.
17.19 No rejected assumption is used.
17.20 No hardcoded number exists inside a forecast formula.
17.21 Formula graph contains no cycles unless an approved iterative calculation is
      explicitly configured and convergence-tested.
17.22 DCF FCFF equals the three-statement FCFF bridge.
17.23 WACC components are dated and sourced.
17.24 WACC is greater than terminal growth.
17.25 Enterprise-to-equity adjustments are sourced.
17.26 Diluted shares are nonzero and sourced before per-share value is shown.
17.27 No NaN, Infinity, or null appears in a released calculation.
17.28 Primary and independent benchmark results meet Section 4 tolerance.
17.29 Display rounding ties to full-precision values.
17.30 Every released output has source and formula lineage.

======================================================================
18. FORMULA ENGINE REQUIREMENTS
======================================================================

18.1 Store formulas as versioned definitions.
18.2 Allow only approved operators and functions.
18.3 Do not evaluate arbitrary user code.
18.4 Parse formulas into a dependency graph.
18.5 Topologically order calculations.
18.6 Detect cycles before evaluation.
18.7 Hash inputs and formula version for reproducibility.
18.8 Recalculate only affected descendants after a change.
18.9 Preserve the prior calculated model version.
18.10 Provide a human-readable formula for every calculated cell.
18.11 Provide the exact input values used for every calculation.
18.12 Provide unit checking so percentages, currency, shares, and multiples cannot
      be combined nonsensically.
18.13 Reject division by zero with a visible diagnostic.
18.14 Reject missing inputs; do not coerce them to zero.
18.15 Run deterministic calculations server-side.
18.16 The browser may preview edits, but released outputs must come from the
      authoritative server calculation.

======================================================================
19. API REQUIREMENTS
======================================================================

Use versioned endpoints. Exact framework syntax may vary.

19.1 POST /api/v1/documents                Upload a PDF.
19.2 GET  /api/v1/documents/{id}           Read metadata/status.
19.3 GET  /api/v1/documents/{id}/pages     Read page/source index.
19.4 GET  /api/v1/documents/{id}/facts     Read extracted facts.
19.5 PATCH /api/v1/facts/{id}              Correct/verify a fact with reason.
19.6 POST /api/v1/mappings/propose         Generate mapping proposals.
19.7 PATCH /api/v1/mappings/{id}           Review a mapping.
19.8 POST /api/v1/models                   Create a model version.
19.9 GET  /api/v1/models/{id}              Read model metadata.
19.10 GET /api/v1/models/{id}/statements   Read statements.
19.11 GET /api/v1/models/{id}/schedules    Read schedules.
19.12 POST /api/v1/models/{id}/scenarios   Create scenario.
19.13 PATCH /api/v1/assumptions/{id}       Edit assumption with reason.
19.14 POST /api/v1/models/{id}/calculate   Run authoritative calculation.
19.15 GET /api/v1/models/{id}/dcf          Read DCF output.
19.16 GET /api/v1/models/{id}/validations  Read checks.
19.17 GET /api/v1/models/{id}/lineage      Read dependencies/source lineage.
19.18 POST /api/v1/models/{id}/release     Lock a reviewed version.
19.19 POST /api/v1/models/{id}/exports     Generate selected export.
19.20 GET /api/v1/audit-events             Filtered audit trail.

Every mutation requires authentication when auth is enabled, authorization,
schema validation, optimistic concurrency/version checks, audit reason where
required, and a structured error response.

======================================================================
20. SECURITY AND PRIVACY
======================================================================

20.1 Treat uploaded financial PDFs as confidential.
20.2 Encrypt data in transit and at rest for hosted deployments.
20.3 Store secrets only in the approved secret manager/environment.
20.4 Never commit secrets, source PDFs, or production financial data to Git.
20.5 Use least-privilege database and storage credentials.
20.6 Apply role-based access control if multi-user.
20.7 Prevent cross-company/model access by server-side authorization checks.
20.8 Validate file size, type, signature, and page-count limits.
20.9 Scan uploads before processing.
20.10 Isolate PDF/OCR processing from the web process.
20.11 Sanitize filenames and never execute document content.
20.12 Protect against path traversal, SSRF, injection, XSS, CSRF, insecure direct
      object references, and formula injection in spreadsheet exports.
20.13 Prefix spreadsheet values beginning with =, +, -, or @ when exporting raw
      text that must not execute as a formula.
20.14 Rate-limit upload, extraction, authentication, and export endpoints.
20.15 Log security events without logging source values unnecessarily.
20.16 Redact secrets and private data from application errors.
20.17 Define backup, restore, retention, and permanent-deletion behavior.
20.18 Require action confirmation for permanent deletion.
20.19 Provide a non-advisory disclaimer and model limitations in the UI/exports.
20.20 Complete dependency and vulnerability scans before production release.

======================================================================
21. EXPORT REQUIREMENTS
======================================================================

21.1 XLSX workbook tabs, when enabled:
     Cover, Sources, Raw Facts, Mapping, Historical IS, Historical BS,
     Historical CF, Schedules, Assumptions, Forecast IS, Forecast BS,
     Forecast CF, DCF, Sensitivity, Checks, Audit Summary.
21.2 XLSX hardcodes and formulas must be visually distinguishable.
21.3 XLSX must state currency, units, dates, scenario, and model version.
21.4 CSV exports must include schema/data-dictionary reference.
21.5 JSON exports must validate against a versioned schema.
21.6 PDF report must include valuation date, source coverage, assumptions,
     forecast, DCF, sensitivities, checks, limitations, and model version.
21.7 Every export must include generation timestamp and immutable model version ID.
21.8 Exported values must equal website values at the same model version and
     display precision.

======================================================================
22. TEST PLAN
======================================================================

22.1 Unit tests
     a. Locale-aware number parsing.
     b. Parentheses and sign handling.
     c. Unit normalization.
     d. Every formula definition.
     e. Rounding boundaries.
     f. Zero and near-zero tolerance handling.
     g. WACC/g guard.
     h. Date/time-fraction calculation.
     i. Scenario inheritance.
     j. Permission checks.

22.2 Property-based tests
     a. Assets always equal liabilities plus equity for generated valid models.
     b. Cash roll-forward identities hold.
     c. Increasing WACC reduces DCF value when all else is fixed and cash flows are
        conventional and positive.
     d. Increasing terminal growth increases terminal value when WACC > g and
        final FCFF is positive.
     e. Unit conversions are reversible within exact decimal precision.

22.3 Golden extraction tests
     a. Text-native PDF.
     b. Scanned PDF.
     c. Multi-column PDF.
     d. Parenthetical negatives.
     e. Values in thousands and millions.
     f. Restated prior years.
     g. Rotated pages.
     h. Split tables across pages.

22.4 Integration tests
     a. Upload through verified historical model.
     b. Fact correction invalidates downstream output.
     c. Mapping approval enables model build.
     d. Assumption update recalculates only dependent values.
     e. Release locks the version.
     f. Export matches released output.

22.5 End-to-end tests
     a. Create model.
     b. Upload fixture PDF.
     c. Confirm metadata.
     d. Review facts.
     e. Approve mappings.
     f. Resolve historical checks.
     g. Enter assumptions.
     h. Review forecast.
     i. Review DCF and sensitivity.
     j. Release and export.

22.6 Visual tests
     a. Desktop at 1440px.
     b. Laptop at 1280px.
     c. Tablet at 768px.
     d. Mobile at 390px.
     e. Long company names.
     f. Negative values.
     g. Very large values.
     h. Empty and error states.

22.7 Accessibility tests
     a. Keyboard-only full workflow.
     b. Screen-reader labels.
     c. Focus order.
     d. Color contrast.
     e. Zoom to 200%.
     f. Reduced motion.

22.8 Performance targets, to be measured on documented hardware/data:
     a. Initial authenticated dashboard load target <= 2.5 seconds at p75.
     b. Normal assumption recalculation target <= 500 ms for a standard model.
     c. Large statement table interaction target >= 50 FPS where measurable.
     d. Long extraction jobs run asynchronously with progress and cancellation.

======================================================================
23. IMPLEMENTATION SEQUENCE — DO NOT SKIP STEPS
======================================================================

Phase 0: Establish scope
1. Inspect the existing three-statement-dcf repository.
2. Record current branch, status, tracked files, and existing architecture.
3. Preserve unrelated user changes.
4. Create docs/decision-ledger.md.
5. Enter every decision from Section 2 as Confirmed or OPEN.
6. List work blocked by OPEN decisions.
7. Obtain answers before implementing blocked work.
8. Write acceptance criteria into the repository.

Phase 1: Establish the project
9. Select the documented stack.
10. Create only required folders/files.
11. Configure formatting, linting, and strict type checking.
12. Add environment-variable names to .env.example.
13. Configure reproducible local startup.
14. Add a health endpoint.
15. Add CI with an intentionally simple passing smoke test.
16. Confirm clean install, development start, test, and production build.

Phase 2: Define contracts before features
17. Write the data dictionary.
18. Write source and validation policies.
19. Define API schemas.
20. Define database schema and migrations.
21. Define formula catalog and versions.
22. Define Decimal context and rounding policy.
23. Define error codes and severity.
24. Define model lifecycle states and legal transitions.
25. Review these contracts before UI implementation.

Phase 3: Implement secure source ingestion
26. Implement PDF signature validation.
27. Implement immutable hash and duplicate detection.
28. Implement safe storage.
29. Implement extraction job states.
30. Implement text-native extraction.
31. Implement OCR fallback.
32. Implement page geometry/source locations.
33. Implement raw table and fact persistence.
34. Implement metadata detection with UNCONFIRMED state.
35. Implement unit/sign/locale parsing.
36. Implement confidence and reason codes.
37. Add extraction fixtures and tests.
38. Confirm the original PDF remains unchanged.

Phase 4: Implement source review
39. Build source-room navigation.
40. Build PDF page viewer.
41. Build statement/page bookmarks.
42. Build highlighted source bounding boxes.
43. Build raw-versus-parsed fact view.
44. Build metadata confirmation.
45. Build fact accept/edit/reject actions.
46. Require reasons for changes.
47. Add audit events.
48. Add review progress and unresolved count.
49. Test keyboard and screen-reader workflows.

Phase 5: Implement mapping
50. Create canonical line-item definitions.
51. Implement mapping proposals.
52. Build mapping review table.
53. Implement split and combine mappings.
54. Add duplicate-count prevention.
55. Add subtotal reconciliation.
56. Require approval before verification.
57. Version mapping sets.
58. Test mapping invalidation.

Phase 6: Implement historical statements
59. Build normalized income statement.
60. Build normalized balance sheet.
61. Build normalized cash flow statement.
62. Build equity statement when available.
63. Add reported and normalized views.
64. Add common-size and growth views.
65. Add source drill-down per cell.
66. Implement all historical checks.
67. Keep differences visible; do not plug.
68. Add golden historical-model tests.

Phase 7: Implement schedules
69. Build working-capital schedule.
70. Build PP&E/depreciation schedule.
71. Build intangible/amortization schedule.
72. Build debt/interest schedule.
73. Build lease schedule when selected.
74. Build tax schedule.
75. Build equity/share schedule.
76. Reconcile every schedule to statements.
77. Add unit and integration tests.

Phase 8: Implement formula engine
78. Build safe formula parser.
79. Build dependency graph.
80. Build cycle detection.
81. Build Decimal evaluator.
82. Build unit validation.
83. Build missing-input errors.
84. Build input/formula fingerprints.
85. Build incremental recalculation.
86. Build human-readable formula trace.
87. Build independent benchmark implementation.
88. Run Section 4 accuracy tests.

Phase 9: Implement assumptions and scenarios
89. Build assumption schema and statuses.
90. Build assumption editor.
91. Require source, date, rationale, and owner.
92. Build scenario creation and inheritance.
93. Build unsaved-change preview.
94. Build dependency impact preview.
95. Add approval workflow.
96. Test missing/rejected assumptions.

Phase 10: Implement forecast statements
97. Create estimate periods after actual periods.
98. Build revenue drivers.
99. Build expense drivers.
100. Link D&A to schedules.
101. Forecast working capital.
102. Forecast CapEx.
103. Forecast debt and interest.
104. Forecast taxes.
105. Build forecast income statement.
106. Build forecast balance sheet.
107. Build forecast cash flow statement.
108. Run checks for every scenario and period.

Phase 11: Implement DCF
109. Build NOPAT bridge.
110. Build FCFF bridge.
111. Build WACC input/source panel.
112. Implement timing convention.
113. Discount explicit FCFF.
114. Build terminal-value method(s).
115. Enforce WACC > g for Gordon Growth.
116. Build enterprise value.
117. Build enterprise-to-equity bridge.
118. Build per-share value when eligible.
119. Build sensitivity tables.
120. Add DCF benchmark tests.

Phase 12: Implement the dashboard and design system
121. Implement design tokens.
122. Add licensed open-source fonts.
123. Build navigation shell.
124. Build responsive 12-column dashboard.
125. Build metric cards with period/scenario/source/status.
126. Build charts with text summaries and downloads.
127. Build statement tables with frozen headers/columns.
128. Build errors, empty states, skeletons, and confirmations.
129. Add mobile/tablet layouts.
130. Run visual regression and accessibility tests.

Phase 13: Diagnostics, lineage, and audit
131. Build diagnostics page.
132. Build source-to-output lineage.
133. Build formula dependency view.
134. Build filterable audit log.
135. Build benchmark-accuracy report.
136. Build release-readiness checklist.
137. Prevent release when CRITICAL/ERROR checks remain.

Phase 14: Exports
138. Implement JSON export and schema validation.
139. Implement CSV export and injection protection.
140. Implement XLSX workbook and formula/hardcode styling.
141. Implement PDF valuation report.
142. Add model version and timestamps.
143. Compare exports with website outputs.
144. Test large and negative values.

Phase 15: Security and operations
145. Implement authentication if required.
146. Implement server-side authorization.
147. Implement upload limits and isolation.
148. Implement rate limits.
149. Implement structured logs and redaction.
150. Implement backup/restore.
151. Implement retention/deletion.
152. Run dependency and security scans.
153. Document incident and recovery procedures.

Phase 16: Final verification
154. Run formatting and linting.
155. Run strict type checks.
156. Run all unit tests.
157. Run property-based tests.
158. Run golden extraction tests.
159. Run integration tests.
160. Run end-to-end tests.
161. Run accessibility tests.
162. Run visual regression tests.
163. Run production build.
164. Run independent arithmetic benchmark suite.
165. Confirm Section 4 accuracy contract passes.
166. Confirm no real source PDFs or secrets are in Git.
167. Confirm all documentation reflects actual behavior.
168. Produce a release-readiness report with PASS/FAIL evidence.

Phase 17: Deployment
169. Do not deploy until target, access level, and data policy are confirmed.
170. Deploy to staging first.
171. Use synthetic data in staging unless private-data controls are confirmed.
172. Run staging smoke tests.
173. Verify database migrations and rollback plan.
174. Verify storage permissions.
175. Verify TLS and security headers.
176. Verify backups.
177. Obtain release approval.
178. Deploy the exact tested version to production.
179. Run production smoke tests without exposing private data.
180. Record deployed commit, model schema version, and formula version.

======================================================================
24. RELEASE ACCEPTANCE CRITERIA
======================================================================

The application is not complete until all applicable items pass.

24.1 A user can upload a valid company PDF.
24.2 The original PDF is preserved and hashed.
24.3 Every extracted value links to a page and location.
24.4 Ambiguous metadata and values require review.
24.5 Historical statements reconcile or show explicit unresolved errors.
24.6 Supporting schedules link to the statements.
24.7 Every forecast assumption is visible, sourced, dated, and owned.
24.8 Forecast statements integrate and balance.
24.9 FCFF comes from the forecast model.
24.10 WACC and terminal assumptions are sourced.
24.11 DCF outputs reproduce from the stored model version.
24.12 All critical outputs have source/formula lineage.
24.13 Independent arithmetic checks satisfy Section 4.
24.14 The site never claims forecast accuracy of 0.0001%.
24.15 The dashboard works at desktop, tablet, and mobile widths.
24.16 Keyboard and automated accessibility checks pass WCAG 2.2 AA targets.
24.17 Exports match website outputs.
24.18 Unauthorized users cannot access another model.
24.19 Secrets and private PDFs are absent from version control and logs.
24.20 CI and production build pass from a clean checkout.
24.21 README and user guide contain exact start, test, review, export, and recovery
      instructions.
24.22 A release-readiness report records evidence for every criterion.

======================================================================
25. REQUIRED USER-FACING DISCLAIMERS
======================================================================

Display concise language with the same meaning as the following; obtain legal
review before commercial use:

"This model is an analytical tool, not investment, accounting, tax, or legal
advice. Historical information may contain extraction or classification errors
until reviewed. Forecasts and valuations depend on assumptions and are inherently
uncertain. Verify all source data, assumptions, and outputs before relying on
them."

Do not bury this only in Terms. Show it in the model, release flow, and exports.

======================================================================
26. RESEARCH BASIS FOR THE FINDASH.AI-INSPIRED PRODUCT PATTERNS
======================================================================

Official pages inspected on 2026-09-16:

1. https://findash.ai/
   Observed broad visual principles: warm light canvas, editorial serif headings,
   restrained sans-serif UI, green primary actions, blue financial totals,
   rounded card grid, generous spacing, and modular financial surfaces.

2. https://findash.ai/documentation/getting-started/platform-overview
   Product patterns described by FinDash: dashboard widgets, net worth, historical
   and future cash flow, goals/projections, documents, tasks, tax, insurance,
   estate, integrations, and AI-assisted workflows.

3. https://findash.ai/documentation/cash-flow/cash-flow-plans
   Product patterns described by FinDash: explicit cash-flow inputs, scenario
   planning, source review, and Sankey/timeline views.

4. https://findash.ai/documentation/for-advisors/report-exports
   Product patterns described by FinDash: configurable widgets, branded exports,
   exact report preview, scenario selection, and final review before sharing.

Use these only as design/product inspiration. Build original branding, components,
copy, information architecture, and implementation.

======================================================================
27. FINAL HANDOFF REQUIREMENTS FOR THE IMPLEMENTING AGENT
======================================================================

When implementation work is requested, the implementing agent must report:

1. Exact files created or changed.
2. Existing user files preserved.
3. Decisions confirmed and decisions still OPEN.
4. Features completed.
5. Tests executed and exact results.
6. Numerical-accuracy dataset and exact benchmark result.
7. Known limitations.
8. Security/privacy items not yet production-ready.
9. How to run the website locally.
10. How to upload and verify a PDF.
11. How to create assumptions and run the forecast.
12. How to inspect the DCF and sensitivity analysis.
13. How to export and reproduce a released model.

Do not say "complete," "production-ready," or "error below 0.0001%" unless every
relevant acceptance criterion has evidence. If something is unknown, label it
UNKNOWN or OPEN instead of guessing.

END OF SPECIFICATION
