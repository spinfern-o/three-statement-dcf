"""Section 22's test plan, mapped onto the tests that cover each clause.

Section 22 lists fifty-one clauses across eight subsections. Items 156 to 162
say to *run* them, and running them means first knowing which of them exist —
so this is the map, and a test asserts every function named here is real.

**A clause with no test says so.** `Coverage.covered` is False and the reason
is written out. That is the whole value of this file: a plan where an uncovered
clause looks the same as a covered one tells a reader that everything is
covered, and the one time that matters is the time it is not.

Two clauses are deliberately not covered and each says why in its own row:
22.1.j's permission checks (2.2.d makes RBAC not applicable — one user, one
role) and all of 22.8's performance targets, which 22.8 itself scopes "to be
measured on documented hardware/data" that no deployment has yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
TEST_DIRS = (ROOT / "tests", ROOT / "apps" / "api" / "tests")


@dataclass(frozen=True)
class Coverage:
    """One Section 22 clause, and what covers it."""

    clause: str
    what: str
    #: Test function names, without their module. Asserted to exist.
    tests: tuple[str, ...] = ()
    #: Set when nothing covers it. Required in that case.
    uncovered_because: str = ""

    def __post_init__(self) -> None:
        if not self.tests and not self.uncovered_because:
            raise ValueError(
                f"{self.clause} names no test and no reason. A clause with "
                "neither reads as covered and is not."
            )

    @property
    def covered(self) -> bool:
        return bool(self.tests)


#: Section 22, clause by clause. The `tests` are named rather than counted: a
#: count goes stale silently and a name fails loudly.
PLAN = (
    # 22.1 Unit tests
    Coverage(
        "22.1.a",
        "Locale-aware number parsing",
        (
            "test_a_confirmed_locale_resolves_it",
            "test_an_ambiguous_number_is_refused_while_the_locale_is_unconfirmed",
        ),
    ),
    Coverage(
        "22.1.b",
        "Parentheses and sign handling",
        (
            "test_a_confirmed_locale_resolves_it",
            "test_unambiguous_numbers_parse_without_a_confirmed_locale",
        ),
    ),
    Coverage(
        "22.1.c",
        "Unit normalization",
        (
            "test_a_bare_number_may_scale_a_currency_and_may_not_be_added_to_one",
            "test_accepting_while_the_scale_is_unconfirmed_is_refused",
        ),
    ),
    Coverage(
        "22.1.d", "Every formula definition", ("test_every_derived_subtotal_has_a_catalogue_row",)
    ),
    Coverage(
        "22.1.e",
        "Rounding boundaries",
        (
            "test_rounding_is_half_even_like_every_other_rounding_here",
            "test_trailing_zeros_survive_the_round_trip",
        ),
    ),
    Coverage(
        "22.1.f",
        "Zero and near-zero tolerance handling",
        (
            "test_step10_undeclared_driver_is_an_error_not_a_zero",
            "test_an_absent_value_is_an_em_dash_and_never_a_zero",
        ),
    ),
    Coverage(
        "22.1.g",
        "WACC/g guard",
        ("test_step31_wacc_must_exceed_terminal_growth", "test_wacc_must_exceed_the_growth_rate"),
    ),
    Coverage(
        "22.1.h",
        "Date/time-fraction calculation",
        (
            "test_the_exact_fraction_counts_real_days",
            "test_the_exact_convention_needs_a_date_to_count_from",
        ),
    ),
    Coverage(
        "22.1.i",
        "Scenario inheritance",
        (
            "test_an_override_keeps_its_lineage",
            "test_a_preview_in_a_child_scenario_starts_from_what_it_inherits",
        ),
    ),
    Coverage(
        "22.1.j",
        "Permission checks",
        (),
        uncovered_because=(
            "2.2.d: one user, one role, so 20.6's RBAC is not applicable "
            "rather than untested. What IS tested is 20.7's authorization "
            "on every read -- see test_security.py -- which is the "
            "requirement that survives a single-user deployment."
        ),
    ),
    # 22.2 Property-based tests
    Coverage(
        "22.2.a",
        "Assets = liabilities + equity for generated models",
        ("test_randomized_identity_sweep",),
    ),
    Coverage("22.2.b", "Cash roll-forward identities hold", ("test_randomized_identity_sweep",)),
    Coverage(
        "22.2.c",
        "Increasing WACC reduces DCF value",
        ("test_the_grid_moves_monotonically_with_both_axes",),
    ),
    Coverage(
        "22.2.d",
        "Increasing terminal growth increases terminal value",
        ("test_the_grid_moves_monotonically_with_both_axes",),
    ),
    Coverage(
        "22.2.e",
        "Unit conversions reverse exactly",
        ("test_a_fractional_factor_inverts_to_the_rate_it_came_from",),
    ),
    # 22.3 Golden extraction tests
    Coverage("22.3.a", "Text-native PDF", ("test_fixture_is_unchanged",)),
    Coverage(
        "22.3.b", "Scanned PDF", ("test_a_scanned_page_names_the_page_rather_than_being_skipped",)
    ),
    Coverage("22.3.c", "Multi-column PDF", ("test_fixture_is_unchanged",)),
    Coverage("22.3.d", "Parenthetical negatives", ("test_a_confirmed_locale_resolves_it",)),
    Coverage(
        "22.3.e",
        "Values in thousands and millions",
        ("test_a_randomized_sweep_across_nine_orders_of_magnitude",),
    ),
    Coverage(
        "22.3.f",
        "Restated prior years",
        (
            "test_the_restated_comparatives_are_what_reach_the_model",
            "test_the_original_figures_in_the_restatement_note_never_become_facts",
            "test_nothing_in_the_extracted_facts_records_that_2024_was_restated",
        ),
    ),
    # 22.4 Integration tests
    Coverage("22.4.a", "Ingestion to verified facts", ("test_step_d_review_every_fact",)),
    Coverage(
        "22.4.b",
        "Mapping to statements",
        (
            "test_step_e_propose_and_approve_the_mappings",
            "test_step_f_the_historical_checks_are_shown_and_pass",
        ),
    ),
    Coverage(
        "22.4.c",
        "Assumptions to forecast",
        (
            "test_step_g_enter_and_approve_every_required_assumption",
            "test_step_h_the_forecast_builds_and_labels_its_estimates",
        ),
    ),
    Coverage("22.4.d", "Forecast to DCF", ("test_step_i_the_dcf_and_its_sensitivity_grid",)),
    Coverage(
        "22.4.e",
        "Release locks the version",
        (
            "test_the_same_model_exported_twice_carries_the_same_version",
            "test_changing_one_assumption_changes_the_version",
        ),
    ),
    Coverage(
        "22.4.f",
        "Export matches released output",
        (
            "test_step_j_all_four_exports_are_served_and_agree",
            "test_the_enterprise_value_on_the_screen_is_the_one_in_the_export",
        ),
    ),
    # 22.5 End-to-end tests
    Coverage("22.5.a", "Create model", ("test_step_c_confirm_metadata",)),
    Coverage("22.5.b", "Upload fixture PDF", ("test_step_c_confirm_metadata",)),
    Coverage("22.5.c", "Confirm metadata", ("test_step_c_confirm_metadata",)),
    Coverage("22.5.d", "Review facts", ("test_step_d_review_every_fact",)),
    Coverage("22.5.e", "Approve mappings", ("test_step_e_propose_and_approve_the_mappings",)),
    Coverage(
        "22.5.f",
        "Resolve historical checks",
        (
            "test_step_f_the_historical_checks_are_shown_and_pass",
            "test_step_f_the_schedules_build_and_reconcile",
        ),
    ),
    Coverage(
        "22.5.g", "Enter assumptions", ("test_step_g_enter_and_approve_every_required_assumption",)
    ),
    Coverage(
        "22.5.h", "Review forecast", ("test_step_h_the_forecast_builds_and_labels_its_estimates",)
    ),
    Coverage(
        "22.5.i", "Review DCF and sensitivity", ("test_step_i_the_dcf_and_its_sensitivity_grid",)
    ),
    Coverage(
        "22.5.j",
        "Release and export",
        (
            "test_step_j_the_release_gate_is_reachable_and_says_what_blocks_it",
            "test_step_j_all_four_exports_are_served_and_agree",
        ),
    ),
    # 22.6 Visual tests
    Coverage(
        "22.6.a", "Desktop at 1440px", ("test_no_screen_scrolls_sideways_at_any_supported_width",)
    ),
    Coverage(
        "22.6.b", "Laptop at 1280px", ("test_no_screen_scrolls_sideways_at_any_supported_width",)
    ),
    Coverage(
        "22.6.c", "Tablet at 768px", ("test_no_screen_scrolls_sideways_at_any_supported_width",)
    ),
    Coverage(
        "22.6.d", "Mobile at 390px", ("test_no_screen_scrolls_sideways_at_any_supported_width",)
    ),
    Coverage(
        "22.6.e",
        "Long company names",
        (
            "test_a_very_long_company_name_does_not_widen_any_screen",
            "test_a_long_company_name_is_not_truncated_into_a_different_name",
        ),
    ),
    Coverage(
        "22.6.f",
        "Negative values",
        ("test_very_large_and_very_negative_figures_stay_inside_their_table",),
    ),
    Coverage(
        "22.6.g",
        "Very large values",
        ("test_very_large_and_very_negative_figures_stay_inside_their_table",),
    ),
    Coverage(
        "22.6.h",
        "Empty and error states",
        (
            "test_an_empty_state_renders_without_overflowing",
            "test_an_error_state_is_announced_and_does_not_overflow",
        ),
    ),
    # 22.7 Accessibility tests
    Coverage(
        "22.7.a",
        "Keyboard-only full workflow",
        (
            "test_a_reviewer_can_confirm_metadata_with_the_keyboard_alone",
            "test_a_reviewer_can_accept_a_fact_with_the_keyboard_alone",
        ),
    ),
    Coverage(
        "22.7.b",
        "Screen-reader labels",
        (
            "test_every_interactive_control_has_an_accessible_name",
            "test_the_action_buttons_resolve_by_role_and_name",
        ),
    ),
    Coverage(
        "22.7.c",
        "Focus order",
        (
            "test_focus_moves_down_the_page_not_around_it",
            "test_the_navigation_comes_before_the_content_and_the_skip_link_before_both",
        ),
    ),
    Coverage(
        "22.7.d",
        "Colour contrast",
        ("test_text_meets_wcag_aa", "test_interactive_boundaries_meet_non_text_contrast"),
    ),
    Coverage(
        "22.7.e",
        "Zoom to 200%",
        (
            "test_the_layout_does_not_scroll_sideways_at_200_percent",
            "test_the_forecast_screen_does_not_scroll_sideways_at_200_percent",
        ),
    ),
    Coverage(
        "22.7.f",
        "Reduced motion",
        ("test_reduced_motion_is_honoured", "test_the_only_animation_stops_under_reduced_motion"),
    ),
    # 22.8 Performance targets
    Coverage(
        "22.8.a",
        "Dashboard load <= 2.5s at p75",
        (),
        uncovered_because=(
            "22.8 scopes its own targets 'to be measured on documented "
            "hardware/data', and no deployment exists to document. A "
            "figure measured on CI runners would be a number about GitHub, "
            "presented as a number about this application."
        ),
    ),
    Coverage(
        "22.8.b",
        "Recalculation <= 500ms",
        (),
        uncovered_because=(
            "As 22.8.a: 22.8 scopes its own targets to documented hardware and "
            "data, and no deployment exists to document. A recalculation time "
            "measured on a CI runner is a number about that runner."
        ),
    ),
    Coverage(
        "22.8.c",
        "Table interaction >= 50 FPS",
        (),
        uncovered_because=(
            "As 22.8.a, and 'where measurable' is doing work in the "
            "clause: this application ships no JavaScript, so scrolling a "
            "table is the browser's own frame rate and nothing here "
            "influences it."
        ),
    ),
    Coverage(
        "22.8.d",
        "Long extraction jobs run asynchronously",
        (),
        uncovered_because=(
            "Ingestion is a CLI (10.x makes it a pipeline with a custody "
            "trail), so there is no request to keep open and nothing to "
            "cancel. A queue worker is 3.2.f's and belongs with a "
            "deployment that needs one."
        ),
    ),
)


def _test_names() -> set[str]:
    """Every test function name in the repository."""
    found: set[str] = set()
    pattern = re.compile(r"^def (test_[A-Za-z0-9_]+)", re.MULTILINE)
    for directory in TEST_DIRS:
        for path in directory.rglob("test_*.py"):
            found.update(pattern.findall(path.read_text()))
    return found


def missing_tests() -> tuple[tuple[str, str], ...]:
    """Every `(clause, test)` this plan names that does not exist.

    The check that keeps the map honest. A renamed test silently turns a
    covered clause into a claim, and this is what turns that back into a
    failure.
    """
    names = _test_names()
    return tuple((row.clause, test) for row in PLAN for test in row.tests if test not in names)


def uncovered() -> tuple[Coverage, ...]:
    return tuple(row for row in PLAN if not row.covered)


def summary() -> dict[str, int]:
    return {
        "clauses": len(PLAN),
        "covered": sum(1 for row in PLAN if row.covered),
        "uncovered": len(uncovered()),
    }
