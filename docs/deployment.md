# Deployment

Specification Phase 17, items 169-180.

This document is the deployment half of Phase 17. It is written as a runbook
rather than a description, because a runbook is the thing somebody actually
follows at the moment they deploy.

Two kinds of item live in Phase 17, and they are kept apart on purpose:

- **Items the application can answer.** Security headers (175), the build
  record (180), the smoke tests (172, 179) and the backup verification (176)
  are code and tests. They are done, and the checks below run them.
- **Items only the owner can answer.** The deployment target, the access
  level, the data policy (169) and the release approval (177) are decisions,
  not code. Nothing here guesses them. They are listed in §6 with the exact
  question each one asks.

Item 169 is a gate, not a step: **do not deploy until §6 is answered.**

---

## 1. What is deployed

One FastAPI application, server-rendered, with no JavaScript anywhere
(deviation F-14). Storage is JSON files on a filesystem
(`apps/api/app/persistence/json_store.py`). There is no database server and no
migration tool, which is what makes item 173 answerable at all -- see §4.

    apps/api/app/api/main.py        the ASGI application
    <storage root>/                 documents, extractions, mappings,
                                    scenarios, audit log, renders/

`renders/` is derived: page images regenerated from the stored PDF. It is the
one directory `security/backup.py` excludes, because backing up a cache costs
space and proves nothing.

## 2. Configuration

Three environment variables.

**The first two are not optional for a deployment**, and the refusal is
enforced at the point where it matters rather than at import time.
`review_server.py` refuses to bind to anything but loopback when no credential
is configured, and prints the two commands that produce one. An unconfigured
process is therefore a local review session -- which says so on every page --
and never an unauthenticated site on a network. That is decision 2.2.c.

`REVIEW_SECRET_KEY` behaves differently on purpose: unset, `signing_key`
generates a key per process, so every restart logs everybody out. That is not
a fallback that makes the application work anyway; it is a visible consequence
of not configuring it. A configured key shorter than 32 characters is refused
outright.

| Variable | Required | What it is |
| --- | --- | --- |
| `REVIEW_PASSWORD_HASH` | yes | scrypt hash of the review password. Generate with `python3 -m apps.api.app.security.credentials`, which prompts for the password and prints only the hash. Never the password itself. |
| `REVIEW_SECRET_KEY` | yes | session and CSRF signing key, >= 32 random bytes. Rotating it logs everybody out, which is the intended effect after an incident. |
| `INGEST_SCAN_COMMAND` | no | the malware scanner to run on upload. Absent means `NOT_SCANNED`, which is reported as a gap and never as clean (20.7). |

Neither secret may appear in version control. `security/repository_scan.py`
is the test that says so, and it runs in CI.

## 3. Staging first (items 170, 171)

Deploy to staging before production, every time, and **use synthetic data
there** unless the private-data controls in §6 are confirmed for staging as
well as production.

The fixtures in `apps/api/tests/fixtures/` are synthetic by construction --
`build_fixtures.py` generates them, and `test_fixtures.py` pins their hashes.
There is no real filing in this repository and
`security/repository_scan.py::_accounted_for` is what keeps it that way: a
fixture must be *both* pinned and generated, so a real PDF dropped into that
directory fails the suite rather than being quietly shipped.

Load staging with:

    python3 ingest_pdf.py apps/api/tests/fixtures/<fixture>.pdf

## 4. Migrations and rollback (item 173)

**There are no schema migrations, because there is no database.** Item 173 is
answered honestly rather than by pointing at a migration tool that does not
exist here. What it asks for -- that a deployment can be undone without losing
data -- is satisfied by three properties:

1. **Records carry their own version.** A reader that meets a record it does
   not understand refuses it and says so. It does not guess.
2. **The stored PDF is never rewritten** (rule 1.12). Every derived artefact
   can be rebuilt from it, so the worst case of a bad deploy is recomputation,
   not loss.
3. **Rollback is: take a snapshot, deploy the previous commit, restore if
   needed.** Concretely:

       python3 -c "from apps.api.app.security.backup import snapshot; \
                  snapshot('<storage root>', '<archive>.tar.gz')"
       # deploy the previous commit
       python3 -c "from apps.api.app.security.backup import verify; \
                  print(verify('<archive>.tar.gz'))"

`verify` re-hashes every file in the archive against the manifest written
inside it. A restore that does not reproduce what was backed up raises
`RestoreFailed` and names the file, rather than returning a success that is
not one.

When PostgreSQL replaces the JSON store (specification 3.2.d, still open),
this section is the part that has to be rewritten, and item 173 becomes a real
migration plan. Nothing above should be read as saying that work is done.

## 5. Pre-flight checks

Run these in order. Every one of them is a command, not a judgement.

**Storage permissions (item 174).** The storage root must be writable by the
application user and readable by nobody else. `0700`, owned by the service
account:

    stat -c '%a %U:%G' <storage root>      # expect 700 and the service user

The reason is item 20.1: a filing is confidential, and a world-readable
directory makes every other control decorative.

**TLS and security headers (item 175).** TLS terminates at the reverse proxy;
the application never holds a certificate. It does send every header itself,
so a proxy misconfiguration cannot silently drop them
(`app/security/headers.py`). `Strict-Transport-Security` is sent **only on an
HTTPS request**, because sending it over plaintext is meaningless and
misleading.

The Content-Security-Policy is unusually strict -- `script-src 'none'` -- and
that is not aspirational: the application ships no JavaScript, and
`test_no_template_contains_a_script_tag` is the test the claim rests on.

    curl -sI https://<host>/health | grep -i \
      -e content-security-policy -e strict-transport-security \
      -e x-content-type-options -e referrer-policy -e cache-control

**Backups (item 176).** Do not trust a backup that has not been restored:

    python3 -m pytest apps/api/tests/integration/test_operations.py \
      -k "snapshot or restore or backup"

**Smoke tests (items 172, 179).** Sixteen checks against a running
deployment:

    python3 -m apps.api.app.verification.smoke https://<host>

It **never authenticates**, which is what makes it safe to run against
production: it cannot reach a filing, so it cannot expose one. That is item
179's actual requirement. What it checks instead is the shape of a correct
deployment -- that the guard refuses an unauthenticated request, that the
refusal carries the security headers, that `/health` names a commit, and that
the commit is not `-dirty`.

**The exact tested version (item 178).** The smoke check named
`deploys a clean tree (178)` fails when `/health` reports a `-dirty` commit.
A deployment from a modified working tree is not the version the suite passed,
so the check says so rather than rounding it off.

**Release readiness (items 166-168, 24.22).** Regenerate and read it:

    python3 -m apps.api.app.verification.report --out docs/release-readiness.md

A `NOT_RUN` row blocks release. That is `Report.may_release`, and it is
deliberate: rule 1.14 forbids an unresolved requirement appearing as a pass,
and a gate nobody ran is unresolved.

## 6. What the owner must decide

These are the Phase 17 items this repository cannot close for itself. Each one
is a question with a consequence, not a checkbox.

**Item 169.a -- deployment target.** Where does this run? The answer changes
§5's TLS step and the backup destination. Decision 2.2.a says private hosted;
the host itself is unnamed.

**Item 169.b -- access level.** The application is built for a single
reviewer: one credential, no roles, no tenancy
(`security/authorization.py` returns 404 rather than 403, so a reader cannot
even learn that another model exists). If more than one person needs access,
that is not a configuration change -- it is an authorization model this codebase
does not have.

**Item 169.c -- data policy.** Specifically: may a real filing be uploaded,
and for how long is it kept? `security/retention.py` implements permanent
deletion with a typed-back confirmation, but *how long* is a policy and it is
not set anywhere in this repository. Until it is answered, item 171 stands:
synthetic data only.

**Item 177 -- release approval.** A human decision, recorded. The release
report gives the evidence; it does not give the approval, and nothing in the
code should ever appear to.

Two further items need repository administration rather than deployment, and
are noted here so they are not lost:

- delete the stale branches;
- enable branch protection on `main`, so that the CI this report depends on
  cannot be bypassed by a direct push.

## 7. After deploying

1. `python3 -m apps.api.app.verification.smoke https://<host>` -- expect every
   check to pass.
2. Record `/health`'s `commit`, `schema_version` and `formula_version`
   (item 180). These are the three values that answer "which code produced
   this figure" six months later, when an export and a screenshot disagree.
3. Take the first backup and verify it (§5).
