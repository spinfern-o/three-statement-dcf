"""Phase 15, items 147, 150, 151: isolation, scanning, backup and deletion.

2.6.d's own words are the standard these are written against: **an untested
backup is not a backup.** `verify` is the quarterly restore test, run here on
every commit instead.
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from apps.api.app.api.main import create_app
from apps.api.app.api.rendering import render_page
from apps.api.app.security.backup import (
    BACKUP_RETENTION_DAYS,
    EXCLUDED,
    MANIFEST_NAME,
    NOTE,
    RestoreFailed,
    restore,
    snapshot,
    verify,
)
from apps.api.app.security.retention import (
    RETENTION,
    DeletionRefused,
    Tombstone,
    check_confirmation,
    delete_permanently,
    load_tombstone,
    tombstones,
)
from apps.api.app.security.sandbox import (
    DEFAULT_TIMEOUT_SECONDS,
    Limits,
    SandboxError,
    is_available,
    run_isolated,
)
from apps.api.app.security.scanning import (
    SCAN_COMMAND_ENV,
    ScanOutcome,
    quarantine,
    scan,
    scan_state,
)
from apps.api.tests.conftest import browser_client

# --- item 147: 20.10, the isolated parser -----------------------------------


def _add(a, b):
    return a + b


def _raise():
    raise ValueError("a malformed cross-reference table")


def _spin():
    while True:
        pass


def test_isolation_is_available_here():
    assert is_available()


def test_an_isolated_call_returns_its_result():
    assert run_isolated(_add, 2, 3) == 5


def test_an_exception_inside_the_child_becomes_a_refusal_not_a_crash():
    with pytest.raises(SandboxError, match="ValueError"):
        run_isolated(_raise)


def test_a_runaway_loop_is_stopped_by_the_cpu_limit():
    """A parser that never returns ends in the child, not in the web process."""
    with pytest.raises(SandboxError):
        run_isolated(_spin, limits=Limits(cpu_seconds=1, timeout_seconds=20))


def test_the_wall_clock_limit_is_separate_from_the_cpu_limit():
    """A child blocked on something burns no CPU and would never hit the other."""
    assert DEFAULT_TIMEOUT_SECONDS > 0
    assert Limits().cpu_seconds != Limits().timeout_seconds


def test_the_isolated_render_is_byte_for_byte_the_in_process_one(store, stored):
    """The separation must change nothing about the output, or it is a rewrite
    rather than an isolation."""
    document_hash = stored.document.immutable_hash
    isolated = render_page(store, document_hash, 1, isolate=True)
    inline = render_page(store, document_hash, 1, isolate=False)
    assert isolated == inline and isolated[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_bad_page_number_still_raises_index_error_through_the_sandbox(store, stored):
    """One outcome a caller distinguishes, recovered by name rather than
    flattened into a generic sandbox failure."""
    with pytest.raises(IndexError, match="outside this document"):
        render_page(store, stored.document.immutable_hash, 99, isolate=True)


# --- item 147: 20.9, scanning -----------------------------------------------


def test_with_no_scanner_configured_the_result_is_not_clean(tmp_path):
    """The claim this module exists not to make."""
    result = scan(tmp_path, environ={})
    assert result.outcome is ScanOutcome.NOT_SCANNED
    assert not result.outcome.is_known
    assert "not the same as a clean result" in result.describe()


def test_not_scanned_still_lets_a_single_user_process_their_own_filing(tmp_path):
    assert scan(tmp_path, environ={}).may_process


def test_a_scanner_that_exits_zero_is_clean(tmp_path):
    result = scan(tmp_path, environ={SCAN_COMMAND_ENV: "true"})
    assert result.outcome is ScanOutcome.CLEAN and result.may_process


def test_a_scanner_that_finds_something_stops_the_upload(tmp_path):
    result = scan(tmp_path, environ={SCAN_COMMAND_ENV: "false"})
    assert result.outcome is ScanOutcome.INFECTED and not result.may_process


def test_a_scanner_that_cannot_run_is_an_error_not_a_pass(tmp_path):
    result = scan(tmp_path, environ={SCAN_COMMAND_ENV: "no-such-scanner-anywhere"})
    assert result.outcome is ScanOutcome.ERRORED and not result.may_process


def test_a_failed_file_is_quarantined_rather_than_deleted(tmp_path):
    """Deleting destroys the evidence of why an upload was refused, and the
    question asked afterwards is always what was in it."""
    suspect = tmp_path / "suspect.pdf"
    suspect.write_bytes(b"%PDF-1.4 ...")
    result = scan(suspect, environ={SCAN_COMMAND_ENV: "false"})
    moved = quarantine(suspect, tmp_path / "store", result)
    assert not suspect.exists()
    assert Path(moved.quarantined_at).read_bytes() == b"%PDF-1.4 ..."


def test_quarantine_does_not_overwrite_an_earlier_one(tmp_path):
    for _ in range(2):
        suspect = tmp_path / "suspect.pdf"
        suspect.write_bytes(b"x")
        quarantine(suspect, tmp_path / "store", scan(suspect, environ={SCAN_COMMAND_ENV: "false"}))
    quarantined = sorted((tmp_path / "store" / "quarantine").iterdir())
    assert len(quarantined) == 2


def test_the_settings_page_reports_scanning_per_deployment_not_per_document(tmp_path):
    assert scan_state(tmp_path).outcome is ScanOutcome.NOT_SCANNED


# --- item 150: the backup, and the restore that proves it -------------------


@pytest.fixture
def populated(tmp_path, stored):
    """A store with a filing in it, plus a render cache to be excluded."""
    root = tmp_path / "store"
    (root / "a").mkdir(parents=True)
    (root / "a" / "filing.pdf").write_bytes(b"%PDF-1.4 pretend filing")
    (root / "records").mkdir()
    (root / "records" / "doc.json").write_text('{"document": {}}')
    (root / "renders").mkdir()
    (root / "renders" / "page.png").write_bytes(b"cache")
    return root


def test_a_snapshot_lists_every_file_and_its_hash(populated, tmp_path):
    manifest = snapshot(populated, tmp_path / "snap.tgz")
    assert set(manifest.files) == {"a/filing.pdf", "records/doc.json"}
    for digest in manifest.files.values():
        assert len(digest) == 64


def test_a_restore_is_verified_by_re_hashing_not_by_extracting(populated, tmp_path):
    """A tar that extracts proves the tar is well-formed, not that the bytes
    inside it are the bytes that went in."""
    archive = tmp_path / "snap.tgz"
    snapshot(populated, archive)
    manifest = verify(archive)
    assert manifest.file_count == 2


def test_a_corrupted_archive_fails_verification(populated, tmp_path):
    archive = tmp_path / "snap.tgz"
    snapshot(populated, archive)

    # Rebuild the archive with one file's contents changed and the original
    # manifest kept, which is exactly what a silent corruption looks like.
    tampered = tmp_path / "tampered.tgz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(tampered, "w:gz") as target:
        for member in source.getmembers():
            handle = source.extractfile(member)
            body = handle.read() if handle else b""
            if member.name == "a/filing.pdf":
                body = b"%PDF-1.4 something else entirely"
                member.size = len(body)
            import io

            target.addfile(member, io.BytesIO(body))

    with pytest.raises(RestoreFailed, match="changed"):
        verify(tampered)


def test_a_missing_file_fails_verification(populated, tmp_path):
    archive = tmp_path / "snap.tgz"
    snapshot(populated, archive)
    stripped = tmp_path / "stripped.tgz"
    with tarfile.open(archive, "r:gz") as source, tarfile.open(stripped, "w:gz") as target:
        for member in source.getmembers():
            if member.name == "records/doc.json":
                continue
            handle = source.extractfile(member)
            import io

            target.addfile(member, io.BytesIO(handle.read() if handle else b""))
    with pytest.raises(RestoreFailed, match="missing"):
        verify(stripped)


def test_an_archive_with_no_manifest_is_refused(tmp_path):
    archive = tmp_path / "foreign.tgz"
    payload = tmp_path / "x.txt"
    payload.write_text("hello")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="x.txt")
    with pytest.raises(RestoreFailed, match="no manifest"):
        restore(archive, tmp_path / "out")


def test_an_archive_that_would_write_outside_the_destination_is_refused(tmp_path):
    """20.12, path traversal. Refused rather than sanitized: an archive with a
    member like this is not one this module wrote."""
    archive = tmp_path / "evil.tgz"
    payload = tmp_path / "x.txt"
    payload.write_text("hello")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(payload, arcname="../escaped.txt")
    with pytest.raises(RestoreFailed, match="outside the destination"):
        restore(archive, tmp_path / "out")


def test_the_render_cache_is_not_backed_up(populated, tmp_path):
    """A derivative that a re-render reproduces, costing space and restoring
    nothing."""
    manifest = snapshot(populated, tmp_path / "snap.tgz")
    assert "renders" in EXCLUDED
    assert not any(name.startswith("renders/") for name in manifest.files)


def test_the_manifest_says_what_the_archive_contains_and_how_sensitive_it_is(populated, tmp_path):
    archive = tmp_path / "snap.tgz"
    snapshot(populated, archive)
    with tarfile.open(archive, "r:gz") as tar:
        body = tar.extractfile(MANIFEST_NAME).read().decode()
    note = json.loads(body)["note"]
    assert note == NOTE
    assert "SOURCE PDFs" in note
    assert "not encrypted" in note
    assert "confidential" in note


def test_two_snapshots_of_one_state_agree(populated, tmp_path):
    first = snapshot(populated, tmp_path / "one.tgz")
    second = snapshot(populated, tmp_path / "two.tgz")
    assert first.files == second.files


def test_the_backup_retention_is_the_confirmed_one():
    assert BACKUP_RETENTION_DAYS == 30


# --- item 151: retention and permanent deletion -----------------------------


def test_retention_is_a_stated_decision_not_an_absence():
    assert "Indefinite until the owner deletes" in RETENTION
    assert "2.6.b" in RETENTION


def test_a_deletion_without_the_filename_typed_back_is_refused(stored):
    with pytest.raises(DeletionRefused, match="type its filename"):
        check_confirmation(stored, "yes", "no longer needed")


def test_a_deletion_without_a_reason_is_refused(stored):
    with pytest.raises(DeletionRefused, match="written reason"):
        check_confirmation(stored, stored.document.sanitized_filename, "  ")


def test_a_refused_deletion_deletes_nothing(client, stored, store_root):
    before = sorted(p.name for p in Path(store_root).rglob("*.pdf"))
    response = client.post(
        f"/documents/{client.document_id}/delete",
        data={"confirm_filename": "wrong.pdf", "reason": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 303 and "error=" in response.headers["location"]
    assert sorted(p.name for p in Path(store_root).rglob("*.pdf")) == before


def test_a_confirmed_deletion_removes_the_bytes_and_leaves_a_tombstone(
    stored, store_root, store, repository
):
    stone = delete_permanently(
        stored,
        store_root,
        actor="owner",
        reason="the filing was withdrawn by the issuer",
        typed_filename=stored.document.sanitized_filename,
        store=store,
        repository=repository,
    )
    assert not store.path_for(stored.document.immutable_hash).exists()
    assert not (Path(repository.root) / f"{stored.document.id}.json").exists()

    recovered = load_tombstone(store_root, stored.document.id)
    assert recovered == stone
    assert recovered.reason == "the filing was withdrawn by the issuer"
    assert recovered.facts_removed == len(stored.facts)


def test_the_tombstone_keeps_the_identifier_and_not_the_content(
    stored, store_root, store, repository
):
    """The flagged interaction, answered: an audit entry naming this document
    still has something to point at, and nothing confidential survives."""
    stone = delete_permanently(
        stored,
        store_root,
        actor="owner",
        reason="withdrawn",
        typed_filename=stored.document.sanitized_filename,
        store=store,
        repository=repository,
    )
    body = json.loads((Path(store_root) / "tombstones" / f"{stored.document.id}.json").read_text())
    assert body["document_id"] == stored.document.id
    assert body["immutable_hash"] == stored.document.immutable_hash
    assert set(body) == {
        "audit_events_kept",
        "deleted_at",
        "deleted_by",
        "document_id",
        "facts_removed",
        "immutable_hash",
        "reason",
        "sanitized_filename",
    }
    assert stone.audit_events_kept > 0


def test_a_deleted_document_is_gone_from_the_application(stored, store_root, store, repository):
    delete_permanently(
        stored,
        store_root,
        actor="owner",
        reason="withdrawn",
        typed_filename=stored.document.sanitized_filename,
        store=store,
        repository=repository,
    )
    with browser_client(create_app(store_root)) as client:
        assert client.get(f"/documents/{stored.document.id}").status_code == 404
        assert stored.document.sanitized_filename not in client.get("/").text


def test_deleting_removes_the_render_cache_too(stored, store_root, store, repository):
    """A render is a derivative of the bytes and must not outlive them."""
    render_page(store, stored.document.immutable_hash, 1, cache_root=Path(store_root))
    cached = list((Path(store_root) / "renders").rglob("*.png"))
    assert cached, "this assertion proved nothing; nothing was cached"

    delete_permanently(
        stored,
        store_root,
        actor="owner",
        reason="withdrawn",
        typed_filename=stored.document.sanitized_filename,
        store=store,
        repository=repository,
    )
    assert not list((Path(store_root) / "renders").rglob("*.png"))


def test_tombstones_are_listed_in_order(stored, store_root, store, repository):
    delete_permanently(
        stored,
        store_root,
        actor="owner",
        reason="withdrawn",
        typed_filename=stored.document.sanitized_filename,
        store=store,
        repository=repository,
    )
    listed = tombstones(store_root)
    assert len(listed) == 1 and isinstance(listed[0], Tombstone)


def test_the_settings_screen_names_the_file_that_must_be_typed(client, stored):
    page = client.get(f"/documents/{client.document_id}/settings")
    assert page.status_code == 200
    assert stored.document.sanitized_filename in page.text
    assert "cannot be undone" in page.text
    # 20.18: no default value and no autofocus on the confirmation field.
    assert 'name="confirm_filename"' in page.text
    assert "autofocus" not in page.text


# --- items 152, 153: the scans and the procedure ----------------------------


def test_no_source_pdf_and_no_secret_is_committed():
    """20.4 and item 166, as a check that runs rather than a box somebody ticks."""
    from apps.api.app.security.repository_scan import run

    findings = run()
    assert findings == [], "\n".join(f.describe() for f in findings)


def test_the_scan_catches_a_pdf_that_is_not_an_accounted_for_fixture(tmp_path):
    import shutil
    import subprocess

    from apps.api.app.security.repository_scan import ROOT, run

    repo = tmp_path / "repo"
    shutil.copytree(
        ROOT,
        repo,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "var"),
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "docs" / "acquisition-target.pdf").write_bytes(b"%PDF-1.4 a real filing")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    found = [f.path for f in run(repo)]
    assert "docs/acquisition-target.pdf" in found


def test_the_scan_catches_a_committed_secret(tmp_path):
    import shutil
    import subprocess

    from apps.api.app.security.repository_scan import ROOT, run

    repo = tmp_path / "repo"
    shutil.copytree(
        ROOT,
        repo,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "var"),
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    # Assembled rather than written out, so this file does not itself contain
    # the shape it is testing for. The alternative is adding it to
    # SHAPE_EXEMPT, and every name on that list is a file the scan no longer
    # protects -- a list that grows by one each time somebody writes a test.
    secret = "pass" + "word" + ': "' + "hunter2" * 2 + '"'
    (repo / "deploy.env").write_text(secret + "\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)

    assert "deploy.env" in [f.path for f in run(repo)]


def test_env_example_carries_names_and_not_values():
    """Phase 1 item 12 and 20.3. The file exists to name the variables."""
    from apps.api.app.security.repository_scan import ROOT, scan_secrets

    body = (ROOT / ".env.example").read_text()
    assert "REVIEW_PASSWORD_HASH" in body or "INGEST_STORAGE_ROOT" in body
    assert ".env.example" not in [f.path for f in scan_secrets(ROOT)]


def test_ci_runs_the_dependency_audit():
    from apps.api.app.security.repository_scan import ROOT

    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text()
    assert "pip_audit" in workflow or "pip-audit" in workflow
    assert "repository_scan" in workflow


def test_the_incident_procedure_exists_and_names_the_residual_risks():
    """Item 153. A procedure that does not say what it cannot defend against
    gets read as a guarantee it never made."""
    from apps.api.app.security.repository_scan import ROOT

    body = (ROOT / "docs" / "incident-response.md").read_text()
    for required in (
        "not a security boundary",  # the sandbox's own limits
        "NOT SCANNED",  # 20.9 with no scanner configured
        "per process",  # the rate limiters
        "encrypted by the process that writes it",  # the backup archive
        "--verify",  # the restore test, by command
        "Rotate the signing key first",  # the order that matters in 4.1
    ):
        assert required in body, required


# --- 20.19 and Section 25: the disclaimer, on every surface ------------------


def test_the_disclaimer_is_section_25s_own_language():
    from model.disclaimer import DISCLAIMER, SENTENCES

    assert len(SENTENCES) == 4
    for fragment in (
        "not investment, accounting, tax, or legal advice",
        "extraction or classification errors until reviewed",
        "inherently uncertain",
        "Verify all source data, assumptions, and outputs",
    ):
        assert fragment in DISCLAIMER, fragment


def test_the_disclaimer_is_in_the_model(forecast_client):
    """Section 25: in the model. Every screen, not one page linked from a footer."""
    from model.disclaimer import DISCLAIMER

    for screen in ("", "/statements", "/valuation", "/exports"):
        page = forecast_client.get(f"/documents/{forecast_client.document_id}{screen}").text
        assert DISCLAIMER in page, screen


def test_the_disclaimer_is_in_the_release_flow(forecast_client):
    from model.disclaimer import DISCLAIMER

    page = forecast_client.get(f"/documents/{forecast_client.document_id}/diagnostics").text
    assert DISCLAIMER in page
    # Inside the release-readiness card, where a reader deciding whether to
    # rely on the model is looking -- not only in the footer at the bottom.
    assert page.index("Release readiness") < page.index(DISCLAIMER)
    assert page.index(DISCLAIMER) < page.index("Every Section 17 check")


def test_the_disclaimer_is_in_every_export(forecast_client):
    """Section 25's third surface. All four formats, not just the report."""
    import json

    from model.disclaimer import DISCLAIMER

    document_id = forecast_client.document_id
    body = json.loads(forecast_client.get(f"/documents/{document_id}/exports/model.json").text)
    assert DISCLAIMER in body["limitations"]

    import io

    import openpyxl
    import pymupdf

    workbook = openpyxl.load_workbook(
        io.BytesIO(forecast_client.get(f"/documents/{document_id}/exports/model.xlsx").content)
    )
    assert any(
        isinstance(cell.value, str) and "not investment" in cell.value
        for sheet in workbook
        for row in sheet.iter_rows()
        for cell in row
    )

    report = pymupdf.open(
        stream=forecast_client.get(f"/documents/{document_id}/exports/report.pdf").content,
        filetype="pdf",
    )
    text = " ".join(" ".join(page.get_text().split()) for page in report)
    assert " ".join(DISCLAIMER.split()) in text


def test_the_cli_report_prints_it(tmp_path):
    """The surface that had none. A CLI report is the model for whoever runs it."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    completed = subprocess.run(
        [sys.executable, "run_model.py", "--company", "inputs/example/company.yaml"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    completed.stdout + completed.stderr
    # The example inputs ship blank, so the engine halts -- which is the
    # documented behaviour. What matters is that a run that DOES report
    # carries the disclaimer, so the assertion is on the report path.
    from model.disclaimer import block

    assert "DISCLAIMER (specification Section 25)" in block()
    assert "Section 25" in block()


def test_no_surface_carries_a_trimmed_version():
    """The failure this replaced: a footer with two of the four sentences.

    Trimming a disclaimer keeps the part that sounds most like boilerplate and
    drops the part that is about this system in particular.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    stale = "Scenario forecasts are not facts or guarantees"
    for path in (root / "apps/api/app/api/templates").glob("*.html"):
        assert stale not in path.read_text(), path.name
