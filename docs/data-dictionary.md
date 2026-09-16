# Data dictionary

Specification [Section 9](website-build-spec.md) names fourteen entities and
their fields. This file defines each field: its type, whether it is required,
its unit/currency/scale where that applies, and the specification rule or
workflow step it serves.

It also records, for every entity, what the **existing Python engine** in
[`model/`](../model) has today. That matters because the engine was built to
the 37-step workflow in
[`three_statement_model_to_dcf_step_by_step.txt`](../three_statement_model_to_dcf_step_by_step.txt),
not to this specification, and the two vocabularies overlap without matching.
Where they diverge it is said plainly rather than smoothed over.

**Nothing in Section 9 is persisted today.** The engine has no database, no
identifiers, no timestamps, and no versioning. Every `id` column below is a
definition, not a description of something that exists.

## How to read the tables

| Column | Meaning |
|---|---|
| **Field** | The field name as specification Section 9 gives it. Names ending `_optional` are reproduced verbatim from the specification; the `Req` column carries the actual obligation. |
| **Type** | Storage type. `decimal(string)` means the value crosses the API boundary as a decimal string (4.2) and becomes a `Decimal` before arithmetic (4.3). |
| **Req** | `Y` required, `N` optional, `OPEN` where a decision determines it. |
| **Unit / scale** | The unit the field is expressed in. `—` where the field is not a quantity. |
| **Serves** | The specification rule/section or workflow STEP the field exists for. |

Conventions that apply to every table:

- Every `id` is an opaque server-generated identifier. Its concrete type
  (UUID, integer, ULID) follows from the database engine, now PostgreSQL via
  2.2.a *private hosted* (so UUID or bigint, not SQLite rowid) — it follows from the database
  choice, which follows from the hosting model (3.2.d).
- Every `*_at` / `*_date` timestamp is UTC, ISO 8601. Storing local time
  would make `10.19` (columns with different dates) and `2.5.b–h`
  (observation dates) ambiguous.
- No monetary field is a float anywhere, at any boundary. Rules 1.15 and 4.4
  prohibit it, and [`model/numeric.py`](../model/numeric.py) enforces it by
  refusing a `float` rather than converting one.

---

## 9.1 User

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.1; actor reference for 9.14 `actor_id` |
| `name` | string | Y | — | Audit legibility (20.15); "model owner" on 7.1.c |
| `email` | string | Y | — | Identity; 2.2.c authentication |
| `role` | enum | Y | `owner` | 2.2.d: **one role**. Single-valued, because 2.2.b is single user and 20.6 applies RBAC only if multi-user |
| `created_at` | timestamp | Y | UTC | Audit |
| `disabled_at` | timestamp | N | UTC | Soft deactivation; keeps 9.14 actor references resolvable after a user leaves |

**Engine counterpart: none.** There is no user, no actor, and no notion of
who did anything. Assumptions carry a free-text `source` string but no owner.

**Resolved (2026-09-16).** 2.2.b is **single user**, so this entity collapses to
a single constant row and `role` is single-valued. 2.2.c is **authentication
required** — the credential exists even though there is only one identity
behind it, because 2.2.a puts confidential filings behind a network endpoint.
Retained for the audit trail, where 10.33 needs an actor even when there is
only ever one. Historical note: **if**
authentication is not required, there are no credentials to model and `email`
becomes a label rather than an identifier. 2.2.d is answered — the role
enumeration. The specification lists four candidate roles in 2.2.d but does
not confirm them; writing them into a schema would be answering the decision.

---

## 9.2 Company

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.2 |
| `legal_name` | string | Y | — | STEP 1 (company name); export cover (21.3) |
| `display_name` | string | Y | — | 7.1.a portfolio listing |
| `ticker_optional` | string | N | — | 16.20 per-share context; absent for a private company |
| `reporting_currency` | ISO 4217 code | Y | — | STEP 1; rule 1.10 (never mix currencies) |
| `fiscal_year_end` | string (month-day) | Y | — | STEP 1; 2.4.c; period construction |
| `industry_optional` | string | N | — | Context only; no calculation depends on it |
| `created_at` | timestamp | Y | UTC | Audit |
| `updated_at` | timestamp | Y | UTC | Optimistic concurrency (Section 19) |

**Engine counterpart:
[`model/profile.py`](../model/profile.py) `CompanyProfile`.**

| Engine field | Section 9 field | Note |
|---|---|---|
| `company_name` | `legal_name` / `display_name` | The engine has **one** name field. Section 9.2 has two. |
| `reporting_period` | — | No Section 9.2 equivalent. Closest is `SourceDocument.reporting_period_start/end` (9.3), which is a different granularity: the engine's is a label such as `FY2025`, not a date pair. |
| `fiscal_year_end` | `fiscal_year_end` | Free text in the engine (`"December 31"`), not a structured month-day. |
| `reporting_currency` | `reporting_currency` | Free text in the engine; not validated against ISO 4217. |
| `units` (`Units` enum) | `SourceDocument.displayed_scale` (9.3) | **Divergence.** The engine puts scale on the *company*; Section 9 puts it on the *document*. See the note below. |
| `audited` (bool) | `SourceDocument.audited_status` (9.3) | **Divergence**, same shape: per-company in the engine, per-document in Section 9. |
| — | `id`, `ticker_optional`, `industry_optional`, `created_at`, `updated_at` | Absent from the engine. |

### Divergence worth deciding: where scale and audited status live

Section 9 is right and the engine is narrower. A company that supplies two
filings can have one in thousands and one in millions, or one audited and one
not; the engine cannot represent that, because it carries a single
`units`/`audited` pair for the whole model. The engine is internally
consistent about it — one declared unit for every figure, which satisfies
rule 1.9 (never mix scales) by making mixing unrepresentable — but it does so
by removing a capability rather than by reconciling.

Moving these to `SourceDocument` is a schema change with no OPEN decision
behind it, and **is not blocked**. It is recorded here rather than done,
because `model/` is out of scope for this document.

---

## 9.3 SourceDocument

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.3 |
| `company_id` | id → 9.2 | Y | — | 20.7 (prevent cross-company access) |
| `immutable_hash` | string (SHA-256, hex) | Y | — | 10.2; 10.3 duplicate detection; check 17.1 |
| `original_filename` | string | Y | — | 10.5; must be stored sanitized (20.11) |
| `mime_type` | string | Y | — | 10.1 — determined by **signature**, not by filename extension |
| `byte_size` | integer | Y | bytes | 10.5; 20.8 size limits |
| `page_count` | integer | Y | pages | 10.5; 20.8 page-count limits |
| `reporting_period_start` | date | Y | — | 10.10; rule 1.7 (never mix annual/quarterly/YTD/TTM) |
| `reporting_period_end` | date | Y | — | 10.10; rule 1.7 |
| `filing_type` | enum | Y | `annual` | 10.10. 2.3.b is **annual only**, so the set is single-valued today; it widens if quarterly comes into scope |
| `reporting_currency` | ISO 4217 code | Y | — | 10.10; rule 1.10 |
| `displayed_scale` | enum `units\|thousands\|millions` | Y | — | 10.10; rule 1.9; STEP 1 |
| `audited_status` | enum `audited\|unaudited\|reviewed\|unknown` | Y | — | 10.10; STEP 1 |
| `uploaded_at` | timestamp | Y | UTC | 10.5 |
| `extraction_status` | enum | Y | — | 10.6–10.8; Phase 3 item 29 (extraction job states) |
| `verification_status` | enum | Y | — | 10.11–10.13; check 17.2 |

Every detected value in this table starts **UNCONFIRMED** (10.11) and requires
reviewer confirmation or correction (10.12–10.13). `displayed_scale`,
`reporting_currency` and the period bounds are the four that rules 1.7, 1.9
and 1.10 make dangerous to get wrong, and 1.4 forbids choosing silently.

**Now implemented for ingestion (Phase 3).**
[`apps/api/app/extraction/records.py`](../apps/api/app/extraction/records.py)
holds every field in this table, with the hash computed on the bytes as
received and the file stored write-once and content-addressed. The engine note
below still describes `model/`, which is a separate stage and unchanged.

**Engine counterpart: a string.** `Source.document` in
[`model/provenance.py`](../model/provenance.py) and `SourceMap.document` in
[`model/profile.py`](../model/profile.py) are both free text, e.g.
`"Example Industries FY2025 Form 10-K"`. There is no file, no hash, no byte
size, no page count, no MIME type, and no extraction or verification state.
The engine begins *after* a human has read the PDF; the document is a citation
label, not an artifact. Nothing in the engine can satisfy check 17.1.

`extraction_status` and `verification_status` enumerations are **OPEN** — see
"Lifecycle states" at the end of this file.

---

## 9.4 SourceLocation

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.4 |
| `document_id` | id → 9.3 | Y | — | 10.9 (preserve the original page for every span) |
| `page_number` | integer ≥ 1 | Y | pages | 10.9; 7.3.e; 24.3 |
| `bounding_box` | 4 × decimal(string) | Y | PDF user-space points | 10.31 (show the highlighted cell); 7.3.e |
| `raw_text` | string | Y | — | 10.7; 10.25 (extract as raw strings before parsing) |
| `table_id_optional` | id | N | — | 10.14–10.15 table structure |
| `row_label_optional` | string | N | — | 11.2 (preserve every original company label) |
| `column_label_optional` | string | N | — | 10.19 (columns with different dates/periods) |

`bounding_box` is stored as four decimal strings, not floats, for the same
reason as everything else: it is the evidence that a reviewer's highlight sits
where the number was, and it should reconstruct exactly. Its coordinate origin
and rotation handling must be recorded alongside it — 22.3.g requires rotated
pages be tested.

**Now implemented for ingestion (Phase 3).** `SourceLocation` in
[`records.py`](../apps/api/app/extraction/records.py) carries the page, a
`BoundingBox` of four decimal strings, the raw text, and the table, row and
column labels. `page_number` is required and `bounding_box` is produced for
every fact, which is what acceptance criterion 24.3 asks for.

**Engine counterpart: `Source(document, page, line_item)`** in
[`model/provenance.py`](../model/provenance.py).

| Engine field | Section 9 field | Note |
|---|---|---|
| `page` | `page_number` | **Divergence on obligation.** The engine allows `page=None` (`Source.cite()` prints `"(page not recorded)"`). Specification 10.9 and acceptance criterion 24.3 require a page for every value, so `page_number` above is required. |
| `line_item` | `row_label_optional` | The engine **requires** it, and requires it to be the company's own wording. Section 9.4 marks it optional. The engine is stricter here, and 11.2 supports the engine. |
| — | `bounding_box`, `raw_text`, `table_id_optional`, `column_label_optional` | Absent. A hand-transcribed figure has a page, not a rectangle. |

---

## 9.5 ReportedFact

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.5 |
| `source_location_id` | id → 9.4 | Y | — | 24.3 (every extracted value links to a location) |
| `raw_label` | string | Y | — | 11.2; STEP 4 (reported line-item name) |
| `raw_value` | string | Y | — | 10.25. The characters as printed, including parentheses, dashes and footnote markers |
| `parsed_decimal_optional` | decimal(string) | N | source scale | 10.26. **Null is meaningful**: it means parsing did not produce a defensible number — see rule 1.5 below |
| `currency` | ISO 4217 code | Y | — | rule 1.10 |
| `source_scale` | enum `units\|thousands\|millions` | Y | — | rule 1.9; 4.5 |
| `normalized_value_optional` | decimal(string) | N | model base unit | 4.6. Null until scale/currency are confirmed |
| `period_start` | date | Y | — | rule 1.7; 4.5 |
| `period_end` | date | Y | — | rule 1.7; 4.5 |
| `instant_date_optional` | date | N | — | Balance-sheet items are instants, not durations. Required for balance-sheet facts, null for flows |
| `scope` | enum `consolidated\|segment\|parent` | Y | — | rule 1.11; 10.23 |
| `segment_optional` | string | N | — | 10.23; STEP 13 segment revenue |
| `sign_convention` | enum | Y | — | 10.16 (parentheses as negative evidence); 11.8 (record sign normalization separately from source sign) |
| `confidence` | decimal(string) 0–1 | Y | — | 10.28; 10.29 (low confidence forces manual review) |
| `verification_status` | enum | Y | — | 10.29–10.33; check 17.5 |
| `reviewer_id_optional` | id → 9.1 | N | — | 10.32 (correction only with a reviewer note) |

Three field-level rules deserve stating, because they are where silent damage
happens:

1. **`raw_value` and `parsed_decimal_optional` are both stored, always.** 4.6
   requires the source value be retained for exact reconstruction. A fact
   whose `raw_value` is `"(1,234)"` and whose parsed value is `-1234` keeps
   both; discarding the string discards the evidence for the sign.
2. **`parsed_decimal_optional = null` is not zero.** Rule 1.5 forbids treating
   a blank, dash, em dash or "N/A" as zero unless the source defines it as
   zero or a reviewer confirms it. The null and the reason code carry that;
   see [`source-policy.md`](source-policy.md).
3. **`normalized_value_optional` never overwrites `parsed_decimal_optional`.**
   4.6 requires both the normalized and the source value. `source_scale` is
   what makes the conversion reversible (22.2.e).

`sign_convention`, `verification_status` and the `confidence` reason codes are
enumerated in [`source-policy.md`](source-policy.md) rather than here.

**Now implemented for ingestion (Phase 3),** with three recorded divergences
from this table:

1. **`period_label` exists, and `period_start`/`period_end` may be null at
   ingestion.** A column headed `2025` is an unambiguous *label*; its date
   range depends on the fiscal year-end, which is UNCONFIRMED until a reviewer
   confirms it. Filling the dates from an unconfirmed year-end is what rule 1.4
   forbids, so the label is stored and the dates wait.
2. **`currency` and `source_scale` are references to the document's detected
   metadata, not values copied onto each fact.** Copying an UNCONFIRMED scale
   onto ten thousand facts makes correcting it a migration. Until both are
   confirmed, every fact carries `SCALE_UNCONFIRMED` and
   `CURRENCY_UNCONFIRMED`, which block it.
3. **`confidence` is a `Confidence` object, not a bare number** — the score
   plus the evidence conditions that produced it. See finding F-13.

**Engine counterpart: `Figure`** in
[`model/provenance.py`](../model/provenance.py) — `value`, `year`, `source`.

| Section 9 field | Engine | Note |
|---|---|---|
| `raw_value` | **absent** | The engine stores only the parsed `Decimal`. The YAML file *is* the raw layer; `model/yaml_exact.py` preserves the scalar as written so the digits survive parsing, but the text is not retained on the `Figure`. |
| `parsed_decimal_optional` | `Figure.value` | Required in the engine, never null. Absence is expressed by the account simply not being in the sparse `Ledger`. |
| `period_start` / `period_end` / `instant_date_optional` | `Figure.year` | **Divergence.** The engine's period is a label (`"2025A"`), not a date pair. It has no dates at all — see 9.9 and the 16.12 note in [`formula-catalog.md`](formula-catalog.md). |
| `currency`, `source_scale` | **absent per fact** | Carried once on `CompanyProfile` for the whole model. |
| `normalized_value_optional` | **absent** | The engine performs **no** unit normalization — see the 4.6 note under 9.8. |
| `scope`, `segment_optional` | **absent** | Segment revenue exists in the *forecast* (`assumptions.segments`) but not on a historical fact. |
| `sign_convention` | **absent as a field** | The engine states its convention once, as module constants `POSITIVE_AND_SUBTRACTED` and `EXPECTED_NEGATIVE` in [`model/accounts.py`](../model/accounts.py). This is a design choice, not an oversight: one convention for the whole model rather than per fact. It cannot record that a *source* used the opposite sign, which is what 11.8 asks for. |
| `confidence`, `verification_status`, `reviewer_id_optional` | **absent** | There is no confidence model and no review workflow. Every transcribed figure is treated as equally authoritative. |

---

## 9.6 NormalizedLineItem

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.6 |
| `canonical_code` | string (stable) | Y | — | 11.1 canonical chart of accounts; join key for 9.12 |
| `display_name` | string | Y | — | 7.5; 6.6.d accessible table markup |
| `statement_type` | enum `income\|balance\|cashflow\|equity` | Y | — | 12.1–12.3 |
| `parent_code_optional` | string → `canonical_code` | N | — | 7.5.f row hierarchy; 11.6 (prevent double counting of components and subtotals) |
| `expected_sign` | enum `positive\|negative\|either` | Y | — | 10.16; 11.8 |
| `cash_or_non_cash` | enum | Y | — | 12.3.b non-cash adjustments; 11.9 |
| `operating_or_financing` | enum `operating\|investing\|financing\|non_operating` | Y | — | 11.9; STEP 7 |
| `definition` | text | Y | — | 11.3 ("map … only when definitions align") — the text a reviewer compares a raw label against |

This is the entity with the **largest existing overlap**, and the one where
the divergence is most worth reading carefully.

**Engine counterpart:
[`model/accounts.py`](../model/accounts.py)** — but as *module constants*, not
as rows.

| Section 9.6 field | Engine equivalent | Status |
|---|---|---|
| `canonical_code` | The string constants: `REVENUE = "revenue"`, `COGS = "cogs"`, … | **Present.** The 40 distinct codes below are the engine's chart of accounts (41 statement slots; `net_income` appears on both the income statement and the cash flow statement, which is what check #5 reconciles). |
| `statement_type` | `Statement` enum + `VALID_ACCOUNTS` | **Present**, three statements. No `equity` statement type — see the gap note. |
| `parent_code_optional` | `DERIVED` | **Present but inverted.** `DERIVED` maps *subtotal → (positive terms, negative terms)*. That is a child list with signs, which is strictly more information than a parent pointer, and it is what lets the engine both derive and cross-check a subtotal. A `parent_code` view is derivable from it. |
| `expected_sign` | `POSITIVE_AND_SUBTRACTED`, `EXPECTED_NEGATIVE` | **Partial, and purely declarative.** Two module-level tuples covering 9 of the 40 codes. Not a per-account field, and **neither tuple is read anywhere in `model/`** — they document the convention that the formulas were written to, and nothing validates a value against them. |
| `operating_or_financing` | `OPERATING_ITEMS`, `INVESTING_ITEMS`, `FINANCING_ITEMS` | **Present** for cash-flow accounts only. Income and balance accounts carry no such tag. |
| `cash_or_non_cash` | — | **Absent.** D&A and stock-based compensation are non-cash add-backs and are treated as such in `forecast.py`, but nothing declares them non-cash. |
| `display_name` | — | **Absent.** Reports print the raw code (`other_noncurrent_liabilities`). |
| `definition` | — | **Absent.** No account has a written definition anywhere in the repository. This is the gap that matters most for 11.3: a reviewer approving a mapping has no canonical text to compare the company's label against. |

### The engine's chart of accounts, as it stands

Income statement (`INCOME_ACCOUNTS`, STEP 5): `revenue`, `cogs`,
`gross_profit`, `operating_expenses`, `ebit`, `interest_expense`,
`other_income_expense`, `pretax_income`, `taxes`, `net_income`.

Balance sheet (`BALANCE_ACCOUNTS`, STEP 6): `cash`, `accounts_receivable`,
`inventory`, `other_current_assets`, `ppe_net`, `other_noncurrent_assets`,
`total_assets`; `accounts_payable`, `other_current_liabilities`, `debt`,
`other_noncurrent_liabilities`, `total_liabilities`; `common_equity`,
`retained_earnings`, `total_equity`.

Cash flow (`CASHFLOW_ACCOUNTS`, STEP 7): `net_income`,
`depreciation_amortization`, `stock_based_compensation`, `change_in_nwc`,
`other_operating`, `cash_flow_from_operations`; `capex`, `acquisitions`,
`other_investing`, `cash_flow_from_investing`; `debt_issuance`,
`debt_repayment`, `share_repurchases`, `dividends`, `other_financing`,
`cash_flow_from_financing`.

### Where the engine's vocabulary is short of Section 12

Specification 12.1–12.3 names lines the engine has no code for. None of these
is a defect in the engine — 11.1 says explicitly "do not force every company
to use every canonical line" — but a canonical chart built for the website
needs them, and the engine's balance check would fail for a company that has
them, as [`README.md`](../README.md) already warns.

| Missing | Specification | Consequence today |
|---|---|---|
| `goodwill`, `intangibles` | 12.2.e | No intangibles schedule (13.3) and therefore no check 17.12 |
| `lease_liabilities` | 12.2.i | Required. 2.4.j: leases **are** debt in the bridge when the filing discloses a liability. Not yet implemented — `EquityBridge` has no lease field |
| `minority_interest` (balance sheet) | 12.2.k | Exists only as an equity-bridge input in `dcf.py`, not as a balance-sheet account |
| `ebitda` | 12.1.f | No line. 12.1.f makes EBITDA conditional on a visible bridge, and the 37-step workflow never defines one. Recorded already in [`decision-ledger.md`](decision-ledger.md) F-1 as outstanding against 4.16 |
| Operating expense **by disclosed category** | 12.1.d | The engine has a single `operating_expenses` line |
| Statement of equity | 12.2.l, 7.5.d | No `equity` statement type; only a retained-earnings roll-forward |
| `fx_effect_on_cash` | 12.3.l | No line; the engine's cash roll-forward is `begin + CFO + CFI + CFF` with no FX term |

---

## 9.7 FactMapping

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.7 |
| `reported_fact_id` | id → 9.5 | Y | — | 11.3 |
| `normalized_line_item_id` | id → 9.6 | Y | — | 11.3 |
| `mapping_type` | enum `one_to_one\|aggregate\|split\|rejected` | Y | — | 11.4 (keep combined unless notes defend a split); 11.5 (show the aggregation) |
| `allocation_formula_optional` | string | N | — | 11.4. Required when `mapping_type = split`; null otherwise |
| `reviewer_note` | text | Y | — | 7.4.e ("Reviewer note required for any manual change"); 10.32 |
| `approved_by` | id → 9.1 | Y | — | 11.10–11.11; check 17.6 |
| `approved_at` | timestamp | Y | UTC | 11.11 |

`approved_by` and `approved_at` are required **on this table** because 11.11
forbids labelling the historical model Verified until every mapping is
human-approved. A proposal that has not been approved is a row in a proposals
table or a null-approval row, depending on the schema; either way check 17.6
counts unapproved mappings, so the distinction must be queryable.

Mapping sets are versioned (11.12), and changing one invalidates dependent
model results.

**Engine counterpart: none — and this is a structural difference, not a gap.**

In the engine the mapping *is* the input file. A modeller writes:

```yaml
income_statement:
  revenue:
    line_item: "Net sales"     # the company's wording  (9.5 raw_label)
    page: 31
    values: { 2025A: 1200.0 }
```

which fuses `ReportedFact`, `SourceLocation` and `FactMapping` into one
hand-authored record. `revenue` is the `canonical_code`; `line_item` is the
`raw_label`. There is no proposal, no approval state, no reviewer, no
`mapping_type`, and no way to express a split or an aggregation other than by
the modeller doing the arithmetic before typing it in — which defeats 11.5's
requirement that the aggregation be shown.

---

## 9.8 ModelVersion

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.8; 21.7 (immutable model version ID on every export) |
| `company_id` | id → 9.2 | Y | — | 20.7 |
| `name` | string | Y | — | 7.1.a |
| `version_number` | integer | Y | — | 18.9 (preserve the prior calculated model version) |
| `status` | enum | Y | — | 7.1.b; Phase 2 item 24 (lifecycle states) — see below |
| `valuation_date` | date | Y | — | 16.8, 16.12. 2.5.a: the date the model version is released, recorded explicitly. Not yet present in the engine |
| `reporting_currency` | ISO 4217 code | Y | — | rule 1.10. 2.4.a: one currency per model, taken from the filing and confirmed at STEP 1 |
| `calculation_scale` | enum | Y | — | 4.6 base unit for calculation; distinct from display scale (2.4.b, 4.18) |
| `created_by` | id → 9.1 | Y | — | Audit |
| `created_at` | timestamp | Y | UTC | 21.7 |
| `locked_at_optional` | timestamp | N | UTC | 19.18 release; null means unreleased |
| `parent_version_id_optional` | id → 9.8 | N | — | 18.9; 14.7 scenario/version lineage |

### `calculation_scale` versus `displayed_scale`, and what the engine does

4.6 requires normalizing every value to **one base unit for calculation**
while retaining the source value and source unit for exact reconstruction.
4.18 requires calculation precision be displayed separately from display
precision. So three things are distinct: the document's `displayed_scale`
(9.3), the model's `calculation_scale` (here), and the UI's display unit
(2.4.b, a Settings concern per 7.12.b).

**The engine implements none of this.** `Units` in
[`model/profile.py`](../model/profile.py) defines a `multiplier` property
(`dollars: 1, thousands: 1_000, millions: 1_000_000`) that **is never called
anywhere in `model/`, `run_model.py` or `tests/`.** Every figure is stored
and calculated in whatever unit the modeller declared, and no conversion ever
occurs. The engine satisfies rule 1.9 (never mix scales) by making mixing
unrepresentable — there is exactly one unit for the whole model — but it does
not satisfy 4.6, because there is no normalized value and nothing to
reconstruct from.

This is a **statement of current behaviour, not a defect report**: for a
single-document model the two are indistinguishable in result. It becomes a
defect the moment 2.3.a permits multiple PDFs per company.

`status` is a lifecycle enumeration — see the end of this file.

**Engine counterpart: none.** No versioning, no locking, no valuation date,
no identifiers. A run of `run_model.py` produces text on stdout and keeps
nothing.

---

## 9.9 ModelPeriod

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.9; referenced by 9.10 and 9.12 |
| `model_version_id` | id → 9.8 | Y | — | 9.9 |
| `start_date` | date | Y | — | 15.1; 16.12 (exact time fraction) |
| `end_date` | date | Y | — | 16.12 |
| `label` | string | Y | — | 15.2; 8.x widget "period/scenario" requirement |
| `actual_or_estimate` | enum `A\|E` | Y | — | 15.2 ("Label all periods A for actual or E for estimate"); 7.8.d; STEP 12 |
| `cadence` | enum `annual\|quarterly\|monthly` | Y | `annual` | rule 1.7. 2.4.f: **annual**, so single-valued today |
| `sort_order` | integer | Y | — | Deterministic period ordering |

**Engine counterpart: `Periods`** in
[`model/profile.py`](../model/profile.py) — two tuples of year labels.

| Section 9.9 field | Engine | Note |
|---|---|---|
| `label` | the tuple element, e.g. `"2026E"` | Present. |
| `actual_or_estimate` | the `A`/`E` suffix, enforced by `YEAR_RE` | Present, and validated: historical years must end `A`, forecast years `E`. |
| `sort_order` | tuple position | Present, and validated: ascending, no duplicates, **consecutive**, and the forecast must begin the year after the last actual. |
| `cadence` | — | **Annual only, structurally.** `YEAR_RE = ^(\d{4})(A\|E)$` cannot express a quarter or a month. |
| `start_date`, `end_date` | — | **Absent.** This is the consequential one. |

### The engine has no dates, and that is why 16.12 cannot be met

Specification 16.12 requires "the exact time fraction from valuation date to
cash-flow date". The engine's discount period is
`Periods.discount_period(year)` = *the index of the year in the forecast tuple,
plus one* — an ordinal, not a duration. With no `valuation_date` (9.8) and no
period dates (here), there is nothing to take a fraction of.

That is the correct implementation of the 37-step workflow, which asks for
`PV = FCFF_t / (1 + WACC)^t` with integer `t` (STEP 29), and it is honest
about being that. It is **not** an implementation of 16.11–16.14, and it
cannot become one without dates. See
[`formula-catalog.md`](formula-catalog.md) `DCF-DF-01`.

---

## 9.10 Assumption

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.10 |
| `model_version_id` | id → 9.8 | Y | — | 9.10 |
| `scenario_id` | id → Scenario | Y | — | 14.6; **see the missing-entity note below** |
| `code` | string (stable) | Y | — | 14.4.a; join key for formula inputs (9.11 `input_codes`) |
| `period_id_optional` | id → 9.9 | N | — | 14.4.c. Null = applies to every period |
| `decimal_value` | decimal(string) | Y | per `unit` | 4.2–4.4 |
| `unit` | enum `ratio\|percent\|days\|currency\|shares\|multiple\|years` | Y | — | 14.4.b; **18.12 unit checking** |
| `source_type` | enum | Y | — | 14.3 — the six permitted values are fixed by the specification |
| `source_document_id_optional` | id → 9.3 | N | — | 14.4.f |
| `source_url_optional` | string | N | — | 14.4.f. 2.3.e: external retrieval is **not** permitted, so this records a URL a human consulted, never one the system fetched |
| `source_date` | date | Y | — | 14.4.g; check 17.23 for WACC components |
| `rationale` | text | Y | — | 14.4.h |
| `owner` | id → 9.1 | Y | — | 14.4.i |
| `status` | enum | Y | — | 14.2 — the five permitted values are fixed by the specification |
| `created_at` | timestamp | Y | UTC | 14.4.j |
| `updated_at` | timestamp | Y | UTC | 14.4.j; optimistic concurrency |

Two enumerations are **closed by the specification** and may be written down
without answering a decision:

- `status` (14.2): `Draft`, `Needs Source`, `Reviewed`, `Approved`, `Rejected`.
- `source_type` (14.3): `Company Guidance`, `Company Filing`,
  `External Market Data`, `Historical Driver`, `Analyst Assumption`,
  `Scenario Override`.

`unit` is **not** given by the specification as an enumeration, but 18.12
requires unit checking so that "percentages, currency, shares, and multiples
cannot be combined nonsensically". The seven values above are the minimum set
the engine's own drivers need (ratios, days, currency amounts, share counts);
they are a proposal, and the authoritative list belongs with the formula
catalogue, where 9.11 `output_unit` must agree with it.

**Engine counterpart: `Assumption`** in
[`model/assumptions.py`](../model/assumptions.py).

| Section 9.10 field | Engine | Note |
|---|---|---|
| `code` | `name` | Present. The engine's driver names are listed in [`formula-catalog.md`](formula-catalog.md). |
| `decimal_value` | `value` | Present, and an exact `Decimal`; a float is refused. |
| `period_id_optional` | `year` (`str \| None`) | Present in effect: `None` means all years, and `Assumptions.get` falls back from year-specific to all-years. |
| `source_type` | `basis` (`Basis` enum) | **Divergence.** The engine has **three** values (`company_guidance`, `external_research`, `model_assumption`), from STEP 10. Section 14.3 requires **six**. The engine's three do not partition the six: `external_research` covers both `Company Filing` and `External Market Data`, and there is no `Historical Driver` or `Scenario Override` at all. |
| `source_url_optional` / `source_document_id_optional` | `source` (free string) | **Divergence.** One unstructured string carries document, page and URL indiscriminately. It is *required* and must be non-empty — the engine refuses to construct an `Assumption` without it — but it is not parseable, so no check can verify it points anywhere. |
| `rationale` | `note` | **Divergence on obligation.** Optional in the engine (defaults to `""`), required by 14.4.h. |
| `unit` | — | **Absent.** The unit is encoded in the *driver name* by convention: `_pct_revenue` is a ratio, `dso`/`dpo`/`inventory_days` are days, `capex_amount` is a currency amount. Nothing enforces it, so 18.12 unit checking has no data to run on. |
| `status` | — | **Absent.** Nothing is Draft or Approved. Every declared assumption is live. Checks 17.18 and 17.19 have nothing to read. |
| `owner`, `source_date`, `created_at`, `updated_at` | — | **Absent.** |
| `scenario_id` | — | **Absent.** One scenario, unnamed. |

The engine adds one concept Section 9 has no entity for: `Conflict`
(STEP 11) — two dated sources that disagree, with a mandatory explicit choice
and rationale. It is enforced (`chosen` must equal one of the two recorded
sources) and it is reported. Section 9 has nowhere to put it; the nearest fit
is a pair of `Assumption` rows plus an `AuditEvent`, which loses the
structure. Logged as a new finding in
[`decision-ledger.md`](decision-ledger.md).

### Missing entity: Scenario

`Assumption.scenario_id` (9.10) and `CalculatedValue.scenario_id` (9.12) are
required, and `ValidationResult.scenario_id_optional` (9.13) references one —
but **Section 9 defines no Scenario entity.** Section 14.6–14.9 describes its
behaviour (Base/Upside/Downside plus custom, inherited lineage on copy, names
that must not imply probability unless probability is modelled and sourced),
so the requirements exist; the schema row does not.

This is a gap in the specification, not a decision, and it is recorded as a
finding in [`decision-ledger.md`](decision-ledger.md) rather than resolved
here.

---

## 9.11 FormulaDefinition

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.11 |
| `code` | string (stable) | Y | — | 18.1 versioned definitions; the codes in [`formula-catalog.md`](formula-catalog.md) |
| `version` | integer | Y | — | 18.1; 18.7 (hash inputs **and formula version**) |
| `expression` | string | Y | — | 18.2–18.3 (approved operators only; never evaluate arbitrary user code) |
| `description` | text | Y | — | 18.10 (human-readable formula for every calculated cell) |
| `input_codes` | array of string | Y | — | 18.4 dependency graph; 18.11 (exact input values used) |
| `output_unit` | enum (as 9.10 `unit`) | Y | — | 18.12 unit checking |
| `rounding_policy` | enum | Y | — | 4.8–4.9. Default `ROUND_HALF_EVEN`; 4.8 requires any deviation be recorded |
| `effective_date` | date | Y | — | 18.1; reproducibility of a released version |

`expression` is stored as text and parsed into the dependency graph (18.4);
it is **not** executable user code (18.3). The permitted operator and function
set is part of the formula engine's contract (Phase 8 item 78) and is not
settled by this document.

`rounding_policy` is per formula because 4.8 allows a company's reporting
policy to require something other than half-even. The engine's global default
is declared once in [`model/numeric.py`](../model/numeric.py) as
`ROUND_HALF_EVEN` at 50 significant digits.

**Engine counterpart: none as data.** Formulas in the engine are Python
expressions in [`model/forecast.py`](../model/forecast.py) and
[`model/dcf.py`](../model/dcf.py). Two things come close and neither is a
`FormulaDefinition`:

- `Cell.basis` ([`model/statements.py`](../model/statements.py)) — a
  human-readable string attached to each derived or forecast cell, e.g.
  `"ebit = revenue - cogs - operating_expenses (STEP 15)"`. This serves 18.10
  (human-readable formula) but not 18.4, 18.7, 18.11 or 18.12: it is prose, not
  a parseable expression, and it carries no version.
- `RollForward.formula` ([`model/schedules.py`](../model/schedules.py)) — a
  fixed description string per schedule, e.g. `"Ending Debt = Beginning Debt +
  New Borrowing - Debt Repayment"`.

There is no `code`, no `version`, no `effective_date`, no `input_codes`, and
no per-formula `rounding_policy`. [`formula-catalog.md`](formula-catalog.md)
assigns the codes; nothing in `model/` reads them yet.

---

## 9.12 CalculatedValue

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.12 |
| `model_version_id` | id → 9.8 | Y | — | 9.12 |
| `scenario_id` | id → Scenario | Y | — | see the missing-entity note under 9.10 |
| `period_id` | id → 9.9 | Y | — | 9.12 |
| `line_item_code` | string → 9.6 `canonical_code` | Y | — | 9.12 |
| `decimal_value` | decimal(string) | Y | model base unit | 4.3, 4.9 (unrounded) |
| `formula_definition_id` | id → 9.11 | Y | — | 18.10; 24.12 lineage |
| `input_fingerprint` | string (hash) | Y | — | 18.7 (hash inputs and formula version for reproducibility); 18.8 incremental recalculation |
| `calculated_at` | timestamp | Y | UTC | Audit; 21.7 |

`decimal_value` is stored **unrounded** (4.9). Display rounding happens at
presentation only, and check 17.29 requires the displayed value tie back to
this one.

**Engine counterpart: `Cell`** in
[`model/statements.py`](../model/statements.py) —
`value`, `origin`, `source`, `basis`.

| Section 9.12 field | Engine | Note |
|---|---|---|
| `decimal_value` | `value` | Present, exact, unrounded. |
| `line_item_code` + `period_id` | the `(account, year)` dict key | Present in effect. |
| `formula_definition_id` | `basis` (prose) | **Divergence.** A sentence, not a reference. |
| `input_fingerprint` | — | **Absent.** No hashing, no incremental recalculation; the whole model is rebuilt on every run. |
| `calculated_at`, `model_version_id`, `scenario_id` | — | **Absent.** |

The engine adds a field Section 9.12 does not have, and it earns its place:
**`origin`** — `reported`, `derived`, or `forecast`. Section 9 draws this line
between *tables* (a `ReportedFact` is not a `CalculatedValue`), whereas the
engine draws it *within* a cell, which is what lets check 10 ("no unintended
forecast hardcodes", specification 17.20) work: a forecast-year cell whose
origin is `reported` is a hardcode, detectable in one pass. A schema that
separates the tables gets the same result from a different query, but the
distinction must survive into whatever replaces this.

---

## 9.13 ValidationResult

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.13 |
| `model_version_id` | id → 9.8 | Y | — | 9.13 |
| `scenario_id_optional` | id → Scenario | N | — | 15.20 (run checks for every scenario); null for model-wide checks |
| `check_code` | string (stable) | Y | — | The codes in [`validation-policy.md`](validation-policy.md) |
| `severity` | enum `CRITICAL\|ERROR\|WARNING\|INFO` | Y | — | Section 17 severity system |
| `status` | enum `PASS\|FAIL\|SKIP` | Y | — | rule 1.14; see the SKIP note |
| `expected_value_optional` | decimal(string) | N | model base unit | 4.10 |
| `actual_value_optional` | decimal(string) | N | model base unit | 4.10 |
| `difference_optional` | decimal(string) | N | model base unit | 12.4 ("a visible amount and source trail") |
| `tolerance_optional` | decimal(string) | N | ratio | 4.11, 4.13 |
| `message` | text | Y | — | 7.10.b |
| `created_at` | timestamp | Y | UTC | Audit |

**On `status`:** Section 17 does not enumerate statuses. `PASS`/`FAIL` are
implied throughout, and rule 1.14 forbids an unresolved critical error
appearing as PASS. **`SKIP` is the engine's contribution and it should be
kept**: a check whose inputs were absent has verified nothing, and collapsing
it into PASS is precisely the failure rule 1.14 is about. See
[`validation-policy.md`](validation-policy.md).

**Engine counterpart: `CheckResult`** in
[`model/checks.py`](../model/checks.py) — `name`, `status`, `detail`.

| Section 9.13 field | Engine | Note |
|---|---|---|
| `status` | `Status` enum | Present: `PASS`, `FAIL`, `SKIP`. |
| `message` | `detail` | Present. |
| `check_code` | — | **Absent.** Checks are identified by display name only (`"PP&E schedule linkage"`). [`validation-policy.md`](validation-policy.md) assigns codes; nothing reads them yet. |
| `severity` | — | **Absent.** All thirteen checks are equal; there is no CRITICAL/ERROR/WARNING/INFO distinction anywhere in `model/`. |
| `expected_value_optional`, `actual_value_optional`, `difference_optional` | folded into `detail` text | **Divergence.** The numbers exist — `"2027E: out by 0.0004"` — but as formatted prose, not as queryable decimals. A diagnostics page (7.10) cannot sort or threshold on them. |
| `tolerance_optional` | `Tolerance`, model-wide | **Partial.** One tolerance for the whole run, printed once in the panel header, not recorded per result. |
| `created_at`, `model_version_id`, `scenario_id_optional` | — | **Absent.** |

---

## 9.14 AuditEvent

| Field | Type | Req | Unit / scale | Serves |
|---|---|---|---|---|
| `id` | id | Y | — | 9.14 |
| `actor_id` | id → 9.1 | Y | the owner | 10.33; constant in single-user mode (2.2.b), but still required as a column so the trail survives a later multi-user change |
| `model_version_id` | id → 9.8 | N | — | Null for events before a model exists (e.g. document upload) |
| `entity_type` | string | Y | — | 9.14 |
| `entity_id` | id | Y | — | 9.14 |
| `action` | enum | Y | — | 10.33 requires acceptance, correction, split, combination and rejection to be recorded; the full set is wider |
| `old_value_json` | JSON | N | — | rule 1.13 (never alter a verified historical value without an audit entry) |
| `new_value_json` | JSON | N | — | rule 1.13 |
| `reason` | text | Y | — | 10.32 (correction only with a reviewer note); 7.4.e; 19.5/19.13 |
| `timestamp` | timestamp | Y | UTC | 9.14 |

`old_value_json` and `new_value_json` must be redacted per 20.15/20.16 before
they reach a log stream — the audit table itself holds the values, the
application log does not.

**Engine counterpart: none.** There is no audit log, and nothing in the engine
is mutable after construction in a way that would need one: inputs are files,
a run is a pure function of those files, and `Figure`, `Source`, `Cell`,
`Assumption` and `CostOfCapital` are all frozen dataclasses. Git history over
`inputs/` is the only change record that exists today.

---

## Lifecycle states

Phase 2 item 24 requires model lifecycle states and their legal transitions be
defined before features are built. The specification supplies the state
*names* in 7.1.b:

> Draft, Extracting, Needs Review, Validated, Forecast Ready, Valuation Ready,
> Archived

and one hard transition rule in 15.21 ("Do not label the model Forecast Ready
until every critical check passes"), plus 19.18 (release locks a version) and
13x/137 (prevent release when CRITICAL or ERROR checks remain).

**The model-version transition table is still OPEN.** The specification gives
the states and three constraints but not the graph — whether Validated can
return to Needs Review after a fact correction (10.35 implies yes), whether
Archived is terminal, and whether a locked version can be superseded rather
than unlocked. 10.35 ("re-run all dependent mappings and calculations after an
approved change") and 11.12 ("invalidate dependent model results") both imply
backward transitions exist, but neither names them. This is **not** a Section 2
decision, so it is not in the ledger's Section 2 tables; it is recorded as
finding F-4's neighbour in the ledger.

### The extraction lifecycle is now CLOSED (Phase 3, finding F-12)

`SourceDocument.extraction_status`, `SourceDocument.verification_status` and
`ReportedFact.verification_status` were in the same position — required fields
whose value sets the specification describes behaviourally but never
enumerates. Phase 3 item 29 could not be built on an open enumeration, so
[`apps/api/app/extraction/jobs.py`](../apps/api/app/extraction/jobs.py) defines
them:

| Field | Enumeration | Serves |
|---|---|---|
| `SourceDocument.extraction_status` | `JobState`: received → validating → stored → classifying → extracting → extracted, plus terminal `refused` and `failed` | 10.6–10.8; Phase 3 item 29 |
| `SourceDocument.verification_status` | `DocumentVerificationState`: `unconfirmed` → `in_review` → `confirmed` | 10.11–10.13; check `VAL-017-002` |
| `ReportedFact.verification_status` | `FactVerificationState`: `unverified`, `needs_review`, `accepted`, `corrected`, `rejected`, `verified` | 10.29–10.33; check `VAL-017-005` |

`LEGAL_TRANSITIONS` is the graph, asserted complete at import. Three properties
are enforced rather than described: every non-terminal state may refuse or
fail, every terminal state is terminal, and a transition without a stated
reason raises (10.33). There are **no backward edges** — a re-extraction is a
new job over the same stored document, because 10.33 requires the old job's
history not be mutated.

`refused` and `failed` are distinguished deliberately. A refusal is a *policy*
stop: a rule said no, and the system is working. A failure is an *unexpected*
stop. The first is answered by a reviewer, the second by an engineer, and
collapsing them into one state loses that.

---

## Summary: Section 9 against the engine

| Entity | Engine equivalent | Coverage |
|---|---|---|
| 9.1 User | — | None |
| 9.2 Company | `profile.CompanyProfile` | Partial — no id/ticker/industry/timestamps; scale and audited status sit here instead of on the document |
| 9.3 SourceDocument | a free-text string in `model/`; **full record in `apps/api` (Phase 3)** | Complete for ingestion |
| 9.4 SourceLocation | `provenance.Source` in `model/`; **full record in `apps/api` (Phase 3)** | Complete for ingestion, including geometry and raw text |
| 9.5 ReportedFact | `provenance.Figure` in `model/`; **full record in `apps/api` (Phase 3)** | Complete for ingestion; three recorded divergences, above |
| 9.6 NormalizedLineItem | `model/accounts.py` | **Strongest overlap** — codes, statement type and component structure present; no display name, definition, or per-item sign/cash tags |
| 9.7 FactMapping | — | None; the input file fuses fact and mapping |
| 9.8 ModelVersion | — | None; no versioning, no valuation date, no base-unit normalization |
| 9.9 ModelPeriod | `profile.Periods` | Partial — labels, A/E and ordering; **no dates**, annual only |
| 9.10 Assumption | `assumptions.Assumption` | Partial — code, value, period, basis and a required source string; no unit, status, owner, source date or scenario |
| 9.11 FormulaDefinition | — | None as data; prose `basis` strings only |
| 9.12 CalculatedValue | `statements.Cell` | Partial — value plus an `origin` field Section 9 lacks; no fingerprint, formula reference or timestamp |
| 9.13 ValidationResult | `checks.CheckResult` | Partial — status and message; no code, severity, or structured expected/actual/difference |
| 9.14 AuditEvent | **`records.AuditEvent` (Phase 3)** | Present for ingestion; an entry without a reason raises (10.33). Not yet wired to reviewer actions, which are Phase 4 |

---

## Related documents

- [`website-build-spec.md`](website-build-spec.md) — Section 9, authoritative
- [`formula-catalog.md`](formula-catalog.md) — 9.11 as a catalogue
- [`source-policy.md`](source-policy.md) — 9.3–9.7 ingestion and verification rules
- [`validation-policy.md`](validation-policy.md) — 9.13 check codes and severities
- [`decision-ledger.md`](decision-ledger.md) — the OPEN decisions cited above
- [`WORKFLOW.md`](WORKFLOW.md) — the 37 steps mapped to the code
