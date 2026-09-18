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
#: A complete balance sheet, so the forecast has everything it anchors on.
FORECASTABLE = FIXTURES / "forecastable.pdf"
EU_LOCALE = FIXTURES / "eu_locale_statements.pdf"
IMAGE_ONLY = FIXTURES / "image_only_scan.pdf"
PARTLY_SCANNED = FIXTURES / "partly_scanned.pdf"
MIXED = FIXTURES / "mixed_text_and_image.pdf"
ENCRYPTED = FIXTURES / "encrypted.pdf"
NOT_A_PDF = FIXTURES / "not_actually_a_pdf.pdf"
TRUNCATED = FIXTURES / "truncated.pdf"


def browser_client(app):
    """A `TestClient` that sends the CSRF token, the way a browser does.

    20.12 requires every state-changing request to carry this session's token,
    and a browser gets it from the hidden field in the form it is submitting.
    A test posting without one is not testing the domain logic it was written
    for -- it is testing the CSRF guard, which has its own tests in
    `test_security.py` that supply no token, a stale token and a forged one.

    So this fills the field in when the caller has not, and never overrides a
    caller who has: a test that wants to submit a bad token still can.
    """
    from fastapi.testclient import TestClient

    class _Browser(TestClient):
        def post(self, url, *args, **kwargs):
            data = kwargs.get("data")
            if data is None and "files" not in kwargs and "json" not in kwargs:
                data = {}
            if isinstance(data, dict) and "csrf_token" not in data:
                kwargs["data"] = {**data, "csrf_token": self.csrf_token()}
            return super().post(url, *args, **kwargs)

        def csrf_token(self) -> str:
            """This client's current token, derived the way the guard does."""
            from apps.api.app.security import csrf, sessions

            state = self.app.state
            cookie = self.cookies.get(sessions.COOKIE_NAME, "")
            nonce = "local-review"
            if state.credential is not None and cookie:
                nonce = sessions.verify(state.signing_key, cookie).nonce
            return csrf.token_for(state.signing_key, nonce)

    return _Browser(app)


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

    from apps.api.app.api.main import create_app

    with browser_client(create_app(store_root)) as test_client:
        test_client.document_id = stored.document.id
        yield test_client


@pytest.fixture
def empty_client(tmp_path):
    """A client over a store with nothing in it, for the empty state."""

    from apps.api.app.api.main import create_app

    with browser_client(create_app(tmp_path / "empty")) as test_client:
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


def _review_and_map(path, root):
    """Everything Phases 3 to 5 do, in the order a reviewer does them."""
    from apps.api.app.core.config import IngestionConfig
    from apps.api.app.extraction.pipeline import ingest
    from apps.api.app.extraction.records import confirm_metadata
    from apps.api.app.extraction.storage import SourceStore
    from apps.api.app.mapping.actions import approve_all, propose_all
    from apps.api.app.mapping.checks import apply_findings
    from apps.api.app.review.actions import accept_fact, correct_fact

    outcome = ingest(
        Path(path).read_bytes(),
        original_filename=Path(path).name,
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
def forecastable(tmp_path_factory):
    """A reviewed filing whose balance sheet is complete enough to forecast.

    `three_statements` cannot be forecast, and correctly so: the engine anchors
    its roll-forwards on four balance-sheet lines that filing does not report,
    and STEP 5 forbids substituting zero. This one reports all four.
    """
    return _review_and_map(FORECASTABLE, tmp_path_factory.mktemp("forecastable"))


@pytest.fixture
def forecast_client(tmp_path, forecastable):
    """A client over the forecastable filing, with an approved base scenario.

    Carries the forecast drivers AND the market inputs, so one client serves
    the forecast screen and the valuation screen. Stored the way the
    application stores it, so the screens read the same JSON a reviewer's own
    session would.
    """

    from apps.api.app.api.main import create_app
    from apps.api.app.assumptions.store import ScenarioStore
    from apps.api.app.persistence.json_store import JsonDocumentRepository

    root = tmp_path / "forecast"
    JsonDocumentRepository(root).save(forecastable)
    ScenarioStore(root).save(forecastable.document.id, approved_scenario("owner"))

    with browser_client(create_app(root)) as test_client:
        test_client.document_id = forecastable.document.id
        yield test_client


#: 16.6-16.10 and 16.15, as decimal strings (4.2). None can be derived from the
#: filing, which is why each one is EXTERNAL_MARKET_DATA with a URL and a date.
MARKET_INPUTS = {
    "risk_free_rate": ("0.042", "ratio"),
    "beta": ("1.15", "ratio"),
    "equity_risk_premium": ("0.055", "ratio"),
    "pretax_cost_of_debt": ("0.05", "ratio"),
    "market_value_equity": ("2500000", "currency"),
    "market_value_debt": ("550000", "currency"),
    "terminal_growth": ("0.02", "ratio"),
}


def approved_scenario(owner: str = "owner"):
    """A base scenario with every forecast driver AND every market input."""
    from apps.api.app.assumptions.drivers import BY_CODE
    from apps.api.app.assumptions.scenarios import ScenarioSet, base_scenario
    from apps.api.app.assumptions.schema import Assumption, Evidence, SourceType, Status

    def driver(code, value):
        unit = BY_CODE[code].unit
        fields = dict(
            code=code, name=code.replace("_", " "), value=value, unit=unit,
            owner=owner, reviewer=owner, status=Status.APPROVED,
            rationale="entered for this test, with a stated source",
        )
        if unit == "days":
            fields.update(
                source_type=SourceType.HISTORICAL_DRIVER,
                evidence=Evidence(measured_over=("2025A",)),
            )
        else:
            fields.update(
                source_type=SourceType.COMPANY_GUIDANCE,
                evidence=Evidence(document_id="doc-1", page=31, date="2026-02-14"),
            )
        return Assumption(**fields)

    def market(code, value, unit):
        return Assumption(
            code=code, name=code.replace("_", " "), value=value, unit=unit,
            owner=owner, reviewer=owner, status=Status.APPROVED,
            rationale="observed on the valuation date and recorded with its source",
            source_type=SourceType.EXTERNAL_MARKET_DATA,
            evidence=Evidence(url=f"https://example.test/{code}", date="2026-09-17"),
        )

    return ScenarioSet(
        (base_scenario(owner),),
        tuple(driver(code, value) for code, value in FORECAST_DRIVERS.items())
        + tuple(market(code, value, unit) for code, (value, unit) in MARKET_INPUTS.items()),
    )


#: The rates the forecastable filing itself implies, as decimal strings (4.2).
FORECAST_DRIVERS = {
    "revenue_growth": "0.08",
    "cogs_pct_revenue": "0.60",
    "opex_pct_revenue": "0.24",
    "depreciation_pct_beginning_ppe": "0.1412",
    "capex_pct_revenue": "0.085",
    "dso": "58.4",
    "inventory_days": "73",
    "dpo": "60.8",
    "other_current_assets_pct_revenue": "0.02",
    "other_current_liabilities_pct_revenue": "0.045",
    "interest_rate_on_debt": "0.04",
    "tax_rate": "0.25",
}


@pytest.fixture(scope="module")
def forecast_built(forecastable):
    from apps.api.app.statements.build import build_statements

    return build_statements(forecastable)


@pytest.fixture
def three_statement_client(tmp_path, three_statements):
    """A client serving the fully reviewed three-statement filing.

    The `client` fixture serves the two-statement filing at the start of
    review, which is the right subject for the source room and the wrong one
    for a screen that only has something to show once mappings are approved.
    """

    from apps.api.app.api.main import create_app
    from apps.api.app.persistence.json_store import JsonDocumentRepository

    root = tmp_path / "reviewed"
    JsonDocumentRepository(root).save(three_statements)
    with browser_client(create_app(root)) as test_client:
        test_client.document_id = three_statements.document.id
        yield test_client


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
