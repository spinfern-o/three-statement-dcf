# Source policy

Specification [Section 10](website-build-spec.md) sets out 35 ingestion and
verification rules. This file restates them as a policy a reviewer can
actually follow: what makes a fact verified, what forces manual review, how
restatements and duplicate sources are handled, how blanks and dashes are
treated, and what the confidence and reason-code model is.

Section 11 (normalization and mapping) is included where it is inseparable
from verification — 11.11 gates the Verified label, so it belongs here.

**Scope note.** The *ingestion* half of this policy is now implemented, in
[`apps/api/app/extraction/`](../apps/api/app/extraction) (Phase 3, items
26-38): upload custody, extraction job states, text-native extraction with page
geometry, metadata detection in the UNCONFIRMED state, the deterministic
parser, reason codes and confidence. §12 has the rule-by-rule status.

The *review* half is not. There is no UI, no reviewer action, no mapping and no
verified fact. Where this document says "the reviewer", it is still describing
a system to be built (Phase 4). And the calculation engine in
[`model/`](../model) is unchanged: it begins at STEP 4, with a human having
already read the PDF and transcribed figures into YAML with a page citation.
Nothing yet connects extracted facts to that engine — the mapping stage
between them is Phase 5.

---

## 1. The governing principle

Rule 1.1 through 1.5 are one idea stated five ways: **the system never supplies
a number nobody sourced.**

> 1.1 Never invent a financial value.
> 1.2 Never silently fill a missing PDF value with zero.
> 1.3 Never silently map an ambiguous PDF line item to a model line.
> 1.4 Never silently choose a currency, unit, fiscal year-end, tax rate, WACC,
> terminal growth rate, forecast period, or valuation date.
> 1.5 Never treat a blank, dash, em dash, "N/A," or missing table cell as zero
> unless the source explicitly defines it as zero or a reviewer confirms it.

Every rule below is an application of that. When a rule here seems to make
work slower, that is the rule operating correctly.

---

## 2. Upload and custody

| # | Rule | Policy |
|---|---|---|
| 10.1 | Verify the upload is a PDF **by MIME signature, not filename** | Read the leading bytes. A file named `.pdf` that is not one is rejected at the boundary, before any parser touches it (20.8, 20.11). |
| 10.2 | Calculate and store a SHA-256 hash | Computed on the bytes as received, before any processing. Stored as `SourceDocument.immutable_hash`. It is the identity of the document for the life of the system. |
| 10.3 | Refuse exact duplicate uploads unless the user explicitly creates a linked duplicate record | See §3. |
| 10.4 | Scan the file using the approved security process | 2.2.a is **private hosted**, so this is a server-side scan before the file is written to storage. The specific scanner is an implementation choice, not a Section 2 decision. See [`security-model.md`](security-model.md) §20.9. |
| 10.5 | Record filename, byte size, page count, upload timestamp | Filename stored **sanitized** (20.11); the original is retained as data, never used as a path. |
| 10.12 | Never overwrite an uploaded source document (rule 1.12) | Object storage is write-once. A corrected document is a **new** `SourceDocument`, linked to the old one, never a replacement. |

### Duplicate sources (10.3)

An upload whose SHA-256 already exists for the company is **refused by
default**. The user's options are:

1. **Use the existing document.** The correct answer almost always.
2. **Create a linked duplicate record.** Permitted only as an explicit action,
   recorded with a reason in the audit log (9.14). The new record references
   the existing `immutable_hash` — the bytes are stored once.

A file with a *different* hash but the same filename, period and filing type is
**not** a duplicate. It is a candidate restatement or a revised filing, and it
goes to §4.

2.3.a: **one primary filing per model version**, many versions per company. Historical note on the alternative — if the
answer is one PDF per company, duplicate handling collapses to "refuse", and
the linked-duplicate path is dead code. If multiple, the linkage model above is
required. Do not build either branch until this is answered.

---

## 3. Extraction

| # | Rule | Policy |
|---|---|---|
| 10.6 | Detect whether each page is text-native, image-only, or mixed | Per page, recorded. Drives which path runs and feeds the confidence model (§7). |
| 10.7 | Extract embedded text **and coordinates** from text-native pages | Coordinates are not optional — they are what 10.31's highlighted-cell view and `SourceLocation.bounding_box` need. |
| 10.8 | OCR image-only pages | 2.3.c: **text-native only**. OCR is not built, and an image-only page is a hard rejection with an explanatory message rather than a silent empty extraction. |
| 10.9 | Preserve the original page number for **every** text span and table cell | No exceptions. A fact without a page cannot be verified, and acceptance criterion 24.3 requires every extracted value link to a page and location. |
| 10.25 | Extract values as **raw strings before numeric parsing** | `ReportedFact.raw_value` is the characters as printed. Parsing happens afterwards and separately, and both are retained (see §6). |

**Isolation.** PDF and OCR processing runs outside the web process (20.10) and
never executes document content (20.11). Extraction jobs that may exceed a
request timeout run on a queue (3.2.f) — which, per 2.3.c (text-native only), may not
be needed at all if OCR is out of scope.

---

## 4. Metadata detection and confirmation

This is where rule 1.4 lives. Ten fields are detected and **none of them is
trusted.**

10.10 requires detecting: document title, company name, reporting period,
fiscal year-end, currency, scale, audited status, and accounting standard.

| # | Rule | Policy |
|---|---|---|
| 10.11 | Mark detected metadata as **UNCONFIRMED** | The initial state of every detected field, without exception. A value being obviously right does not make it confirmed. |
| 10.12 | Present each detected metadata field to a reviewer | Shown beside the page region it came from. |
| 10.13 | Require confirmation or correction of **every required** metadata field | Nothing downstream runs until every required field is confirmed. Check `VAL-017-002` in [`validation-policy.md`](validation-policy.md) is the gate. |

**The four that are load-bearing**, because getting them wrong produces a
plausible, confident, wrong model:

| Field | Rule | Failure mode if silently chosen |
|---|---|---|
| `displayed_scale` | 1.9 | A 1000× error that looks entirely normal |
| `reporting_currency` | 1.10 | Values mixed across currencies with no exchange-rate basis |
| Reporting period (start/end) | 1.7 | Annual, quarterly, YTD and TTM figures mixed in one column |
| `audited_status` | STEP 1 | An unaudited figure presented with the authority of an audited one |

The engine takes the same position, one step earlier: `CompanyProfile` has no
defaults at all, and `loader.load_profile` refuses a blank `units` field with
a message naming STEP 1. It cannot *detect* anything — a human types it in —
so it enforces confirmation by making omission fatal rather than by tracking an
UNCONFIRMED state.

---

## 5. Table and period structure

| # | Rule | Policy |
|---|---|---|
| 10.14 | Build a source map for IS, BS, CF, statement of equity and all relevant notes | The engine's direct ancestor: `profile.SourceMap` requires a page for twelve named sections (STEP 2) and `SourceMap.missing()` lists every section still unmapped rather than treating the map as complete. |
| 10.15 | Remove repeated table headers **only in normalized table data**; retain the raw extraction | Two representations, always. The raw one is evidence. |
| 10.18 | Detect footnote markers without including the marker in the numeric value | A superscript `(2)` is not a digit. The marker is retained on the fact as a pointer to the note. |
| 10.19 | Detect columns with different dates or periods | A table whose columns are FY2025 and FY2024 must not have its columns transposed or merged. Drives `SourceLocation.column_label_optional`. |
| 10.22 | Detect continuing versus discontinued operations | Recorded on the fact. Mixing them is a restatement-class error. |
| 10.23 | Detect consolidated versus segment tables | `ReportedFact.scope`. Rule 1.11 forbids mixing them. |
| 10.24 | Detect annual, quarterly, YTD and TTM periods | Rule 1.7. 2.3.b and 2.4.f are both **annual**, so the model holds annual periods only — the others are detected in order to be *rejected*, not stored. |

**Subtotals are not components (rule 1.6).** A table row labelled "Total
current assets" is a validation target (11.7), not an addend. The engine
implements this precisely: `accounts.DERIVED` names each subtotal's components,
`Ledger.fill_derivable()` computes an absent subtotal from them, and
`Ledger.cross_check()` compares a *reported* subtotal against its derived value
and reports the delta without correcting it.

---

## 6. Parsing, signs, and rule 1.5

### The parse is deterministic and reversible

| # | Rule | Policy |
|---|---|---|
| 10.26 | Parse deterministically based on locale, currency, unit and sign | No heuristic that varies by document. The locale is a recorded input to the parse, not a guess. |
| 10.27 | **Reject ambiguous decimal/thousands separators for manual review** | `1.234` is 1.234 or 1234 depending on locale. If the locale is not confirmed, the fact does not get a parsed value — it gets a reason code and a review flag. |
| 10.16 | Preserve parentheses as negative-sign evidence | `(1,234)` parses to `−1234` **and** retains the string `"(1,234)"`. The parentheses are the evidence for the sign; discarding them discards the justification. |
| 11.8 | Record sign normalization separately from source sign | A source may print an expense positive that the model stores negative. Both are recorded. The engine cannot do this — it declares one convention for the whole model in `accounts.POSITIVE_AND_SUBTRACTED` / `EXPECTED_NEGATIVE` and has no per-fact field. |

### Rule 1.5: blanks, dashes, em dashes and N/A

**This is the rule most likely to be violated by accident, so it gets its own
treatment.**

10.17 requires distinguishing hyphens used as zero, blank, unavailable, or
punctuation. Those are four different meanings of one glyph, and the difference
between the first two changes a subtotal.

The policy:

| Cell content | Default interpretation | Parsed value | What happens |
|---|---|---|---|
| A number | the number | the number | Normal path |
| Empty cell | **unknown** | `null` | Reason code `BLANK_CELL`; review required |
| `-` / `–` / `—` (hyphen, en dash, em dash) | **unknown** | `null` | Reason code `DASH_AMBIGUOUS`; review required |
| `N/A`, `n/a`, `NA`, `not applicable` | **unknown** | `null` | Reason code `NOT_APPLICABLE`; review required |
| `nil`, `none`, `0`, `0.0` | zero | `0` | A written zero is a zero |
| Cell absent from the table entirely | **unknown** | no fact created | The line is not reported; nothing is created to review |

Two exits from `null`, and only two:

1. **The source explicitly defines it.** A filing whose legend says "— denotes
   nil" has defined the dash as zero. The reviewer records the legend's page as
   the basis, and the fact becomes a sourced zero.
2. **A reviewer confirms it**, with a note (10.32). The fact becomes zero with
   `verification_status = CORRECTED` and an audit entry (10.33).

**A `null` parsed value is never coerced to zero to let a calculation
proceed.** Under 18.14 the calculation fails instead, and the failure names the
missing fact.

The engine enforces the same distinction with different machinery, and this is
its central design commitment: the `Ledger` is **sparse**. `ledger.get(COGS,
"2025A")` returns `None`, not `0`, when the company does not report COGS, and
that `None` propagates into the checks. `Ledger.require()` raises with the text
"do not substitute zero". In the input YAML, a `null` under `values:` is
skipped rather than stored, and a line the company does not report is meant to
be omitted entirely — [`README.md`](../README.md) says so explicitly.

The difference: the engine cannot distinguish *"the filing printed a dash"*
from *"the modeller has not typed it in yet"*. Both are absence. The
reason-code model in §7 is what adds that distinction, and it does not exist
today.

---

## 7. Confidence and reason codes

10.28 requires every extracted fact carry a **confidence score and reason
codes**. 10.29 requires manual review for every low-confidence fact.

### Confidence

`ReportedFact.confidence` is a decimal in `[0, 1]`, stored as a decimal string
like every other number.

**The scoring function was OPEN and is now defined** (Phase 3, finding F-13).
The specification requires a score and a review threshold and does not say how
the score is computed, and inventing a calibrated-looking formula would be
exactly the unjustified precision Section 27 warns against. So the score is
defined as the one thing defensible without calibration data:

> **Confidence is the fraction of eight named evidence conditions the fact
> satisfies**, computed exactly.

The eight are listed in `EvidenceCheck` in
[`reasons.py`](../apps/api/app/extraction/reasons.py): read from the embedded
text layer; inside a detected table; a non-empty row label; a resolved column
period; the parse produced a value; the sign follows from an explicit
convention; no footnote marker had to be stripped; the table neither split
across a page break nor repeated its header.

**It is not a probability.** 0.75 means six of eight conditions hold, not a
three-in-four chance the number is right. A reviewer is shown the failed
conditions, not the number alone. The requirements below all still hold, and
the definition was chosen to satisfy them:

- Confidence is **monotonic in evidence**, not in plausibility. A number that
  looks reasonable does not score higher for looking reasonable.
- Confidence is **never** raised by a downstream calculation succeeding.
- A fact with **any** blocking reason code (below) is reviewable regardless of
  its score. Reason codes are not inputs to a threshold — they are independent
  gates.
- The review threshold is a recorded configuration value, not a constant
  buried in code, and it is shown on the diagnostics page (7.10). It is
  `INGEST_REVIEW_THRESHOLD`, default `0.875` — "at most one piece of evidence
  may be missing".

### Reason codes

Two classes. **Blocking** codes force review on their own (10.29, 10.30).
**Advisory** codes reduce confidence and are shown to the reviewer.

#### Blocking — manual review required

| Code | Raised when | Rule |
|---|---|---|
| `BLANK_CELL` | The cell is empty | 1.5, 10.17 |
| `DASH_AMBIGUOUS` | The cell holds a hyphen, en dash or em dash with no source legend defining it | 1.5, 10.17 |
| `NOT_APPLICABLE` | The cell holds N/A or equivalent | 1.5 |
| `SEPARATOR_AMBIGUOUS` | Decimal/thousands separators cannot be resolved for the confirmed locale | 10.27 |
| `SCALE_UNCONFIRMED` | The document's `displayed_scale` is still UNCONFIRMED | 1.9, 10.11 |
| `CURRENCY_UNCONFIRMED` | The document's `reporting_currency` is still UNCONFIRMED | 1.10, 10.11 |
| `PERIOD_AMBIGUOUS` | The column's period cannot be resolved, or mixes bases (annual/quarterly/YTD/TTM) | 1.7, 10.19, 10.24 |
| `SUBTOTAL_MISMATCH` | The fact fails a subtotal reconciliation | **10.30** |
| `CROSS_STATEMENT_MISMATCH` | The fact fails a cross-statement reconciliation | **10.30** |
| `RESTATEMENT_CONFLICT` | Two columns report the same period with different values | 10.20–10.21 |
| `SCOPE_AMBIGUOUS` | Consolidated versus segment cannot be determined | 1.11, 10.23 |
| `SIGN_UNRESOLVED` | The sign cannot be determined from parentheses, position or legend | 10.16 |
| `OCR_LOW_CONFIDENCE` | The OCR engine's own confidence is below its threshold | 10.8, 10.29 |
| `MULTI_CONCEPT_LINE` | One raw line contains several concepts with no defensible split | 11.4 |

#### Advisory — recorded, shown, not individually blocking

| Code | Raised when | Rule |
|---|---|---|
| `OCR_DERIVED` | The value came from OCR rather than an embedded text layer | 10.8 |
| `FOOTNOTE_MARKER_STRIPPED` | A footnote marker was removed from the numeric string | 10.18 |
| `HEADER_REPEATED` | The row came from a table whose header repeats across pages | 10.15 |
| `TABLE_SPLIT_ACROSS_PAGES` | The source table spans a page break | 22.3.h |
| `PAGE_ROTATED` | The source page is rotated | 22.3.g |
| `DISCONTINUED_OPERATIONS` | The fact belongs to discontinued operations | 10.22 |
| `ADJUSTED_MEASURE` | The fact is an adjusted/non-GAAP figure | **1.8** — must not be mixed with reported figures without a labelled bridge |
| `RESTATED_VALUE` | The fact comes from a restated column | 10.20–10.21 |

**10.30 is not negotiable.** Any fact failing a subtotal or cross-statement
reconciliation goes to manual review regardless of confidence. A high score
does not excuse an identity that does not hold.

---

## 8. Restatements

10.20 requires detecting restated and originally reported columns. 10.21 is
the rule with teeth:

> **Prefer the latest explicitly restated historical value and retain both.**

Both halves matter and the second is the one that gets dropped:

1. **Prefer the latest explicitly restated value.** "Explicitly" is doing
   work — the document must *say* the prior period was restated. A prior-year
   column that merely differs from last year's filing is not a restatement; it
   is `RESTATEMENT_CONFLICT` and goes to review.
2. **Retain both.** The originally reported value is not deleted, not
   overwritten and not superseded out of existence. It remains a
   `ReportedFact` with `RESTATED_VALUE` recorded, and rule 1.12's
   never-overwrite requirement applies to the document it came from.

Which value the model *uses* is recorded as an explicit choice with a reason.
The two values, their dates and the chosen one are all visible — 7.3.f
requires restatement warnings be surfaced in the Source Room.

**The engine has an analogue for the choice but not for the detection.**
`assumptions.Conflict` (STEP 11) requires exactly this shape for *assumptions*:
two sources, both dated, both values recorded, and a `chosen` field that must
equal one of the two, plus a mandatory rationale. An unresolved conflict is a
hard error. There is no equivalent for historical facts — the engine's
`Ledger` holds one value per (account, year) and has nowhere to put the
superseded one.

---

## 9. What makes a fact *verified*

This is the question the whole section exists to answer, so it is stated as a
conjunction. **All** of the following must hold:

1. The fact has a `SourceLocation` with a page number and a bounding box
   (10.9, 24.3).
2. Its `raw_value` string is stored, and its `parsed_decimal` was produced by
   the deterministic parser from that string (10.25, 10.26).
3. Its document's metadata — currency, scale, period, audited status — is
   **CONFIRMED**, not merely detected (10.11–10.13).
4. It carries **no blocking reason code**, or every blocking code it carried
   has been resolved by a reviewer action with a note (10.29, 10.32).
5. It passes, or has been explicitly accepted against, its subtotal and
   cross-statement reconciliations (10.30, 11.7, 12.4).
6. A reviewer has accepted or corrected it, and that action is in the audit log
   with a reason (10.32, 10.33).
7. Its mapping to a `NormalizedLineItem` is **human-approved** (11.10, 11.11).

Only then may `verification_status = VERIFIED`.

### Verified is a snapshot, and changes invalidate downstream work

- 10.34: verified source facts are **locked in a versioned snapshot**.
- 1.13: a verified historical value may never be altered without an audit
  entry.
- 10.35: after an approved change, **all dependent mappings and calculations
  re-run**.
- 11.12: the mapping set is versioned, and changing it invalidates dependent
  model results.

A correction is therefore never a quiet edit. It is a new version, an audit
entry, and an invalidation cascade. Integration test 22.4.b ("fact correction
invalidates downstream output") is the executable form of this rule.

### Verified ≠ correct

Verification establishes that a number matches its source and that a human
looked at it. It does not establish that the source is right, that the mapping
is the best one, or that the model built on it means anything. Specification
4.1's SOURCE ACCURACY is what verification delivers; COMPUTATIONAL and
FORECAST accuracy are separate, and 25's disclaimer must remain visible
regardless of how much of the model is Verified.

---

## 10. Reviewer actions and what each requires

| Action | Permitted when | Requires | Rule |
|---|---|---|---|
| **Accept** | No blocking codes, or all resolved | Audit entry | 10.32, 10.33 |
| **Correct** | Any time | **Reviewer note**, audit entry with old and new values | 10.32, 10.33, 1.13 |
| **Split** | The PDF notes provide a defensible basis | Note, allocation formula, audit entry | 11.4, 11.5 |
| **Combine** | Multiple raw lines map to one normalized line | Note, the aggregation shown, audit entry | 11.5, 11.6 |
| **Reject** | The fact should not enter the model | Note, audit entry | 10.33 |

Three constraints on the reviewer's freedom:

- **11.4**: when one raw line contains multiple concepts, **keep it combined**
  unless the notes defend a split. The default is to preserve the company's
  presentation, not to improve on it.
- **11.6**: prevent double counting of components and subtotals. A split that
  leaves the subtotal also mapped double-counts.
- **11.2**: every original company label is preserved, whatever the mapping
  does to it. The engine enforces this at the point of transcription —
  `provenance.Source.line_item` is required and must be the company's own
  wording, and `Figure` cannot be constructed without it.

**Reviewer identity is the owner (2.2.b single user, 2.2.d one role).** The
reviewer, the approver and the author are the same person, so review is a
discipline the tool enforces on one user rather than a separation of duties
between two. That does not weaken the rules — a fact still cannot be verified
without an explicit act — but it is worth stating plainly rather than implying
a second pair of eyes exists. Every rule above requires "a
reviewer"; whether that is a distinct person from the preparer, and whether the
system can tell them apart, depends on whether this is single- or multi-user
and on the role model. If single-user, "reviewer note" degrades to "a note",
which is weaker than 7.4.e intends but is the honest reading. Do not build an
approval workflow that assumes separation of duties until 2.2.b and 2.2.d are
answered.

---

## 11. Rules 1.7–1.11: the five never-mix rules

These are cross-cutting and belong to no single step, so they are collected.

| Rule | Never mix | Enforced by |
|---|---|---|
| 1.7 | Annual, quarterly, YTD, TTM | `PERIOD_AMBIGUOUS`; `ModelPeriod.cadence`; 10.24 detection |
| 1.8 | Reported and adjusted/non-GAAP, without a labelled bridge | `ADJUSTED_MEASURE`; the bridge is a first-class object, not a note |
| 1.9 | Thousands, millions, full units | `SCALE_UNCONFIRMED`; `ReportedFact.source_scale`; 4.6 normalization |
| 1.10 | Currencies, without an explicit dated exchange-rate source | `CURRENCY_UNCONFIRMED`; no implicit conversion exists anywhere |
| 1.11 | Consolidated and segment-level values | `SCOPE_AMBIGUOUS`; `ReportedFact.scope` |

**The engine satisfies 1.9 and 1.10 by construction and not by checking.**
There is exactly one `units` value and one `reporting_currency` for the whole
model, declared on `CompanyProfile`, and no conversion code exists — so mixing
is unrepresentable rather than prevented. That is genuinely sufficient for a
single-document model, which 2.3.a confirms, and genuinely insufficient the moment that
permits more than one. See [`data-dictionary.md`](data-dictionary.md) §9.8 on
the unused `Units.multiplier` and the absent 4.6 normalization.

1.7, 1.8 and 1.11 have **no enforcement in the engine at all**. A modeller who
transcribes a TTM column into a year labelled `2025A`, or an adjusted EBIT
alongside reported revenue, gets a model that computes happily. The engine's
refusals are about *absence*, not about *comparability*.

---

## 12. Section 10 coverage summary

Two columns, because they are two different systems. **Ingestion** is
[`apps/api/app/extraction/`](../apps/api/app/extraction), built in Phase 3.
**Engine** is [`model/`](../model), which begins after a human has transcribed
the figures and is unchanged by Phase 3.

| # | Rule | Ingestion (Phase 3) | Engine (`model/`) |
|---|---|---|---|
| 10.1 | Type by MIME signature | **Yes** — `signature.py`; header at offset 0, version, `%%EOF`, size limit. The filename is never consulted | n/a |
| 10.2 | SHA-256 hash | **Yes** — `hashing.py`, computed on the bytes as received | No |
| 10.3 | Refuse duplicates unless explicitly linked | **Yes** — refused by default; a linked duplicate needs an explicit action *and* a reason | No |
| 10.4 | Security scan | **Structural only** — `scan.py` refuses encryption, JavaScript, `/OpenAction`, launch actions and embedded files, and records a MuPDF repair. **Not an antivirus scan**, and says so | n/a |
| 10.5 | Record filename, size, pages, timestamp | **Yes**, filename stored sanitized (20.11) | No |
| 10.6 | Text-native / image-only / mixed per page | **Yes** — `pages.py` | No |
| 10.7 | Embedded text and coordinates | **Yes** — `text_native.py` + `geometry.py` | No |
| 10.8 | OCR image-only pages | **Refused, by decision 2.3.c.** An image-only page rejects the document and names the page. See finding F-11 | n/a |
| 10.9 | Page number for every span and cell | **Yes**, required — every fact has a `SourceLocation` with a page and a bounding box | **Partial** — `Source.page` is optional where 10.9 requires it |
| 10.10 | Detect the ten metadata fields | **Yes** — `metadata.py`, plus `filing_type` and `number_locale` | No; `CompanyProfile` refuses blanks instead |
| 10.11 | Mark detected metadata UNCONFIRMED | **Yes**, without exception | Different mechanism |
| 10.12–10.13 | Present to a reviewer; require confirmation | **State transition yes, UI no.** `confirm_metadata()` implements 10.13 and 10.35; the reviewer interface is Phase 4 item 44 | n/a |
| 10.14 | Source map for statements and notes | **Partial** — tables are found and captioned, but a *mapped* source map is Phase 4 | **Yes, in spirit** — `profile.SourceMap`, twelve required sections, `missing()` reports gaps |
| 10.15 | Repeated headers removed only from normalized data | **Yes** — raw cells kept; repeated header rows flagged and excluded from facts | n/a |
| 10.16 | Parentheses as negative-sign evidence | **Yes** — the value is negative *and* `"(1,234)"` is retained | n/a |
| 10.17 | Distinguish hyphen as zero / blank / unavailable | **Yes** — every dash form is `DASH_AMBIGUOUS` with no value. This is rule 1.5's main test | Sparse `Ledger`: absent is not zero |
| 10.18 | Footnote markers not in the numeric value | **Yes**, and the marker is kept. NFKC is deliberately *not* used, because it turns a superscript one into a digit | n/a |
| 10.19 | Columns with different dates or periods | **Yes** — per-column period labels | n/a |
| 10.20–10.21 | Restatement detection and retention | **No** — `RESTATEMENT_CONFLICT` is defined but nothing raises it | No for facts; `assumptions.Conflict` has the shape for assumptions |
| 10.22 | Continuing versus discontinued operations | **No** — the code exists, the detector does not | No |
| 10.23 | Consolidated versus segment | **Yes** — read from the table caption; `SCOPE_AMBIGUOUS` when it cannot be determined | No |
| 10.24 | Annual / quarterly / YTD / TTM | **Detected to be refused** — a column header naming another basis raises `PERIOD_AMBIGUOUS` (2.3.b is annual only) | `Periods` validates structure; no dates, so basis cannot be checked |
| 10.25 | Raw strings before numeric parsing | **Yes** — `raw_value` is always stored | **Partial** — `yaml_exact.py` preserves the scalar as written, but the text is not retained on the `Figure` |
| 10.26 | Deterministic parse by locale, currency, unit, sign | **Yes** — `parsing.py` | n/a |
| 10.27 | Reject ambiguous separators for review | **Yes** — a cell is ambiguous iff two locales both read it and disagree | n/a |
| 10.28 | Confidence and reason codes | **Yes** — see §7 and finding F-13 | No |
| 10.29 | Low confidence forces review | **Yes** — `LOW_CONFIDENCE` below the configured threshold | No |
| 10.30 | Reconciliation failure forces review | **Codes defined, not raised.** `SUBTOTAL_MISMATCH` and `CROSS_STATEMENT_MISMATCH` need the mapping of Phase 5 before a subtotal has components to compare | The engine's own equivalent runs: `Ledger.cross_check()` is check 17.10 |
| 10.31 | Highlighted PDF cell beside the fact | **Data yes, UI no** — every fact carries a page and a box | n/a |
| 10.32 | Correction only with a reviewer note | **Yes for metadata**; fact-level correction is Phase 4 | n/a |
| 10.33 | Audit every action | **Partial** — `AuditEvent` exists, an entry without a reason raises, and job transitions and metadata confirmations are recorded. Fact-level actions are Phase 4 | No audit log |
| 10.34 | Lock verified facts in a versioned snapshot | **No** — nothing is verified yet, so there is nothing to lock | No versioning |
| 10.35 | Re-run dependents after an approved change | **Yes, at the parse level** — confirming metadata re-parses and re-scores every fact | Every run rebuilds the whole model, which is reproducible but not a snapshot |

**What is still missing, stated plainly:** no fact reaches `VERIFIED`. §9's
conjunction requires a reviewer action (Phase 4) and an approved mapping
(Phase 5), and neither exists. Everything Phase 3 produces is `UNVERIFIED` and
waiting.

---

## Related documents

- [`website-build-spec.md`](website-build-spec.md) — Sections 10 and 11, authoritative
- [`data-dictionary.md`](data-dictionary.md) — the `SourceDocument`, `SourceLocation`, `ReportedFact` and `FactMapping` fields this policy governs
- [`validation-policy.md`](validation-policy.md) — checks 17.1–17.7, which test compliance with this policy
- [`security-model.md`](security-model.md) — 20.8–20.11, upload safety
- [`decision-ledger.md`](decision-ledger.md) — the decisions cited above, and findings F-11 to F-13
- [`../apps/api/app/extraction/`](../apps/api/app/extraction) — the implementation
