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
