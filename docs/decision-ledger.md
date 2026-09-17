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
Five are forced by rules elsewhere in the specification:

| Check | Severity | Forced by |
|---|---|---|
| 17.18 no required forecast assumption missing | CRITICAL | 14.1 "No forecast may calculate until all required assumptions have a status" |
| 17.24 WACC > g | CRITICAL | 16.16 "Block calculation when WACC <= g"; rule 1.18 |
| 17.26 diluted shares nonzero and sourced | CRITICAL | 16.20 |
| 17.27 no NaN/Infinity/null released | CRITICAL | 17.27's own wording; 4.4 |
| 17.28 benchmark meets Section 4 tolerance | ERROR | 4.20 |

Each of those five cites a rule stating a **consequence** — block calculation,
block release, do not compute the figure, do not make the claim — because the
consequence is what the level *means*. That is the test for a forcing rule, and
it is F-26's lesson.

The remaining twenty-five are not derivable from the text.
[`validation-policy.md`](validation-policy.md) §1 proposes an assignment and
labels every proposed row as a proposal.

**Phase 13 built item 137 anyway, and said what it was standing in for.** A
release gate cannot be built on a proposal, so
[`release.py`](../apps/api/app/diagnostics/release.py) does not use one: every
outstanding check blocks, failed and skipped alike, whatever severity it has
been proposed. That is strictly stricter than 137 under any assignment the
owner might make, so the gate cannot release a model 137 would have stopped —
it can only refuse one 137 would have allowed. `severity_is_unratified` is
carried on the result and printed on the screen, so the reader is told that
ratifying this finding is what would let the gate tell a blocking failure from
an acknowledged warning. **Confirming the twenty-five is still owner work.**

This is not a Section 2 decision — it is a gap in Section 17 — so it is
recorded here rather than in the tables above.

### F-5 — RESOLVED BY DESIGN in Phase 9. Section 9 referenced a Scenario entity it never defined

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

**Phase 9 designed the entity, because item 92 requires it.** The
specification constrains its behaviour in four places and its schema in none,
so `apps/api/app/assumptions/scenarios.py` is built from the behaviour and
every choice is listed here for the owner to overrule:

| Choice | Why | Where the specification says so |
|---|---|---|
| A scenario is a set of **overrides over a parent**, not a copy | 14.7 asks that a copied scenario retain inherited lineage. Copying values makes the child's provenance a snapshot that goes stale the moment the parent is corrected | 14.7 |
| Exactly one root, `base`, with no parent | Every variant is a variant **of** something; without a root, "differs from its parent" has no meaning for the first scenario | 14.6, 14.7 |
| Nearer scenario wins, and the parent's value stays reachable | What makes an override legible as an override rather than as a different number | 14.7 |
| A variant with **no differences from its parent is refused** | An Upside identical to Base is a label, not a case | 14.6 |
| A name asserting likelihood is **refused** unless a sourced probability is attached | This system models no distribution, so the claim would be unsupported | 14.9, 1.19 |
| Fields: `id`, `name`, `parent_id`, `description`, `created_by`, `created_at`, optional `probability` | Section 9's own conventions for the rows it does define | 9.8, 9.10 |

**The `Conflict` half of this finding is still open.** Section 9 still has
nowhere to record two dated sources that disagree with an explicit choice and
rationale, and `model/assumptions.py:Conflict` still has no Section 9 row.
Phase 9 did not need it -- the assumptions it stores each have one source --
but the moment two do, the nearest Section 9 fit is a pair of `Assumption`
rows plus an `AuditEvent`, which loses the structure that makes the conflict
legible. That remains an owner decision or a Section 9 amendment.

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


### F-16 — RESOLVED in Phase 5. The canonical chart had no definitions

[`data-dictionary.md`](data-dictionary.md) §9.6 recorded it as the gap that
mattered most:

> **Absent.** No account has a written definition anywhere in the repository.
> This is the gap that matters most for 11.3: a reviewer approving a mapping
> has no canonical text to compare the company's label against.

[`apps/api/app/mapping/chart.py`](../apps/api/app/mapping/chart.py) now carries
one per line, and `test_every_line_has_a_real_definition` rejects a stub — it
caught four of them on the first run, which is the point of testing prose at
all.

The definitions are **metadata over `model/accounts.py`, not a second chart**.
Two charts that drift apart is the obvious failure mode here and it is silent,
so `test_chart.py` asserts the two cannot gain or lose an account
independently, and that the expected-sign and working-capital tags agree with
the conventions the engine states in prose.

### F-17 — OPEN. The chart is short of Section 12, and mapping makes it visible

[`data-dictionary.md`](data-dictionary.md) already listed what the engine's
vocabulary lacks against specification 12.1–12.3: `goodwill`, `intangibles`,
`lease_liabilities`, `minority_interest`, `ebitda`, operating expense by
disclosed category, a statement of equity, and `fx_effect_on_cash`.

That was a note about the engine. Phase 5 turns it into something a reviewer
meets: mapping a filing's goodwill line offers `other_noncurrent_assets`,
because there is nowhere else for it to go. The proposal says so in its rule
text, which is the honest handling, and it is not a fix — an entity with
material goodwill gets a model whose balance sheet is right and whose
intangibles schedule (13.3) and check 17.12 do not exist.

Extending the chart is a change to `model/accounts.py` and therefore to the
engine's derivation and checks, which is why it is not folded into Phase 5.
It should be done before the system is pointed at a filing with material
goodwill, leases, or minority interests.

**Phase 7 turned the cost of this from an argument into a count.** Three of
the seven schedules Section 13 asks for cannot be built at all, and each says
so on the screen rather than rendering an empty table:

- **13.3 intangibles** — no `goodwill` or `intangibles` line, and no separate
  amortization line either, so neither side of the roll-forward exists.
- **13.5 leases** — no lease liability and no right-of-use asset. Worse than
  absent: nothing can distinguish a company with no leases from one whose
  leases sit inside `other_noncurrent_liabilities`.
- **13.7 share counts** — basic and diluted share counts are not in the chart
  at all. The chart holds currency amounts, and a share count is neither. STEP
  34's last division is equity value per share, so a valuation needs this.

A fourth consequence is subtler and shows up as a caveat rather than a gap:
`depreciation_amortization` is one combined line, so the PP&E schedule charges
amortization against PP&E. That is right only if the company amortizes
nothing, and the schedule says so rather than quietly being wrong for any
filing with intangibles.


### F-18 — RESOLVED in Phase 6. The extractor was truncating long row labels

A wide statement title puts a column boundary in the middle of the label
column, and the table extractor then returns a row's label as two cells:
`"Net cash provided by oper"` and `"ating activities"`. Phase 3 took column
zero and stopped.

**The failure was silent, which is what makes it worth recording.** The number
was right. The label was plausible. Nothing raised a reason code. What
happened instead was that the mapping proposer stopped recognising the line,
so the reviewer saw "no rule recognises 'Net cash provided by oper'" and would
reasonably have mapped it by hand — never learning that a quarter of the label
was missing from the citation, which is the thing that makes the figure
checkable later.

Two obvious fixes are both wrong, and the reason is worth keeping:

- **Join the fragments with nothing.** Correct for a split landing mid-word
  (`"amortiza" + "tion"`), wrong for one landing on a space, because the
  extractor strips each cell and the space is already gone:
  `"Purchases of property and" + "equipment"`.
- **Join them with a space.** Exactly the opposite pair of outcomes.

The label is now re-read from the page over the rectangle the label columns
occupy, which has the text as printed, spaces and all. Found by Phase 6: the
cash-flow lines it produced would not map, and the checks that depend on them
could only skip.

### F-19 — RESOLVED in Phase 6. `normalize()` summed net income across statements

`net_income` is the one canonical code on two statements: the income statement
defines it and the cash flow statement restates it as its opening line. Phase
5 keyed the normalized ledger on `(code, period)` and **summed** the
contributions, so any filing presenting a cash flow statement would have had
its net income doubled.

It was invisible because the only fixture available in Phase 5 had no cash
flow statement. That is the general shape of the thing: a fixture that cannot
exercise a path also cannot fail on it, and the test suite reported 534 green
while this sat in the middle of the mapping stage.

The key is now `(code, period, statement)`. Thirty-nine of the forty codes are
unaffected. Two consequences worth noting:

- The **net-income linkage check became real.** Before, it compared one figure
  with itself and could not fail — a check that cannot fail is not one.
- The Phase 6 fixture (`three_statements.pdf`) ties across all three
  statements deliberately, so a check that passes is passing on evidence.

---

---

### F-20 — RESOLVED in Phase 7. A reconciliation reported "ties exactly" when
it merely fell inside the tolerance

Found by a unit test written to assert the opposite of what the code did.
`schedules/checks.py:reconcile` compared a schedule's closing figure with the
balance sheet's using `Tolerance.close`, and on PASS reported
`"N period(s) tie exactly"` — counting every period that passed, including any
that differed by less than the tolerance.

That is a small wording bug with a specific, expensive failure behind it. The
tolerance exists because a filing rounds its own figures, so a difference in
the last printed digit is the company's rounding. A missing disposal that
happens to be small is a different thing entirely, and the old message made
the two indistinguishable at exactly the size where telling them apart
matters. A reviewer reading "ties exactly" has been told the schedule accounts
for the whole movement, and would have no reason to look.

The check now counts exact ties separately, and a period inside the tolerance
but not equal is reported with its amount and the tolerance it passed under.
Specification 12.5 and STEP 6 say to keep differences visible; a difference
described as an exact tie is not visible.

---

### F-21 — RESOLVED in Phase 7. The schedules screen scrolled sideways at 200%

Caught by the accessibility test for the new screen, and only after that test
was fixed. The first version of it ran against the `served` fixture, which
holds a filing at the start of review — where the schedules screen correctly
shows its empty state. A 200%-zoom test on an empty page passes and proves
nothing.

Pointed at a populated screen it failed immediately: 111px of horizontal page
scroll at a 640px viewport, from the roll-forward tables, which carry a period
per column plus a sentence of basis per row.

The fix is not to reflow them. A reconciliation table is two-dimensional data,
and WCAG 1.4.10 exempts exactly that — but only if the table scrolls inside
its own region instead of taking the page with it. Each wide table is now in a
focusable, named `role="region"`, so it can also be scrolled from the keyboard
alone (2.1.1).

Worth recording as a finding rather than a fix because of how it was found:
the test that would have caught it was written first, and passed, against the
wrong page.

---

### F-22 — RESOLVED in Phase 9. A division by zero was classed as a formula
defect when 4.12 calls it a data state

Phase 8's `calculate(strict=False)` tolerated a missing input and re-raised a
division by zero. The reasoning written into the code was that a missing input
is a fact about the filing while a division by zero is a fact about the
formula, and it is wrong: `gross_profit / revenue` is a correct formula, and a
company with no revenue has no gross margin. 4.12 says so directly — a
relative measure against a zero expected value is **undefined**, which is a
state a figure can legitimately be in.

Found by building 14.8's impact preview, where it matters most. A reviewer
asking "what would this do?" about a change that drives revenue to zero wants
the answer "the gross margin becomes undefined". Under the old rule the
preview raised instead, so the one case where the preview is most worth having
was the one case it could not render.

The rule is now: a missing input and a division by zero are both data states —
reported with their reason when gaps are tolerated, refused when they are not,
because an export must not move on a figure nobody has. A **unit error** stays
a defect and is raised either way, because no data makes `revenue * revenue`
mean something.

---

### F-23 — RESOLVED in Phase 10. "Other non-current assets" mapped to the
CURRENT line

Phase 5's proposal rules carried `^(other|prepaid|prepayments)` for
`other_current_assets` and nothing that distinguished a non-current "other"
line. A balance sheet reporting "Other non-current assets" was therefore
offered `other_current_assets` as its best candidate, on nothing but the order
the rules happened to be written in.

The consequence is specific and quiet. A non-current balance mapped to a
current line moves net working capital by the whole amount, changes the change
in NWC, and changes free cash flow — while the balance sheet still balances,
every subtotal still reconciles, and every Section 12 check still passes.
Nothing downstream catches it, because nothing downstream is looking at
current-versus-non-current.

Found while building `forecastable.pdf`, which is the first fixture to report
any of the four "other" lines — which is itself the lesson: the rule was
written in Phase 5 and could not be wrong until a fixture exercised it.

Four EXACT rules now match `other (non-current|long-term) (assets|liabilities)`
and `other current (assets|liabilities)` explicitly, and they outrank the
generic one by score rather than by position.

---

### F-24 — RESOLVED in Phase 12. Two font families were named and neither was
present

`packages/design-tokens/tokens.css` has declared
`--font-serif: "Source Serif 4", ...` and `--font-sans: Inter, ...` since
Phase 4, and neither font was ever added to the repository. Every screen had
been rendering in the system fallback stack for four phases.

It survived because the design-token tests read the CSS, and the CSS was
correct: the families were named, the tokens resolved, the contrast ratios
computed from the colour tokens all passed. Nothing asserted that a named
family could actually be loaded.

The cost is not cosmetic. 6.2.c requires tabular numerals for all financial
values, and a fallback stack that lacks them misaligns every column of figures
on every statement screen — which is the one thing a financial table cannot
do.

Both families are now vendored as Latin subsets with their OFL text, and a
browser test reads `document.fonts` and asserts they load. That is the check
that would have caught it: a test that reads a stylesheet can only confirm
what the stylesheet claims.

---

### F-26 — RESOLVED in Phase 13. A severity was marked settled on a shared word

`validation-policy.md` was written in Phase 2 and says, in its own prose,
**"Only four are forced"** — then bolds **six** rows in the table underneath.
The registry Phase 13 generated from that table inherited both, so six
severities sat in the settled column and one of them had no rule behind it.

The two extra rows are not the same mistake:

- **17.18 is genuinely forced** and the summary table had simply missed it.
  14.1 — "No forecast may calculate until all required assumptions have a
  status" — blocks calculation, and blocking calculation is CRITICAL's own
  stated consequence. It is now in the summary table.
- **17.5 was forced on a word.** Its citation was rule 1.14, "never allow an
  unresolved *critical* validation error to appear as PASS". That rule
  presupposes some checks are critical and never says which — it is the *cause*
  of F-4, not its answer. Reading 17.5's "critical fact" as the missing
  assignment is a word in common, not a derivation. It is now a proposal, and
  the count is five forced, twenty-five proposed.

**The test this yields is the useful part: a rule forces a severity only when
it states a consequence.** Block calculation, block release, do not compute the
figure, do not make the claim — the consequence is what the level *means*, so a
rule naming one fixes the level, and a rule merely using the word does not. All
five surviving citations pass that test. A new test also asserts the document's
summary table and its row-by-row table name the same set, which is the drift
that hid this for eleven phases.

Nothing downstream moves: the release gate blocks on every outstanding check
regardless of severity, so 17.5 blocked before and blocks now. What changes is
what the screen tells a reader is **settled**, and one row claiming more
authority than it has is how a reader stops trusting the column.

### F-25 — RESOLVED in Phase 12. Every table screen scrolled the page sideways

Found by widening item 130's sweep from two screens at one width to eight
screens at three widths. Every screen with a statement table on it pushed the
whole document sideways at 390px, and several did at 1000px.

The cause is the `min-width: auto` default on grid and flex items: an item
refuses to shrink below its content's intrinsic minimum, so a table whose
numeric cells are `white-space: nowrap` sized its entire column. `min-width:
0` down the chain from the shell to the cards fixed most of it.

The remainder is the part worth recording. **`overflow-x: auto` makes a box
scroll; it does not stop the box's contents contributing their min-content
width to its ancestors.** The scroll container was doing its job and the page
still overflowed. `contain: inline-size` is the declaration that actually says
"this box's inline size is independent of its contents", and it is what makes
the scroll happen inside the focusable, labelled region where WCAG 1.4.10
intends it rather than on the document.

The narrower tests that preceded this had passed for two phases. A layout test
that covers one screen covers the screen that happened to be easy.

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

**Phase 13 (items 131-137) is built**, in
[`apps/api/app/diagnostics/`](../apps/api/app/diagnostics): Section 17's thirty
checks in one registry, source-to-output lineage, the audit log made
searchable, the benchmark-coverage report, and the release gate.

**The thirty checks were never missing; they were scattered.** Phases 3 to 11
each built the checks its own stage needed -- extraction confidence, subtotal
and cross-statement reconciliation, the balance-sheet identity, the cash tie,
schedule reconciliation, the formula graph's cycles, the 14.1 assumption gate,
the engine's thirteen PASS/FAIL checks, the terminal-value share. A reader met
six panels and had to know which one to look in.
[`run.py`](../apps/api/app/diagnostics/run.py) maps each Section 17 clause onto
the code that already answers it and reports it under the clause's own code.
Nothing is reimplemented, because a second implementation of a check is a
second answer to the same question.

**SKIP is a reported state, not an absence.** Rule 1.14 -- "an unresolved
requirement must never appear as PASS" -- is the whole reason the third state
exists. A check whose inputs do not exist has not passed, it has not run, and
the difference is the one a reviewer needs. Every skip carries its reason.

Two clauses cannot be evaluated by this system at all and say so instead of
skipping quietly: **17.12**'s intangibles schedule, because the chart has no
intangibles line (F-17), and **17.21**'s iterative-calculation clause, because
no iterative calculation is configured and the dependency graph is checked for
cycles regardless. A gate permanently red for a reason no reviewer can act on
teaches reviewers to ignore it.

**Item 137 cannot be implemented as written, and the gate says which rule it
is standing in for.** "Prevent release when CRITICAL/ERROR checks remain"
needs a severity per check; Section 17 supplies four severities and assigns
none of the thirty to one. That is **F-4**, open since Phase 2. Five severities
are *forced* by rules elsewhere in the specification and carry their citations;
the other twenty-five are proposals in `validation-policy.md` (F-26 corrected
that count: one of the six had been forced on a shared word rather than a rule).

So [`release.py`](../apps/api/app/diagnostics/release.py) does the thing that
cannot be wrong in the dangerous direction: **every outstanding check blocks,
whatever its proposed severity** -- failed and skipped alike. That is strictly
stricter than 137 under any assignment the owner might later make, so the gate
cannot release a model 137 would have stopped. It can refuse one 137 would have
allowed, an acknowledged WARNING say, and for a valuation that is the direction
to err in.

Building that gate found **F-26**: `validation-policy.md` said "only four are
forced" and bolded six, and one of the two extra rows was forced on a word
1.14 uses rather than a rule 1.14 states. Five, not six. `severity_is_unratified` is carried on the result and printed on the
screen, so a reader who is told "not releasable" is also told that ratifying
F-4 is what would let the gate distinguish a blocking failure from a warning.

**Lineage stops being per-fact at the forecast, and says so.** The chain
[`lineage.py`](../apps/api/app/diagnostics/lineage.py) walks -- a page, a
located fact, a human decision with its written reason, an approved mapping, a
ledger cell carrying its `Figure` and `Source`, a forecast cell naming its
driver, an FCFF year and a discount factor -- is real up to the forecast
boundary and then changes shape. A projected cell rests on the whole last
actual year plus a driver, not on one page. The forward trace reports that join
explicitly rather than continuing to name a single page, because a lineage that
looks more precise than it is, is worse than one that admits where it widens.

**The benchmark report makes the weaker, true claim.** 4.20 forbids claiming
"less than 0.0001% error" until the benchmark suite passes *and* the report
identifies the exact dataset and formulas tested. A running web process cannot
honour the first half -- the benchmark lives in the test suite and runs in CI,
and this process does not observe its result. A screen printing "0.0001%
accuracy" because somebody once ran the tests would be making exactly the claim
4.20 exists to prevent. So
[`benchmark.py`](../apps/api/app/diagnostics/benchmark.py) reports the second
half, which it can establish: which of 4.16's required outputs are compared,
formula by formula, against an implementation sharing no helper with the
engine, and where each comparison lives. Twenty of twenty-two rows are
compared; the verdict line says the result is not observed here and where to
look for it.

**The audit log becomes searchable.** `AuditEvent` has been written on every
mutation since Phase 3 and nothing read it back except a count.
[`audit.py`](../apps/api/app/diagnostics/audit.py) adds the four questions
somebody actually asks -- who, what kind of thing, to which entity, in what
window -- and composes them, because the useful question is usually two at
once. Ordering is newest-first and stable, tie-broken on the monotonic id: a
log whose order drifts between two readings is one nobody can cite.

On the fixture model the panel reports **23 passed, 3 failed, 4 could not run**,
and all three failures are true facts about that filing rather than defects:
two trap labels correctly left unmapped (17.5, 17.6), and 16.19's lease
liability line that nobody has addressed (17.25).

**Phase 12 (items 121-130) is built**, in
[`apps/api/app/dashboard/`](../apps/api/app/dashboard),
[`packages/design-tokens/`](../packages/design-tokens) and the templates:
Section 6's design system, the navigation shell, and the 7.1 portfolio.

**Item 122 found that `tokens.css` had named two font families since Phase 4
and neither was present.** Every screen had been falling through to the system
stack, which the design-token tests could not see because they read CSS.
Source Serif 4 and Inter are now vendored as Latin subsets -- 114 KB for five
faces -- with their SIL Open Font License text beside them. Self-hosted rather
than fetched from a CDN, because the review server binds to 127.0.0.1 and
holds an unreleased filing: a page that fetched its fonts from a third party
would tell that third party when the model was being looked at. A browser test
now asserts the faces actually load, which is the check that would have caught
the original gap.

6.2.c is why this is not a matter of taste: tabular numerals on every
financial value. A fallback stack that happens to lack them misaligns every
column of figures on every statement screen.

**7.1.b's seven statuses are computed, never stored.** Each is the furthest
stage whose gate is satisfied, and every gate is the entry condition of the
one after it -- you cannot review what was not extracted, or value what did
not forecast. That costs real work on every portfolio render (it builds the
statements and attempts the forecast) and it is the trade worth making for the
first thing a reader sees: a stored status is wrong from the moment anything
else changes, and a reader who has once been misled by one stops trusting the
column. `Archived` is deliberately never inferred -- a model nobody touched
recently is not the same as a model somebody finished.

**Item 130's sweep -- three viewports across eight screens -- found real
horizontal overflow on every screen with a table on it.** The cause was the
`min-width: auto` trap: a grid or flex item refuses to shrink below its
content's intrinsic width, so a wide statement table pushed its whole column
past the viewport and the PAGE scrolled sideways rather than the table, which
is the one thing WCAG 1.4.10 does not exempt.

`min-width: 0` down the shell chain fixed most of it. The last of it needed
`contain: inline-size` on the scroll container: `overflow-x: auto` makes a box
scroll, and does **not** stop its contents' min-content width propagating
upward. That distinction is not obvious, and the earlier narrower tests had
missed it because they covered two screens at one width.

The sweep also found two bare tables in the source room and the mapping screen
that had never been inside a scroll region at all, and a class collision:
`source_room.html` has used `class="card sidenav"` since Phase 4, so the new
shell's `.sidenav` rules were silently restyling it. The shell's class is now
`.shell-nav`.

**One accessibility test had to be rescoped, and the reasoning is recorded
rather than the test quietly weakened.** `test_focus_moves_down_the_page_not_
around_it` asserted tab order follows visual order across the whole document.
With a persistent left navigation (6.3.a) the last navigation link sits
visually above the first content control, which that test reads as a backwards
jump -- and it is not: navigation-before-content is the correct reading order
across landmarks, and is the reason a skip link exists at all. The test is now
scoped to `<main>`, and a new test asserts the landmark ordering directly, so
the property is still covered rather than dropped.

**Phase 11 (items 109-120) is built**, in
[`apps/api/app/valuation/`](../apps/api/app/valuation) and
[`model/timing.py`](../model/timing.py): Section 16's DCF, driven from a
scenario's approved inputs.

**The engine was short of Section 16 in one place that mattered, and it is now
fixed.** STEP 29 says year-end discounting and the engine implemented exactly
that: integer periods, integer exponentiation. Section 16 asks for three things
that convention alone does not give -- 16.11's documented choice between
year-end and mid-year, 16.12's exact time fraction from a valuation date, and
16.13's tested precision policy for the non-integer exponent both of those
imply. `model/timing.py` supplies all three, and **the year-end path is
unchanged**: a test asserts every discount factor on the fixture model is still
what it was, so adopting the options cannot silently move a valuation that did
not ask for them.

The precision policy is stated once and pinned by tests rather than asserted in
prose. An integer exponent routes through repeated multiplication and never
touches a transcendental function. A fractional one is `exp(t * ln(1 + WACC))`,
where `Decimal.ln` and `Decimal.exp` are *correctly rounded* to the 50-digit
context -- so the residual is a few units in the last place of fifty, which the
tests bound at 1e-40 relative, forty orders of magnitude inside 4.11's 0.0001%.

**`CostOfCapital` already required a source string per input, and "Bloomberg"
satisfies it.** The market inputs are now Section 14 assumptions, so
`SourceType.EXTERNAL_MARKET_DATA`'s evidence rule does the work: a URL AND an
observation date, because the same field observed a month later is a different
number and a valuation nobody can reproduce is a valuation nobody can check.
Decision 2.3.e forbids external retrieval, so the system never fetches any of
it -- the reviewer supplies the number and says where it came from.

**STEP 27's trap is named in words where a reviewer will read it.** "Do not
automatically use book equity for market capitalization" -- the engine refuses
a non-positive market equity and cannot tell book from market, because both are
positive numbers. That distinction can only be made by a person, so the row
says so.

**16.22 is followed exactly as written.** A terminal value above the review
threshold *warns* and does not fail, because a high terminal share is ordinary
for a company still growing and a red flag for one that is not, and no
threshold tells the two apart. What the warning says is where a reviewer's
attention belongs: on the perpetual growth rate, which is carrying most of the
answer.

**Three things Section 16 asks for cannot be built, and each says so.**
16.19's lease liability line (the chart has none, and decision 2.4.j treats
leases as debt -- so a company with material leases is over-valued by their
whole amount if this is left unsaid); 16.20's per-share value (no verified
diluted share count, and no share count in the chart to cross-check one
against); and 16.24's exit multiple (no EBITDA line to apply a multiple to).
All three are F-17 again. 16.25's rule against averaging terminal methods has
nothing to bind as a result, and that is stated rather than left to inference.

Item 120's benchmark recomputes the whole valuation longhand -- no `model.dcf`,
no `model.timing`, no `model.numeric` -- and asserts **exact equality** across
every 4.16 valuation output, because every operation involved is addition,
subtraction, multiplication or a terminating division.

**Phase 10 (items 97-108) is built**, in
[`apps/api/app/forecast/`](../apps/api/app/forecast): Section 15's forecast
statements, driven from a scenario's approved assumptions.

**Nothing in this phase forecasts anything.** `model/forecast.py` already
implements all twenty-one of Section 15's steps -- revenue from a stated
method, COGS and opex from documented drivers, D&A from the PP&E schedule
rather than a disconnected input, working capital account by account, debt and
interest from the debt schedule, taxes from the tax schedule, the three
statements and the cash link -- with an independent benchmark and 0.0001%
accuracy assertions behind it. Reimplementing it against the website's data
structures would produce a second answer to every question in Section 15, and
the two would disagree the first time either changed.

So Phase 10 is a boundary, and the boundary has three obligations:

- **14.1 is checked before the engine is touched.** The engine raises on a
  missing driver, naming one at a time; the gate names all of them at once,
  per period. A reviewer fixing eleven missing drivers one traceback at a time
  is a reviewer the gate exists to spare.
- **Only Reviewed and Approved assumptions cross.** A Draft is not an answer,
  and letting one through would put an unsourced number into a valuation while
  the screen still showed it as unfinished.
- **The scenario travels with the result**, because 9.12 records a calculated
  value against its `scenario_id` and 15.20 asks for every scenario.

**A new fixture, `forecastable.pdf`, because a phase whose deliverable never
runs is a phase nobody verified.** `three_statements.pdf` cannot be forecast,
and the refusal is correct: the engine anchors its roll-forwards on the last
actual year's `other_current_assets`, `other_noncurrent_assets`,
`other_current_liabilities` and `other_noncurrent_liabilities`, that filing
reports none of them, and STEP 5 forbids substituting zero. The new filing
reports all four and ties across all three statements. Both fixtures are kept,
and the refusal on the first one is now a test.

Building it exposed a real defect in Phase 5's mapping rules, fixed here:
**"Other non-current assets" was proposed as `other_current_assets`.** The
generic `^other` rule won on nothing but ordering, and a non-current balance
mapped to a current line moves working capital by its whole amount while the
balance sheet still balances -- so nothing downstream catches it. Four EXACT
rules now distinguish current from non-current on both sides.

**15.21's word "critical" is the problem, and it is F-4.** Section 17 assigns a
severity to none of its thirty checks, and `validation-policy.md`'s proposals
are proposals. A gate that invented its own severities would make a release
decision on an assumption nobody approved, so this one reads "every critical
check" as **every check**: any failure, and any check that could not run,
withholds Forecast Ready. That is strictly stricter than any severity
assignment, so it cannot wrongly pass, and the panel says so out loud.

With one carve-out that is not a loophole. Two of the engine's thirteen checks
are about the *valuation*, and at this phase there is no valuation, so both
skip. Counting that against Forecast Ready would report the forecast as
unfinished because Phase 11 has not been built, which makes the label
unreachable by construction. They are reported separately as `deferred`, and
`VALUATION_CHECKS` names them explicitly so a test can assert the set has not
silently grown.

**Phase 9 (items 89-96) is built**, in
[`apps/api/app/assumptions/`](../apps/api/app/assumptions): Section 14's
assumption system, with the Scenario entity Section 9 references and never
defines (see **F-5**, now resolved by design).

**14.4 lists ten things every assumption must contain, and the engine's own
`Assumption` carries four.** Name, value, a three-way basis and a source
string is enough for a model run by the person who built it, and not enough
for one somebody else has to review. The record here is a superset, and
`engine_basis` narrows it back down so there is still exactly one place a
number enters the forecast.

**The evidence rules are the part worth reviewing.** Taken literally, 14.4.f
and 14.4.g are two more string fields, and an assumption citing "the 10-K"
with no page satisfies them. It should not -- STEP 2 makes the page the unit
of evidence, and Phase 3 already refuses a fact without a location. So the
requirement is per source type: a company filing needs a document AND a page;
external market data needs a URL AND an observation date, because a beta is a
fact about a date; a historical driver must name the periods it was measured
over, because a DSO of 59.9 days means nothing without saying 59.9 days of
which year.

**Self-review is recorded, not refused.** 14.4.i wants an owner and a
reviewer. This system is single-user, so requiring them to differ would block
every approval and invite a made-up second name. Both are required, they may
be the same person, and the gate reports how many approvals rest on it.

**14.1 needed a definition of "required", and the only authoritative one is
the engine.** `model/forecast.py` reads a structural driver through
`assumptions.get`, which raises when it is absent, and a discretionary one
through `_optional`, which defaults to zero because zero is the meaningful
"this did not happen" value for a buyback. `drivers.py` is a reading of that,
and two tests keep it one -- including one that greps `model/forecast.py` for
`assumptions.get` calls the table does not carry, because a gate that misses
one passes a model that then halts.

That test earned its place immediately: **`tax_rate` was missing from the
table**, because the engine takes it through `TaxSchedule` from
`valuation.yaml` rather than through the assumptions register. It is the one
required driver on a different route, and without it the gate would have said
a forecast could calculate when running it halts on `tax.source is required by
STEP 16`.

**7.7.a is the join with Phase 7.** The historical driver analysis is not
recomputed here: DSO, inventory days, DPO, the implied interest rate on
BEGINNING debt (the basis the forecast charges on), the effective tax rate and
depreciation on opening PP&E all come out of the Section 13 schedules, with
`measured_over` already filled in -- which is exactly the field a hand-entered
historical driver gets left blank. Every one arrives as a **Draft**, because a
proposal that arrived Approved would make STEP 14's assumption -- that every
driver stays where it was -- for all of them at once, silently.

**The preview truthfully reports that nothing moves, and says why.** 14.8 asks
that a change show every affected output *before saving*, and the
implementation does exactly that on a copy. But the formula registry currently
holds only the historical derivation family; the forecast formulas are still
Python in `model/forecast.py` and become registry entries in Phase 10. So a
forecast driver reaches nothing yet, and the screen says so rather than
rendering an empty table as though it had looked.

Phase 9 found one defect in Phase 8 -- **F-22**, a division by zero classed as
a formula defect when 4.12 names it a data state.

**Phase 8 (items 78-88) is built**, in
[`apps/api/app/formula/`](../apps/api/app/formula): the formula engine of
specification Section 18 — formulas as versioned definitions, parsed into a
dependency graph, ordered, checked for cycles *before* evaluation, evaluated
exactly in `Decimal`, unit-checked, and fingerprinted.

**18.3 is a property of the implementation, not a promise about inputs.**
There is no `eval`, `exec`, `compile` or `ast.literal_eval` anywhere in the
package — a parametrised test greps the source for each of them, because
grammar tests would still pass if someone added a fast path beside the parser.
Numeric literals are built from their matched characters straight into
`Decimal`; references resolve through a dictionary, never an attribute
lookup, so a formula cannot reach a method or a dunder even before the
tokenizer refuses dunder segments outright.

**The unit system is the smaller half of a dimensional algebra, plus one rule
it would miss.** Four base dimensions — currency, shares, days, years — with
multiplication adding exponents catches `revenue * revenue` and
`revenue + shares`. What it does not catch is `growth_rate + pe_multiple` or
`revenue * growth_percent`, because all three are dimensionless; so addition
additionally requires the same *named* unit, and `percent` refuses to
multiply or divide at all. A percent is stored as the number a person reads —
5, not 0.05 — and that error is a factor of 100 with nothing downstream to
catch it.

**The declared output unit is verified, not inferred.** `currency / currency`
is dimensionless, and whether that is a margin or an EV/EBITDA is intent, not
algebra.

**The catalogue is generated, not transcribed.** The ten derivation formulas
(`IS-*-D`, `BS-*-D`, `CF-*-D`) are built from `model/accounts.py:DERIVED`, so
a component added to a subtotal appears in the catalogue without anyone
remembering to. A hand-typed catalogue is a second chart of accounts, and two
charts that disagree is worse than one — `mapping/chart.py` made the same call.

**Items 87 and 88 are answered structurally rather than by assertion.** 4.15
requires the primary engine and the benchmark not call the same helper.
`Ledger._try_derive` walks tuples of account names into a running total; the
formula engine parses text into a tree, topologically orders a graph and
evaluates node by node. They share the `DERIVED` table deliberately and no
arithmetic at all, and a test asserts they agree **exactly** — not within
tolerance — on the golden filing, on eight extreme-input cases (4.17: zeros,
all-negative, 1e-8, 1e30, mixed scales, 24-significant-digit decimals) and on
125 randomized cases across five orders of magnitude.

Where the two implementations genuinely differ is tested rather than papered
over. `_try_derive` treats a residual "and anything else" line as zero when
absent, silently. The formula engine refuses an unresolved reference outright
(18.14), so the policy lives in `ledger_environment`, which supplies the zero
**and records that it did** — and the screen lists them. A subtotal resting on
an assumed-nil residual otherwise reads exactly like one resting on a reported
figure.

**18.10 and 18.11 are screens, not assertions.** Both clauses are written as
obligations to a person. `/documents/{id}/formulas` recomputes every subtotal
the filing prints, from its own components, and shows the formula, the
substituted inputs, the computed figure, the printed figure and whether they
agree — a real STEP 9 cross-check by a second implementation. A test corrupts
a reported gross profit and asserts the screen flags it, and that it flags
*only* it: because every subtotal is recomputed from leaf inputs rather than
from the subtotal above it, one transcription error does not look like four.

**Phase 7 (items 69–77) is built**, in
[`apps/api/app/schedules/`](../apps/api/app/schedules): the historical
supporting schedules of Section 13, reconciled to the statements they claim to
explain.

The design decision that shapes the whole package is what to do about the
movements a filing does not disclose. Every formula in Section 13 ends in a
term like `+/- FX and Other Adjustments`, and a filing almost never puts a
number beside that on the face of its statements. Solving for it would make
every roll-forward tie, every reconciliation in 13.8 pass, and the entire
phase worthless. So nothing here plugs: the schedule's closing figure is the
opening balance plus what was disclosed, the balance sheet's figure is its
own, and the gap between them is reported as **unexplained**.

That choice is what the tests are built around. Four of them corrupt a
different input — CapEx, a debt repayment, a dividend, a receivable — and
assert the reconciliation catches it *with the right amount*, because a
reconciliation that fails with the wrong number is still wrong.

Two conventions are stated rather than assumed, both because the alternative
is defensible and gives a different answer:

- **Days drivers use year-end balances, not averages** (13.1.e). The average
  is arguably the better description of the year, but this driver exists to be
  inverted — `model/schedules.py:days_to_balance` forecasts a *closing*
  balance — so an average-based DSO would not reproduce the balance sheet it
  came from.
- **Interest is implied on beginning debt** (13.4), because that is what
  `model/forecast.py` charges it on. The average-debt rate is computed and
  shown beside it, marked as not the one the forecast uses. A test reads
  `model/forecast.py` and fails if that stops being true.

Three of the seven schedules cannot be built at all — see **F-17**, which
Phase 7 turns from an argument into a count.

Phase 7 found two defects in its own work, both recorded: **F-20** (a
reconciliation reported "ties exactly" for a difference merely inside the
tolerance) and **F-21** (the new screen scrolled sideways at 200%, caught only
after the accessibility test was fixed to run against a populated page).

**Phase 6 (items 59–68) is built**, in
[`apps/api/app/statements/`](../apps/api/app/statements), and with it **the two
halves of this repository are joined**. Until Phase 6 they agreed and did not
touch: `model/` built statements from YAML a human typed, `apps/api/` read a
PDF into verified, mapped facts.
[`build.py`](../apps/api/app/statements/build.py) takes the second and produces
the first — real `model.statements.Ledger` objects whose every cell carries a
`Figure` with the page it was printed on — and
[`export.py`](../apps/api/app/statements/export.py) writes the two files
`run_model.py` reads.

The end-to-end test runs the engine's CLI on the exported files and asserts it
**halts** with `MODEL HALTED ... required by STEP 16`. That is the right
outcome: the historical half came from the filing, and the forecast half still
needs a human, because a beta and a risk-free rate are not lines in a document.

Phase 6 also found two bugs in the phases beneath it — F-18 and F-19 — both
silent, both invisible to the fixtures that existed at the time.

**Phase 5 (items 50–58) is built**, in
[`apps/api/app/mapping/`](../apps/api/app/mapping): the canonical chart with a
written definition per line (the gap `data-dictionary.md` called the one that
mattered most), deterministic mapping proposals that refuse the traps, split
and combine, duplicate-count **prevention**, subtotal and cross-statement
reconciliation, human approval, and versioned mapping sets.

Two things it turned on that nothing else could. **`VERIFIED` is reachable**:
source-policy.md §9's seventh condition is a human-approved mapping, so before
Phase 5 the correct answer for every fact was no. On the fixture filing 46 of
50 facts now reach it. **`SUBTOTAL_MISMATCH` and `CROSS_STATEMENT_MISMATCH`
fire**: both were defined in Phase 3 and never raised, because a subtotal has
nothing to disagree with until its components are mapped.

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
  `validation-policy.md` proposes twenty-five and labels each a proposal. Phase
  13's release gate is built and blocks on *every* outstanding check rather than
  on a proposed severity — strictly stricter, so it cannot wrongly release — but
  it cannot tell a blocking failure from an acknowledged warning until the
  owner ratifies the assignment.
- **F-5** — Section 9 requires `scenario_id` and defines no Scenario entity.
  That is a specification amendment, not an implementation choice.
