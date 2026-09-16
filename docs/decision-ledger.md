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
No owner answers had been supplied at the time of writing, so no row below is
CONFIRMED by a person.

---

## 2.1 Product identity

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.1.a | Product name | OPEN | — | Branding, page titles, export headers, README naming |
| 2.1.b | Logo or text-only wordmark | OPEN | — | Navigation shell, export cover page |
| 2.1.c | Company/owner name for footer and exports | OPEN | — | Footer, PDF/XLSX cover, LICENSE decision |

Note: the repository description reads "three statement dcf model done by astra".
That is a repository description, not a confirmed product name, and has not been
treated as one.

## 2.2 Use and access

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.2.a | Local-only, private hosted, or public | OPEN | — | Phase 17 deployment entirely; DB choice (3.2.d); security model depth |
| 2.2.b | Single user or multi-user | OPEN | — | User entity, ownership columns, Phase 15 |
| 2.2.c | Authentication required | OPEN | — | All auth work; API auth middleware (Section 19) |
| 2.2.d | Roles (owner/analyst/reviewer/read-only) | OPEN | — | RBAC, approval workflow gating (14.x), audit actor semantics |

**This is the highest-priority blocker.** 2.2.a alone gates deployment, database
selection, and how much of Section 20 applies.

## 2.3 Source documents

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.3.a | One PDF per company or multiple | OPEN | — | SourceDocument cardinality, restatement handling (10.20–10.21) |
| 2.3.b | Annual only, or annual and quarterly | OPEN | — | Period cadence (2.4.f), rule 1.7 enforcement |
| 2.3.c | Text-native only, or scanned too | OPEN | — | Whether OCR (3.3.c) is built at all; Phase 3 scope; job queue need |
| 2.3.d | May public filings/XBRL cross-check the PDF | OPEN | — | Cross-check validation, external fetch permissions |
| 2.3.e | May external market data be retrieved | OPEN | — | Whether 2.5.b–2.5.e are manual entry or fetched; egress policy |

2.3.c materially changes cost and complexity: OCR brings a job queue, a
Tesseract/OCR dependency, and a whole class of confidence handling (10.8, 10.28).

## 2.4 Model policy

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.4.a | Reporting currency | OPEN | — | Rule 1.10; all normalization |
| 2.4.b | Display unit (units/thousands/millions) | OPEN | — | Rule 1.9; display precision (4.18) |
| 2.4.c | Fiscal year-end | OPEN | — | Period construction |
| 2.4.d | Number of historical periods | OPEN | — | Model period generation |
| 2.4.e | Number of forecast periods | OPEN | — | Forecast horizon, terminal year |
| 2.4.f | Cadence (annual/quarterly/monthly/mixed) | OPEN | — | Rule 1.7; discount time fractions (16.12) |
| 2.4.g | FCFF or FCFE | OPEN | *Spec recommends FCFF; confirmation required (2.4.g)* | Section 16 entirely |
| 2.4.h | Year-end or mid-year discounting | OPEN | — | 16.11–16.14; every PV |
| 2.4.i | Gordon Growth, exit multiple, or both | OPEN | — | 16.15–16.17, 16.24 |
| 2.4.j | Leases treated as debt in the bridge | OPEN | — | 16.19; lease schedule (13.5) |
| 2.4.k | Stock-based compensation treatment | OPEN | — | FCFF bridge, equity schedule |
| 2.4.l | Minority interest, pensions, associates, investments | OPEN | — | 16.19 bridge lines |
| 2.4.m | Tax-loss carryforwards and deferred taxes | OPEN | — | Tax schedule (13.6) |

The existing Python engine already implements an FCFF, year-end, Gordon-Growth
model. **That is a prototype default, not a confirmation of 2.4.g/h/i.** It was
built to the 37-step workflow, before this specification existed.

## 2.5 Market assumptions

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.5.a | Valuation date | OPEN | — | Every discount factor (16.12); rule 1.4 |
| 2.5.b | Risk-free rate source and observation date | OPEN | — | CostOfEquity (16.6); check 17.23 |
| 2.5.c | Beta source, type, observation date | OPEN | — | CostOfEquity |
| 2.5.d | Equity risk premium source and date | OPEN | — | CostOfEquity |
| 2.5.e | Pre-tax cost of debt source and date | OPEN | — | WACC (16.9) |
| 2.5.f | Target or current capital structure | OPEN | — | WACC weights |
| 2.5.g | Terminal growth rate source and justification | OPEN | — | Terminal value (16.15); check 17.24 |
| 2.5.h | Diluted shares source and measurement date | OPEN | — | Per-share value (16.20); check 17.26 |

None of these are derivable from a filing. All require an external, dated source.

## 2.6 Export and retention

| ID | Decision | Status | Answer | Blocks |
|---|---|---|---|---|
| 2.6.a | Required exports (XLSX/CSV/PDF/JSON) | OPEN | — | Phase 14 scope |
| 2.6.b | Retention period for PDFs and extracted data | OPEN | — | 20.17; storage lifecycle |
| 2.6.c | May an administrator permanently delete data | OPEN | — | 20.18; deletion flow |
| 2.6.d | Backup and restore policy | OPEN | — | 20.17; Phase 15 |

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

### F-6 — `run_model.py --rel-tol` and `--abs-tol` crash with an unhandled traceback

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

**F-7a. `sensitivity._shift_wacc` silently fails when `beta = 0`.**
The line `implied_erp = (implied_ke - base.risk_free_rate) / base.beta if base.beta else ZERO`
returns a zero ERP when beta is zero — but with beta zero the cost of equity
equals the risk-free rate regardless of the ERP, so the target WACC is never
reached. The `SensitivityCell` is nonetheless labelled with the target WACC it
did not achieve. Verified by direct construction: a base with `beta = 0` and
`wacc = 0.039166…` shifted to a target of `0.12` returns a `CostOfCapital`
whose `.wacc` is still `0.039166…`. Beta of exactly zero is an unusual input;
the failure is silent, which is the class of thing this repository exists to
prevent.

**F-7b. `Valuation.tv_share_of_ev`'s None guard is not honoured by its only
consumer.** The property returns `None` rather than dividing by zero when
enterprise value is zero (specification 17.27). `report.valuation_block` then
formats it with `f"{valuation.tv_share_of_ev:.1%}"`, which raises `TypeError`
on `None`. The guard is correct; the call site defeats it.

**F-7c. Dividends use silent precedence where every comparable driver
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

### F-10 — Two of the twelve STEP 37 checks test the same identity

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
  (database schema and migrations — needs 3.2.d, which needs 2.2.a),
  **item 23** (error codes and severity), **item 24** (model lifecycle states
  and legal transitions — the state *names* are given in 7.1.b, the transition
  graph is not), and **item 25** (owner review of these contracts).
- Canonical chart of accounts and line-item definitions (11.1) — the engine's
  40 codes are catalogued in [`data-dictionary.md`](data-dictionary.md) §9.6,
  but **no account has a written definition**, which 11.3 mapping review needs.
- Validation check registry and severity model (Section 17), as declarations —
  registry written; **severity assignment blocked by F-4**.
- Design tokens as *named* tokens with contrast-tested candidate values (6.4).
- Fixing F-6 and F-7a–c, adding a dependency-audit step to CI (3.5.c, 20.20),
  and printing the Section 25 disclaimer in the CLI report (20.19). None of
  these depends on an OPEN decision.

Blocked until answered: all of Phase 17, authentication and RBAC, OCR,
deployment, retention, and every numeric market assumption in 2.5.
