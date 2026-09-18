# Incident response and recovery

Required by [`website-build-spec.md`](website-build-spec.md) Phase 15 item 153
("Document incident and recovery procedures"), and by 20.17's requirement that
backup, restore, retention and permanent-deletion behaviour be defined.

**Who this is for.** One person: the owner (2.2.b), who is also the reviewer,
the approver and the administrator (2.2.d). Everything below is written for
somebody acting alone, at an hour they did not choose, on a system they have
not touched for months. That is why each step says what to run rather than what
to consider.

Last reviewed: 2026-09-18.

---

## 1. What this system holds, and why that sets the bar

One or more **company filings that have not been released**, and a valuation
built from them. 20.1 classifies those confidential. The realistic harms, in
the order they matter:

| Harm | What it looks like |
|---|---|
| **Disclosure** | A filing or a valuation reaches somebody outside the owner |
| **Silent corruption** | A stored figure changes and a valuation is built on it |
| **Loss** | The store is destroyed and the review work with it |
| **Unavailability** | The application is down |

Unavailability is last deliberately. A single-user private review tool being
offline for a day costs a day. The other three are the ones this document is
organised around.

---

## 2. Residual risks, stated before an incident rather than after

These are the things this system does **not** defend against, named so that an
incident is diagnosed against what is true rather than against an assumption.

- **The isolated parser is not a security boundary.**
  [`sandbox.py`](../apps/api/app/security/sandbox.py) runs PDF parsing in a
  child process under memory, CPU and wall-clock limits. That contains a crash,
  a runaway allocation and an endless loop. It does **not** contain code
  execution: the child runs as the same user with the same filesystem and the
  same network. Making it a security boundary needs a container, a seccomp
  filter or a separate user, all of which are deployment mechanisms.
- **Uploads are not scanned unless a scanner is configured.**
  `INGEST_SCAN_COMMAND` is a hook and there is no scanner in this repository.
  With it unset, every document records `NOT SCANNED` — which is reported as
  such and never as clean.
- **The rate limits are per process.** `Limiters.is_shared` returns `False`.
  A deployment running N workers has N independent limiters and every limit is
  N times weaker.
- **There is no encryption at rest in the application.** 20.2 binds for hosted
  deployments and is satisfied by the storage layer, not by this code. A backup
  archive written by [`backup.py`](../apps/api/app/security/backup.py) is **not
  encrypted by the process that writes it**, and its manifest says so.
- **A session cannot be revoked before it expires.** Sessions are signed
  cookies with an eight-hour absolute lifetime and no server-side store.
  Rotating `REVIEW_SECRET_KEY` invalidates all of them at once, which is the
  revocation mechanism — see §4.

---

## 3. Detection: what to look at first

Everything the application knows about its own operation is in the security
log, one JSON object per line, written by
[`logging.py`](../apps/api/app/security/logging.py).

```
# Failed sign-ins, newest last
grep '"action": "authentication.failed"' review-security.log

# Everything one actor did
grep '"actor": "203.0.113.7"' review-security.log
```

The log contains **identifiers and never values** (20.15). A figure out of a
filing is redacted before it is written, so the log tells you *which* fact and
never *what* it said. To see the value, open the model.

The **audit trail is a different thing**: it records what a reviewer decided
and why, including corrected values, and lives with the model because it is
evidence. It is on the diagnostics screen.

---

## 4. Procedures

Each is written as: **signal → do this → then this.**

### 4.1 A credential may be compromised

*Signal:* repeated `authentication.failed` from an address you do not
recognise; or you typed the password somewhere it should not have gone.

1. **Rotate the signing key first, not the password.** This invalidates every
   existing session immediately, including one an attacker already holds.
   ```
   python3 -m apps.api.app.security.credentials --key
   ```
   Set `REVIEW_SECRET_KEY` to the new value and restart. Every browser is
   signed out.
2. **Then rotate the password.**
   ```
   python3 -m apps.api.app.security.credentials
   ```
   Set `REVIEW_PASSWORD_HASH` and restart.
3. Read the security log for the period in question and write down what the
   attacker could have reached had they got in: every document, since there is
   one user and one role.
4. If a session was actually established from an address you do not recognise,
   treat it as **§4.2 disclosure** as well.

Rotating the password without rotating the key leaves an existing session
valid for up to eight hours. That is the mistake to avoid, and it is why the
order above is the order.

### 4.2 A filing may have been disclosed

*Signal:* an unexplained successful sign-in; an export downloaded at a time
nobody was working; a backup archive found somewhere it should not be.

1. **Do not delete anything.** The evidence of what happened is in the store
   and the logs, and deletion is the one action that cannot be undone.
2. Establish scope from the security log: which documents were opened, which
   exports were served, over what window.
3. Establish what those documents were, from the tombstones and records — the
   *identifiers* are in the log, the *contents* are in the store.
4. Tell whoever the filing belongs to. That is a judgement about an obligation
   to somebody else, and this document does not make it for you; it only says
   that it is the step people skip.
5. Rotate as in §4.1 regardless of whether the credential is implicated.

### 4.3 A stored figure may be wrong

*Signal:* a reconciliation that used to tie stops tying; a check that used to
pass fails with no change to the model.

1. **The store detects this itself.** `SourceStore.read` re-hashes the bytes on
   every read and refuses anything that has changed (rule 1.12). A silently
   altered PDF surfaces as a refusal, not as a wrong number.
2. Run the suite. The golden fixtures are pinned by hash; a fixture that
   changed fails `test_fixtures.py` by name.
3. If the model's own figures moved, the diagnostics screen's lineage panel
   traces any line back to the page it came from. Compare against the page
   image, which is rendered from the stored bytes.
4. A figure that cannot be traced to a page is a bug, not an incident. File it.

### 4.4 The store is lost or damaged

*Signal:* the storage volume is gone, the directory is empty, or a restore is
needed for any other reason.

1. **Verify the backup before trusting it.** This is the step the whole backup
   design exists to make possible:
   ```
   python3 -m apps.api.app.security.backup --verify snapshot.tgz
   ```
   It restores into a scratch directory and re-hashes every file against the
   archive's manifest. An archive that extracts is not a backup; one whose
   bytes still hash to what went in is.
2. Restore to a **new** directory, never over the existing one. 1.12 forbids
   overwriting evidence, and a half-completed restore over a damaged store
   leaves neither.
   ```
   python3 -m apps.api.app.security.backup --verify snapshot.tgz  # first
   tar -xzf snapshot.tgz -C var/sources-restored
   python3 review_server.py --store var/sources-restored
   ```
3. Re-run the suite against the restored store.
4. The render cache is **not** in the backup and does not need to be: it is a
   derivative, and the first page view rebuilds it.

### 4.5 A dependency has a published vulnerability

*Signal:* the `dependencies` CI job fails, or an advisory reaches you directly.

1. The job runs `pip-audit --strict` on the whole installed tree, transitive
   dependencies included, on **every commit** rather than at release time — a
   vulnerability disclosed today is in the tree today.
2. Upgrade the pinned version in `requirements.txt` and run the suite.
3. If no fixed version exists, decide explicitly whether the affected code path
   is reachable from this application and record that decision in
   [`decision-ledger.md`](decision-ledger.md). Do not silence the job.

### 4.6 Something must be permanently deleted

*Signal:* the owner decides a model should not exist any more.

1. Settings → *Delete this model permanently*. The confirmation is the
   filename typed back and a written reason (20.18) — not a button, because a
   button is the same gesture whatever it is attached to.
2. What is removed: the stored PDF, every extracted fact, every mapping, every
   cached render.
3. What remains: a **tombstone** carrying the identifier, the hash, the
   filename, and who deleted it and why. That is deliberate — the audit entries
   referencing the document still need something to point at, and a cascade
   would delete the record of the deletion itself.
4. Deletion does not reach backups taken before it. If the deletion is a
   disclosure response, the archives have to be dealt with separately, and this
   document cannot do that for you because it does not know where you put them.

---

## 5. Recovery-time expectations

Stated as what the design supports, not as a promise to anybody:

| | |
|---|---|
| Restore from a verified snapshot | Minutes, bounded by the size of the store |
| Maximum data loss | Whatever changed since the last nightly snapshot (2.6.d) |
| Sign-in outage during a key rotation | One restart |

The nightly cadence is 2.6.d's, and it means up to a day of review work can be
lost. For a single reviewer that is the trade that was made against operating a
continuous-replication setup alone.

---

## 6. After any incident

1. Write what happened in [`decision-ledger.md`](decision-ledger.md) if it
   changed a decision, or in the commit message if it changed code.
2. Add the test that would have caught it. Every finding in that ledger, from
   F-1 to F-29, has one — that is the standard this repository holds itself to
   and an incident is not an exception to it.
3. Re-read §2. If the incident happened in a gap named there, the gap is now a
   thing to close rather than a thing to accept.

---

## Related documents

- [`security-model.md`](security-model.md) — Section 20, requirement by requirement
- [`decision-ledger.md`](decision-ledger.md) — every decision and every finding
- [`source-policy.md`](source-policy.md) — what makes a fact verified
