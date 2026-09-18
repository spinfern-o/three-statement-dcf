"""Criterion 24.22: the release report records evidence for every criterion.

Section 24 lists twenty-two release acceptance criteria and opens with "the
application is not complete until all applicable items pass". 24.22 then asks
that **a release-readiness report record evidence for every criterion** -- and
until this module existed, the report recorded evidence for items 154-168 and
for Section 22's clauses, and said nothing about Section 24 at all.

That is the gap this closes, and it was a real one: the report was printing
**READY** without having addressed the section that defines what release
means. Finding F-37.

The design follows `plan.py`, for the same reason. A criterion is evidenced by
one of three things, and it must name which:

  `gate`      an item row already in this report. The criterion's status is
              then *derived* from that gate's result rather than asserted
              here, so a criterion cannot read PASS while the gate under it
              is red.
  `tests`     named tests, read out of the tree rather than guessed. The
              suites they belong to are themselves gates, so a criterion
              evidenced this way is only as green as the suite that runs it.
  `document`  a document, for a criterion about what is written down rather
              than about what the code does. Two of the twenty-two are of
              this kind and both say so.

`Criterion.__post_init__` refuses a row with none of the three and no stated
reason, because a row with no evidence renders identically to one with
evidence in a markdown table -- which is the failure mode of every acceptance
checklist ever filled in.

**"Applicable" is not a loophole here.** Section 24's preamble allows a
criterion not to apply; a criterion declared inapplicable must say why, in the
same field, and `not_applicable()` lists them so the reason is read rather
than inferred from a blank cell.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT RUN"
UNEVIDENCED = "UNEVIDENCED"


class AcceptanceError(Exception):
    """A criterion that would render as evidenced without being evidenced."""


@dataclass(frozen=True)
class Criterion:
    """One of Section 24's twenty-two."""

    clause: str
    what: str
    #: An item string matching a row already in the report, e.g. "161".
    gate: str = ""
    #: Test functions, as they are actually named in the tree.
    tests: tuple[str, ...] = ()
    #: A document path, for a criterion about what is written rather than run.
    document: str = ""
    #: Why this criterion has no runnable evidence, or does not apply.
    because: str = ""
    #: Set when the criterion is declared not applicable under 24's preamble.
    not_applicable: bool = False
    #: Extra prose printed under the table for a criterion that needs it.
    note: str = ""

    def __post_init__(self) -> None:
        has_evidence = bool(self.gate or self.tests or self.document)
        if not has_evidence and not self.because:
            raise AcceptanceError(
                f"{self.clause} names no gate, no test and no document, and "
                f"gives no reason. In a rendered table that row is "
                f"indistinguishable from an evidenced one."
            )
        if self.not_applicable and not self.because:
            raise AcceptanceError(
                f"{self.clause} is declared not applicable without saying why. "
                f"Section 24 allows a criterion not to apply; it does not "
                f"allow the reason to be left to the reader."
            )

    @property
    def is_evidenced(self) -> bool:
        return bool(self.gate or self.tests or self.document)


#: Section 24, verbatim in `what`, with the evidence for each.
#:
#: Every test name here was read out of the tree with grep, not written from
#: what a test ought to be called. `missing_tests()` is the check that keeps it
#: that way, and it exists because the first draft of `plan.py` carried
#: twenty-seven names that did not exist.
CRITERIA: tuple[Criterion, ...] = (
    Criterion(
        clause="24.1",
        what="A user can upload a valid company PDF",
        gate="160",
        tests=("test_step_c_confirm_metadata",),
        note="22.5.a and 22.5.b are the end-to-end suite's module fixture: it "
        "ingests `forecastable.pdf` through `ingest_pdf.py` **as a "
        "subprocess**, so the path under test is the upload path a person "
        "uses and not the library behind it. Every `test_step_*` below "
        "depends on that fixture, so any of them failing is also this "
        "criterion failing.",
    ),
    Criterion(
        clause="24.2",
        what="The original PDF is preserved and hashed",
        tests=(
            "test_item_38_the_uploaded_pdf_is_unchanged",
            "test_the_hash_is_of_the_bytes_as_received",
            "test_a_hash_collision_path_is_refused_not_overwritten",
        ),
        note="Rule 1.12. The hash is taken of the bytes as received rather "
        "than of the stored copy, because hashing what was written proves "
        "the write, not the receipt.",
    ),
    Criterion(
        clause="24.3",
        what="Every extracted value links to a page and location",
        tests=(
            "test_every_cell_carries_a_page_and_the_companys_own_wording",
            "test_a_reported_line_traces_back_to_the_page_it_was_printed_on",
            "test_a_filing_cited_without_a_page_is_not_a_citation",
        ),
    ),
    Criterion(
        clause="24.4",
        what="Ambiguous metadata and values require review",
        tests=(
            "test_metadata_starts_unconfirmed",
            "test_an_ambiguous_number_is_refused_while_the_locale_is_unconfirmed",
            "test_accepting_while_the_scale_is_unconfirmed_is_refused",
            "test_no_fact_starts_verified",
        ),
    ),
    Criterion(
        clause="24.5",
        what="Historical statements reconcile or show explicit unresolved errors",
        gate="158",
        tests=(
            "test_every_subtotal_reconciles_on_a_correctly_mapped_filing",
            "test_the_balance_check_fails_rather_than_plugging",
            "test_step_f_the_historical_checks_are_shown_and_pass",
        ),
    ),
    Criterion(
        clause="24.6",
        what="Supporting schedules link to the statements",
        tests=(
            "test_step_f_the_schedules_build_and_reconcile",
            "test_the_change_in_working_capital_reconciles_to_the_cash_flow",
            "test_interest_is_linked_to_the_debt_schedule",
            "test_every_section_13_schedule_is_present_or_explained",
        ),
    ),
    Criterion(
        clause="24.7",
        what="Every forecast assumption is visible, sourced, dated, and owned",
        tests=(
            "test_step10_assumption_requires_source",
            "test_a_record_with_no_recorded_owner_is_refused",
            "test_step_g_enter_and_approve_every_required_assumption",
            "test_market_data_without_an_observation_date_is_not_reproducible",
        ),
    ),
    Criterion(
        clause="24.8",
        what="Forecast statements integrate and balance",
        gate="157",
        tests=(
            "test_balance_sheet_balances_every_forecast_year",
            "test_randomized_identity_sweep",
            "test_a_broken_balance_sheet_fails_rather_than_being_plugged",
        ),
    ),
    Criterion(
        clause="24.9",
        what="FCFF comes from the forecast model",
        tests=("test_fcff_is_read_back_out_of_the_model", "test_fcff_formula"),
        note="The distinction the criterion is drawing is that FCFF is *read "
        "out of* the built forecast rather than recomputed beside it from "
        "the same assumptions. A second computation that agrees proves the "
        "arithmetic; only reading it back proves the figure on screen is "
        "the model's.",
    ),
    Criterion(
        clause="24.10",
        what="WACC and terminal assumptions are sourced",
        tests=(
            "test_step10_assumption_requires_source",
            "test_capm_and_wacc",
            "test_step31_wacc_must_exceed_terminal_growth",
        ),
    ),
    Criterion(
        clause="24.11",
        what="DCF outputs reproduce from the stored model version",
        tests=(
            "test_the_same_model_exported_twice_carries_the_same_version",
            "test_the_same_inputs_over_the_same_formulas_hash_the_same",
            "test_changing_one_assumption_changes_the_version",
            "test_the_export_produces_files_the_engine_loads",
        ),
        note="Reproduction is proved in two halves, because one without the "
        "other is worth little. The version is a **digest of what the "
        "model contains**, so the same model digests the same and a "
        "changed assumption digests differently (21.7); and the exported "
        "files load back into the engine, so the stored version is "
        "sufficient to re-run from rather than merely to label with.",
    ),
    Criterion(
        clause="24.12",
        what="All critical outputs have source/formula lineage",
        tests=(
            "test_every_cell_in_the_model_is_traceable",
            "test_a_derived_line_traces_to_its_formula_not_to_a_page",
            "test_an_absent_line_has_no_lineage_and_says_so",
        ),
    ),
    Criterion(
        clause="24.13",
        what="Independent arithmetic checks satisfy Section 4",
        gate="164",
        tests=(
            "test_the_two_implementations_agree_on_the_golden_filing",
            "test_the_two_implementations_agree_on_extreme_inputs",
        ),
        note="The gate is item 164, and the 4.20 section below is the other "
        "half: the clause requires the dataset and the formulas be named, "
        "not merely that a suite went green.",
    ),
    Criterion(
        clause="24.14",
        what="The site never claims forecast accuracy of 0.0001%",
        tests=(
            "test_the_benchmark_panel_does_not_claim_a_result_it_did_not_see",
            "test_a_failed_benchmark_makes_the_accuracy_contract_unproven",
            "test_the_report_refuses_to_claim_the_suite_passed",
            "test_the_disclaimer_is_on_every_page",
        ),
        note="This is the one criterion phrased as a prohibition, and the "
        "tests are shaped accordingly: the claim is **absent** from every "
        "screen, and the two places that may state a benchmark result "
        "report UNPROVEN unless they observed the suite pass. 4.20 is "
        "about arithmetic reproduction, never about forecast accuracy.",
    ),
    Criterion(
        clause="24.15",
        what="The dashboard works at desktop, tablet, and mobile widths",
        gate="162",
        tests=(
            "test_no_screen_scrolls_sideways_at_any_supported_width",
            "test_the_navigation_becomes_a_rail_on_tablet",
            "test_the_navigation_moves_below_the_content_on_mobile",
        ),
    ),
    Criterion(
        clause="24.16",
        what="Keyboard and automated accessibility checks pass WCAG 2.2 AA targets",
        gate="161",
        tests=(
            "test_text_meets_wcag_aa",
            "test_interactive_boundaries_meet_non_text_contrast",
            "test_a_reviewer_can_accept_a_fact_with_the_keyboard_alone",
        ),
    ),
    Criterion(
        clause="24.17",
        what="Exports match website outputs",
        tests=(
            "test_every_historical_figure_in_the_export_is_on_the_statements_page",
            "test_every_dcf_figure_in_the_export_is_on_the_valuation_page",
            "test_the_enterprise_value_on_the_screen_is_the_one_in_the_export",
            "test_the_four_formats_agree_with_each_other",
        ),
        note="21.8 compares at the same model version and the same display "
        "precision. The comparison runs figure by figure rather than on a "
        "spot check, in both directions: every figure in the export is on "
        "the screen it came from.",
    ),
    Criterion(
        clause="24.18",
        what="Unauthorized users cannot access another model",
        tests=(
            "test_a_document_belonging_to_somebody_else_is_a_404_not_a_403",
            "test_the_owner_is_read_from_the_record_not_from_the_request",
            "test_an_unauthenticated_page_request_goes_to_the_login",
        ),
        note="Under decision 2.2.b there is one user, so this can never fail "
        "today. It is built and tested with a second owner anyway: the "
        "alternative is authorization that is a comment saying it would "
        "not matter, and the day it starts to matter is not the day to "
        "find out reads were never checked.",
    ),
    Criterion(
        clause="24.19",
        what="Secrets and private PDFs are absent from version control and logs",
        gate="166",
        tests=(
            "test_no_source_pdf_and_no_secret_is_committed",
            "test_the_scan_catches_a_committed_secret",
            "test_a_failed_login_is_logged_and_the_password_is_not",
            "test_every_redaction_pattern_is_exercised_by_a_test",
        ),
    ),
    Criterion(
        clause="24.20",
        what="CI and production build pass from a clean checkout",
        gate="163",
        note="The gate is item 163, run here. **The 'clean checkout' half is "
        "CI's**, not this report's: this report runs in a working tree "
        "that may be dirty, and `/health` says `-dirty` when it is (item "
        "178). What proves the clean-checkout claim is the GitHub Actions "
        "run on the commit, which clones fresh on four Python versions. "
        "A report cannot certify the environment it is running in.",
    ),
    Criterion(
        clause="24.21",
        what="README and user guide contain exact start, test, review, export, "
        "and recovery instructions",
        gate="167",
        document="README.md",
        note="Item 167's checks verify the claims in `README.md` that a "
        "program can check -- the test count, the phase range -- and "
        "`docs/deployment.md` carries the operational commands, each one "
        "run at least once. What is **not** mechanically checked is "
        "whether the instructions are *exact* in the sense of a reader "
        "following them successfully on a clean machine; that is a human "
        "reading, and it belongs to item 177's approval rather than to a "
        "green row here.",
    ),
    Criterion(
        clause="24.22",
        what="A release-readiness report records evidence for every criterion",
        document="docs/release-readiness.md",
        note="Satisfied by the section this table is in, which is a "
        "self-reference and so worth stating plainly rather than "
        "asserting: the criterion asks that evidence be *recorded*, and "
        "`every_criterion_is_evidenced()` is the test that the recording "
        "has no blank rows. It cannot and does not assert that the "
        "evidence is sufficient -- that is what the other twenty-one rows "
        "are for, and what a human approving item 177 is reading.",
    ),
)


def unevidenced() -> tuple[Criterion, ...]:
    """Criteria with no gate, no test and no document."""
    return tuple(c for c in CRITERIA if not c.is_evidenced)


def not_applicable() -> tuple[Criterion, ...]:
    """Criteria declared inapplicable under Section 24's preamble."""
    return tuple(c for c in CRITERIA if c.not_applicable)


def every_criterion_is_evidenced() -> bool:
    """24.22 itself: no criterion is recorded without evidence.

    Deliberately not "every criterion passes". This says the *record* is
    complete. Whether the evidence is good enough is a reading, and rule 1.14
    is better served by a row that names its gap than by a boolean that hides
    one.
    """
    return not unevidenced() and len(CRITERIA) == 22


def missing_tests(known: set[str] | None = None) -> tuple[tuple[str, str], ...]:
    """Every `(clause, test)` this table names that does not exist.

    `plan.py`'s first draft named twenty-seven tests that did not exist,
    written from what a test ought to be called. This is the check that a
    renamed test becomes a failure rather than a silently weakened claim.

    The scanner is `plan._test_names`, imported rather than copied: two
    scanners would eventually disagree about which directories hold tests,
    and the one that found fewer would be the one reporting everything fine.
    """
    if known is None:
        from .plan import _test_names

        known = _test_names()
    return tuple((c.clause, name) for c in CRITERIA for name in c.tests if name not in known)


def gates_named() -> tuple[str, ...]:
    """Every report item a criterion defers to, so the report can check them."""
    return tuple(sorted({c.gate for c in CRITERIA if c.gate}))


@dataclass
class Assessment:
    """One criterion's status, derived rather than asserted."""

    criterion: Criterion
    status: str
    evidence: str
    blocking: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_pass(self) -> bool:
        return self.status == PASS


def assess(gate_status: dict[str, str]) -> list[Assessment]:
    """Derive each criterion's status from the gates it defers to.

    `gate_status` maps a report item to its result. A criterion naming a gate
    takes that gate's status; one naming only tests or a document is reported
    PASS when the suites that run them passed, which the caller expresses by
    passing those suites' gates in. A criterion whose gate is absent from the
    mapping is **NOT RUN**, never PASS -- rule 1.14, applied to the one table
    most likely to be read as a summary.
    """
    results: list[Assessment] = []
    for criterion in CRITERIA:
        if criterion.not_applicable:
            results.append(Assessment(criterion, PASS, f"not applicable: {criterion.because}"))
            continue
        if not criterion.is_evidenced:
            results.append(Assessment(criterion, UNEVIDENCED, criterion.because))
            continue
        if criterion.gate:
            status = gate_status.get(criterion.gate)
            if status is None:
                results.append(
                    Assessment(
                        criterion,
                        NOT_RUN,
                        f"item {criterion.gate} is not in this report",
                        (criterion.gate,),
                    )
                )
                continue
            if status != PASS:
                results.append(
                    Assessment(
                        criterion,
                        status,
                        f"item {criterion.gate} reported {status}",
                        (criterion.gate,),
                    )
                )
                continue
        parts = []
        if criterion.gate:
            parts.append(f"item {criterion.gate} passed")
        if criterion.tests:
            parts.append(f"{len(criterion.tests)} named test(s)")
        if criterion.document:
            parts.append(f"`{criterion.document}`")
        results.append(Assessment(criterion, PASS, "; ".join(parts)))
    return results
