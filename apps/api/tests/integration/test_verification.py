"""Phase 16, items 166-168: the plan, the report, and the claims it may make.

The report runs the suites, so these do not run it end to end -- that would
mean running the whole suite from inside the suite. They test the parts a
generated report gets wrong: a plan naming a test that does not exist, a
claim made without the evidence for it, and a verdict that reads green when
something was skipped.
"""

from __future__ import annotations

import pytest

from apps.api.app.verification import plan, report

# --- the plan ---------------------------------------------------------------


def test_every_test_the_plan_names_exists():
    """The check that keeps the map honest.

    A renamed test silently turns a covered clause into a claim. Twenty-seven
    of these names were wrong when this file was first written -- guessed from
    what a test *should* be called rather than read from the tree -- and this
    is what found them.
    """
    missing = plan.missing_tests()
    assert missing == (), f"{len(missing)} named test(s) do not exist: {missing}"


def test_every_section_22_clause_is_present():
    """Fifty-five clauses across eight subsections, none skipped."""
    clauses = {row.clause for row in plan.PLAN}
    for subsection, letters in (
        ("22.1", "abcdefghij"),
        ("22.2", "abcde"),
        ("22.3", "abcdef"),
        ("22.4", "abcdef"),
        ("22.5", "abcdefghij"),
        ("22.6", "abcdefgh"),
        ("22.7", "abcdef"),
        ("22.8", "abcd"),
    ):
        for letter in letters:
            assert f"{subsection}.{letter}" in clauses, f"{subsection}.{letter}"


def test_a_clause_with_no_test_and_no_reason_is_refused():
    """The failure this file exists to prevent: a row that reads as covered."""
    with pytest.raises(ValueError, match="reads as covered"):
        plan.Coverage("22.9.a", "something nobody tested")


def test_every_uncovered_clause_states_why():
    uncovered = plan.uncovered()
    assert uncovered, "this assertion proved nothing; the plan claims full coverage"
    for row in uncovered:
        assert len(row.uncovered_because) > 60, (
            f"{row.clause}'s reason is too short to be a reason: {row.uncovered_because!r}"
        )


def test_the_uncovered_clauses_are_the_ones_expected():
    """Named, so a clause quietly losing its test is a failure rather than a
    number going up by one."""
    assert {row.clause for row in plan.uncovered()} == {
        "22.1.j",  # RBAC: not applicable under 2.2.d, not untested
        "22.3.f",  # restated prior years: no fixture carries both readings
        "22.8.a",
        "22.8.b",
        "22.8.c",
        "22.8.d",  # no documented hardware
    }


# --- the report's own claims ------------------------------------------------


def test_a_failed_benchmark_makes_the_accuracy_contract_unproven():
    """4.20, enforced on the report rather than trusted to it.

    The contract may be reported as passing only when the benchmark suite
    actually passed. A report that carried the claim forward from the last
    green run would be making exactly the claim 4.20 exists to prevent.
    """
    failed = report.Outcome("164", "benchmark", report.FAIL, "3 failed")
    contract = report.accuracy_contract(failed)
    assert contract.status == report.FAIL
    assert "UNPROVEN" in contract.evidence
    assert "4.20" in contract.evidence


def test_a_skipped_benchmark_also_makes_it_unproven():
    """NOT RUN is not PASS. Rule 1.14, applied to the report itself."""
    skipped = report.Outcome("164", "benchmark", report.NOT_RUN, "skipped")
    assert report.accuracy_contract(skipped).status == report.FAIL


def test_a_passing_benchmark_lets_the_contract_pass_and_names_the_count():
    passed = report.Outcome("164", "benchmark", report.PASS, "12 passed")
    contract = report.accuracy_contract(passed)
    assert contract.status == report.PASS
    assert "4.16" in contract.evidence and "4.15" in contract.evidence


def test_a_skipped_gate_blocks_the_verdict():
    """A release report whose worst row is NOT RUN is one somebody reads as
    green. Rule 1.14 again: a check that did not run has not passed."""
    built = report.Report(
        generated_at="2026-09-18T00:00:00+00:00",
        outcomes=[
            report.Outcome("156", "Unit tests", report.PASS, "all passed"),
            report.Outcome("161", "Accessibility", report.NOT_RUN, "no browser"),
        ],
    )
    assert not built.may_release
    assert "NOT READY" in built.markdown()


def test_a_failing_gate_blocks_the_verdict_and_is_named_at_the_top():
    built = report.Report(
        generated_at="2026-09-18T00:00:00+00:00",
        outcomes=[report.Outcome("156", "Unit tests", report.FAIL, "3 failed")],
    )
    assert not built.may_release
    body = built.markdown()
    assert "NOT READY" in body
    assert "3 failed" in body.split("## Evidence")[0], (
        "a failure is only in the table, not in the verdict a reader reads first"
    )


def test_a_ready_verdict_does_not_read_as_permission_to_deploy():
    """Phase 17 item 169 is explicit, and a report saying READY is the thing
    most likely to be quoted as though it were not."""
    built = report.Report(
        generated_at="2026-09-18T00:00:00+00:00",
        outcomes=[report.Outcome("156", "Unit tests", report.PASS, "all passed")],
    )
    body = built.markdown()
    assert "READY" in body
    assert "item 169" in body
    assert "not a recommendation to deploy" in body


def test_the_report_names_the_dataset_and_the_formulas_4_20_requires():
    built = report.Report(
        generated_at="2026-09-18T00:00:00+00:00",
        outcomes=[report.Outcome("164", "benchmark", report.PASS, "12 passed")],
    )
    body = built.markdown()
    assert "**Dataset:**" in body
    assert "build_fixtures.py" in body
    # One row per 4.16 output, and the two that are not compared say so.
    assert body.count("| yes |") >= 20
    assert "| **no** |" in body


def test_the_report_carries_the_section_25_disclaimer():
    from model.disclaimer import DISCLAIMER

    built = report.Report(
        generated_at="2026-09-18T00:00:00+00:00",
        outcomes=[report.Outcome("156", "Unit tests", report.PASS, "ok")],
    )
    assert DISCLAIMER in built.markdown()


def test_every_item_phase_16_names_has_a_row_to_produce():
    """Items 154-168. A report that silently covers fourteen of fifteen is the
    failure this catches."""
    produced = (
        {item for item, _what, _cmd in report.CHECKS}
        | {item for item, _what, _sel in report.SUITES}
        | {"165", "167"}
    )
    # 168 is the report itself; 169 is Phase 17.
    assert produced == {
        "154",
        "155",
        "156",
        "157",
        "158",
        "159",
        "160",
        "161",
        "162",
        "163",
        "164",
        "165",
        "166",
        "167",
    }


def test_the_committed_report_is_not_stale(tmp_path):
    """The report in docs/ is a generated artefact, and a generated artefact
    committed once and never regenerated is worse than none: it reads as
    current. This asserts it describes the suite that exists now.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    body = (root / "docs" / "release-readiness.md").read_text()

    # Every clause in the plan is in the committed table.
    for row in plan.PLAN:
        assert f"| {row.clause} |" in body, f"{row.clause} is missing from the report"

    # And the verdict it carries is a verdict, not a placeholder.
    assert re.search(r"## Verdict: (READY|NOT READY)", body)


def test_the_last_meaningful_line_skips_a_dependency_warning():
    """A DeprecationWarning is usually the final line of a subprocess's
    output, and reporting it as the evidence for a passing gate makes the row
    read like a failure."""
    output = (
        "33 routes, health 200, static and tokens served\n"
        "/usr/lib/testclient.py:1: StarletteDeprecationWarning: deprecated\n"
        "  from starlette.testclient import TestClient as TestClient  # noqa"
    )
    assert report._last_meaningful_line(output).startswith("33 routes")


# --- Phase 17: the deployment preconditions ---------------------------------


def test_every_security_header_is_on_every_response(client):
    """Item 175, and 20.12's XSS half. This application was sending none."""
    from apps.api.app.security.headers import HEADERS

    for path in ("/health", "/", f"/documents/{client.document_id}/statements"):
        response = client.get(path)
        for name in HEADERS:
            assert name in response.headers, f"{path} is missing {name}"


def test_the_headers_reach_the_guards_own_refusals(client):
    """A route-level hook would miss these, which is why it is middleware.

    A 403 from the CSRF check is a response like any other, and it is one an
    attacker's page provoked -- so it is exactly the response that needs the
    frame and referrer policies on it.
    """
    refused = client.post(
        f"/documents/{client.document_id}/metadata",
        data={"page": "1", "reason": "x", "csrf_token": "wrong"},
    )
    assert refused.status_code == 403
    assert "Content-Security-Policy" in refused.headers
    assert refused.headers["X-Frame-Options"] == "DENY"


def test_the_policy_forbids_script_because_there_is_none():
    """`script-src 'none'` is not a compromise here -- it is simply true.

    This application ships no JavaScript, so the strongest possible value is
    also the correct one, and a policy that merely restricted script SOURCES
    would be throwing that away.
    """
    from apps.api.app.security.headers import CSP_DIRECTIVES

    directives = dict(CSP_DIRECTIVES)
    assert directives["script-src"] == "'none'"
    assert directives["default-src"] == "'none'"
    assert directives["connect-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert directives["base-uri"] == "'none'"


def test_no_template_contains_a_script_tag():
    """The claim `script-src 'none'` rests on, asserted rather than assumed.

    If a template ever gains a `<script>`, the policy above silently stops it
    working -- and the symptom is a broken page rather than a policy error, so
    this fails first and says why.
    """
    from pathlib import Path

    templates = Path(__file__).resolve().parents[2] / "app" / "api" / "templates"
    for path in sorted(templates.glob("*.html")):
        body = path.read_text().lower()
        assert "<script" not in body, (
            f"{path.name} has a <script> tag, which `script-src 'none'` blocks. "
            f"Either remove it or change the policy deliberately."
        )


def test_inline_style_attributes_are_the_only_exception_taken():
    """`style-src-attr 'unsafe-inline'` and not `style-src 'unsafe-inline'`.

    The narrower form permits `style=` attributes and nothing else -- no inline
    `<style>` blocks. That is the difference between "inline styles are
    allowed" and "these three are".
    """
    from apps.api.app.security.headers import CSP_DIRECTIVES

    directives = dict(CSP_DIRECTIVES)
    assert directives["style-src"] == "'self'"
    assert directives["style-src-attr"] == "'unsafe-inline'"


def test_the_stylesheet_may_be_cached_and_a_filing_may_not(client):
    """20.1: no shared cache holds a filing. A stylesheet is not one."""
    assert client.get("/static/app.css").headers["Cache-Control"] == "public, max-age=3600"
    assert client.get("/").headers["Cache-Control"] == "no-store"


def test_a_route_that_set_its_own_cache_control_keeps_it(client):
    """The page-image route sets `private, max-age=3600` deliberately: an
    image is expensive to render and belongs to one reader."""
    response = client.get(f"/documents/{client.document_id}/pages/2/image.png")
    assert response.headers["Cache-Control"] == "private, max-age=3600"


def test_hsts_is_sent_only_over_https():
    """Off HTTPS a browser ignores it, so sending it would be a header that
    looks like a control and is not."""
    from apps.api.app.security.headers import for_request

    assert "Strict-Transport-Security" in for_request("/", is_https=True)
    assert "Strict-Transport-Security" not in for_request("/", is_https=False)


# --- item 180: the build identity -------------------------------------------


def test_health_records_the_three_versions_item_180_requires(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["commit"] and body["schema_version"] and body["formula_version"]


def test_health_carries_no_filing_detail(client):
    """It is public, so a company name or a document id here would be a filing
    detail served without a credential."""
    body = client.get("/health").json()
    assert set(body) == {
        "status",
        "commit",
        "commit_source",
        "schema_version",
        "formula_version",
        "started_at",
        "identified",
    }


def test_an_unidentifiable_commit_says_so_rather_than_guessing():
    """Item 180 says RECORD the commit. A recorded value that is wrong is
    worse than one that is absent, because the point is to trust it."""
    from apps.api.app.verification.build_info import UNKNOWN, BuildInfo

    unknown = BuildInfo(
        commit=UNKNOWN,
        commit_source="no .git directory",
        schema_version="1.0.0",
        formula_version="abc",
        started_at="now",
    )
    assert not unknown.is_identified
    assert "cannot identify its own commit" in unknown.describe()


def test_a_dirty_tree_is_marked_because_it_is_not_the_tested_version():
    """Item 178: deploy the exact tested version. A dirty tree is not it."""
    from apps.api.app.verification.build_info import collect

    info = collect()
    # Whatever the state here, the marker's meaning is what is asserted.
    assert info.commit.endswith("-dirty") == ("uncommitted" in info.commit_source)


# --- items 172, 179: the smoke tests ----------------------------------------


def test_the_smoke_test_checks_every_deployment_property_that_matters():
    """It never authenticates, which is what makes it safe against production
    -- and "does an unauthenticated request get refused" is the most important
    thing to check after a deployment."""
    import inspect

    from apps.api.app.verification import smoke

    source = inspect.getsource(smoke)
    for expected in ("2.2.c", "175", "180", "20.1", "20.2", "178"):
        assert expected in source, f"the smoke test checks nothing for {expected}"
    # Nothing in it signs in.
    assert "/login" in source
    assert "password" not in source.lower().replace("never sends a credential", "")


def test_the_smoke_headers_are_case_insensitive():
    """The bug this found on its first run: uvicorn sends header names
    lowercase, and looking them up in title case reported every header absent
    on a deployment that was sending all of them -- which is the worst kind of
    wrong for a smoke test, because somebody then "fixes" the deployment."""
    from apps.api.app.verification.smoke import _Headers

    headers = _Headers([("content-security-policy", "default-src 'none'")])
    assert "Content-Security-Policy" in headers
    assert headers.get("CONTENT-SECURITY-POLICY") == "default-src 'none'"


# --- criterion 24.22: evidence for every acceptance criterion ---------------
#
# F-37: the report recorded evidence for items 154-168 and for Section 22's
# clauses, and said nothing about Section 24 at all -- while printing READY.
# Section 24 is the section that defines what release means.


def test_section_24_has_all_twenty_two_criteria():
    from apps.api.app.verification.acceptance import CRITERIA

    assert len(CRITERIA) == 22
    assert [c.clause for c in CRITERIA] == [f"24.{n}" for n in range(1, 23)]


def test_every_criterion_is_evidenced():
    """24.22's own requirement, as a check rather than as a section heading."""
    from apps.api.app.verification.acceptance import every_criterion_is_evidenced, unevidenced

    assert every_criterion_is_evidenced(), [c.clause for c in unevidenced()]


def test_every_test_the_table_names_exists():
    """The failure that plan.py's first draft had twenty-seven of.

    A name written from what a test ought to be called turns a criterion into
    a claim. This is what turns it back into a failure.
    """
    from apps.api.app.verification.acceptance import missing_tests

    assert missing_tests() == ()


def test_a_criterion_with_no_evidence_and_no_reason_is_refused():
    from apps.api.app.verification.acceptance import AcceptanceError, Criterion

    with pytest.raises(AcceptanceError) as raised:
        Criterion(clause="24.99", what="something nobody checked")
    assert "indistinguishable from an evidenced one" in str(raised.value)


def test_a_criterion_declared_inapplicable_must_say_why():
    from apps.api.app.verification.acceptance import AcceptanceError, Criterion

    with pytest.raises(AcceptanceError):
        Criterion(clause="24.99", what="x", tests=("test_x",), not_applicable=True)


def test_a_criterion_takes_the_status_of_the_gate_it_defers_to():
    """The point of deriving rather than asserting.

    24.16 defers to item 161, the accessibility suite. If that suite failed,
    24.16 is not a green row with a red gate above it.
    """
    from apps.api.app.verification.acceptance import assess

    failed = dict.fromkeys(("157", "158", "160", "162", "163", "164", "166", "167"), "PASS")
    failed["161"] = "FAIL"
    by_clause = {a.criterion.clause: a for a in assess(failed)}
    assert by_clause["24.16"].status == "FAIL"
    assert "161" in by_clause["24.16"].blocking
    assert by_clause["24.15"].status == "PASS"


def test_a_criterion_whose_gate_did_not_run_is_not_a_pass():
    """Rule 1.14 on the table most likely to be read as a summary."""
    from apps.api.app.verification.acceptance import assess

    by_clause = {a.criterion.clause: a for a in assess({})}
    for clause in ("24.5", "24.8", "24.13", "24.16", "24.19", "24.20"):
        assert by_clause[clause].status == "NOT RUN", clause
    # A criterion evidenced only by tests or a document has no gate to miss.
    assert by_clause["24.2"].status == "PASS"
    assert by_clause["24.22"].status == "PASS"


def test_the_criteria_that_defer_to_a_gate_name_one_the_report_produces():
    """A gate reference that matches no row reads NOT RUN forever.

    `documentation_claims` emits its rows under item 167 and criterion 24.22
    directly rather than from a table, so they are named here alongside the
    two tables. This test caught a genuine dangling reference when it was
    written -- 24.21 defers to 167, which is in neither SUITES nor CHECKS.
    """
    from apps.api.app.verification.acceptance import gates_named
    from apps.api.app.verification.report import CHECKS, SUITES

    produced = {item for item, *_ in SUITES} | {item for item, *_ in CHECKS} | {"167", "24.22"}
    assert set(gates_named()) <= produced, set(gates_named()) - produced


def test_a_failing_row_is_not_masked_by_a_later_row_with_the_same_item():
    """Seven rows share item 167, and a plain dict keeps the last one.

    That is the wrong one precisely when it matters. 24.21 defers to 167, so
    a failing 167 row followed by a passing one must not leave 24.21 green.
    """
    from apps.api.app.verification.report import Outcome, Report

    one = Report(generated_at="now")
    one.outcomes = [
        Outcome("167", "a claim that went stale", "FAIL", "stale"),
        Outcome("167", "a claim that held", "PASS", "fine"),
    ]
    assert one._worst_status_per_item()["167"] == "FAIL"

    from apps.api.app.verification.acceptance import assess

    by_clause = {a.criterion.clause: a for a in assess(one._worst_status_per_item())}
    assert by_clause["24.21"].status == "FAIL"


def test_the_report_carries_the_section_24_table():
    from apps.api.app.verification.report import Report

    text = Report(generated_at="now").markdown()
    assert "## Section 24, criterion by criterion" in text
    for n in range(1, 23):
        assert f"| 24.{n} |" in text


def test_the_section_24_table_reports_not_run_when_no_gate_ran():
    """The empty report is the honest one, and it must not read green."""
    from apps.api.app.verification.report import Report

    text = Report(generated_at="now").markdown()
    assert "**NOT RUN**" in text


def test_ci_checks_the_section_24_table_for_drift():
    """The table is only worth having if it cannot go stale quietly.

    CI's drift check filtered `| 22.` rows only, so a criterion could have
    named a renamed test and the committed report would have kept the old
    name. It now covers `| 24.` too.
    """
    from pathlib import Path

    workflow = Path("/".join(__file__.split("/")[:-4]) + "/../.github/workflows/tests.yml")
    text = workflow.resolve().read_text()
    assert 'line.startswith("| 22.")' in text
    assert 'line.startswith("| 24.")' in text


def test_only_the_result_column_of_the_section_24_table_depends_on_the_run():
    """Which is why CI masks it rather than excluding the rows.

    `--fast` does not run the accessibility or visual suites, so 24.15 and
    24.16 legitimately read NOT RUN there and PASS in the committed full run.
    Everything else in those rows -- the clause, the requirement, the evidence
    each names -- must be identical, because that is the part that goes stale.
    """
    import re

    def masked(text):
        return [
            re.sub(r"\*\*(PASS|FAIL|NOT RUN|UNEVIDENCED)\*\*", "**-**", line)
            for line in text.splitlines()
            if line.startswith("| 24.")
        ]

    gates = [str(n) for n in range(154, 168)] + ["24.22"]
    full = report.Report(generated_at="a")
    full.outcomes = [report.Outcome(g, "x", "PASS", "e") for g in gates]
    fast = report.Report(generated_at="b")
    fast.outcomes = [
        report.Outcome(g, "x", "NOT RUN" if g in ("161", "162") else "PASS", "e") for g in gates
    ]

    assert masked(full.markdown()) == masked(fast.markdown())
    # And the masking is doing work rather than passing trivially.
    assert "**NOT RUN**" in fast.markdown()
    assert "**NOT RUN**" not in full.markdown()
