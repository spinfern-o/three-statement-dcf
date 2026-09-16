# Decision ledger

Required by [`website-build-spec.md`](website-build-spec.md) Section 2 and
Section 23 Phase 0. Section 2 is explicit:

> If an answer is unavailable, display it as OPEN in the decision ledger. Build
> only parts that do not depend on it. Do not replace OPEN with an inferred
> answer.

Every decision below is therefore **OPEN** unless a specific, citable answer
exists. Nothing here is inferred. "Recommended" records what the specification
itself recommends, which is not the same as a decision having been made.

| Status | Meaning |
|---|---|
| **CONFIRMED** | Answered by the owner, with date and reason recorded |
| **OPEN** | No answer exists. Work depending on it must not begin |
| **N/A** | Established as not applicable, with reason |

Last reviewed: 2026-09-16. Recorded by: Claude (implementing agent).

**All 37 decisions are answered as of 2026-09-16.**

Two by the owner directly: **2.2.a** (private hosted) and **2.2.b** (single
user — the owner alone). The remaining 35 were **delegated**: the owner
instructed the implementing agent to decide them ("do single user just me and
everything else you can assume", 2026-09-16).

That delegation is why these are recorded CONFIRMED rather than inferred.
Section 2 forbids *replacing OPEN with an inferred answer*; it does not forbid
the owner delegating the choice. Each delegated row names its decider and the
reasoning, so any of them can be overturned by saying so — none is load-bearing
on anything already built.

**One line was held, and matters.** The delegation covers *policy*: which
method, which source, which convention. It does **not** cover *values* — a
risk-free rate, a beta, a company's fiscal year-end, a share count. Those are
facts about a specific filing or a specific market on a specific date, and
inventing one would be precisely the fabrication rules 1.1 and 1.4 forbid and
that this entire codebase is built to refuse. So 2.4.a–f and 2.5.a–h below fix
the **source and convention**; the number itself still arrives at model time,
sourced and dated, and the engine still refuses to run without it.

---

## 2.1 Product identity

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.1.a | Product name | **CONFIRMED** (delegated) | **"Three-Statement DCF"** — plain and descriptive, matching the repository. Invented branding is the easiest thing to get wrong on someone else's behalf and the cheapest to change later | — |
| 2.1.b | Logo or text-only wordmark | **CONFIRMED** (delegated) | **Text-only wordmark.** No logo asset exists, and commissioning one is not an implementation decision | — |
| 2.1.c | Company/owner name for footer and exports | **CONFIRMED** (delegated) | **"spinfern-o"** (the owner's GitHub handle), with the footer line "Private model — not for distribution". A real legal name was not assumed, and the owner's email address is deliberately not used anywhere in output | — |

Note: the repository description reads "three statement dcf model done by astra".
That is a repository description, not a confirmed product name, and has not been
treated as one.

## 2.2 Use and access

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.2.a | Local-only, private hosted, or public | **CONFIRMED** | **Private hosted application** — owner (spinfern-o), 2026-09-16, relayed via the parent session | *(was: Phase 17 deployment entirely; DB choice (3.2.d); security model depth — all now unblocked)* |
| 2.2.b | Single user or multi-user | **CONFIRMED** | **Single user — the owner alone.** Stated by the owner, 2026-09-16 | — |
| 2.2.c | Authentication required | **CONFIRMED** (delegated) | **Yes.** Not a preference: 2.2.a puts confidential financial PDFs behind a network endpoint, and 20.1 classifies them confidential. A single-user hosted app still needs one credential in front of it | — |
| 2.2.d | Roles | **CONFIRMED** (delegated) | **One role: owner.** 20.6 applies RBAC "if multi-user", and 2.2.b says single — so RBAC is **N/A**, not deferred. The `User.role` enumeration collapses to a single value, and the reviewer/approver in 14.x is the same person as the author | — |

**2.2.a is answered: private hosted.** Three consequences follow from the
specification's own wording, not from inference:

- **3.2.d — PostgreSQL.** The spec permits SQLite "only for a documented
  single-user local prototype", which a hosted deployment is not.
- **20.2 — encryption in transit and at rest now binds.** The requirement is
  written "for hosted deployments".
- **Phase 17 and Section 20 are no longer blocked on 2.2.a**, and
  [`security-model.md`](security-model.md) §1's *Private hosted* column is now
  the governing one rather than one of three branches.

2.2.b was subsequently answered **single user**, which makes 20.6's RBAC
**N/A** rather than deferred — the requirement is written "if multi-user".

## 2.3 Source documents

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.3.a | One PDF per company or multiple | **CONFIRMED** (delegated) | **One primary filing per model version**, many model versions per company. This keeps 4.6 unit normalization genuinely out of scope (one document, one scale) rather than half-built — see F-8. Multiple documents is the first thing to revisit when restatements matter | — |
| 2.3.b | Annual only, or annual and quarterly | **CONFIRMED** (delegated) | **Annual only.** Mixing cadences is what rule 1.7 forbids, and quarterly adds seasonality the forecast engine does not model | — |
| 2.3.c | Text-native only, or scanned too | **CONFIRMED** (delegated) | **Text-native only.** The single largest scope decision here: OCR brings Tesseract, a job queue, and a whole confidence-scoring model (10.8, 10.28) whose scoring function the spec does not define. A scanned PDF is rejected at upload with a clear message rather than silently OCR'd badly | — |
| 2.3.d | May public filings/XBRL cross-check the PDF | **CONFIRMED** (delegated) | **No.** Consistent with 2.3.a and with keeping egress closed | — |
| 2.3.e | May external market data be retrieved | **CONFIRMED** (delegated) | **No — manual entry with a cited source.** The engine already requires a source string for every cost-of-capital input (STEP 25–27). An automated fetch would supply the number while weakening the citation | — |

2.3.c materially changes cost and complexity: OCR brings a job queue, a
Tesseract/OCR dependency, and a whole class of confidence handling (10.8, 10.28).

## 2.4 Model policy

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.4.a | Reporting currency | **CONFIRMED** (delegated) | **Policy: one currency per model, taken from the filing and confirmed at STEP 1. No mixing, ever** (rule 1.10). The currency *value* comes from the filing; there is no default | — |
| 2.4.b | Display unit | **CONFIRMED** (delegated) | **Policy: as filed.** The engine calculates in the filing's units and states them; it does not convert (see F-8 — 4.6 normalization is unimplemented, and 2.3.a keeps it unnecessary). Display precision: 1 decimal place | — |
| 2.4.c | Fiscal year-end | **CONFIRMED** (delegated) | **Policy: from the filing, confirmed at STEP 1.** Per-company fact, not a global setting | — |
| 2.4.d | Number of historical periods | **CONFIRMED** (delegated) | **Policy: every year the filing provides; minimum 2, target 3.** Two is the floor because the first change-in-NWC needs a prior year (STEP 17). STEP 3 still forbids inventing a missing year | — |
| 2.4.e | Number of forecast periods | **CONFIRMED** (delegated) | **5 years.** The spec's own worked example, and the horizon beyond which annual drivers stop meaning much | — |
| 2.4.f | Cadence | **CONFIRMED** (delegated) | **Annual**, consistent with 2.3.b | — |
| 2.4.g | FCFF or FCFE | **CONFIRMED** (delegated) | **FCFF.** The spec's own recommendation, and what the engine implements | — |
| 2.4.h | Year-end or mid-year discounting | **CONFIRMED** (delegated) | **Year-end.** What STEP 29 specifies and the engine implements. Mid-year is the more defensible convention for a real valuation and is the first thing to revisit; switching is a change to one function plus 16.12's time fractions, which need dated periods the model does not yet have | — |
| 2.4.i | Gordon Growth, exit multiple, or both | **CONFIRMED** (delegated) | **Gordon Growth only.** Exit multiple needs a sourced comparable set (16.24) that 2.3.e's closed egress cannot supply | — |
| 2.4.j | Leases treated as debt in the bridge | **CONFIRMED** (delegated) | **Yes, when the filing discloses a lease liability.** Post-IFRS-16/ASC-842 the liability is on the balance sheet; excluding it from the bridge while including the asset would overstate equity value | — |
| 2.4.k | Stock-based compensation | **CONFIRMED** (delegated) | **Expensed in EBIT, added back as non-cash in CFO, and credited to common equity** — which is exactly what the engine already does. Not treated as a "real" cash cost removed from FCFF: that is a defensible alternative, and it is not the reported treatment | — |
| 2.4.l | Minority interest, pensions, associates, investments | **CONFIRMED** (delegated) | **Explicit bridge lines, defaulting to zero, printed whether or not they are zero** — already the engine's behaviour, and what 16.19's "do not silently ignore these items" requires | — |
| 2.4.m | Tax-loss carryforwards and deferred taxes | **CONFIRMED** (delegated) | **Not modelled. Effective tax rate only**, with the basis stated (STEP 16). NOL scheduling needs disclosure depth a single annual filing rarely gives, and a half-modelled NOL is worse than none | — |

The existing Python engine already implements an FCFF, year-end, Gordon-Growth
model. **That is a prototype default, not a confirmation of 2.4.g/h/i.** It was
built to the 37-step workflow, before this specification existed.

## 2.5 Market assumptions

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
These fix the **source and convention**. Every one still requires a dated,
cited value at model time, and the engine refuses to run without it — that
refusal is the point of STEP 25–27 and is not weakened here.

| ID | Decision | Status | Source / convention decided | |
|---|---|---|---|---|
| 2.5.a | Valuation date | **CONFIRMED** (delegated) | **The date the model version is released**, recorded on the version and never implied | — |
| 2.5.b | Risk-free rate | **CONFIRMED** (delegated) | **US Treasury constant-maturity 10-year yield**, observed on the valuation date, cited with that date. Ten-year to match a five-year explicit forecast plus a perpetuity | — |
| 2.5.c | Beta | **CONFIRMED** (delegated) | **Levered beta, 5-year monthly, against a broad domestic index**, provider and observation date both recorded. Monthly over weekly to damp thin-trading noise | — |
| 2.5.d | Equity risk premium | **CONFIRMED** (delegated) | **A published implied ERP**, most recent edition, cited with its publication date. Implied over historical: it reflects prices on the valuation date rather than a realised average over a window nobody chose | — |
| 2.5.e | Pre-tax cost of debt | **CONFIRMED** (delegated) | **The company's own disclosed weighted-average borrowing rate** where the filing gives one; otherwise the yield on comparable-rated debt of similar tenor, with the comparable named | — |
| 2.5.f | Capital structure | **CONFIRMED** (delegated) | **Current market values**, not book and not a target. 16.8 and STEP 27 both say market; a target structure is a second assumption stacked on the first | — |
| 2.5.g | Terminal growth | **CONFIRMED** (delegated) | **Justified per model and capped at long-run nominal GDP growth for the reporting currency's economy.** A perpetuity growing faster than the economy eventually is the economy. The engine already enforces WACC > g (STEP 31); the cap is the modeller's discipline above it | — |
| 2.5.h | Diluted shares | **CONFIRMED** (delegated) | **The diluted weighted-average share count from the EPS note**, or the cover-page count where more recent, with the measurement date recorded (STEP 35) | — |

None of these are derivable from a filing. All require an external, dated source.

## 2.6 Export and retention

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.6.a | Required exports | **CONFIRMED** (delegated) | **All four, in this order: JSON, CSV, XLSX, then PDF.** JSON first because 21.5's versioned schema is what makes an export reproducible; the PDF report is the most presentation work for the least verification value | — |
| 2.6.b | Retention | **CONFIRMED** (delegated) | **Indefinite until the owner deletes.** Single user, private, own data — a retention clock would delete the owner's own work to satisfy a policy nobody imposed | — |
| 2.6.c | May an administrator permanently delete data | **CONFIRMED** (delegated) | **Yes**, with the explicit confirmation 20.18 requires. The owner is the only user; a delete they cannot perform is data they cannot control | — |
| 2.6.d | Backup and restore | **CONFIRMED** (delegated) | **Nightly encrypted snapshot of database and object storage, 30-day retention, restore verified quarterly.** An untested backup is not a backup | — |

---

## Attachment referenced by Section 0

| Item | Status | Detail |
|---|---|---|
| `Homework 2 (1)(1).png` | N/A | No such file reached the implementing session. A filesystem search of the environment and the repository found nothing matching. Nothing was excluded on its account, and no financial value has been taken from it. Section 0 says to stop and ask if it was intended to be used — it cannot be used, because it is not present. If it matters, it must be supplied. |

---

## Findings that are not Section 2 decisions

Recorded here because they change what can truthfully be claimed.

### F-1 — RESOLVED (2026-09-16). The engine now uses exact decimal arithmetic

**Was: blocks any claim of Section 4 compliance. Now: closed.**

The calculation path was ported to `Decimal`. `grep` now finds zero
`float()` coercions in `model/` and 132 `Decimal` references. What follows
is the original finding, kept for the record, then the resolution.

#### Original finding

Rules 1.15 and 4.4 prohibit binary floating point in the authoritative
calculation engine. The merged Python engine in `model/` uses Python `float`
throughout — `grep` finds four explicit `float()` coercions and zero uses of
`Decimal`.

This is a real, reproducible defect, not a theoretical one:

```
float:   0.7 * 0.1      = 0.06999999999999999
Decimal: 0.7 * 0.1      = 0.07
float:   0.1 summed 10x = 0.9999999999999999   (== 1.0 is False)
Decimal: 0.1 summed 10x = 1.0
```

The engine's existing precision tests pass, but they compare float against
float. They establish that the implementation matches the specified formulas;
they do **not** establish Section 4 compliance, because Section 4.4 rules out
the arithmetic on both sides.

#### Resolution

The authoritative path is now `Decimal` end to end.

- `model/numeric.py` declares the context: 50 significant digits (4.7 requires
  at least 28), `ROUND_HALF_EVEN` (4.8), and traps on `InvalidOperation`,
  `DivisionByZero` and `Overflow` so a NaN or Infinity can never reach a
  released value (17.27, 18.13).
- `D()` **refuses** floats rather than converting them. Converting a float
  preserves its error instead of removing it, so a port that accepted floats
  would look compliant and not be. This is the same "refuse rather than
  default" stance the rest of the codebase takes.
- `model/yaml_exact.py` was necessary and is the subtle part. PyYAML resolves
  a numeric scalar to a float *during parsing*, so `yaml.safe_load` had
  already destroyed the value before any conversion could run. Numeric
  scalars are now preserved as the text the file contained, satisfying 4.2's
  requirement that monetary inputs be handled as decimal strings at the
  boundary.
- The context is installed on import in `model/__init__.py`. This was found
  the hard way: `power()` ran inside an explicit 50-digit context while the
  division around it ran at Python's default 28, so a discount factor was
  computed at one precision and divided at another. Mixed precision is the
  exact class of error this port removes.

**Limit of the claim, stated precisely.** Decimal is exact for addition,
subtraction, multiplication, and any division that terminates. It is *not*
exact for a division that repeats: `x / 365` and `x / 6` are rounded at 50
significant digits, so two mathematically equal sums built in a different
order can differ by one unit in the last place. The measured worst case
across the randomized sweep is **1E-46 absolute, 3.4e-50 relative** — forty
orders of magnitude inside the 0.0001% contract, and far below any real
modelling error. `tests/test_precision.py` asserts exact equality where no
division is involved (the PP&E, debt and retained-earnings schedules) and a
precision-derived bound where it is.

Verification, per 4.15–4.16: `test_independent_recomputation` rebuilds all
seven years with its own loader and its own Decimal construction — sharing no
helper with the engine, as 4.15 requires — and compares 192 values. All agree
**exactly**. `test_randomized_identity_sweep` covers 150 further models across
nine orders of magnitude. `test_no_float_survives_in_the_calculation_path`
asserts every released value is a `Decimal`.

Still outstanding for full Section 4 coverage: 4.16 names EBITDA, CFO/CFI/CFF
and change-in-NWC among the benchmarked outputs; the benchmark covers
CFO/CFI/CFF and change-in-NWC but the model has no EBITDA line, because the
37-step workflow never defines one (12.1.f makes it conditional on a visible
bridge).

### F-2 — Section 26's design observations could not be independently verified

findash.ai renders its content with JavaScript; fetching the page yields only
the document title. The colors and typefaces in Section 6.1–6.2 are recorded as
the owner's stated observations. Section 6.4 requires token values to pass
contrast testing regardless, which governs what is actually adopted.

### F-3 — `main` has no branch protection

CI (`.github/workflows/tests.yml`) runs on pull requests but is not a required
check, so it cannot block a merge. PR #1 merged into `main` with no CI in the
repository at all. Enabling a required status check is a repository-settings
action the implementing agent cannot perform.

### F-4 — Section 17 does not assign a severity to any of its thirty checks

**Blocks Phase 13 item 137 (prevent release when CRITICAL/ERROR checks remain).**

Section 17 defines four severity levels and their consequences, then lists
thirty required checks — and never says which check carries which level.
Four are forced by rules elsewhere in the specification:

| Check | Severity | Forced by |
|---|---|---|
| 17.24 WACC > g | CRITICAL | 16.16 "Block calculation when WACC <= g"; rule 1.18 |
| 17.26 diluted shares nonzero and sourced | CRITICAL | 16.20 |
| 17.27 no NaN/Infinity/null released | CRITICAL | 17.27's own wording; 4.4 |
| 17.28 benchmark meets Section 4 tolerance | ERROR | 4.20 |

The remaining twenty-six are not derivable from the text.
[`validation-policy.md`](validation-policy.md) §1 proposes an assignment and
labels every proposed row as a proposal. A release gate cannot be built on a
proposal, so item 137 is blocked until the owner confirms the mapping.

This is not a Section 2 decision — it is a gap in Section 17 — so it is
recorded here rather than in the tables above.

### F-5 — Section 9 references a Scenario entity it never defines

`Assumption.scenario_id` (9.10) and `CalculatedValue.scenario_id` (9.12) are
required fields, and `ValidationResult.scenario_id_optional` (9.13) references
one, but **Section 9 defines no Scenario entity**. Section 14.6–14.9 describes
the behaviour it must have — Base/Upside/Downside plus custom, inherited
assumption lineage on copy, and names that must not imply probability unless
probability is explicitly modelled and sourced — so the requirements exist and
the schema row does not.

Section 9 also has nowhere to record the engine's `assumptions.Conflict`
(STEP 11): two dated sources that disagree, with a mandatory explicit choice
and rationale. The nearest Section 9 fit is a pair of `Assumption` rows plus an
`AuditEvent`, which loses the structure that makes the conflict legible.

Neither is answerable by inference. Both need the owner, or an amendment to
Section 9.

### F-6 — RESOLVED in #7. `--rel-tol` / `--abs-tol` crashed with an unhandled traceback

**Fixed 2026-09-16.** Both flags now parse as decimal strings (4.2), and an
unparseable value exits 2 instead of raising. Regression test
`test_f6_tolerance_flags_accept_a_decimal_string`, verified to fail against the
unfixed `run_model.py`. Original finding follows.

**Reproducible. [`README.md`](../README.md) documents these flags as the
supported override mechanism, and they do not work.**

`run_model.py` declares both with `type=float`. `Tolerance.__post_init__` then
calls `numeric.D()`, which **refuses floats by design** (specification 1.15,
4.4). The defaults are `Decimal` constants and pass through untouched, so the
failure appears only when a user actually supplies the flag:

```
$ python3 run_model.py --inputs tests/fixtures --rel-tol 1e-8
...
model.numeric.PrecisionError: Tolerance.rel arrived as a float (1e-08).
```

The whole report is printed first, then the process dies on an uncaught
exception after the sensitivity table. The `except ProvenanceError` block in
`main()` does not cover it, because `PrecisionError` derives from `ValueError`,
not from `ProvenanceError`.

The fix is one line per flag (`type=str`, letting `D()` parse the decimal
string — which is what 4.2 asks for anyway). It was **not applied**: the
session that found it was scoped to documentation only, and `run_model.py` was
explicitly out of scope.

### F-7 — Three narrower defects found while reading the engine

None was fixed, for the same scope reason. All are verified, not suspected.

**F-7a. RESOLVED in #7.** `_shift_wacc` now raises rather than returning an
unshifted cost of capital labelled with a WACC it did not reach. Regression test
`test_f7a_shifting_wacc_refuses_rather_than_missing_its_target`. Original
finding: **`sensitivity._shift_wacc` silently fails when `beta = 0`.**
The line `implied_erp = (implied_ke - base.risk_free_rate) / base.beta if base.beta else ZERO`
returns a zero ERP when beta is zero — but with beta zero the cost of equity
equals the risk-free rate regardless of the ERP, so the target WACC is never
reached. The `SensitivityCell` is nonetheless labelled with the target WACC it
did not achieve. Verified by direct construction: a base with `beta = 0` and
`wacc = 0.039166…` shifted to a target of `0.12` returns a `CostOfCapital`
whose `.wacc` is still `0.039166…`. Beta of exactly zero is an unusual input;
the failure is silent, which is the class of thing this repository exists to
prevent.

**F-7b. RESOLVED in #7.** `report.valuation_block` now prints "undefined"
instead of formatting `None`. Regression test
`test_f7b_report_survives_an_undefined_terminal_value_share`. Original finding:
**`Valuation.tv_share_of_ev`'s None guard is not honoured by its only
consumer.** The property returns `None` rather than dividing by zero when
enterprise value is zero (specification 17.27). `report.valuation_block` then
formats it with `f"{valuation.tv_share_of_ev:.1%}"`, which raises `TypeError`
on `None`. The guard is correct; the call site defeats it.

**F-7c. RESOLVED in #7.** Declaring both `dividend_payout_ratio` and
`dividends_amount` is now rejected, as it already was for COGS, opex and CapEx.
Regression test `test_f7c_dividends_reject_two_declared_methods`. Original
finding: **Dividends use silent precedence where every comparable driver
refuses.** `forecast._pick_driver` rejects declaring both a percentage and an
absolute driver for COGS, opex or CapEx in the same year — STEP 14/18 require
one stated methodology per line. Dividends do not go through `_pick_driver`:
declaring both `dividend_payout_ratio` and `dividends_amount` silently prefers
`dividends_amount`. Inconsistent with the engine's own stated stance, and with
14.5.

### F-8 — Declared helpers in `model/numeric.py` that nothing calls

Not defects, but they mean two specification requirements have no code path
behind them despite appearing to.

- **`quantize_for_display`** is the declared 4.9/4.18 display boundary.
  `model/report.py` formats with Python f-strings instead. The result is the
  same under the installed context, but the declared helper is unexercised and
  no test asserts check 17.29's tie between displayed and stored values.
- **`relative_error`** implements specification 4.10 verbatim. The checks use
  `Tolerance.close`, a different comparison. **No runtime code measures
  relative error in the specification's terms**; `tests/test_precision.py`
  does the equivalent independently.

Similarly, **`profile.Units.multiplier`** is defined and never called anywhere
in `model/`, `run_model.py` or `tests/`. The engine performs no unit
normalization, so specification 4.6 (normalize to one base unit while retaining
the source value) is unimplemented. For a single-document model this is
indistinguishable in result; it becomes a real gap the moment 2.3.a permits
more than one PDF per company.

### F-9 — The engine's error messages conflict with 20.16 under hosted deployment

Not a defect today, and worth recording before the website inherits it.

The engine's exceptions are deliberately informative: `D()` prints a refused
float's exact decimal expansion, `Ledger.require()` names the account, year and
step, `_balance_check` reports the delta, `RollForward.add_year` prints both
balances. For a local CLI run by the data's owner this is correct and is most
of what makes the tool usable.

Several of those messages contain financial values. Specification 20.16
requires private data be redacted from application errors, so under **OPEN
(2.2.a)** private-hosted or public, they must not cross the API boundary in
that form. The resolution is a structured error code plus a redacted message at
the boundary, with the full diagnostic retained server-side for the authorized
owner — not a quieter engine. Phase 2 item 23 ("define error codes and
severity") is where that belongs; it depends on no OPEN decision and has not
been done.

### F-10 — RESOLVED in #7. Two of the twelve STEP 37 checks tested the same identity

**Fixed 2026-09-16.** The two are now distinct: "Forecast cash flow
reconciliation" checks each cash-flow subtotal against the items beneath it,
and "Ending cash linkage" checks the cash balance against those subtotals. The
FCFF check now rebuilds its terms from the statements instead of re-calling
`fcff_inputs`. `Ledger.cross_check` is wired in as a thirteenth check (17.10).
The panel reports **13 PASS**, all names distinct. Original finding follows.

`checks.run_all_checks` calls `_cashflow_reconciliation` with **identical
arguments** for both "Forecast cash flow reconciliation" and "Ending cash
linkage". The panel is faithful to STEP 37, which lists both — but they are one
identity tested twice, so `12 PASS` is eleven pieces of evidence, not twelve.

Separately, "FCFF matches three-statement forecast" recomputes
`ForecastResult.fcff_inputs(year)` — the same function `build_fcff` built the
`FCFFYear` from. It verifies nothing mutated in between; it does not verify
what 17.22 asks, because there is no independent assembly to disagree with.
The model's underlying property is real (FCFF genuinely comes from the
forecast, satisfying 24.9); the check's evidentiary value is weaker than its
name. See [`validation-policy.md`](validation-policy.md) §3.


### F-11 — OPEN. Refusing a whole filing for one scanned page may be too strict

Decision 2.3.c is **text-native only**, and
[`source-policy.md`](source-policy.md) §3 states the consequence: "an
image-only page is a hard rejection with an explanatory message rather than a
silent empty extraction." Phase 3 implements exactly that — `ING-010-08`
refuses the document and names the pages.

**The practical problem.** Real filings are not uniformly text-native. A 10-K
routinely carries a scanned signature page, a scanned auditor's letter, or an
image-only exhibit, inside a document that is otherwise perfectly readable.
Under the rule as written, one such page refuses the entire filing, and the
owner's only recourse is to split the PDF by hand — which produces a document
whose SHA-256 is no longer the filing's.

**Why it was implemented as written anyway.** The policy document is the
contract, it was written and shipped before this phase, and changing it
mid-implementation without the owner is worse than implementing it. The
refusal is also the safe direction: it never produces a model with pages
silently missing.

**The proposed amendment**, for the owner to accept or reject:

> An image-only page refuses the document only when it falls inside a page
> range the reviewer has mapped as a financial statement or a relevant note
> (10.14). Outside that range it is recorded as a document-level finding the
> reviewer must acknowledge, listed by page, and no fact is created from it.

That requires the source map, which is Phase 4 work, so the change cannot land
before then. Until it does, the current behaviour stands.

### F-12 — RESOLVED in Phase 3. The extraction lifecycle enumerations were OPEN

[`data-dictionary.md`](data-dictionary.md) recorded
`SourceDocument.extraction_status`, `SourceDocument.verification_status` and
`ReportedFact.verification_status` as **OPEN**: required fields whose value
sets the specification describes behaviourally but never enumerates. Phase 2
item 24 asked for lifecycle states and legal transitions and was not done.

Item 29 ("implement extraction job states") cannot be built on an open
enumeration, so Phase 3 closed the extraction half of it:
[`apps/api/app/extraction/jobs.py`](../apps/api/app/extraction/jobs.py) defines
`JobState` (8 states), `LEGAL_TRANSITIONS` (the graph, asserted complete at
import), `DocumentVerificationState` and `FactVerificationState`. Three
properties are enforced rather than documented: every non-terminal state may
refuse or fail, every terminal state is terminal, and a transition without a
stated reason raises (10.33).

The design choice worth recording: **the graph has no backward edges.** A
re-extraction is a new job over the same stored document, not a rewind, because
10.33 requires the old job's history not be mutated.

Still open from Phase 2 item 24: the **model version** lifecycle (7.1.b's
Draft / Extracting / Needs Review / Validated / Forecast Ready / Valuation
Ready / Archived), which belongs to Phases 9-13 and has no implementation to
constrain it yet.

Phase 2 item 23 (error codes) is in the same position, and the same half is
now done: `ING-010-NN` and `ING-020-NN` in
[`apps/api/app/core/errors.py`](../apps/api/app/core/errors.py), on the pattern
[`validation-policy.md`](validation-policy.md) set with `VAL-017-NNN`. Each
code carries the specification rule it enforces.

### F-13 — RESOLVED in Phase 3. The confidence scoring function was OPEN

[`source-policy.md`](source-policy.md) §7 left the scoring function
deliberately open: 10.28 requires a score and 10.29 requires a review
threshold, but the specification never defines how the score is computed, and
inventing a formula would be unjustified precision.

That was right about the danger and insufficient as a stopping point — item 36
cannot ship without a score. The resolution is to define it as the one thing
defensible without calibration data: **the fraction of eight named evidence
conditions the fact satisfies**, listed in `EvidenceCheck` and computed
exactly. It satisfies §7's three stated requirements (monotonic in evidence
rather than plausibility, never raised by a downstream success, and
independent of the blocking reason codes), and it is explainable — a reviewer
sees which conditions failed, not a number.

**What it is not**, stated in the module and repeated here: it is not a
probability. 0.75 means six of eight evidence conditions hold, not a
three-in-four chance the number is right. Nothing downstream may treat it as a
likelihood.

The threshold is configuration (`INGEST_REVIEW_THRESHOLD`, default 0.875 — "at
most one piece of evidence missing"), which 7.10 requires be shown on the
diagnostics page.


### F-14 — RESOLVED by decision. Phase 4 deviates from 3.1.a, deliberately

Specification 3.1.a recommends **Next.js with TypeScript** for the front end.
The source room built in Phase 4 is **server-rendered HTML from FastAPI**
instead.

The reasoning is 3.1.b's own — "React Server Components only where they do not
complicate financial state":

- **The source room has no financial state to complicate.** It is a document
  annotation surface: a page image, rectangles drawn on it, a list of printed
  values, and a form that posts one decision with one reason. Nothing
  recalculates. Nothing is derived. Nothing changes as you type.
- **Every requirement in 6.6 is easier to meet in semantic HTML** than in a
  component tree — landmarks, heading order, labels, focus order and the
  error summary are all markup, and all of them are tested in
  `apps/api/tests/integration/test_accessibility.py` against a real browser.
- **No build step** means the review tool runs from a checkout, which matters
  for something whose whole job is to be opened next to a PDF.

Where React earns its place is **Phase 12's dashboard**: live recalculation,
charts, and 6.5.c's unsaved assumption edits marked as you type. That is the
right place to introduce it, and doing so does not require rewriting this —
the review room's URLs are the API.

Section 3 permits this explicitly ("If the repository already has a supported
stack, preserve it and document the deviation"); this is the documentation.
The cost is real and worth naming: two front-end idioms in one repository once
Phase 12 lands.

### F-15 — OPEN. The review application has no authentication

Decision **2.2.c is CONFIRMED: authentication is required.** The reasoning in
that row still holds — 2.2.a puts confidential financial PDFs behind a network
endpoint, and 20.1 classifies them confidential.

**It is not implemented.** `review_server.py` binds to `127.0.0.1` by default
and prints a warning if told to bind anywhere else, which is a mitigation, not
the requirement. Until a credential sits in front of it, this is a local
review tool, and deploying it as the private hosted application 2.2.a
describes would put filings on a network with nothing guarding them.

What it needs, and why none of it is guessed here: a session mechanism, a
credential store, and a decision about what the second factor is for a
single-user application — none of which is a Section 2 row, and all of which
belongs with Phase 15 (security and operations) rather than being half-built
now. Recorded so it cannot be mistaken for done.

---

---

## Work that is NOT blocked

Buildable now, because it depends on no OPEN decision:

- The `Decimal` calculation core and its context policy (Section 4.2–4.9), and
  the independent benchmark implementation (4.15) — resolves F-1.
- ~~Formula catalog and data dictionary as definitions (Phase 2, items 17–24).~~
  **Done 2026-09-16** for items 17, 18 and 21:
  [`data-dictionary.md`](data-dictionary.md),
  [`formula-catalog.md`](formula-catalog.md),
  [`source-policy.md`](source-policy.md),
  [`validation-policy.md`](validation-policy.md),
  [`security-model.md`](security-model.md).
  Still outstanding in Phase 2: **item 19** (API schemas), **item 20**
  (database schema and migrations — 3.2.d resolves to PostgreSQL now that
  2.2.a is answered; records are written to JSON files meanwhile), and
  **item 25** (owner review of these contracts).
  **Item 23** (error codes) and **item 24** (lifecycle states) were closed for
  ingestion by Phase 3 — see F-12. The model-version lifecycle and the check
  severities (F-4) are still open. **Item 9** (select the documented stack) is
  now answered for the front end as well — see F-14.
- Canonical chart of accounts and line-item definitions (11.1) — the engine's
  40 codes are catalogued in [`data-dictionary.md`](data-dictionary.md) §9.6,
  but **no account has a written definition**, which 11.3 mapping review needs.
- Validation check registry and severity model (Section 17), as declarations —
  registry written; **severity assignment blocked by F-4**.
- Design tokens as *named* tokens with contrast-tested candidate values (6.4).
- Adding a dependency-audit step to CI (3.5.c, 20.20),
  and printing the Section 25 disclaimer in the CLI report (20.19). None of
  these depends on an OPEN decision.

**Phase 4 (items 39–49) is built**, in
[`apps/api/app/review/`](../apps/api/app/review) and
[`apps/api/app/api/`](../apps/api/app/api), with
[`review_server.py`](../review_server.py) as its entry point: the source room
with the PDF page and its extracted values side by side (6.3.f), bounding-box
overlays, statement bookmarks, metadata confirmation, accept/correct/reject
with a mandatory reason, the audit trail, and review progress that reports
**zero verified facts** and says why. Design tokens are in
[`packages/design-tokens/`](../packages/design-tokens) with their contrast
ratios tested rather than asserted. Specification 22.7's keyboard and
screen-reader workflows run against a real browser in CI.

**Phase 3 (items 26–38) is built**, in
[`apps/api/app/extraction/`](../apps/api/app/extraction), with
[`ingest_pdf.py`](../ingest_pdf.py) as its entry point: signature validation,
SHA-256 custody and duplicate detection, write-once storage, the extraction job
state machine, text-native extraction with page geometry, page classification
with an image-only refusal (item 31 under 2.3.c — see F-11), metadata detection
in the UNCONFIRMED state, the deterministic locale/sign/unit parser, reason
codes and confidence, and 178 tests over eight committed fixture PDFs.

Nothing is blocked on a Section 2 decision any more. What remains unbuilt is
unbuilt for want of work, not for want of an answer.

Two things are still genuinely open, and neither is a Section 2 row:

- **F-4** — Section 17 assigns a severity to none of its thirty checks.
  `validation-policy.md` proposes twenty-six and labels each a proposal. Release
  gating (Phase 13 item 137) cannot run on a proposal.
- **F-5** — Section 9 requires `scenario_id` and defines no Scenario entity.
  That is a specification amendment, not an implementation choice.
