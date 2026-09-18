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

### F-15 — RESOLVED in Phase 15. The review application had no authentication

Decision **2.2.c is CONFIRMED: authentication is required** — 2.2.a puts
confidential financial PDFs behind a network endpoint, and 20.1 classifies them
confidential.

**It was unimplemented from Phase 4 to Phase 14**, with the mitigation that
`review_server.py` binds to `127.0.0.1` and prints a warning if told to bind
anywhere else. That was recorded here rather than left to be discovered, and it
was the right thing to record: a mitigation is not the requirement, and a
mitigation that depends on a reader passing the right flag and reading a warning
is not even a good mitigation.

Phase 15 item 145 built it, in
[`apps/api/app/security/`](../apps/api/app/security):

- a password verified against a `hashlib.scrypt` hash held in the environment,
  never in the repository (20.3, 20.4);
- a signed session cookie, `HttpOnly`, `SameSite=Strict`, `Secure` off loopback,
  expiring **absolutely** eight hours after sign-in;
- a CSRF token on every state-changing request (20.12), enforced in local-review
  mode too, because authentication and CSRF are different defences;
- login attempts rate-limited, with a successful sign-in clearing the count so
  somebody else's guessing cannot lock the one real user out (20.14);
- 20.7's authorization on every read, at the single point every document route
  already passes through.

And the warning became a **refusal**: `review_server.py` will not bind to
anything but loopback without `REVIEW_PASSWORD_HASH` set. Without one it serves
locally in local-review mode with a banner on every page saying so — which is
not a way to turn 2.2.c off but the development affordance that would otherwise
be somebody commenting out the middleware, made visible and constrained instead.

The three things this row said it needed have answers, each recorded with its
reasoning in the modules themselves: the session mechanism is a signed cookie
with no server-side store (there is one user and one boolean to carry); the
credential store is the environment; and there is **no second factor**, because
2.2.c requires a credential and does not require two, and inventing an
enrolment flow for a single user would be building a thing nobody asked for in
the place where getting it wrong costs most.

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

### F-17 — RESOLVED. The chart now carries every line Section 12 names

Eleven phases open. The chart lacked `goodwill`, `intangibles`,
`lease_liabilities`, `minority_interest`, `ebitda`, interest income separate
from interest expense, operating expense by disclosed category, the D&A split,
disposals, share issuance, `fx_effect_on_cash` and `net_change_in_cash`. Every
one of them now exists, with a definition saying what it is and what it is not.
[`data-dictionary.md`](data-dictionary.md) carries the line-by-line table;
what follows is what building it cost and taught.

**A "when applicable" line is optional, and that is only safe because
something reconciles over it.** 12.2.i and 12.2.k use the phrase, and goodwill,
intangibles and several others behave the same way: a company that has never
acquired anything has no goodwill, and treating that absence as blocking would
make total assets underivable for most filings. The case the optionality could
hide -- a filer who DOES report goodwill and whose goodwill was left unmapped
-- does not stay hidden: the derived total differs from the reported total by
exactly the goodwill, and 12.4.i reports that difference with its amount.
`test_every_optional_line_is_a_term_of_some_subtotal` is that argument as an
assertion, and it caught `amortization` sitting unwatched for the ten minutes
combined D&A was not derived.

**A subtotal with no term reported is not a subtotal of zero.** The engine's
`Ledger._try_derive` has always tracked `contributed` and returned None when
nothing did. The mapping reconciliation and the formula environment both
summed no terms to zero instead. That was unreachable while every derivation
had at least one required term, and reachable the moment 12.1.d's three
operating expense categories arrived, all three optional. What it produced was
not a small error: the reported operating expenses were compared against a
derived zero, so the **whole** of the reported figure was reported as a
discrepancy, the mapping behind it was flagged for review, and the fact lost
its verified status. Both implementations now carry the engine's guard.

**A derived account that cannot be derived here is still the best figure
available.** The formula environment excluded every account in `DERIVED` as an
input, on the reasoning that the formulas produce it -- which is what makes the
recomputation a *check* on the reported figure rather than a reading of it.
That reasoning holds only while the derivation can run. This repository has
fixtures of both shapes: one filing reports three operating expense categories
and no total, the other a total and no categories. For the second, excluding
the reported total left EBIT to be computed from three absent categories, and
EBIT came out too high by the whole of operating expenses. `_derivable_here`
is the fix: skip a derived account as an input only where its own derivation
has something to run on.

The intermediate design was worse and is worth recording. Seeing operating
expenses and D&A break, the first fix made them *checks* rather than
derivations -- reported, compared against their components, never substituted.
That is right for the net income attribution (12.1.l), because net income is
already derived as pre-tax less taxes and an account may be derived only one
way. It is wrong for these two, because the filer who reports categories and
no total then has no total at all. `COMPONENT_CHECKS` kept the one entry that
earned it.

**The forecast's balance sheet totals were summed by hand.** `ending_cash + ar
+ inventory + ...` -- correct for the accounts that existed when it was
written, and silently wrong the moment goodwill joined `ASSET_ACCOUNTS`: the
line was forecast and left out of the total, so A = L + E broke by exactly the
goodwill across every forecast year. The totals now read their own membership
from the chart, which cannot drift.

**Four balances are carried forward, and the forecast says so.** Goodwill,
intangibles, lease liabilities and minority interest are held at their last
reported value with that stated in the basis string, because no assumption in
this model drives them and STEP 10 forbids hiding a forecast decision inside a
formula. The alternatives are worse: growing goodwill forecasts acquisitions
the company has not announced, running leases down needs a payment schedule
(13.5), growing minority interest means forecasting the subsidiaries' earnings
separately from the parent's. **Absent stays absent** -- a company with no
goodwill has none to project, and writing a zero would turn "does not have it"
into "has zero of it" for every forecast year.

**A line that was a trap stopped being one.** "Net increase in cash" was in
`BLOCKED` with the reason that the chart had no line for it and mapping it
would make it an input to the check meant to test it. 12.3.m gave it a line,
and the block came off on the same reasoning every other subtotal already
uses: 12.4.f compares the reported figure against the sum of the three
subtotals rather than substituting one for the other. The fixture filing that
carried it now maps completely, so check 17.6 passes where it used to fail --
asserted as a PASS rather than deleted, because a regression in the chart
should put the failure back.

Two tests had been written to fail the day the chart grew an EBITDA line, so
that nobody would have to notice. They did, and they said what to do.

#### The original finding

**Was: the chart is short of Section 12, and mapping makes it visible.**


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

#### What the chart change does not by itself close

The chart was the blocker for all four, and it is gone. Building on it is
separate work, still outstanding:

- **13.3 intangibles** now has both sides -- `intangibles` and `amortization`
  -- so the roll-forward can be built. It has not been.
- **13.5 leases** now has a liability line, so a filer with leases is
  distinguishable from one whose leases sit inside other non-current
  liabilities. The payment schedule the roll-forward needs does not exist.
- **13.7 share counts** is unchanged and is NOT a chart problem. The chart
  holds currency amounts; a share count is neither. It remains a valuation
  input supplied with its own source (STEP 35), and `BLOCKED` still refuses to
  map a weighted-average share line into a statement.
- The **PP&E caveat** above is now avoidable for a filer that discloses the
  split: `depreciation` exists. The schedule does not yet prefer it.

Check 17.12 still reports SKIP citing F-17, and will until 13.3 is built.


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

### F-37 — The release report said READY without addressing Section 24

Section 24 lists twenty-two release acceptance criteria and opens with "the
application is not complete until all applicable items pass". 24.22 then asks
that a release-readiness report **record evidence for every criterion**.

The generated report recorded evidence for items 154-168 and mapped Section
22's fifty-five test clauses. **It said nothing about Section 24 at all** — and
printed `READY`. The section that defines what release means was the one
section the release report did not cover, and the verdict was being read as
though it did.

Found by reading the specification against the report rather than against the
code, which is the reading that was missing: every individual item had a row,
so nothing looked absent. It is the same shape as F-32 — a checker that
verified everything it knew about and did not know about this.

`verification/acceptance.py` now carries all twenty-two, each with one of
three kinds of evidence, and the kind is part of the record:

  `gate`      a row already in this report. The criterion's status is
              **derived** from that gate rather than asserted, so a criterion
              cannot read PASS with a red gate under it.
  `tests`     named tests, read out of the tree with grep. `missing_tests()`
              imports `plan._test_names` rather than copying it: two scanners
              would eventually disagree about which directories hold tests,
              and the one that found fewer would be the one reporting
              everything fine.
  `document`  for a criterion about what is written down. Two are of this
              kind and both say so.

`Criterion.__post_init__` refuses a row with none of the three and no stated
reason, for `Coverage`'s reason: in a rendered markdown table a row with no
evidence is indistinguishable from a row with evidence.

Three of the criteria could not be answered with a green row and say so
instead:

- **24.20 (CI passes from a clean checkout).** The gate runs here, but the
  *clean checkout* half is CI's: this report runs in a working tree that may
  be dirty, and `/health` says `-dirty` when it is. A report cannot certify
  the environment it is running in.
- **24.21 (exact start, test, review, export and recovery instructions).**
  Item 167's checks verify the claims in `README.md` a program can check. That
  the instructions are *exact* in the sense of a reader following them on a
  clean machine is a human reading, and it belongs to item 177's approval.
- **24.22 itself** is satisfied by the section it asks for, which is a
  self-reference and so stated plainly. The check is that the record has no
  blank rows — not that the evidence is sufficient, which is what the other
  twenty-one rows and a human approver are for.

Two defects came out of building it, both worth recording:

**A plain `{outcome.item: outcome.status}` keeps the last row, not the worst.**
`documentation_claims` emits seven rows under item 167, and criterion 24.21
defers to 167. A failing 167 row followed by a passing one would have left
24.21 reading PASS with a red gate under it — precisely what deriving the
status instead of asserting it was supposed to prevent. `_worst_status_per_item`
folds them.

**The report's row sort was `int(outcome.item)`.** Fine while every item was a
phase number; `ValueError` the moment a criterion was reported as a row.
Sorting is not the place to discover that an item string is not always a
number.

CI's drift check filtered `| 22.` rows only, so it now covers `| 24.` as well
— with the Result column masked, because that column is *derived from the
gates* and `--fast` legitimately leaves 24.15 and 24.16 as NOT RUN. What must
not drift is the evidence each criterion names.

### F-34 — Phase 17. The application was sending no security headers at all

Item 175 asks that TLS and security headers be verified. There was nothing to
verify: every response left the application with FastAPI's defaults and
nothing else — no CSP, no `nosniff`, no `Referrer-Policy`, and no
`Cache-Control: no-store` on a page showing a filing.

Twelve phases of authorization work had been sitting behind a browser that was
free to cache a filing in a shared proxy, sniff a page image into something
executable, or hand a document id to whatever a reader clicked through to.
None of that is an authorization bug, which is exactly why none of the
authorization tests found it.

`app/security/headers.py` now sends them, from the application rather than
from the proxy, so a proxy misconfiguration cannot silently drop them. Two
choices in it are worth recording:

**`script-src 'none'` is not aspirational.** Deviation F-14 decided this
application ships no JavaScript, which makes the strictest possible CSP
simply true rather than ambitious. `default-src 'none'` with `connect-src
'none'` follows for the same reason. The claim rests on a test —
`test_no_template_contains_a_script_tag` — because a CSP that a later template
quietly violates is worse than none: the browser breaks the page rather than
the author noticing.

`style-src-attr 'unsafe-inline'` is the one concession, and it is a real one.
The chart bars and the grid set widths and column spans through the `style`
attribute, which is the only way to express a data-driven length without
JavaScript. It is scoped to attributes, so `<style>` blocks and sheets remain
`'self'`.

**HSTS is sent only on an HTTPS request.** Sending `Strict-Transport-Security`
over plaintext is meaningless — a browser ignores it — and it makes a
`curl -I` against a plaintext deployment look compliant. The middleware reads
the ASGI scope's scheme and omits it otherwise, so the header's presence
is evidence and not decoration.

The middleware is installed **after** the guard, so it wraps the guard's own
refusals. A 303 to `/login` is a response too, and it was the one response an
unauthenticated reader was guaranteed to receive.

### F-35 — Phase 17. A smoke test that authenticates cannot run against production

Item 179 asks for production smoke tests *without exposing private data*, and
those two halves pull against each other. A smoke test that logs in proves
more; it also holds a credential, and anything it prints about what it found
is a filing detail printed by a monitoring job.

`app/verification/smoke.py` resolves it by **never authenticating**. It cannot
reach a filing, so it cannot expose one, and the credential problem does not
arise. What it checks instead is the shape of a correct deployment, which is
most of what a smoke test is actually for: that the process answers, that it
names its own commit, that the commit is not `-dirty` (item 178), that an
unauthenticated request for `/` is refused, that the refusal carries no filing
content, and that all six security headers are on it.

Sixteen checks. Against a guarded loopback server it reports fifteen passes
and one failure — `deploys a clean tree (178)` — which is correct: the tree it
ran from had uncommitted changes. A check that passed there would be useless.

One bug in it is worth recording because of its shape rather than its size.
The first version looked up `"Content-Security-Policy"` in a plain dict.
uvicorn sends header names lowercased, so it reported **every header absent on
a deployment that was sending all of them**. That is the worst failure mode
available to a smoke test: it fails on a correct deployment, so the person
reading it goes and changes the deployment. HTTP header names are
case-insensitive and servers disagree about case; `_Headers` now lowercases on
both sides.

### F-36 — Phase 17. There are no migrations, and item 173 is answered anyway

Item 173 asks that database migrations and a rollback plan be verified. This
application stores JSON files on a filesystem
(`app/persistence/json_store.py`); PostgreSQL is specification 3.2.d and is
still open. There is no migration tool to verify.

The honest answer is not "N/A". What 173 wants is that a deployment can be
undone without losing data, and that is answerable here: the stored PDF is
never rewritten (rule 1.12), so every derived artefact can be rebuilt from it;
records carry their own version and a reader refuses one it does not
understand rather than guessing; and `security/backup.py` takes a verified
snapshot before the deploy. [`docs/deployment.md`](deployment.md) §4 is that
plan, and it says plainly that this section is the part that has to be
rewritten when the JSON store is replaced.

Recorded as a finding rather than a decision because it is a gap being
reported, not a choice being made.

### F-33 — RESOLVED in Phase 16. `margin: 0 auto` on a flex item opts out of stretch

22.6.e asks for a visual test with long company names. Substituting one — a
real-shaped name ending "Aktiengesellschaft (Reorganised) Incorporated" — made
**two screens scroll sideways at 390px**, which is the one thing WCAG 1.4.10
does not exempt. F-25 was supposed to have closed that in Phase 12.

It had, for the reason F-25 identified. This is a different route to the same
failure, and the mechanism is worth writing down because `min-width: 0` does
nothing about it.

    .layout { padding: var(--space-7); max-width: 1680px; margin: 0 auto; }

`.layout` is a flex item of `.shell-main`, a column. **An auto margin on a flex
item's cross axis opts the item out of `stretch`**: instead of being stretched
to the container's inner width and then shrunk, it is sized to *fit-content*,
which is `max(min-content, min(max-content, available))`. So its min-content
won — and its min-content is whatever the widest table demands. At 390px the
mapping screen's layout became **498px**.

`min-width: 0` was already on that element and could not help, because the item
was never being stretched-then-shrunk; it was being sized to its contents from
the start. A definite `width: 100%` makes the cross size definite again, and
the wide table then overflows into its own `.table-scroll` as intended.

The lesson generalises past this rule: **`min-width: 0` fixes shrinking, not
sizing.** An element sized to its content has no shrink step to constrain.

Two content-level defects came out of the same test, both the same shape — a
token with no break opportunity in it:

- **a text input's default intrinsic width is about twenty characters and does
  not shrink.** Four stacked inside a table cell demanded 431px at a 390px
  viewport. `max-width: 100%` with `box-sizing: border-box` makes them fluid,
  which is what every one of them here wants anyway.
- **`987,654,321,098` is one token to a line-breaker.** So is a canonical code,
  a hash prefix, and "Aktiengesellschaft". `overflow-wrap: anywhere` was on
  `.raw`, `code` and `.small` only, so a figure in a finding message overflowed
  a card by 108px. It is now on every prose container and every non-numeric
  table cell — and deliberately **not** on `.num`, because a figure broken
  across two lines is unreadable and numeric columns take 1.4.10's exemption
  inside `.table-scroll` instead.

None of the three was reachable by the Phase 12 sweep, which varies the
viewport and holds the data fixed. These vary the data and hold the viewport at
its narrowest. Both are needed, and 22.6 asks for both.

### F-31 — RESOLVED in Phase 16. A "strict for model/" config was strict for everything

Item 155 asks for strict type checks. The decision recorded in
[`pyproject.toml`](../pyproject.toml) is that **`model/` is checked strictly
and `apps/api/app/` is checked but not strictly**, and the reasoning is stated
there: `model/` is the arithmetic, where a type error is a wrong number, and it
imports nothing but the standard library; `apps/api/app/` sits on FastAPI,
PyMuPDF and openpyxl, whose own type information is incomplete, and making it
strict would produce a lot of `Any` with a strict flag on top — which reads as
checked and is not.

The first configuration expressed that with

    [[tool.mypy.overrides]]
    module = "model.*"
    strict = true

and reported **397 errors across 73 files**, most of them in the package it was
not supposed to be checking strictly. `strict` is a global flag; in a
per-module override it is applied more broadly than it reads. Listing the seven
flags it implies, explicitly, gave 108 — the number the decision actually
described.

The lesson is the one worth keeping: **a configuration that reads correctly and
behaves differently produces a number nobody can interpret.** 397 looks like a
codebase in trouble and was a config bug; 108 was the real figure, and every
one of them was worth reading.

### F-32 — RESOLVED in Phase 16. Sixteen guards the checker could not verify

Working the 108 down to zero found one class of defect over and over, and it is
the one this codebase is most exposed to.

The sparse ledger returns `Decimal | None` — absent is not zero (rule 1.3) —
and the arithmetic that consumes it was guarded in forms a type checker cannot
narrow:

    if None in (begin, end, cfo, cfi, cff):       # model/checks.py
        continue
    delta = (begin + cfo + cfi + cff) - end

    if all(v is not None for v in expected.values()):   # STEP 37's rebuild
        rebuilt = expected["ebit"] * (D(1) - expected["tax_rate"]) + ...

Both guard correctly **today**. Neither states the guarantee in a form anything
can check — so the next edit that adds a sixth term, or moves a check, produces
a `TypeError` in a subtraction, on the first filing that omits a cash-flow
subtotal. That is not a hypothetical failure mode here; it is the *central* one,
and it would surface as a crashed check run rather than as a wrong number, which
is the better of the two but not by much.

Sixteen sites were rewritten into narrowing forms — naming each operand,
binding narrowed locals, or taking the value as a parameter so the guarantee
crosses the function boundary. Three were genuine latent crashes rather than
unverifiable guards:

- **a table with no detected header row** indexed `table.cell(None, column)`
  in two places, which would raise on the first filing whose header could not
  be found;
- **`callable[[str], str | None]`** as an annotation — the builtin predicate,
  not `Callable`, which never evaluated because of
  `from __future__ import annotations`;
- **`_tree: Node = field(default=None)`**, a non-optional field whose own
  default was `None`.

And five loop variables were reused across loops of different types in the same
function — `row` for an `InterestYear` and then a `RollForwardYear`, `year` for
a label and then a period object. Each read as one kind of thing throughout and
was two.

**Six fields typed `object`** were the other recurring shape:
`ExtractionResult.mappings`, `ScenarioForecast.result`,
`ScenarioValuation.valuation` and three on the portfolio row. Each had a comment
naming the real type. A comment naming a type is not a type: five modules were
reaching through `result` for `.income`, `.balance` and `.taxes` on nothing but
faith, and the loose annotations existed to avoid an import cycle that
`TYPE_CHECKING` handles in two lines.

`model/` and `apps/api/app/` both pass now — 134 files, no issues — and both
are gated in CI.

### F-30 — RESOLVED in Phase 15. A CSRF middleware ate every request body

Written the obvious way — Starlette's `@app.middleware("http")` decorator — the
guard checked the CSRF token by calling `await request.form()`, and that
**consumes the request body**. `BaseHTTPMiddleware` offers no supported way to
hand it on afterwards, so every route downstream saw an empty body.

The failure is quiet in the way that matters. It does not raise anything about
middleware or bodies; it surfaces as

    422: {"loc": ["body", "page"], "msg": "Field required"}

on a field the browser did send. A reader debugging that starts by looking at
the form, then at the route signature, then at the browser — three places the
bug is not.

Twenty-one existing tests caught it here, which is the whole argument for
building a security layer against a suite that already exercises every route.
Had this shipped with the two routes a new phase happens to test, it would have
broken the other thirty in a way nobody would attribute to CSRF.

The fix is a raw ASGI middleware: at that layer the body is bytes, reading it
is one loop and replaying it to the application is three lines. A test asserts a
POST's fields arrive intact, so the shape cannot come back.

### F-27 — RESOLVED in Phase 14. Every export said the currency was unconfirmed

`DetectedMetadata` is a dataclass holding **one field**, `fields: dict[str,
DetectedField]`. The export read it as though the metadata were attributes:

    getattr(result.document.metadata, "reporting_currency", "")

which returns the default for every document, always, and never raises. 21.3
requires an export to state its currency, units, dates, scenario and model
version; three of those five were the string "(unconfirmed)" on a filing whose
currency a human had confirmed.

This is the third appearance of the same shape. Phase 13 had check 17.4 reading
`scale` where the field is `displayed_scale`, and the Phase 12 context bar had
the same. Each was a plausible name for a field that exists under a different
one, and `getattr` with a default turns each into a silent wrong answer.

The fix is one reader, `gather.metadata_field`, used everywhere, and it does
one more thing than the broken code did: **it carries the confirmation state
into the value.** 1.9 and 1.10 make a detected currency and a confirmed
currency different claims, and an export printing them identically makes the
stronger one for both. An unconfirmed value now reads `USD (unconfirmed)`.

### F-28 — RESOLVED in Phase 14. The website displayed the same figure three ways

Item 143 says "compare exports with website outputs", and doing it against the
*rendered page* rather than against the view function both would call is what
found this:

| Screen | How it printed a currency figure |
|---|---|
| `statements.html` | `{{ cell.value }}` — full stored precision, no separators |
| `schedules.html` | `{:,}` — separators, full precision |
| `forecast.html` | `{:,.0f}` — separators, whole units |
| `valuation.html` | `{:,.0f}` — separators, whole units |

21.8 requires an export to equal the website "at the same display precision",
and **that requirement cannot be met against a website that does not agree with
itself.** It is also a reading problem before it is a compliance one: a reviewer
comparing a forecast line to the historical line above it had one rounded to
whole units and the other carrying forty-nine decimal places.

Worse, **the two screens that rounded carried no tooltip.** 4.19 is not
conditional: "label every displayed rounded value with a tooltip showing its
full stored value". Enterprise value has been displayed as `2,873,867` since
Phase 11 with the other forty-three digits reachable from nowhere on the page.

[`apps/api/app/display.py`](../apps/api/app/display.py) is now the single
policy -- currency at whole units, percentages at one place, ratios at four,
days at one, discount factors at six -- registered as Jinja filters so a
template cannot reach a different formatter, and called by `exports/gather.py`
so the export and the page cannot disagree without somebody calling a different
function. Every template that prints a figure emits 4.19's tooltip beside it,
and `tooltip` returns empty where nothing was rounded, because a tooltip
repeating what is already on screen teaches a reader that tooltips are noise.

A test greps every template for a self-applied number format, so the second
display precision cannot come back quietly.

### F-29 — RESOLVED in Phase 14. Two wrong answers to "can a spreadsheet hold this"

Item 140 has to disclose which exported values a workbook cannot carry exactly.
Getting the predicate right took three attempts, and the two failures are the
instructive part.

**Ask the double.** `Decimal(repr(float(v))) == v` — `repr` of a float is the
shortest string that round-trips, so this is exactly "is this value a double".
It reports `153895.30421504256` safe. The file contains `153895.3042150426`,
which is a different number.

**Ask the string.** openpyxl writes every float as `"%.16g"`
(`openpyxl/compat/strings.py`), so compare against that. It reports `0.085`
lost, because the string is `0.08500000000000001`. Nothing was lost: that
string parses back to the same double and displays as `0.085`.

Each is a reasonable question and neither is the one that matters. **The
question is about the whole round trip**: take the value to a double, write it
the way the writer writes it, read that string back as a double, and ask whether
the result is still what the model held. The first predicate under-reports,
the second over-reports, and only the composition of both is the file's own
answer.

Both wrong answers are now tests, with the value that defeats each one, because
the next person to simplify this function will reach for exactly one of them.

The disclosure itself: 21.1 requires XLSX, so refusing the format is not
available. The cell holds what the file can hold, a cell note carries the exact
decimal wherever that is not the value, those cells are styled `Inexact`, and
the Cover tab counts them. Around one numeric cell in eight, on the fixture
model.

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

**Phase 16 (items 154-168) is built**, in
[`apps/api/app/verification/`](../apps/api/app/verification), with
[`release-readiness.md`](release-readiness.md) as its output and
[`pyproject.toml`](../pyproject.toml) carrying the two tool configurations.

**Item 168's report is generated, and that is the whole design.** "Produce a
release-readiness report with PASS/FAIL evidence" could be satisfied by a
markdown file somebody wrote, and a file somebody wrote is a claim about the
code rather than evidence about it -- read six months later by whoever has to
decide whether to trust a number. So every row comes from running something,
the command is printed beside the result, and the exit code is non-zero unless
every gate passed.

**It caught three things on its first run**, which is the argument for building
it rather than writing it: two files I had just added were unformatted, and
**the test count in `README.md` was stale** -- the exact drift item 167 exists
to find. It went stale twice more in the same hour as tests were added, and was
caught both times.

**4.20's claim is made here and nowhere else.** The clause permits "less than
0.0001% error" only once the benchmark suite passes *and* the report identifies
the exact dataset and formulas. The in-app panel cannot satisfy the first half
-- a web process does not observe the test suite -- so it reports coverage and
says the result is not observed. A report generator *runs* the suite, so it can
satisfy both halves: it names the fixtures, the extreme-input cases and the
randomized sweep, and lists all twenty-two of 4.16's outputs with where each
comparison lives. When the benchmark does not pass, or was skipped, the contract
is reported **UNPROVEN** rather than carried forward from the last green run.
Three tests assert that, because it is the one claim in this repository that
would be most tempting to make anyway.

**A skipped gate blocks the verdict.** Rule 1.14 applied to the report itself: a
check that did not run has not passed, and a release report whose worst row
reads NOT RUN is one somebody will read as green.

**A READY verdict says it is not permission to deploy.** Phase 17 item 169 is
explicit -- do not deploy until the target, the access level and the data policy
are confirmed -- and a report saying READY is precisely the artefact most likely
to be quoted as though it were that permission. A test asserts the sentence is
there.

**Section 22's plan is a map with its gaps written in.** Fifty-five clauses;
forty-nine covered by named tests, six with a stated reason. `Coverage` refuses
construction with neither a test nor a reason, because a row with neither reads
as covered -- which is the failure mode of every test plan. The six: 22.1.j
(RBAC is not applicable under 2.2.d, not untested), 22.3.f (no fixture carries
both an original and a restated prior year) and all four of 22.8's performance
targets, which 22.8 itself scopes "to be measured on documented hardware/data"
that no deployment has yet.

**Writing that map found its own defect.** Twenty-seven of the test names in the
first draft did not exist -- guessed from what a test *should* be called rather
than read from the tree. `missing_tests()` is what found them, and it now runs
in the suite, so a renamed test is a failure rather than a silently weakened
claim.

**The production-build gate was checking nothing, and admitting that made it a
gate.** `assert app.routes` passes for any application: this FastAPI version
wraps an included router as a *single* entry, so `len(app.routes)` is 4 whether
the router declares thirty routes or none. It now counts the router's own
declared paths (33), serves a request, and resolves both static mounts.

Items 154 and 155 found **F-31** (a mypy configuration that read as "strict for
`model/`" and was strict for everything, reporting 397 errors across a package
the decision did not cover) and **F-32** (sixteen `Decimal | None` guards
written in forms no checker can verify, three genuine latent crashes, five loop
variables reused across loops of different types, and six fields typed `object`
with a comment naming the real type). Items 156 to 162 found **F-33**
(`margin: 0 auto` on a flex item opts it out of `stretch`, so the item sizes to
its content's min-content -- F-25's failure through a door `min-width: 0` does
not close).

**Phase 15 (items 145-153) is built**, in
[`apps/api/app/security/`](../apps/api/app/security) with
[`incident-response.md`](incident-response.md) beside it. **F-15 is closed.**

Decision 2.2.c has read "authentication required" since Phase 2, and F-15 has
recorded it unimplemented since Phase 4 with the mitigation that
`review_server.py` binds to localhost. A mitigation is not the requirement, and
one that depends on a reader passing the right flag is not even a good one.
`review_server.py` now **refuses** to bind anywhere but loopback without a
credential, rather than printing a warning people scroll past.

**No cryptography is invented.** 20.2's note in `security-model.md` says this
application must not implement its own, and nothing here does: `hashlib.scrypt`
for the password, `hmac.compare_digest` for every secret comparison,
`secrets.token_bytes` for the key. The one construction assembled rather than
called is a signed cookie -- HMAC-SHA256 over `issued|expires|nonce` -- which is
twelve lines a reader can check, and is what every framework does.

**scrypt rather than a hash that is merely cryptographic.** The threat to a
password hash is offline guessing against a stolen copy, and a fast hash makes
that cheap. The parameters ask for 32 MiB per verification: a fraction of a
second for the one person logging in, and 32 MiB per guess for somebody working
through a stolen hash. It is in the standard library, so the most costly place
to get a dependency wrong does not have one.

**The guard is a middleware and defaults to closed.** A per-route dependency
has to be added to every route, and the failure mode of forgetting one is an
unprotected endpoint that looks exactly like a protected one -- there are over
thirty routes and more arrive each phase. `PUBLIC` is four entries, each with
its reason written beside it, and everything else needs a session.

**It is a raw ASGI middleware, and that is a finding rather than a preference
-- F-30.** Checking a CSRF token means reading the form, and reading the form
consumes the request body. Written on Starlette's `BaseHTTPMiddleware` the
guard read the token and every route then saw an *empty* body -- which does not
fail loudly: it surfaces as a validation error on a field the browser did send.
Twenty-one tests caught it here. At the ASGI layer the body is bytes and
replaying it is three lines.

**Session expiry is absolute, not idle.** An idle timeout keeps a session alive
indefinitely for somebody who leaves a tab open, and the tab is the thing
likeliest to be left open on an unlocked screen.

**CSRF is enforced in local-review mode too**, because authentication and CSRF
are different defences: a local server is exactly what a page in another tab
can post to. The token is derived from the session under the signing key rather
than stored, so there is nothing to expire or clean up.

**20.7's easy half and its hard half.** The check is one line in
`routes.py:_load`, because every document route already comes through that
function and a check a route must remember is a check a route will one day not
have. The hard half is that **an unauthorized document answers exactly as one
that does not exist** -- same status, same text. Distinguishing them tells a
prober which identifiers are real, and an identifier here belongs to a filing
nobody has released. A test asserts the two responses are byte-identical.

Under 2.2.b every document has the same owner, so this check can never fail
today. It is built and tested with a second owner anyway: the alternative is a
system whose authorization is a comment saying it would not matter, and the day
it starts to matter is the day somebody adds a second user -- not the day to
discover that reads were never checked.

**20.10's isolation says what it does not buy.** PDF parsing runs in a spawned
child under memory, CPU and wall-clock limits, so a crash, a runaway allocation
or an endless loop ends there rather than in the web process -- and the isolated
render is asserted byte-for-byte identical to the in-process one, so the
separation changed nothing. It is **not** a boundary against code execution: the
child runs as the same user with the same filesystem and the same network.
Writing that down matters more than the code, because an isolation layer whose
limits are unstated gets treated as a sandbox and the next person builds on a
guarantee it never made.

**20.9 reports "not scanned" rather than "clean".** There is no scanner in this
repository and bundling one would mean either a signature database that is
stale the day it is committed, or sending a confidential filing to a third
party. So it is a hook, and with nothing configured the result is a recorded
fact that nothing looked at this file. A field reading "clean" because nobody
looked is worse than no field: it answers the question a reviewer was about to
ask, wrongly.

**20.17's flagged interaction, answered.** `security-model.md` asked in Phase 2
what happens to the `AuditEvent` rows referencing a deleted document, and named
three options. Deletion **tombstones**: cascading deletes the record of the
deletion along with everything else, which is the one entry somebody will later
need, and refusing while references exist means a document can never be deleted
because ingestion always writes one. The tombstone keeps the identifier, the
hash and the filename; it keeps none of the content, which is the point of a
permanent deletion.

**20.18's confirmation is the filename typed back, not a button.** A button is
the same gesture whatever it is attached to, and the gesture is what muscle
memory performs. No default value and no autofocus.

**"An untested backup is not a backup" is 2.6.d's own sentence, so the restore
test is the deliverable.** `snapshot` writes an archive with a manifest naming
every file and its SHA-256; `verify` restores into a scratch directory and
re-hashes everything. A tar that extracts proves the tar is well-formed, not
that the bytes inside are the bytes that went in. The quarterly restore test is
a function that runs in CI on every commit rather than a calendar entry
somebody honours.

**20.20 runs on every commit, not before a release.** `pip-audit --strict` over
the whole installed tree, transitive dependencies included, because a
vulnerability disclosed today is in the tree today and a gate that only fires at
release time reports it at the worst possible moment. Beside it,
[`repository_scan.py`](../apps/api/app/security/repository_scan.py) refuses a
commit carrying a source PDF or a secret *value* -- item 166's confirmation,
made into a check rather than a box somebody ticks.

The fixture test in that scan is worth recording, because the first version was
wrong. It required each fixture PDF to label itself `FICTIONAL`, which they do
not: the ledger's note about `FICTIONAL` is about the engine's YAML fixtures,
not the PDFs. The real invariant is stronger and was already in the tree --
every fixture is **pinned by hash** in `test_fixtures.py` *and* **built by**
`build_fixtures.py`. A hash says what a file is; only the generator says where
it came from.

**Section 25's disclaimer was on one surface and a half.** 25 says "show it in
the model, release flow, and exports", and the web footer carried a
*two-sentence* version while the CLI report carried none. The two sentences the
short form dropped are the two about this system in particular: that historical
figures may carry extraction errors until reviewed, and that outputs must be
verified before being relied on. Trimming a disclaimer keeps the part that
sounds most like boilerplate. [`model/disclaimer.py`](../model/disclaimer.py)
is now the single text, on every screen, in the release gate, in all four
exports and at the end of the CLI report, with a test per surface.

**`incident-response.md` names the residual risks before an incident.** The
sandbox is not a security boundary, uploads are unscanned unless configured, the
rate limiters are per process, the backup archive is not encrypted by the
process that writes it, and a session cannot be revoked except by rotating the
signing key. A procedure that does not say what it cannot defend against is read
as a guarantee it never made. The document also fixes an order that matters:
**rotate the signing key before the password**, or an existing session stays
valid for up to eight hours.

**Phase 14 (items 138-144) is built**, in
[`apps/api/app/exports/`](../apps/api/app/exports) with
[`apps/api/app/display.py`](../apps/api/app/display.py) beside it: 21.1's
sixteen tabs in four formats, the model version that identifies them, and the
7.11 screen.

**21.8 is the requirement the whole package is arranged around**, and it is met
structurally rather than by testing. "Exported values must equal website values
at the same model version and display precision" is a claim about four formats
at once, and four formats built independently satisfy it only by coincidence --
a coincidence that would hold on the fixture and stop holding on the first
filing nobody tested. So the export is one *gather* and four *renderers*:
`gather.py` calls the same view functions the screens call, and JSON, CSV, XLSX
and PDF each render that object and never reach past it. They cannot disagree
without one of them calling a different function, which is a change a reader of
the module will see.

That shape is also what made the phase's three findings findable.

**Item 142's version is a digest, not a counter.** 21.7 asks for an *immutable*
model version ID, and a number that increments on save is not one: it names an
event rather than a state, so two exports can carry the same number and a
reader re-exporting to check a figure cannot tell whether the model moved. The
version is computed from what the model contains -- the document's hash, the
approved mapping's decisions, the scenario, and every resolved assumption with
its value and status. The same model exported twice a week apart reads the same
version; one changed digit anywhere changes it. The document hash alone would
not do, because two different valuations of one filing are two different models.

**20.13 says "raw text", and Phase 2 had already said why that matters.**
[`security-model.md`](security-model.md) §20.13 recorded the trap before any
export existed: prefixing an apostrophe to every cell beginning `=`, `+`, `-` or
`@` would catch every negative figure in the model, turning each into text that
sorts as text, sums as zero, and *looks like a number* -- and 21.8 forbids an
export that does not equal the website. Phase 14 implements that: a cell is
neutralized only when it is not a number, because a `Decimal` is not raw text.
Every neutralized cell is listed on the screen, since a reader who finds an
apostrophe in their data is owed the reason.

**The XLSX half of 20.13 was a live hole, and openpyxl makes it sharper than
the clause sounds.** Assigning a string beginning with `=` to a cell does not
store text: openpyxl sets the cell's data type to *formula*. A filing whose
printed label begins with `=` -- a label out of somebody else's PDF -- would
have arrived in the workbook as something Excel evaluates on open. `+`, `-` and
`@` are stored as inline strings and are inert; `=` alone is not. The workbook
now applies the CSV's own `neutralize`, which closes it and keeps the two
formats agreeing as 21.8 requires. A test asserts no cell in any of the sixteen
sheets has the formula data type.

**The workbook says what it cannot hold.** A spreadsheet number is an IEEE 754
double; 4.11 promises 0.0001% end to end. Those cannot both be true inside a
numeric cell, and 21.1 requires XLSX, so refusing the format is not available.
The cell holds what the file can hold, a cell note carries the exact decimal
wherever that is not the value, those cells are styled `Inexact`, and the Cover
tab counts them -- around one numeric cell in eight. Writing the exact string
into the cell instead would produce a workbook whose every figure is text and
sums to zero; disclosing the loss beats both taking it silently and breaking the
file to avoid it. Getting the *predicate* for that disclosure right took three
attempts and is **F-29**.

**21.2 is not met by colour.** Blue for an input and black for a calculation is
the modelling convention, and colour alone fails WCAG 1.4.1. Each numeric cell
also carries a named cell style -- `Hardcode`, `Calculated`, `Inexact` -- which
Excel shows by name and which survives a monochrome print, with the legend in
words on the Cover tab.

**The PDF report is written with PyMuPDF**, which Phase 3 already depends on to
*read* filings. A reporting library would be a fifth dependency carrying its own
fonts, for one file format, to draw text in boxes. 21.6's nine sections are each
present whether or not they have content, because an omitted section reads as
"nothing to report" and an unbuilt stage means the opposite.

**21.6 asks for a valuation date and two of 16.11's three conventions do not
have one.** Year-end and mid-year are defined relative to the last actual period
end, not to a calendar, so the report names the convention rather than printing
today's date as though something had been discounted from it. `ScenarioValuation`
now carries the date it was given, or `None`, so the absence is reportable
instead of being reconstructed by guesswork.

Phase 14 found three defects in the phases beneath it: **F-27** (every export
called the currency unconfirmed, because the metadata was read with `getattr` on
a dict-backed object -- the third appearance of that shape), **F-28** (four
screens displayed the same figure three different ways, and the two that rounded
carried none of 4.19's tooltips), and **F-29** (two reasonable-looking answers to
"can a spreadsheet hold this value", each wrong in a different direction).

It also fixed a gap left by Phase 13: **the diagnostics screen had no navigation
entry**, so the only way to reach it was to type the URL. It and the new exports
screen are now in the shell.

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
