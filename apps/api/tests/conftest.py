"""Shared fixtures for the ingestion tests. All fixture PDFs are fictional."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"

STATEMENTS = FIXTURES / "text_native_statements.pdf"
#: All three statements, internally consistent. The Phase 6 golden fixture.
THREE_STATEMENTS = FIXTURES / "three_statements.pdf"
EU_LOCALE = FIXTURES / "eu_locale_statements.pdf"
IMAGE_ONLY = FIXTURES / "image_only_scan.pdf"
PARTLY_SCANNED = FIXTURES / "partly_scanned.pdf"
MIXED = FIXTURES / "mixed_text_and_image.pdf"
ENCRYPTED = FIXTURES / "encrypted.pdf"
NOT_A_PDF = FIXTURES / "not_actually_a_pdf.pdf"
TRUNCATED = FIXTURES / "truncated.pdf"


@pytest.fixture
def store_root(tmp_path):
    return tmp_path / "sources"


@pytest.fixture
def config(store_root):
    from apps.api.app.core.config import IngestionConfig

    return IngestionConfig(storage_root=str(store_root))


@pytest.fixture
def store(store_root):
    from apps.api.app.extraction.storage import SourceStore

    return SourceStore(store_root)


@pytest.fixture
def repository(store_root):
    from apps.api.app.persistence.json_store import JsonDocumentRepository

    return JsonDocumentRepository(store_root)


@pytest.fixture
def ingest_fixture(config, store, repository):
    """Run one fixture PDF through the pipeline."""
    from apps.api.app.extraction.pipeline import ingest

    def run(path: Path, *, company_id: str = "co-1", **kwargs):
        return ingest(
            Path(path).read_bytes(),
            original_filename=Path(path).name,
            company_id=company_id,
            config=config,
            store=store,
            existing_id_for_hash=repository.lookup_for(company_id),
            **kwargs,
        )

    return run


@pytest.fixture
def extracted(ingest_fixture):
    """The accepted extraction of the three-page statements fixture."""
    outcome = ingest_fixture(STATEMENTS)
    assert outcome.accepted, outcome.describe()
    return outcome.result


@pytest.fixture
def stored(ingest_fixture, repository):
    """The statements fixture, ingested and persisted, ready for review."""
    outcome = ingest_fixture(STATEMENTS)
    assert outcome.accepted, outcome.describe()
    repository.save(outcome.result)
    return outcome.result


@pytest.fixture
def client(store_root, stored):
    """A test client over a store that already holds one extraction."""
    from fastapi.testclient import TestClient

    from apps.api.app.api.main import create_app

    with TestClient(create_app(store_root)) as test_client:
        test_client.document_id = stored.document.id
        yield test_client


@pytest.fixture
def empty_client(tmp_path):
    """A client over a store with nothing in it, for the empty state."""
    from fastapi.testclient import TestClient

    from apps.api.app.api.main import create_app

    with TestClient(create_app(tmp_path / "empty")) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def three_statements(tmp_path_factory):
    """The three-statement fixture, taken to verified, mapped and approved.

    Everything Phases 3 to 5 do, in the order a reviewer does them. The
    fixture ties across all three statements, which is what lets a check tell
    a working reconciliation from one that cannot run.
    """
    from apps.api.app.core.config import IngestionConfig
    from apps.api.app.extraction.pipeline import ingest
    from apps.api.app.extraction.records import confirm_metadata
    from apps.api.app.extraction.storage import SourceStore
    from apps.api.app.mapping.actions import approve_all, propose_all
    from apps.api.app.mapping.checks import apply_findings
    from apps.api.app.review.actions import accept_fact, correct_fact

    root = tmp_path_factory.mktemp("three-statements")
    outcome = ingest(
        Path(THREE_STATEMENTS).read_bytes(),
        original_filename=Path(THREE_STATEMENTS).name,
        company_id="co-1",
        config=IngestionConfig(storage_root=str(root)),
        store=SourceStore(root),
    )
    assert outcome.accepted, outcome.describe()
    result = outcome.result

    result = confirm_metadata(
        result,
        {
            name: None
            for name, field in result.document.metadata.fields.items()
            if field.value is not None
        },
        actor="owner", reason="checked the cover page",
    )
    for fact in list(result.facts):
        if fact.raw_value in ("\u2014", "\u2013", "N/A"):
            result = correct_fact(result, fact.id, "0", actor="owner",
                                  reason="the filer reports nil here")
    for fact in list(result.facts):
        if fact.value is not None and fact.decision is None:
            result = accept_fact(result, fact.id, actor="owner",
                                 reason="matches the printed page")
    result = propose_all(result)
    result = approve_all(result, actor="owner",
                         note="each label matches the canonical definition")
    return apply_findings(result)


@pytest.fixture(scope="module")
def built(three_statements):
    from apps.api.app.statements.build import build_statements

    return build_statements(three_statements)


@pytest.fixture
def mapped_aggregate(extracted):
    """The two-statement fixture with its three expense lines aggregated.

    11.5's case: the filing presents SG&A, R&D and restructuring; the chart has
    one operating expense line. Shared by the mapping and statement suites
    because it is the only fixture with a genuine aggregation.
    """
    from apps.api.app.extraction.records import confirm_metadata
    from apps.api.app.mapping.actions import approve_all, combine_facts, propose_all
    from apps.api.app.mapping.checks import apply_findings
    from apps.api.app.review.actions import accept_fact, correct_fact

    labels = {
        "Selling, general and administrative",
        "Research and development",
        "Restructuring charges",
    }
    result = confirm_metadata(
        extracted,
        {n: None for n, f in extracted.document.metadata.fields.items() if f.value is not None},
        actor="owner", reason="checked the cover page",
    )
    for fact in list(result.facts):
        if fact.raw_value in ("\u2014", "\u2013", "N/A"):
            result = correct_fact(result, fact.id, "0", actor="owner",
                                  reason="the filer reports nil here")
    for fact in list(result.facts):
        if fact.value is not None and fact.decision is None:
            result = accept_fact(result, fact.id, actor="owner",
                                 reason="matches the printed page")
    result = propose_all(result)
    for period in ("2025", "2024"):
        ids = [f.id for f in result.facts
               if f.raw_label in labels and f.period_label == period]
        result = combine_facts(result, ids, "operating_expenses", actor="owner",
                               note="three categories; the chart has one line")
    result = approve_all(result, actor="owner",
                         note="each label matches the canonical definition")
    return apply_findings(result)
