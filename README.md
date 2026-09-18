# three-statement-dcf

Builds an integrated three-statement financial model from a company filing and
values it with a DCF.

Two documents govern this repository, and they are different things:

| Document | What it is | Status |
|---|---|---|
| [`three_statement_model_to_dcf_step_by_step.txt`](three_statement_model_to_dcf_step_by_step.txt) | The 37-step modelling workflow | **Implemented** |
| [`docs/website-build-spec.md`](docs/website-build-spec.md) | The specification for a web application around it | **Phases 2–16 of 17** |

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
3. **The review and mapping application** (`review_server.py`) —
   specification Phases 4 to 15, items 39–153. A browser interface showing
   the PDF page beside the values read from it, with every extracted number
   boxed on the page it came from; accept / correct / reject actions that each
   require a written reason; a mapping screen that carries each reported line
   onto a canonical chart of accounts, with human approval, split and combine,
   double-count prevention and subtotal reconciliation; and the three
   historical statements it all produces, every cell tracing back to the page
   it was printed on; and the supporting schedules that explain how each
   balance moved, reconciled to the statement line each one claims to explain;
   a formula engine that recomputes every subtotal the filing prints, from its
   own components, and shows the formula and the exact inputs it used; and the
   the assumption register, where every driver the forecast needs is listed
   whether or not anyone has entered it; and the forecast statements, built by
   the engine from a scenario's approved assumptions; and the DCF, where every
   market input carries the URL and the date somebody observed it on; and a
   portfolio whose status column is computed from what each model actually
   contains rather than stored.

**The two halves are joined.** Phase 6 turns a verified, mapped document into
the engine's own `Ledger` objects and writes the two YAML files `run_model.py`
reads. Run the engine on them and it loads the filing's history and then halts
on `tax.source is required by STEP 16` — which is the right outcome: the
history came from the document, and the forecast assumptions still need a
person, because a beta and a risk-free rate are not lines in a filing.

**The schedules do not plug.** Every roll-forward in Section 13 ends in a term
like "FX and Other Adjustments", and a filing rarely puts a number beside it.
Solving for that term would make every schedule tie and every reconciliation
pass, which is why nothing here does: a schedule's closing figure is the
opening balance plus what the filing disclosed, and the gap to the reported
balance is shown as **unexplained**. Three of the seven schedules cannot be
built at all from the current chart, and each says why rather than rendering
an empty table.

**Nothing evaluates arbitrary code.** The formula engine has no `eval`,
`exec`, `compile` or `ast.literal_eval` anywhere in it, and a test greps the
source for each of them — grammar tests would still pass if someone added a
fast path beside the parser. Formulas are versioned definitions, parsed into a
dependency graph, checked for cycles *before* evaluation, evaluated exactly in
`Decimal`, and unit-checked so a percent cannot be multiplied by a currency.

**An assumption must earn its status.** A company filing cited without a page
is refused; a beta without the date it was observed is refused; a historical
driver that does not say which periods it measured is refused. The historical
drivers the Section 13 schedules measured are offered, already carrying their
periods — and every one arrives as a **Draft**, because a proposal that
arrived Approved would assume every driver stays where it was, for all of them
at once, silently.

**The forecast is the engine's, not a second one.** `model/forecast.py`
implements all twenty-one of Section 15's steps and has an independent
benchmark behind it, so Phase 10 is a boundary rather than a reimplementation:
a scenario's approved assumptions become the engine's inputs, the engine runs,
and every check runs for every scenario and every period. A second
implementation would produce a second answer to every question in Section 15.

**Discounting now offers the conventions Section 16 requires.** The engine
discounted at whole-year periods; 16.11 asks for a documented choice between
year-end and mid-year, and 16.12 for the exact time fraction from a valuation
date. Both are supplied, with the precision policy for the resulting
non-integer exponent stated and bounded by tests at 1e-40 relative — forty
orders of magnitude inside the 0.0001% contract. The year-end path is unchanged
to the digit.

**The layout is tested in a real browser at three widths.** Item 130's sweep
runs every screen at desktop, tablet and mobile and asserts the page never
scrolls sideways — a wide table scrolls inside its own focusable region, which
is the only place WCAG 1.4.10 permits it. Widening that sweep from two screens
to eight found horizontal overflow on every screen with a table on it, and a
browser test reading `document.fonts` found that two font families had been
named in the tokens and never vendored (F-24, F-25).

**Thirty checks, one panel, and a release gate that admits what it cannot
know.** Section 17's checks were never missing — Phases 3 to 11 each built the
ones its own stage needed — but a reader had to know which of six panels to
look in. Phase 13 maps every clause onto the code that already answers it and
reports PASS, FAIL, or **SKIP with its reason**, because rule 1.14 says an
unresolved requirement must never appear as PASS.

The gate on top of it cannot be built as specified: item 137 blocks release
"when CRITICAL/ERROR checks remain", and Section 17 assigns a severity to none
of its thirty checks (F-4). So the gate blocks on *every* outstanding check
instead — failed and skipped alike, whatever severity has been proposed for it.
That is strictly stricter than item 137 under any assignment the owner might
make, so it cannot release something 137 would have stopped; it can only refuse
something 137 would have allowed, and for a valuation that is the direction to
err in. The screen says so, and says that ratifying the severities is what
would let it tell a blocking failure from an acknowledged warning.

The benchmark panel makes the weaker, true claim for the same reason. 4.20
forbids claiming "less than 0.0001% error" until the suite passes *and* the
report names the dataset and formulas — and a running web process does not
observe the test suite. So it reports what it can establish: which of the
required outputs are compared, against an implementation sharing no helper with
the engine, and where each comparison lives.

**Four exports, one gathered model.** 21.8 requires an exported value to equal
the website's at the same model version and display precision. Four formats
built independently would satisfy that by coincidence, so they are not: one
gather step calls the same view functions the screens call, and JSON, CSV, XLSX
and PDF each render that object. They cannot disagree without one of them
calling a different function.

The model version is a digest of what the model contains — the document's hash,
the mapping's decisions, the scenario, every resolved assumption — rather than a
counter. The same model exported twice a week apart reads the same version, and
one changed digit changes it.

**The CSV defence leaves negative numbers alone.** A cell beginning `=`, `+`,
`-` or `@` is run as a formula by every spreadsheet, and the usual fix prefixes
an apostrophe. Every negative figure begins with a minus sign, and a prefixed
one becomes text that sorts as text, sums as zero and looks like a number. So
only non-numeric cells are neutralized, and every one of them is listed on the
screen.

**The workbook says what it cannot hold.** A spreadsheet number is a double and
this model's decimals are exact; around one numeric cell in eight cannot survive
the trip. Each carries its exact value in a cell note, is styled `Inexact`, and
is counted on the cover tab — rather than being rounded away where nobody
would notice.

**There is a credential in front of it now.** Decision 2.2.c has required one
since Phase 2 and it went unimplemented for ten phases, mitigated only by
binding to localhost. Phase 15 built it — a password hashed with `scrypt` from
the standard library, a signed session cookie expiring absolutely eight hours
after sign-in, a CSRF token on every state-changing request, rate-limited
sign-ins — and turned the mitigation into a refusal: the server will not bind
anywhere but loopback without a credential configured. Without one it serves
locally and says so on every page, because a reviewer who cannot tell whether
the thing in front of them is protected will assume it is.

**The security layer says what it does not do.** PDF parsing runs in a child
process under memory, CPU and time limits, which contains a crash or a runaway
allocation and is explicitly *not* a boundary against code execution. Uploads
are scanned only if a scanner is configured, and with none the result is
recorded as "not scanned" — never as clean. The rate limiters are per process
and say so. The backup archive is not encrypted by the process that writes it,
and its own manifest says so. All of it is in
[`docs/incident-response.md`](docs/incident-response.md), before an incident
rather than after, because a procedure that does not name its gaps is read as a
guarantee it never made.

**An untested backup is not a backup**, so the restore test is the deliverable:
a snapshot carries a manifest of every file's SHA-256, and verifying it restores
into a scratch directory and re-hashes everything. A tar that extracts proves
the tar is well-formed, not that the bytes inside it are the bytes that went in.
That verification runs in CI on every commit rather than quarterly on a
calendar.

**The release-readiness report is generated, not written.** Item 168 asks for
PASS/FAIL evidence, and a file somebody typed is a claim about the code rather
than evidence about it. Every row in
[`docs/release-readiness.md`](docs/release-readiness.md) is the result of
running something, with the command printed beside it, and the generator exits
non-zero unless every gate passed — a skipped gate blocks the verdict, because
a check that did not run has not passed.

It found three real things on its first run, including a stale test count in
this file. CI regenerates it and fails when the committed copy has drifted.

**This is the one place the 0.0001% claim can be made.** 4.20 permits it only
once the benchmark suite passes *and* the report names the exact dataset and
formulas. A web process cannot observe the test suite, so the in-app panel
reports coverage and says the result is not observed; a report generator runs
the suite, so it names the dataset, lists all twenty-two of 4.16's outputs, and
reports the contract **UNPROVEN** when the benchmark did not pass rather than
carrying the claim forward.

**A READY verdict is not permission to deploy**, and the report says so: Phase
17 item 169 requires the target, the access level and the data policy to be
confirmed first.

**Every response now carries its security headers, and the strictest CSP
available is simply true here.** Item 175 had nothing to verify: the
application was sending none. `script-src 'none'` and `default-src 'none'` are
not aspirations but consequences of shipping no JavaScript (deviation F-14),
and `test_no_template_contains_a_script_tag` is the test the claim rests on.
They are sent from the application rather than the proxy, so a proxy
misconfiguration cannot drop them, and the middleware sits *after* the guard so
the guard's own refusals carry them too. `Strict-Transport-Security` is sent
only on an HTTPS request, because over plaintext it is ignored by the browser
and merely makes a `curl -I` look compliant.

**The smoke test never authenticates.** Item 179 wants production smoke tests
that do not expose private data, and the two halves pull against each other: a
test that logs in proves more, but holds a credential and prints filing
details from a monitoring job. `python3 -m apps.api.app.verification.smoke
https://host` cannot reach a filing, so it cannot expose one. Its sixteen
checks are about the shape of a correct deployment — that the process answers,
names its own commit, is not running from a modified tree (item 178), refuses
an unauthenticated request, leaks nothing in the refusal, and carries all six
headers on it.

**`/health` names the code that produced a figure** (item 180): the commit, the
export schema version and the formula fingerprint, read at startup rather than
baked in by a script somebody has to remember to run. A deployment from a dirty
tree reports its commit as `-dirty`, because that deployment is not the version
the suite passed and the value itself should say so.

1367 tests pass on Python 3.10–3.13, including a keyboard-and-screen-reader
suite driven through a real browser, a golden historical model asserting every
cell of all three statements, four tests that each break a different figure and
assert the reconciliation catches it with the right amount, and two independent
implementations of the statement derivations asserted to agree **exactly** on
the golden filing, on eight extreme-input cases and on 125 randomized ones. All
arithmetic is exact decimal.

**Facts can now reach `VERIFIED`.** Verification is a seven-part conjunction
(`docs/source-policy.md` §9) whose seventh condition is a human-approved
mapping. Through Phase 4 the correct answer for every fact was no, because
there was no mapping stage; Phase 5 built one. The application still evaluates
all seven conditions separately and names the one that is failing, because
rule 1.14 says an unresolved requirement must never appear as PASS.

**What does not exist yet: a deployment.** Every one of the specification's
180 items that is code is built. What is left is Phase 17's decisions —
item 169's target, access level and data policy, and item 177's release
approval — and they are the owner's, not the implementing agent's.
[`docs/deployment.md`](docs/deployment.md) is the runbook, and §6 is the list
of questions it cannot answer for itself. The one piece of infrastructure that
is still missing is PostgreSQL: specification 3.2.d asks for it and storage is
JSON files on a filesystem, which is recorded as finding F-36 rather than
glossed.

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

Review and map what it extracted, in a browser:

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

Then open the mapping screen from the source room. Press **Propose mappings**:
46 of the 50 facts get a suggestion with the rule that produced it, and four do
not — `Total current assets` and `Total liabilities and equity` have no
canonical line, and the page says why rather than filing them under the
statement total. **Approve all** is then refused, because three operating
expense categories map to one canonical line and that is a double count until
you declare it an aggregate (11.5). Declare it, approve, and 46 facts reach
`VERIFIED` with every subtotal reconciling.

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

Normalization and mapping (specification Phase 5, items 50–58):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/mapping/chart.py` | 50 | The canonical chart as rows, with a written definition per line |
| `apps/api/app/mapping/proposals.py` | 51 | Deterministic proposals, each carrying the rule that produced it |
| `apps/api/app/mapping/sets.py` | 57 | `FactMapping` and a versioned, immutable `MappingSet` |
| `apps/api/app/mapping/actions.py` | 53, 56 | Map, split, combine, reject, approve |
| `apps/api/app/mapping/checks.py` | 54, 55 | Double-count prevention; subtotal and cross-statement reconciliation |
| `apps/api/app/mapping/normalized.py` | — | What the approved mappings produce, sparse and unplugged |
| `apps/api/app/api/templates/mapping.html` | 52 | The 7.4 review table |

Historical statements (specification Phase 6, items 59–68):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/statements/build.py` | 59–61 | **The join.** Approved mappings become the engine's own `Ledger`, every cell citing its page |
| `apps/api/app/statements/checks.py` | 66, 67 | The historical identities; a difference is reported, never plugged |
| `apps/api/app/statements/views.py` | 62–64 | Reported and normalized, common-size, growth, and why there is no equity statement |
| `apps/api/app/statements/reported.py` | 63, 65 | What the filing printed, and the drill-down behind each cell |
| `apps/api/app/statements/export.py` | — | The two YAML files `run_model.py` reads |
| `apps/api/app/api/templates/statements.html` | 65 | The 7.5 screen |

Supporting schedules (specification Phase 7, items 69–77):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/schedules/base.py` | — | The shared vocabulary: a line, a caveat, a reconciliation, and availability with a reason |
| `apps/api/app/schedules/working_capital.py` | 69 | 13.1, with DSO, inventory days and DPO, and the day-count convention stated |
| `apps/api/app/schedules/rollforward.py` | 70, 72, 75 | PP&E, debt and equity, built from disclosed movements only |
| `apps/api/app/schedules/interest.py` | 72 | 13.4's stated basis: beginning debt, because that is what the forecast charges |
| `apps/api/app/schedules/tax.py` | 74 | 13.6's effective rate, and the four components only a tax footnote carries |
| `apps/api/app/schedules/unavailable.py` | 71, 73 | The three that cannot be built, each with its reason (F-17) |
| `apps/api/app/schedules/checks.py` | 76 | 13.8: every schedule against its statement line, every period |
| `apps/api/app/api/templates/schedules.html` | 77 | The 7.6 screen |

Formula engine (specification Phase 8, items 78–88):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/formula/parse.py` | 78 | A recursive-descent parser over an approved character, operator and function set. No `eval`, anywhere |
| `apps/api/app/formula/units.py` | 82 | 18.12's algebra: four base dimensions, plus the rule that a percent may not be multiplied |
| `apps/api/app/formula/graph.py` | 79, 80 | Topological order, and cycles named **before** evaluation |
| `apps/api/app/formula/evaluate.py` | 81, 83, 86 | Exact `Decimal` evaluation, refusals for missing inputs and division by zero, and the trace |
| `apps/api/app/formula/registry.py` | 78, 84 | Versioned definitions, and the two fingerprints 18.7 asks for |
| `apps/api/app/formula/calculate.py` | 85 | Recalculating only the affected descendants, keeping the prior model |
| `apps/api/app/formula/catalog.py` | 87 | The derivation family, generated from `model/accounts.py` so the two cannot drift |
| `apps/api/app/api/templates/formulas.html` | 86 | 18.10 and 18.11 as a screen: the formula, the inputs, and whether the filing's own arithmetic holds |

Assumptions and scenarios (specification Phase 9, items 89–96):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/assumptions/schema.py` | 89, 91 | 14.4's ten fields, with evidence rules per source type |
| `apps/api/app/assumptions/scenarios.py` | 92 | The Scenario entity Section 9 references and never defines (F-5), with lineage and 14.9's naming rule |
| `apps/api/app/assumptions/drivers.py` | 96 | What the forecast actually requires, read out of `model/forecast.py` |
| `apps/api/app/assumptions/workflow.py` | 95 | 14.2's statuses as legal transitions, each needing an actor and a reason |
| `apps/api/app/assumptions/gate.py` | 96 | 14.1, evaluated per scenario and per period |
| `apps/api/app/assumptions/impact.py` | 93, 94 | 14.8's preview, computed on a copy so nothing is saved |
| `apps/api/app/assumptions/proposals.py` | — | 7.7.a: the historical drivers the Section 13 schedules measured |
| `apps/api/app/api/templates/assumptions.html` | 90 | The 7.7 screen |

Forecast statements (specification Phase 10, items 97–108):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/forecast/build.py` | 97–107 | A scenario's approved assumptions become the engine's inputs; the engine forecasts |
| `apps/api/app/forecast/checks.py` | 108 | 15.20 across every scenario, and 15.21's label withheld for a reason it can defend |
| `apps/api/app/forecast/views.py` | — | 15.4's drivers by period, and 7.8.d's actual/estimate labels |
| `apps/api/app/api/templates/forecast.html` | — | The 7.8 screen, with the scenario comparison |

DCF valuation (specification Phase 11, items 109–120):

| Path | Item | What it does |
|---|---|---|
| `model/timing.py` | 112, 113 | 16.11's convention, 16.12's exact fraction, 16.13's precision policy |
| `apps/api/app/valuation/inputs.py` | 111 | Every WACC input as a dated, sourced observation |
| `apps/api/app/valuation/build.py` | 109–118 | The DCF, driven from a scenario, refusing all at once |
| `apps/api/app/valuation/checks.py` | 115 | 16.21's terminal share, and 16.22's warning that is not a failure |
| `apps/api/app/valuation/sensitivity.py` | 119 | 16.23's grid, centred on the valuation it varies |
| `apps/api/app/api/templates/valuation.html` | — | The 7.9 screen |

Dashboard and design system (specification Phase 12, items 121–130):

| Path | Item | What it does |
|---|---|---|
| `packages/design-tokens/fonts.css` | 122 | Source Serif 4 and Inter, self-hosted with their OFL text |
| `apps/api/app/dashboard/status.py` | — | 7.1.b's seven statuses |
| `apps/api/app/dashboard/standing.py` | — | Each one computed from what the model contains |
| `apps/api/app/dashboard/navigation.py` | 123 | The shell, with unreachable sections dimmed and still reachable |
| `apps/api/app/dashboard/cards.py` | 125 | Period, scenario, source and status on every card |
| `apps/api/app/dashboard/charts.py` | 126 | Charts that cannot be built without a text summary and a CSV |
| `apps/api/app/api/templates/index.html` | 124 | The 12-column portfolio |

Diagnostics, lineage and release readiness (specification Phase 13, items 131–137):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/diagnostics/registry.py` | 131 | Section 17's thirty checks as data, generated from `validation-policy.md` |
| `apps/api/app/diagnostics/run.py` | 131 | Each clause mapped onto the code that already answers it; PASS, FAIL, or SKIP with its reason |
| `apps/api/app/diagnostics/lineage.py` | 132 | A page to a valuation, in either direction, saying where the chain widens |
| `apps/api/app/diagnostics/audit.py` | 134 | The audit log made searchable: who, what, which entity, when |
| `apps/api/app/diagnostics/benchmark.py` | 135 | What the benchmark covers, without making the claim 4.20 forbids |
| `apps/api/app/diagnostics/release.py` | 136, 137 | The checklist, and a gate that blocks on every outstanding check because F-4 is unratified |
| `apps/api/app/api/templates/diagnostics.html` | 133 | The 7.10 screen, with the dependency graph |

Exports (specification Phase 14, items 138–144):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/display.py` | — | One display precision for every screen and every export, with 4.19's tooltip |
| `apps/api/app/exports/version.py` | 142 | 21.7's model version: a digest of what the model contains, not a counter |
| `apps/api/app/exports/gather.py` | — | 21.1's sixteen tables, gathered once from the screens' own view functions |
| `apps/api/app/exports/schema.py` | 138 | The versioned JSON schema, and a validator that refuses to check it partially |
| `apps/api/app/exports/json_export.py` | 138 | Every number as a decimal string, validated on the way out |
| `apps/api/app/exports/csv_export.py` | 139 | Injection protection that leaves negative numbers alone |
| `apps/api/app/exports/xlsx_export.py` | 140 | The workbook, and a note on every value a spreadsheet cannot hold |
| `apps/api/app/exports/pdf_export.py` | 141 | 21.6's nine sections, drawn with the PDF library already here |
| `apps/api/app/api/templates/exports.html` | — | The 7.11 screen |

Security and operations (specification Phase 15, items 145–153):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/security/credentials.py` | 145 | A password hashed with `hashlib.scrypt`, held in the environment |
| `apps/api/app/security/sessions.py` | 145 | A signed cookie with an absolute eight-hour life |
| `apps/api/app/security/guard.py` | 145 | The middleware that defaults to closed, and replays the body |
| `apps/api/app/security/csrf.py` | — | 20.12's token, derived from the session rather than stored |
| `apps/api/app/security/authorization.py` | 146 | 20.7, where "not yours" answers exactly like "does not exist" |
| `apps/api/app/security/sandbox.py` | 147 | PDF parsing in a child process, and what that does not buy |
| `apps/api/app/security/scanning.py` | 147 | 20.9's hook, reporting "not scanned" rather than "clean" |
| `apps/api/app/security/ratelimit.py` | 148 | 20.14, by window and by concurrency |
| `apps/api/app/security/logging.py` | 149 | Identifiers, never values, redacted on the way out |
| `apps/api/app/security/backup.py` | 150 | A snapshot, and the restore that re-hashes every byte |
| `apps/api/app/security/retention.py` | 151 | 2.6.c's deletion, behind 20.18, leaving a tombstone |
| `apps/api/app/security/repository_scan.py` | 152 | No source PDF and no secret in Git, checked in CI |
| [`docs/incident-response.md`](docs/incident-response.md) | 153 | What to do, and what this system does not defend against |

Final verification (specification Phase 16, items 154–168):

| Path | Item | What it does |
|---|---|---|
| `pyproject.toml` | 154, 155 | Ruff and mypy, with a reason beside every rule and every exclusion |
| `apps/api/app/verification/plan.py` | 156–162 | Section 22's fifty-five clauses, mapped onto the tests that cover them |
| `apps/api/app/verification/report.py` | 168 | The release-readiness report: every row the result of running something |
| [`docs/release-readiness.md`](docs/release-readiness.md) | 168 | Its output, regenerated in CI so it cannot go stale |

Deployment (specification Phase 17, items 169–180):

| Path | Item | What it does |
|---|---|---|
| `apps/api/app/security/headers.py` | 175 | Every security header, from the application so a proxy cannot drop them |
| `apps/api/app/verification/build_info.py` | 178, 180 | The commit, the schema version and the formula fingerprint, on `/health` |
| `apps/api/app/verification/smoke.py` | 172, 179 | Sixteen checks that never authenticate, so they cannot expose a filing |
| [`docs/deployment.md`](docs/deployment.md) | 169–180 | The runbook, and §6: the four items only the owner can answer |

Documentation:

| Path | What it is |
|---|---|
| [`docs/WORKFLOW.md`](docs/WORKFLOW.md) | Each of the 37 steps mapped to the code implementing it |
| [`docs/website-build-spec.md`](docs/website-build-spec.md) | The web application specification, verbatim |
| [`docs/decision-ledger.md`](docs/decision-ledger.md) | All 37 Section 2 decisions, and findings F-1 to F-36 |

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

534 tests, no network and no API key. Two trees: `tests/` is the calculation
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
- `apps/api/tests/integration/test_mapping.py` — Phase 5 end to end, including
  the test that matters most: a fully mapped filing produces facts that satisfy
  all seven verification conditions. Also the ones that stop it being easy —
  a split that loses three units is refused, a mapping that would double-count
  cannot be approved, and a finding raised against a wrong mapping does not
  survive the mapping being fixed.
- `apps/api/tests/integration/test_statements.py` — the golden historical
  model: every cell of all three statements, exact, built from a PDF. Plus the
  tests that keep the checks honest — a corrupted total makes the balance
  check FAIL rather than plugging, a corrupted subtotal breaks the cash
  roll-forward, and the net-income linkage fails when the two statements
  disagree. The last of those matters most: before Phase 6 that check compared
  one figure with itself and could not fail.
- `apps/api/tests/unit/test_chart.py` — asserts the canonical chart and
  `model/accounts.py` cannot drift apart, and that the chart's expected-sign
  and working-capital tags agree with the conventions the engine states in
  prose. `test_every_line_has_a_real_definition` rejects a stub; it caught four
  on its first run.
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

The workflow starts at STEP 1 with a PDF already in hand, and the system now
carries it from there to the engine's input files: extracted, reviewed,
mapped, approved, checked, exported. STEP 4 transcription is no longer manual
for a text-native filing.

What it does not do is the forecast. `assumptions.yaml` and `valuation.yaml`
are deliberately not written by the export — a beta, a risk-free rate and a
terminal growth rate are facts about a market on a date, not lines in a
document, and the engine refusing to run without them is the behaviour this
repository exists to have.

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
