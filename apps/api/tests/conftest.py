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
