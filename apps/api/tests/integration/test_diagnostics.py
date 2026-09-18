"""Items 131-137: the diagnostics panel, the lineage, the log and the gate.

Two properties carry most of the weight here.

**Rule 1.14, everywhere.** A check that could not run is reported as such and
never as a pass, and the release gate treats it exactly as it treats a
failure. The tests assert both, because the tempting shortcut -- counting only
failures -- would let a model release on the strength of checks that never
looked at anything.

**F-4 is visible rather than assumed away.** Section 17 assigns a severity to
none of its thirty checks. The gate blocks on every outstanding one, which is
strictly stricter than item 137 under any assignment the owner might make, and
it says so on the screen.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from apps.api.app.diagnostics.audit import Filters, filter_events
from apps.api.app.diagnostics.benchmark import Report
from apps.api.app.diagnostics.lineage import trace, traceable_lines
from apps.api.app.diagnostics.registry import (
    BY_CLAUSE,
    FORCED,
    PROPOSED,
    REGISTRY,
    Severity,
)
from apps.api.app.diagnostics.release import (
    NOT_ACTIONABLE,
    checklist,
    every_clause_is_on_the_checklist,
    readiness,
)
from apps.api.app.diagnostics.run import evaluate
from apps.api.app.statements.build import build_statements
from apps.api.tests.conftest import approved_scenario
from model.checks import Status


@pytest.fixture(scope="module")
def scenarios():
    return approved_scenario("owner")


@pytest.fixture(scope="module")
def full(forecastable, scenarios):
    """A model taken as far as this system can take one."""
    return evaluate(forecastable, scenarios)


@pytest.fixture(scope="module")
def historical_only(three_statements):
    """A model with statements and no scenario at all."""
    return evaluate(three_statements, None)


# --- item 131: the registry -------------------------------------------------


def test_all_thirty_checks_are_present():
    assert len(REGISTRY) == 30
    assert {c.clause for c in REGISTRY} == {f"17.{n}" for n in range(1, 31)}


def test_the_registry_agrees_with_the_document_it_came_from():
    """Generated from validation-policy.md, so the two cannot drift.

    Regenerated here and compared, because a registry that has quietly
    diverged from the document describing it is worse than either alone.
    """
    policy = (
        pathlib.Path(__file__).resolve().parents[4] / "docs" / "validation-policy.md"
    ).read_text()
    rows = re.findall(r"\| `(VAL-017-\d{3})` \| (17\.\d+) \| (.*?) \| (.*?) \| (.*?) \|\n", policy)
    assert len(rows) == 30

    for code, clause, _compares, severity, _engine in rows:
        check = BY_CLAUSE[clause]
        assert check.code == code
        assert check.forced == ("**" in severity), clause
        expected = re.sub(r"\*\*|\(.*?\)$", "", severity).strip()
        assert check.severity.value == expected, clause


def test_only_five_severities_are_forced_and_each_cites_its_rule():
    """F-4. The other twenty-five are proposals, and saying so is the point."""
    assert len(FORCED) == 5
    assert len(PROPOSED) == 25
    for check in FORCED:
        assert check.forced_by, f"{check.code} is forced and cites nothing"


def test_a_rule_forces_a_severity_only_by_stating_a_consequence():
    """F-26. 17.5 was forced on a word, not on a rule.

    1.14 -- "never allow an unresolved critical validation error to appear as
    PASS" -- presupposes that some checks are critical and never says which.
    Reading 17.5's "critical fact" as that answer is a word in common, not a
    forcing rule, and it put one severity in the settled column on nothing.

    What does force a level is a rule naming a consequence, because the
    consequence is what the level means: 14.1 blocks calculation, 16.16 blocks
    calculation, 16.20 forbids computing the figure, 4.20 blocks the claim.
    """
    assert BY_CLAUSE["17.5"].is_proposal
    assert not BY_CLAUSE["17.5"].forced_by
    assert BY_CLAUSE["17.18"].forced

    # The document's summary table is the list, and it must be the same list:
    # the row-by-row table below it bolded two severities the summary never
    # named, which is how 17.5 got into the settled column in the first place.
    policy = (
        pathlib.Path(__file__).resolve().parents[4] / "docs" / "validation-policy.md"
    ).read_text()
    summary = policy.split("Only five are forced")[1].split("Everything else")[0]
    named = set(re.findall(r"`VAL-017-(\d{3})`", summary))
    assert named == {c.code[-3:] for c in FORCED}


def test_section_17s_four_severities_say_what_they_mean():
    assert [s.value for s in Severity] == ["CRITICAL", "ERROR", "WARNING", "INFO"]
    assert Severity.CRITICAL.blocks_release and Severity.ERROR.blocks_release
    assert not Severity.WARNING.blocks_release and not Severity.INFO.blocks_release
    for severity in Severity:
        assert severity.meaning.strip(), severity


# --- running them -----------------------------------------------------------


def test_every_check_gets_an_answer(full, historical_only):
    for diagnostics in (full, historical_only):
        assert len(diagnostics.outcomes) == 30
        assert {o.check.clause for o in diagnostics.outcomes} == {f"17.{n}" for n in range(1, 31)}


def test_a_check_that_could_not_run_is_never_reported_as_passing(historical_only):
    """Rule 1.14, on the model where most of them cannot run."""
    for outcome in historical_only.outcomes:
        if outcome.status is Status.SKIP:
            assert outcome.detail.strip(), f"{outcome.check.clause} skips with no reason"
    forecast_clauses = {"17.16", "17.17", "17.20", "17.22", "17.24"}
    for clause in forecast_clauses:
        assert historical_only.by_code(BY_CLAUSE[clause].code).status is Status.SKIP


def test_a_skipped_check_names_the_stage_that_stopped_it(historical_only):
    """Twenty unrelated failures from one missing stage is not a diagnosis."""
    outcome = historical_only.by_code(BY_CLAUSE["17.16"].code)
    assert outcome.status is Status.SKIP
    assert outcome.blocked_by, "the skip does not say what blocked it"


def test_the_fully_built_model_passes_the_checks_it_can(full):
    passing = {o.check.clause for o in full.passed}
    for clause in (
        "17.1",
        "17.2",
        "17.3",
        "17.4",
        "17.8",
        "17.9",
        "17.10",
        "17.16",
        "17.17",
        "17.18",
        "17.20",
        "17.22",
        "17.24",
        "17.27",
        "17.29",
        "17.30",
    ):
        assert clause in passing, f"{clause} does not pass on a complete model"


def test_the_failures_on_the_fixture_are_real_findings(full):
    """Not a demonstration: each of these is true of the fixture filing."""
    failures = {o.check.clause: o for o in full.failed}
    # 16.19's bridge lines nobody addressed.
    assert "17.25" in failures and "nobody having addressed" in failures["17.25"].detail


def test_every_label_on_the_fixture_now_maps(full):
    """17.6 used to fail here, and the reason it stopped is the point.

    The fixture's "Net increase in cash" had no canonical code to go to, so
    the proposer refused it and 17.6 reported a label mapped to nothing. 12.3.m
    gave the chart `net_change_in_cash` (F-17), so the line maps, 17.6 passes,
    and 12.4.f's cash roll-forward now has a reported figure to check the three
    subtotals against rather than nothing.

    Asserted as a PASS rather than deleted, because "this check stopped
    failing" is worth keeping a test on: a regression in the chart would put
    the failure back.
    """
    outcome = full.by_code(BY_CLAUSE["17.6"].code)
    assert outcome.status is Status.PASS, outcome.detail


def test_17_12_now_skips_for_a_fact_about_the_filing_not_about_this_system(full):
    """The difference between the two kinds of SKIP, which is the whole point.

    17.12 reported "the chart has no intangibles line (F-17)" for eleven
    phases -- a statement about this system, and a reader who met it went
    looking for a missing feature. The chart now has the line and a separate
    amortization line, so the check runs like 17.11 and 17.13. On this
    fixture, which reports no intangibles, it skips because THIS FILING has no
    opening balance to roll forward from, and a reader who meets that goes
    looking at the balance sheet, where the answer is.
    """
    intangibles = full.by_code(BY_CLAUSE["17.12"].code)
    assert intangibles.status is Status.SKIP
    assert "no period has an opening 'intangibles' balance" in intangibles.detail
    assert "F-17" not in intangibles.detail
    assert "chart has no" not in intangibles.detail


def test_one_clause_reports_that_this_system_cannot_evaluate_it(full):
    """17.21, with the reason rather than a silent skip."""
    iterative = full.by_code(BY_CLAUSE["17.21"].code)
    assert iterative.status is Status.SKIP
    assert "no iterative calculation is configured" in iterative.detail


def test_the_benchmark_check_refuses_to_claim_a_result_it_did_not_see(full):
    """4.20: the claim may only be made once the suite has run and reported."""
    outcome = full.by_code(BY_CLAUSE["17.28"].code)
    assert outcome.status is Status.SKIP
    assert "does not observe its result" in outcome.detail


def test_17_27_actually_looks_at_every_value(full):
    outcome = full.by_code(BY_CLAUSE["17.27"].code)
    assert outcome.status is Status.PASS
    assert "value(s) checked" in outcome.detail
    assert "every value is finite" in outcome.detail


# --- items 136, 137: the gate -----------------------------------------------


def test_the_checklist_covers_every_clause():
    """A check missing from the checklist is a check nobody looked at."""
    assert every_clause_is_on_the_checklist()


def test_the_gate_blocks_on_a_skipped_check_as_well_as_a_failed_one(historical_only):
    """Rule 1.14, at the point it decides whether something ships."""
    verdict = readiness(historical_only)
    assert not verdict.may_release
    skipped_blocking = [o for o in verdict.blocking if o.status is Status.SKIP]
    assert skipped_blocking, "a skipped check must block a release"


def test_the_gate_says_which_rule_it_is_standing_in_for(full):
    verdict = readiness(full)
    assert verdict.severity_is_unratified
    described = verdict.describe()
    assert "assigns none of its thirty checks" in described
    assert "finding F-4" in described
    assert "stricter than 137" in described


def test_the_unevaluable_checks_are_excluded_from_the_verdict(full):
    """Otherwise the gate is permanently red for reasons nobody can act on."""
    verdict = readiness(full)
    assert {o.check.clause for o in verdict.unevaluable} <= NOT_ACTIONABLE
    assert not any(o.check.clause in NOT_ACTIONABLE for o in verdict.blocking)
    assert "cannot be evaluated by this system at all" in verdict.describe()


def test_a_model_with_every_actionable_check_clear_may_release(full, forecastable, scenarios):
    """The gate must be reachable, or it is a wall rather than a gate."""
    from dataclasses import replace

    from apps.api.app.diagnostics.run import Diagnostics

    cleared = Diagnostics(
        tuple(
            replace(o, status=Status.PASS, detail="cleared for this test")
            if o.check.clause not in NOT_ACTIONABLE
            else o
            for o in full.outcomes
        )
    )
    verdict = readiness(cleared)
    assert verdict.may_release
    assert "Every check a reviewer can act on has passed" in verdict.describe()


def test_the_checklist_groups_by_stage_so_a_reader_sees_where_work_stopped(
    historical_only,
):
    stages = {item.stage: item for item in checklist(historical_only)}
    assert stages["Source and mapping"].is_clear
    assert not stages["Forecast"].is_clear
    assert not stages["Valuation"].is_clear


# --- item 132: lineage ------------------------------------------------------


def test_a_reported_line_traces_back_to_the_page_it_was_printed_on(forecastable):
    built = build_statements(forecastable, strict=True)
    walked = trace(forecastable, built, "revenue", "2025A")
    assert walked.is_complete
    stages = [step.stage for step in walked.steps]
    assert stages[:2] == ["value", "origin"]
    assert "fact" in stages and "decision" in stages

    fact_step = next(s for s in walked.steps if s.stage == "fact")
    assert "page" in fact_step.detail
    decision_step = next(s for s in walked.steps if s.stage == "decision")
    assert ":" in decision_step.detail, "the decision carries who and why"


def test_a_derived_line_traces_to_its_formula_not_to_a_page(forecastable):
    built = build_statements(forecastable, strict=True)
    walked = trace(forecastable, built, "total_assets", "2025A")
    assert walked.is_complete
    origin = next(s for s in walked.steps if s.stage == "origin")
    assert origin.label in ("reported", "derived")


def test_an_absent_line_has_no_lineage_and_says_so(forecastable):
    built = build_statements(forecastable, strict=True)
    walked = trace(forecastable, built, "acquisitions", "2025A")
    assert not walked.is_complete
    assert "An absent line has no" in walked.incomplete


def test_every_cell_in_the_model_is_traceable(forecastable):
    """17.30, as a count rather than a claim."""
    built = build_statements(forecastable, strict=True)
    lines = traceable_lines(built)
    assert len(lines) >= 50
    for _statement, code, period in lines:
        assert trace(forecastable, built, code, period).is_complete, f"{code} {period}"


# --- item 134: the audit log ------------------------------------------------


def test_the_log_is_newest_first_and_stable(forecastable):
    log = filter_events(forecastable)
    assert log.total == len(log.events)
    stamps = [(e.at, e.id) for e in log.events]
    assert stamps == sorted(stamps, reverse=True)
    assert [e.id for e in filter_events(forecastable).events] == [e.id for e in log.events]


def test_the_filters_compose(forecastable):
    everything = filter_events(forecastable)
    assert everything.total > 10

    by_actor = filter_events(forecastable, Filters(actor="owner"))
    assert by_actor.events and all(e.actor == "owner" for e in by_actor.events)

    action = everything.events[0].action
    narrowed = filter_events(forecastable, Filters(actor="owner", action=action))
    assert all(e.actor == "owner" and e.action == action for e in narrowed.events)
    assert len(narrowed.events) <= len(by_actor.events)


def test_the_log_says_how_many_it_hid(forecastable):
    """A filtered list with no count is a list a reader cannot trust."""
    log = filter_events(forecastable, Filters(text="a phrase that appears nowhere"))
    assert log.events == ()
    assert log.hidden == log.total > 0


def test_every_entry_carries_the_reason_its_actor_typed(forecastable):
    """10.33. An audit entry with no reason is not an audit entry."""
    for event in filter_events(forecastable).events:
        assert event.detail.strip(), f"{event.id} has no reason"


# --- item 135: the benchmark report -----------------------------------------


def test_the_report_covers_4_16s_list():
    report = Report()
    assert len(report.coverage) == 22
    assert len(report.compared) == 20
    assert {c.output for c in report.not_compared} == {"EBITDA", "implied value per share"}
    for row in report.not_compared:
        assert row.reason, f"{row.output} is not compared and gives no reason"


def test_the_report_refuses_to_claim_the_suite_passed():
    """4.20, which is the whole point of this panel."""
    verdict = Report().verdict
    assert "does not assert that the suite passed" in verdict
    assert "EXACT equality" in verdict
    assert "4.15" in verdict and "4.20" in verdict


def test_every_covered_output_names_where_it_is_compared():
    for row in Report().compared:
        assert row.where.endswith(".py") or "::" in row.where, row.output
        assert len(row.method.split()) >= 4, row.output
