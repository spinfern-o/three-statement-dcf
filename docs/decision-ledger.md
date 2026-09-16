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

### F-1 — The existing engine uses binary floating point, which the spec prohibits

**Severity: blocks any claim of Section 4 compliance.**

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

Resolution required: port the authoritative calculation path to `Decimal` under
a declared context (4.7: ≥28 significant digits; 4.8: ROUND_HALF_EVEN), keeping
the existing tests as a behavioural regression net. Until then, no Section 4
claim may be made. See 4.20.

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

---

## Work that is NOT blocked

Buildable now, because it depends on no OPEN decision:

- The `Decimal` calculation core and its context policy (Section 4.2–4.9), and
  the independent benchmark implementation (4.15) — resolves F-1.
- Formula catalog and data dictionary as definitions (Phase 2, items 17–24).
- Canonical chart of accounts and line-item definitions (11.1).
- Validation check registry and severity model (Section 17), as declarations.
- Design tokens as *named* tokens with contrast-tested candidate values (6.4).

Blocked until answered: all of Phase 17, authentication and RBAC, OCR,
deployment, retention, and every numeric market assumption in 2.5.
