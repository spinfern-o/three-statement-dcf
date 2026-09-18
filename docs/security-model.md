# Security model

Specification [Section 20](website-build-spec.md) sets out twenty security and
privacy requirements. This file restates them as a model, and marks each one
with **what is decidable now** versus **what is blocked** on decision 2.2.a
(local-only application / private hosted application / public website) and
2.2.b–d (single- or multi-user, authentication, roles).

> **2.2.a ANSWERED (2026-09-16): private hosted application.** Decided by the
> repository owner and recorded in [`decision-ledger.md`](decision-ledger.md).
> This document was written before the answer arrived, so it states all three
> branches throughout. **The *Private hosted* column of §1 is now the governing
> one**; the local-only and public columns are retained for contrast, not as
> live options. Requirements below marked "blocked on 2.2.a" are unblocked —
> those marked blocked on **2.2.b–d** are not, and those remain open.
>
> **2.2.b–d are also now answered** (2026-09-16): single user, authentication
> required, one role. So 20.6's RBAC is **N/A** rather than deferred, and the
> reviewer/approver in 14.x is the same person as the author. Rows below that
> read "blocked on 2.2.b–d" are resolved by that answer.
>
> The three immediate consequences of 2.2.a, from the specification's own wording:
> **3.2.d resolves to PostgreSQL** (SQLite is permitted "only for a documented
> single-user local prototype"); **20.2 binds** (written "for hosted
> deployments"); and **Phase 17 deployment is unblocked**.

**No hosting model is assumed anywhere in the body of this document**, which
was written before 2.2.a was answered. Section 2 forbids replacing OPEN with an
inferred answer, so where a requirement's *content* depends on 2.2.b–d, both
the invariant part and the branch are still stated and the branch is not
chosen.

**Scope note.** There is no application to secure yet: no server, no database,
no upload path, no authentication, no network listener. The repository today is
a Python library, a CLI, four blank YAML templates and a test suite. Everything
below describes a system to be built; the few requirements that already bind
this repository are marked **binds today**.

---

## 1. What 2.2.a changes

The three options are not three deployment targets for one design. They are
three different threat models, and several requirements below change meaning
rather than degree.

Private hosted is the confirmed answer; that column governs.

| | Local-only | **Private hosted (CONFIRMED)** | Public website |
|---|---|---|---|
| **Adversary** | Anyone with the machine | Anyone on the network, plus other tenants | Anyone on the internet |
| **20.2** encryption at rest / in transit | Filesystem + OS disk encryption; no transit | **Required** (TLS, encrypted storage) | **Required**, plus HSTS and certificate management |
| **20.3** secret manager | `.env` on the machine may be adequate | A real secret manager | A real secret manager, plus rotation |
| **20.6** RBAC | N/A | **N/A — 2.2.b is single user** | Required |
| **20.7** cross-model authorization | N/A if one user owns everything | **Required** | **Required**, and the most likely place to get it wrong |
| **20.14** rate limiting | Little purpose | Required | Required, and must survive abuse |
| **3.2.d** database | SQLite acceptable (documented single-user prototype) | **PostgreSQL** | **PostgreSQL** |
| **Phase 17** deployment | May not exist | Staging then production | Staging then production |

Two things are **invariant across all three**, and are therefore decidable now:

1. **Uploaded financial PDFs are confidential** (20.1). This is a property of
   the data, not of the deployment.
2. **Nothing secret, and no real financial data, enters Git** (20.4). This
   binds the repository as it stands.

---

## 2. Requirement by requirement

### 20.1 — Treat uploaded financial PDFs as confidential

**Decidable now.** A company's unreleased financial statements are
confidential regardless of where the software runs, and the classification
drives 20.2, 20.15, 20.16 and 20.17.

Concretely, and independent of 2.2.a:

- A source PDF's bytes are never written to a log, an error message, an
  exception trace, or an analytics payload.
- Extracted values are not logged (20.15).
- A PDF is never sent to a third-party service — including an LLM — without an
  explicit, recorded decision. 3.3.e already forbids using an LLM result as an
  authoritative number without deterministic validation and human approval;
  the *transmission* is a separate question and is **OPEN**, with **OPEN
  (2.3.e)** (external data retrieval) the nearest existing decision.

**Binds today:** `inputs/` ships blank and
`tests/test_end_to_end.py::test_shipped_templates_contain_no_company_data`
asserts it stays that way. `tests/fixtures/` holds a fictional manufacturer
labelled `FICTIONAL` in every file.

### 20.2 — Encrypt data in transit and at rest for hosted deployments

**Blocked on 2.2.a**, by the specification's own wording — "for hosted
deployments". Under local-only there is no transit and at-rest encryption
becomes an OS-level concern rather than an application one.

Decidable now regardless: the application must not implement its own
cryptography, and any encryption is provided by TLS and by the storage layer.

### 20.3 — Store secrets only in the approved secret manager/environment

**Partly decidable.** The *rule* is fixed: no secret in source, no secret in a
config file that is committed, no secret in a container image.

**Blocked on 2.2.a** for the mechanism — "the approved secret manager" does not
exist and what is appropriate differs across the three options.

**Binds today:** Phase 1 item 12 requires `.env.example` to carry
**names only, never real secrets**. That file does not exist yet.

### 20.4 — Never commit secrets, source PDFs, or production financial data to Git

**Decidable now, and it binds this repository immediately.**

Current state:

| Requirement | Status |
|---|---|
| No secrets in Git | No secrets exist yet; the engine reads no environment variable and makes no outbound request |
| No source PDFs in Git | No PDF is tracked (`git ls-files` confirms none) |
| No production financial data | **Enforced by test.** `test_shipped_templates_contain_no_company_data` keeps `inputs/` blank |

The test is the useful part: a number committed into `inputs/` would look like
real data to whoever opened the file next, and the guard is executable rather
than a convention.

### 20.5 — Least-privilege database and storage credentials

**Blocked on 2.2.a and 3.2.d.** There is no database. Under local-only SQLite
there are no credentials to scope.

Decidable now: the application's runtime credential must not be the schema
owner, and migrations run under a separate credential.

### 20.6 — Apply role-based access control if multi-user

**Blocked on 2.2.b and 2.2.d**, explicitly and by the specification's own
conditional. 2.2.d lists owner, analyst, reviewer and read-only as *candidate*
roles; writing them into a schema or a policy would answer the decision.

What the answer changes: if single-user, this requirement is N/A and
`User.role` in [`data-dictionary.md`](data-dictionary.md) §9.1 collapses.
If multi-user, RBAC is required and it interacts with the approval workflow —
[`source-policy.md`](source-policy.md) §10 notes that "reviewer note"
presupposes a reviewer who may be a different person from the preparer, which
only 2.2.b and 2.2.d can establish.

### 20.7 — Prevent cross-company/model access by server-side authorization checks

**Blocked on 2.2.a and 2.2.b** for whether it applies. If it applies, the
*design* is decidable now and should be fixed before any endpoint exists:

- Authorization is checked **server-side on every request**, including reads.
- The check is on the **resource's owner**, resolved from the resource, never
  from a parameter the client supplied.
- An unauthorized resource returns the same response as a nonexistent one, so
  identifiers do not leak existence.
- 20.12's "insecure direct object references" is the same requirement stated as
  a vulnerability class.

Acceptance criterion 24.18 ("unauthorized users cannot access another model")
is the test.

### 20.8 — Validate file size, type, signature, and page-count limits

**Decidable now**, except the limit values.

The *shape* is fixed by 10.1 (MIME **signature**, not filename) and by the
`SourceDocument` fields in [`data-dictionary.md`](data-dictionary.md) §9.3:
`byte_size`, `page_count`, `mime_type`. Validation happens before any parser
touches the file.

The *numbers* are **OPEN** — a limit depends on what documents are in scope
(2.3.a one filing per model version, 2.3.b annual only, 2.3.c text-native only; a scanned annual report is far larger than a
text-native one) and on the deployment's resources (2.2.a: private hosted). Choosing a
number now would be a guess presented as a policy.

### 20.9 — Scan uploads before processing

**Blocked on 2.2.a.** 10.4 refers to "the approved security process" and no
such process exists. What scanning is proportionate differs sharply: a
local-only tool processing the owner's own filings is a different risk from a
public endpoint accepting arbitrary PDFs.

Decidable now: scanning happens **before** extraction, not in parallel with it,
and a file that fails is quarantined rather than deleted, so the rejection is
auditable.

### 20.10 — Isolate PDF/OCR processing from the web process

**Decidable now as a principle**, blocked on 2.2.a for the mechanism.

PDF parsers and OCR engines are large C libraries processing untrusted input.
They run in a separate process with no network access, a read-only filesystem
except for a scratch directory, and no database credentials. Whether that
separation is a container, a subprocess, or a queue worker (3.2.f) depends on
the deployment.

**Blocked on 2.3.c** for whether OCR exists at all.

### 20.11 — Sanitize filenames and never execute document content

**Decidable now.** Both halves are invariant:

- The original filename is stored **as data** (`SourceDocument.original_filename`)
  and is never used to construct a path. Storage paths derive from the
  server-generated `id` or the content hash.
- Document content is parsed, never executed. No embedded JavaScript, no
  embedded file attachments, no external resource fetches from within a PDF.

### 20.12 — Protect against path traversal, SSRF, injection, XSS, CSRF, IDOR, and formula injection

**Decidable now as a list of invariants.** These are properties of correct code
rather than of a deployment:

| Class | Where it bites here |
|---|---|
| Path traversal | Filenames from PDFs and uploads (20.11) |
| SSRF | 2.3.d and 2.3.e both say **no outbound requests**, so the attack surface does not exist by decision. `Assumption.source_url_optional` records a URL a human consulted; nothing fetches it. Revisit the moment anything does |
| Injection | Every parameterized query; never string-built SQL |
| XSS | Company names, raw line-item labels and reviewer notes are all attacker-influenced text rendered in the UI |
| CSRF | Every mutation, if cookie-based sessions are used. 2.2.c: authentication **is** required, so this applies once the session mechanism is chosen |
| IDOR | Same requirement as 20.7 |
| Formula injection | 20.13, below |

Worth naming explicitly: **`raw_label` and `raw_text` come from an uploaded
PDF**, and they are rendered beside the extracted value in the mapping review
(7.4.a) and the source room (7.3.d). They are untrusted input that looks like
document content.

### 20.13 — Prefix spreadsheet values beginning with `=`, `+`, `-`, or `@`

**Decidable now**, and it is the most concrete requirement in Section 20.

Any raw text exported to CSV or XLSX — company line-item labels, reviewer
notes, source strings, company names — that begins with `=`, `+`, `-` or `@`
is prefixed so a spreadsheet application does not evaluate it as a formula.

Two cautions specific to this application:

1. **Numbers must not be caught by the `-` rule.** A negative value is a
   number, not text. The prefix applies to *raw text fields*, which is what
   20.13 says; applying it to a numeric cell would corrupt the export and
   violate 21.8 (exports must equal website values).
2. 21.2 requires hardcodes and formulas be visually distinguishable in XLSX.
   That is a *styling* requirement and is unrelated to this escaping; do not
   conflate them.

### 20.14 — Rate-limit upload, extraction, authentication, and export endpoints

**Blocked on 2.2.a and 2.2.c.** Under local-only there are no endpoints to
limit and no authentication to protect. Under public hosting this is load-
bearing; under private hosting it is defence in depth.

Decidable now: extraction and export are the expensive operations, and they are
limited by *concurrent jobs per owner*, not only by requests per minute — a
single expensive job is the resource risk, not request volume.

### 20.15 — Log security events without logging source values unnecessarily

**Decidable now.** This is 20.1's classification applied to logging, and it
holds under every hosting model.

Logged: authentication attempts, authorization denials, uploads (hash, size,
page count — **not** content), extraction job lifecycle, mutations with their
actor and reason, permanent deletions, rate-limit rejections.

Not logged: `ReportedFact.raw_value`, `parsed_decimal`, `raw_text`,
calculated values, assumption values, any PDF bytes.

The tension worth naming: 9.14 `AuditEvent` **does** store `old_value_json`
and `new_value_json`, because rule 1.13 requires it. The audit table holds
those values under access control; the application log does not. They are two
different sinks with two different policies.

### 20.16 — Redact secrets and private data from application errors

**Decidable now.** An error message shown to a user, returned in an API
response, or captured by an error reporter carries no financial values, no
credentials and no file contents.

**This one has a live tension with how the engine is built, and it is worth
recording before the website inherits it.** The engine's error messages are
deliberately, unusually informative — that is the design. Examples from
[`model/`](../model):

- `numeric.D()` refusing a float prints the float's exact decimal expansion
  to demonstrate why it was refused.
- `Ledger.require()` names the account, the year and the step that needed it.
- `_balance_check` reports the delta per year.
- `RollForward.add_year` prints both the expected and supplied balances.

For a local CLI run by the person who owns the data, this is correct and it is
most of what makes the tool usable. For a hosted deployment, several of these
messages contain financial values, and 20.16 says they must not leave the
server in that form.

The resolution is **not** to make the engine quieter. It is that the API
boundary carries a structured error code plus a redacted message, while the
full diagnostic goes to the server-side audit/diagnostic record that the
authorized owner can read. That is compatible with 7.10 (diagnostics),
18.13 (visible diagnostic for division by zero) and 12.4 ("a visible amount and
source trail"). **Blocked on 2.2.a** for whether the boundary exists at all.

Phase 2 item 23 ("define error codes and severity") is where the structured
codes belong; that work is **not blocked** and has not been done. The engine
today raises `ProvenanceError` / `InputError` / `PrecisionError` with prose and
no codes.

### 20.17 — Define backup, restore, retention, and permanent-deletion behaviour

**Blocked on 2.6.b, 2.6.c and 2.6.d**, each of which is OPEN:

- 2.6.b — retention period for uploaded PDFs and extracted data
- 2.6.c — whether an administrator may permanently delete data
- 2.6.d — backup and restore policy

And on **2.2.a** for what backup even means.

Decidable now: whatever the retention answer, **rule 1.12 (never overwrite an
uploaded source document) survives it**. Deletion removes; it does not
overwrite in place.

One interaction to flag for whoever answers 2.6.b/c: permanent deletion of a
`SourceDocument` must not silently invalidate the `AuditEvent` rows that
reference it, or the audit trail stops being one. Whether deletion is
tombstoned, cascaded, or refused while references exist is part of answering
2.6.c.

### 20.18 — Require action confirmation for permanent deletion

**Decidable now as a principle**, blocked on **2.6.c** for whether permanent
deletion exists at all.

If it exists: confirmation names the specific object, is not a default-focused
button, and produces an `AuditEvent` with a reason. 6.5.b requires pending,
success and failure feedback for every mutation.

### 20.19 — Provide a non-advisory disclaimer and model limitations in the UI/exports

**Decidable now, and partly satisfied already.**

Section 25 supplies the required language and says it must appear in the model,
the release flow, and exports — "Do not bury this only in Terms."

**Binds today:** [`README.md`](../README.md) carries the Section 25 disclaimer
verbatim as its final section. The CLI report does **not** print it, and
nothing in [`model/report.py`](../model/report.py) emits it. Adding it to the
report output is not blocked by any decision; it is simply not done.

Rules 1.19 and 1.20 are the same requirement in negative form: never describe a
scenario forecast as a fact or a guarantee, and never claim the site is
investment advice. Acceptance criterion 24.14 adds: the site never claims
forecast accuracy of 0.0001% — 4.1 is explicit that the tolerance covers
deterministic arithmetic only, and FORECAST ACCURACY is excluded from it.

### 20.20 — Complete dependency and vulnerability scans before production release

**Blocked on 2.2.a** for "production release" to mean anything.

**Partly binds today.** `requirements.txt` lists two entries — `PyYAML>=6.0`,
the only runtime dependency, and `pytest>=7.0` for the suite — and CI runs the
tests on Python 3.10–3.13. There is **no dependency audit step** in
`.github/workflows/tests.yml`, which 3.5.c requires of CI. Adding one is not
blocked by any decision.

---

## 3. Summary: where each requirement stands

Rewritten after **Phase 15 (items 145-153)**, which built Section 20 rather than
deciding it. 2.2.a, 2.2.b, 2.2.c, 2.2.d, 2.6.b, 2.6.c and 2.6.d are all answered,
so nothing in this section is blocked on a decision any more.

### Built

| # | Requirement | Where |
|---|---|---|
| 20.1 | PDFs are confidential | Enforced by what the log is allowed to carry (20.15) and by `repository_scan.py` |
| 20.3 | Secrets in the environment only | [`credentials.py`](../apps/api/app/security/credentials.py); `.env.example` carries names |
| 20.4 | Nothing secret or real in Git | [`repository_scan.py`](../apps/api/app/security/repository_scan.py), run in CI on every commit |
| 20.6 | RBAC | **N/A** under 2.2.b/2.2.d — one user, one role. Not deferred |
| 20.7 | Cross-model authorization | [`authorization.py`](../apps/api/app/security/authorization.py), at `routes.py:_load` |
| 20.8 | Size, type, signature, page-count limits | `core/config.py` and the Phase 3 pipeline |
| 20.9 | Scan uploads before processing | [`scanning.py`](../apps/api/app/security/scanning.py) — a hook, reporting **not scanned** when unset |
| 20.10 | Isolate PDF processing | [`sandbox.py`](../apps/api/app/security/sandbox.py) — containment, **not** a code-execution boundary |
| 20.11 | Sanitize filenames; never execute content | Storage paths derive from the hash; nothing is executed |
| 20.12 | Path traversal, XSS, CSRF, IDOR, formula injection | [`csrf.py`](../apps/api/app/security/csrf.py), `guard.py`, `backup.py:restore`, `csv_export.py` |
| 20.13 | Spreadsheet formula prefixing | `csv_export.py` and `xlsx_export.py`, on **raw text** only |
| 20.14 | Rate limits | [`ratelimit.py`](../apps/api/app/security/ratelimit.py), by window and by concurrency |
| 20.15 | Log events, not source values | [`logging.py`](../apps/api/app/security/logging.py) |
| 20.16 | Redact errors | Same module; redaction runs on the way out, not at the call site |
| 20.17 | Backup, restore, retention, deletion | [`backup.py`](../apps/api/app/security/backup.py), [`retention.py`](../apps/api/app/security/retention.py) |
| 20.18 | Deletion confirmation | The filename typed back, not a button |
| 20.19 | Disclaimer and limitations | [`model/disclaimer.py`](../model/disclaimer.py) — the model, the release flow **and** the exports |
| 20.20 | Dependency and vulnerability scans | `pip-audit --strict` in CI on every commit |
| 2.2.c | Authentication | [`credentials.py`](../apps/api/app/security/credentials.py), `sessions.py`, `guard.py` — closes **F-15** |

### The deployment's, not the application's

Two requirements are satisfied by where this runs rather than by this code, and
saying so is not a way of skipping them.

| # | Requirement | Why it is not here |
|---|---|---|
| 20.2 | Encryption in transit and at rest | TLS and the storage layer. This application must not implement its own cryptography, and does not |
| 20.5 | Least-privilege credentials | There is no database yet; records are JSON files under the storage root, and the process's own filesystem permissions are the control |

### Residual risks, named

Listed here and in [`incident-response.md`](incident-response.md) §2, because a
control whose limits are unstated gets treated as a guarantee it never made.

- The isolated parser contains a crash, a runaway allocation and an endless
  loop. It does **not** contain code execution: the child runs as the same user
  with the same filesystem and network. A container, a seccomp filter or a
  separate user would make it a boundary.
- With `INGEST_SCAN_COMMAND` unset, nothing scans an upload. The result is
  recorded as `NOT SCANNED` and is never reported as clean.
- The rate limiters are per process. `Limiters.is_shared` returns `False`; a
  deployment with N workers has N independent limiters.
- A backup archive is not encrypted by the process that writes it, and its
  manifest says so.
- A session cannot be revoked individually. Rotating `REVIEW_SECRET_KEY`
  invalidates all of them at once, which is the revocation mechanism.

### Still not done

1. **Structured error codes and severity** (Phase 2 item 23). The engine raises
   prose exceptions with no codes. Not blocked on anything.
2. **Legal review of the Section 25 language** before commercial use, which 25
   itself asks for. The text is verbatim from the specification; nobody has
   reviewed it for this deployment.

---

## 4. What the repository is doing right today

Recorded because a security document that only lists gaps is misleading about
where the risk is.

- **No network, no secrets, no credentials.** The engine makes no outbound
  request and reads no environment variable. There is no attack surface
  because there is no surface.
- **`inputs/` is blank and a test keeps it blank.** The most likely way real
  financial data would reach this repository is someone filling in a tracked
  template and committing it. `.gitignore` covers only `inputs/*.local.yaml`,
  so the tracked templates themselves are guarded by the test rather than by
  the ignore file — which is the stronger of the two, since a test fails
  loudly where an ignore rule silently does not apply.
- **Fixtures are fictional and labelled.** `tests/fixtures/` is an internally
  consistent invented manufacturer, marked `FICTIONAL` in every file.
- **Inputs are data, never code.** `model/yaml_exact.py` subclasses
  `yaml.SafeLoader`, so no YAML tag can construct an arbitrary Python object.
  This is the one place where a malicious input file could have executed
  something, and it does not.
- **Every value is a `Decimal` or a refusal.** Not a security property as such,
  but it eliminates a class of silent corruption that would be invisible in an
  export.

The repository is **private**, and the [`decision-ledger.md`](decision-ledger.md)
finding F-3 stands: `main` has no branch protection, so CI cannot block a
merge. That is a repository-settings action, not a code change.

---

## Related documents

- [`website-build-spec.md`](website-build-spec.md) — Section 20, authoritative
- [`decision-ledger.md`](decision-ledger.md) — 2.2.a–d and 2.6.a–d, all OPEN
- [`source-policy.md`](source-policy.md) — 20.8–20.11 as part of the ingestion path
- [`data-dictionary.md`](data-dictionary.md) — `User`, `AuditEvent`, and the fields these rules protect
- [`validation-policy.md`](validation-policy.md) — release gating, which 20.17's retention answers interact with
