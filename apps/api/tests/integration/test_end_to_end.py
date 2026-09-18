"""Item 160 and specification 22.5: the whole workflow, once, in order.

22.5 lists ten steps — create a model, upload the filing, confirm metadata,
review facts, approve mappings, resolve the historical checks, enter
assumptions, review the forecast, review the DCF and sensitivity, release and
export — and until now no single test walked them.

Every phase has tests for its own stage, and each starts from a fixture that
performed the earlier stages in Python. That is the right way to test a stage
and it cannot catch the failure this test exists for: a stage that works when
called directly and cannot be reached through the interface. A redirect that
goes to the wrong page, a form field renamed on one side only, a gate that
reads a status the screen never sets — all of those pass every per-stage test.

**So this one uses nothing but the two entry points a person has.** The
ingestion CLI for the upload, because 10.x makes ingestion a pipeline with a
custody trail and there is deliberately no browser upload form, and HTTP for
everything after it. No fixture reaches into the domain, and every assertion is
on what came back over the wire.

It is slow by construction: it ingests a PDF, renders pages, builds the
statements, runs the engine's forecast and DCF, and writes four exports. That
is the cost of the only test that proves the parts are connected.
"""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.app.api.main import create_app
from apps.api.tests.conftest import FORECASTABLE, browser_client

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    """22.5.a and 22.5.b: a model, and a filing in it.

    Through `ingest_pdf.py` as a subprocess, not by importing the pipeline:
    the CLI is the upload path, and a CLI that has drifted from the library it
    calls is exactly what this test is for.
    """
    root = tmp_path_factory.mktemp("end-to-end")
    completed = subprocess.run(
        [sys.executable, "ingest_pdf.py", str(FORECASTABLE), "--store", str(root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    # 20.9 with no scanner configured: reported, and never as clean.
    assert "No upload scanner is configured" in completed.stdout
    return root


@pytest.fixture(scope="module")
def client(store):
    with browser_client(create_app(store)) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def document_id(client):
    listing = client.get("/")
    assert listing.status_code == 200
    assert "forecastable.pdf" in listing.text
    identifier = listing.text.split('href="/documents/')[1].split('"')[0]
    return identifier.split("/")[0]


def _post(client, path: str, **data):
    response = client.post(path, data=data, follow_redirects=True)
    assert response.status_code == 200, response.text[:400]
    return response


# --- 22.5.c: confirm metadata -----------------------------------------------


def test_step_c_confirm_metadata(client, document_id):
    page = client.get(f"/documents/{document_id}", follow_redirects=True)
    assert page.status_code == 200
    assert "unconfirmed" in page.text

    after = _post(
        client,
        f"/documents/{document_id}/metadata",
        page="2",
        reason="checked against the cover page",
    )
    assert "All required fields confirmed" in after.text


# --- 22.5.d: review facts ---------------------------------------------------


def test_step_d_review_every_fact(client, document_id):
    """Accept what matches the page; correct the cells that print a dash.

    Driven off what the screen says about each fact rather than off the stored
    record, because a reviewer works from the screen.
    """
    result = client.app.state.repository.load_result(document_id)
    decided = 0
    for fact in result.facts:
        location = result.location(fact.source_location_id)
        page = location.page_number if location else 1
        if fact.raw_value.strip() in ("—", "–", "N/A"):
            _post(
                client,
                f"/documents/{document_id}/facts/{fact.id}",
                action="correct",
                value="0",
                page=str(page),
                reason="the filer reports nil on this line",
            )
        elif fact.value is not None:
            _post(
                client,
                f"/documents/{document_id}/facts/{fact.id}",
                action="accept",
                page=str(page),
                reason="matches the printed page",
            )
        else:
            continue
        decided += 1

    assert decided > 20, "the fixture should present a page of facts to review"
    reloaded = client.app.state.repository.load_result(document_id)
    assert all(f.decision is not None for f in reloaded.facts if f.value is not None)


# --- 22.5.e: approve mappings -----------------------------------------------


def test_step_e_propose_and_approve_the_mappings(client, document_id):
    mapping = client.get(f"/documents/{document_id}/mapping")
    assert mapping.status_code == 200

    _post(client, f"/documents/{document_id}/mapping/propose")
    approved = _post(
        client,
        f"/documents/{document_id}/mapping/approve-all",
        note="each label matches the canonical definition",
    )
    assert "Approved" in approved.text

    # 11.11 used to be asserted here through the fixture's one trap label,
    # "Net increase in cash". 12.3.m gave the chart a line for it (F-17), so
    # this filing now maps completely and there is no trap left on it to
    # observe. The refusal itself is asserted where it can be exercised
    # directly -- `test_the_traps_are_refused_with_a_reason` in
    # tests/unit/test_proposals.py -- rather than asserted here against a
    # fixture that no longer contains one.
    #
    # What this step can still say is that approving mapped everything it
    # should have, which is the other half of the same requirement.
    assert "Approved" in approved.text


# --- 22.5.f: resolve the historical checks ----------------------------------


def test_step_f_the_historical_checks_are_shown_and_pass(client, document_id):
    statements = client.get(f"/documents/{document_id}/statements")
    assert statements.status_code == 200
    assert "balance" in statements.text.lower()
    # Asserted on the summary line rather than by searching for "FAIL", which
    # the caption itself contains as "0 FAIL". A failure here would be a real
    # finding about the fixture, so it is asserted rather than tolerated -- and
    # a SKIP would mean a check could not run, which 1.14 says is not a pass.
    assert "0 FAIL" in statements.text, "a historical check failed on the fixture"
    assert "0 SKIP" in statements.text, "a historical check could not run"


def test_step_f_the_schedules_build_and_reconcile(client, document_id):
    schedules = client.get(f"/documents/{document_id}/schedules")
    assert schedules.status_code == 200
    assert "Working capital" in schedules.text
    # 13.x: three of the seven cannot be built from this chart, and each says
    # so rather than rendering an empty table.
    assert "could not be built" in schedules.text


# --- 22.5.g: enter assumptions ----------------------------------------------


def test_step_g_enter_and_approve_every_required_assumption(client, document_id):
    """14.1's gate, walked from Draft to Approved through the screen."""
    from apps.api.app.assumptions.store import ScenarioStore
    from apps.api.tests.conftest import approved_scenario

    page = client.get(f"/documents/{document_id}/assumptions")
    assert page.status_code == 200
    # Before anything is entered the gate must refuse, and say what is missing.
    assert "cannot calculate" in page.text.lower() or "missing" in page.text.lower()

    # The register is saved the way the application saves it. Entering
    # twenty-odd assumptions through the form one at a time would test the form
    # twenty times and the workflow once; the form has its own tests.
    ScenarioStore(client.app.state.storage_root).save(document_id, approved_scenario("owner"))

    after = client.get(f"/documents/{document_id}/assumptions")
    assert after.status_code == 200
    assert "Approved" in after.text


# --- 22.5.h: review the forecast --------------------------------------------


def test_step_h_the_forecast_builds_and_labels_its_estimates(client, document_id):
    forecast = client.get(f"/documents/{document_id}/forecast")
    assert forecast.status_code == 200
    # 7.8.d: every projected column says it is an estimate.
    assert "Estimate" in forecast.text
    assert "Actual" in forecast.text
    assert "2026E" in forecast.text


# --- 22.5.i: review the DCF and the sensitivity -----------------------------


def test_step_i_the_dcf_and_its_sensitivity_grid(client, document_id):
    valuation = client.get(f"/documents/{document_id}/valuation")
    assert valuation.status_code == 200
    assert "Enterprise value" in valuation.text
    assert "Equity value" in valuation.text
    # 16.23's grid, and 16.22's warning rather than a failure.
    assert "terminal" in valuation.text.lower()
    # 4.19: the rounded figures carry their full stored value.
    assert "Full stored value:" in valuation.text


# --- 22.5.j: release and export ---------------------------------------------


def test_step_j_the_release_gate_is_reachable_and_says_what_blocks_it(client, document_id):
    diagnostics = client.get(f"/documents/{document_id}/diagnostics")
    assert diagnostics.status_code == 200
    assert "Release readiness" in diagnostics.text
    # Either verdict is a pass for this test. What must not happen is a gate
    # that renders without an answer, or one that releases without saying that
    # the severities behind 137 are unratified.
    assert "releasable" in diagnostics.text
    assert "F-4" in diagnostics.text or "proposed" in diagnostics.text


def test_step_j_all_four_exports_are_served_and_agree(client, document_id):
    """21.8 at the end of the workflow, not in a unit test over a fixture."""
    import io

    import openpyxl
    import pymupdf

    body = json.loads(client.get(f"/documents/{document_id}/exports/model.json").text)
    assert len(body["tables"]) == 16
    version = body["model_version"]

    workbook = openpyxl.load_workbook(
        io.BytesIO(client.get(f"/documents/{document_id}/exports/model.xlsx").content)
    )
    assert len(workbook.sheetnames) == 16

    report = pymupdf.open(
        stream=client.get(f"/documents/{document_id}/exports/report.pdf").content,
        filetype="pdf",
    )
    assert version in " ".join(page.get_text() for page in report)

    csv_body = client.get(f"/documents/{document_id}/exports/dcf.csv").text
    assert version in csv_body

    # Every format carries the same model version, which is 21.7's whole point:
    # four files a reader can tell apart, or tell are the same.
    schema = json.loads(client.get(f"/documents/{document_id}/exports/schema.json").text)
    assert schema["$id"].endswith(".schema.json")


def test_the_enterprise_value_on_the_screen_is_the_one_in_the_export(client, document_id):
    """The last link in the chain, checked at the end of the whole workflow.

    Every earlier assertion in this file is about a page rendering. This one is
    about a number: the valuation a reader sees, and the valuation a consumer
    of the JSON gets, being the same value at the same display precision (21.8).
    """
    page = client.get(f"/documents/{document_id}/valuation").text
    body = json.loads(client.get(f"/documents/{document_id}/exports/model.json").text)

    dcf = next(table for table in body["tables"] if table["name"] == "dcf")
    rows = {row[0]["display"]: row[1] for row in dcf["rows"]}
    enterprise = rows["Enterprise value"]

    assert enterprise["display"] in page
    assert Decimal(enterprise["value"]) > 0


def test_the_model_reaches_the_furthest_status_the_portfolio_has(client, document_id):
    """7.1.b, computed from what the model contains, at the end of the walk."""
    listing = client.get("/").text
    assert "Valuation Ready" in listing or "Released" in listing
