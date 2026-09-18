# Release-readiness report

Required by [`website-build-spec.md`](website-build-spec.md) Phase 16 item 168. **Generated, not written** — every row below is the result of running something, and the command is printed beside it so a reader can run it again.

Generated at: `2026-09-18T08:15:35+00:00`

## Verdict: READY

Every gate below passed and none was skipped.

This is a statement about the gates, not a recommendation to deploy. Phase 17 item 169 is explicit: do not deploy until the target, the access level and the data policy are confirmed.

## Evidence, item by item

| Item | What | Result | Evidence | Seconds |
|---|---|---|---|---|
| 154 | Formatting | **PASS** | 208 files already formatted | 0.0 |
| 154 | Formatting and linting | **PASS** | All checks passed! | 0.0 |
| 155 | Strict type checks | **PASS** | Success: no issues found in 141 source files | 0.2 |
| 156 | Unit tests | **PASS** | 595 passed in 0.59s | 0.9 |
| 157 | Property-based tests | **PASS** | 10 passed in 0.17s | 0.4 |
| 158 | Golden extraction tests | **PASS** | 46 passed in 14.35s | 14.7 |
| 159 | Integration tests | **PASS** | 689 passed, 2 warnings in 140.23s (0:02:20) | 140.7 |
| 160 | End-to-end tests | **PASS** | 24 passed, 2 warnings in 4.91s | 5.3 |
| 161 | Accessibility tests | **PASS** | 15 passed, 76 deselected in 7.63s | 8.1 |
| 162 | Visual regression tests | **PASS** | 72 passed, 19 deselected in 16.07s | 16.5 |
| 163 | Production build | **PASS** | 33 routes, health 200, static and tokens served | 0.8 |
| 164 | Independent arithmetic benchmark | **PASS** | 12 passed, 24 deselected in 0.87s | 1.2 |
| 165 | Section 4 accuracy contract | **PASS** | 20 of 22 outputs 4.16 names are compared against an implementation sharing no helper with the engine (4.15), on the dataset named below, and every comparison asserts EXACT equality rather than a toler | 1.2 |
| 166 | No source PDF or secret in Git | **PASS** | No source PDF and no secret value in the tree (259 tracked file(s) checked). 20.4 holds. | 0.1 |
| 167 | 21.1's sixteen export tabs are all built | **PASS** | 16 tabs | 0.0 |
| 167 | Every Section 22 clause is either covered or says why not | **PASS** | 55 clauses, 49 covered, 6 with a stated reason | 0.0 |
| 167 | Every test the Section 22 plan names exists | **PASS** | every named test resolves | 0.0 |
| 167 | README's phase range is stated | **PASS** | README says phases 2-16 of 17 | 0.0 |
| 167 | README's test count matches the suite | **PASS** | README says 1452, pytest collects 1452 | 0.0 |
| 167 | Section 17's thirty checks are all in the registry | **PASS** | 30 checks registered | 0.0 |
| 167 | The forced/proposed severity split agrees across the documents | **PASS** | registry: 5 forced, 25 proposed; validation-policy.md and decision-ledger.md agree | 0.0 |
| 24.22 | Every Section 24 criterion has recorded evidence | **PASS** | 22 criteria, 22 evidenced | 0.0 |
| 24.22 | Every test the Section 24 table names exists | **PASS** | every named test resolves | 0.0 |

## Section 22, clause by clause

49 of 55 clauses are covered by a named test. The rest are listed below with the reason, because a plan where an uncovered clause looks like a covered one tells a reader that everything is covered.

| Clause | What | Covered by |
|---|---|---|
| 22.1.a | Locale-aware number parsing | `test_a_confirmed_locale_resolves_it`, `test_an_ambiguous_number_is_refused_while_the_locale_is_unconfirmed` |
| 22.1.b | Parentheses and sign handling | `test_a_confirmed_locale_resolves_it`, `test_unambiguous_numbers_parse_without_a_confirmed_locale` |
| 22.1.c | Unit normalization | `test_a_bare_number_may_scale_a_currency_and_may_not_be_added_to_one`, `test_accepting_while_the_scale_is_unconfirmed_is_refused` |
| 22.1.d | Every formula definition | `test_every_derived_subtotal_has_a_catalogue_row` |
| 22.1.e | Rounding boundaries | `test_rounding_is_half_even_like_every_other_rounding_here`, `test_trailing_zeros_survive_the_round_trip` |
| 22.1.f | Zero and near-zero tolerance handling | `test_step10_undeclared_driver_is_an_error_not_a_zero`, `test_an_absent_value_is_an_em_dash_and_never_a_zero` |
| 22.1.g | WACC/g guard | `test_step31_wacc_must_exceed_terminal_growth`, `test_wacc_must_exceed_the_growth_rate` |
| 22.1.h | Date/time-fraction calculation | `test_the_exact_fraction_counts_real_days`, `test_the_exact_convention_needs_a_date_to_count_from` |
| 22.1.i | Scenario inheritance | `test_an_override_keeps_its_lineage`, `test_a_preview_in_a_child_scenario_starts_from_what_it_inherits` |
| 22.1.j | Permission checks | — |
| 22.2.a | Assets = liabilities + equity for generated models | `test_randomized_identity_sweep` |
| 22.2.b | Cash roll-forward identities hold | `test_randomized_identity_sweep` |
| 22.2.c | Increasing WACC reduces DCF value | `test_the_grid_moves_monotonically_with_both_axes` |
| 22.2.d | Increasing terminal growth increases terminal value | `test_the_grid_moves_monotonically_with_both_axes` |
| 22.2.e | Unit conversions reverse exactly | `test_a_fractional_factor_inverts_to_the_rate_it_came_from` |
| 22.3.a | Text-native PDF | `test_fixture_is_unchanged` |
| 22.3.b | Scanned PDF | `test_a_scanned_page_names_the_page_rather_than_being_skipped` |
| 22.3.c | Multi-column PDF | `test_fixture_is_unchanged` |
| 22.3.d | Parenthetical negatives | `test_a_confirmed_locale_resolves_it` |
| 22.3.e | Values in thousands and millions | `test_a_randomized_sweep_across_nine_orders_of_magnitude` |
| 22.3.f | Restated prior years | — |
| 22.4.a | Ingestion to verified facts | `test_step_d_review_every_fact` |
| 22.4.b | Mapping to statements | `test_step_e_propose_and_approve_the_mappings`, `test_step_f_the_historical_checks_are_shown_and_pass` |
| 22.4.c | Assumptions to forecast | `test_step_g_enter_and_approve_every_required_assumption`, `test_step_h_the_forecast_builds_and_labels_its_estimates` |
| 22.4.d | Forecast to DCF | `test_step_i_the_dcf_and_its_sensitivity_grid` |
| 22.4.e | Release locks the version | `test_the_same_model_exported_twice_carries_the_same_version`, `test_changing_one_assumption_changes_the_version` |
| 22.4.f | Export matches released output | `test_step_j_all_four_exports_are_served_and_agree`, `test_the_enterprise_value_on_the_screen_is_the_one_in_the_export` |
| 22.5.a | Create model | `test_step_c_confirm_metadata` |
| 22.5.b | Upload fixture PDF | `test_step_c_confirm_metadata` |
| 22.5.c | Confirm metadata | `test_step_c_confirm_metadata` |
| 22.5.d | Review facts | `test_step_d_review_every_fact` |
| 22.5.e | Approve mappings | `test_step_e_propose_and_approve_the_mappings` |
| 22.5.f | Resolve historical checks | `test_step_f_the_historical_checks_are_shown_and_pass`, `test_step_f_the_schedules_build_and_reconcile` |
| 22.5.g | Enter assumptions | `test_step_g_enter_and_approve_every_required_assumption` |
| 22.5.h | Review forecast | `test_step_h_the_forecast_builds_and_labels_its_estimates` |
| 22.5.i | Review DCF and sensitivity | `test_step_i_the_dcf_and_its_sensitivity_grid` |
| 22.5.j | Release and export | `test_step_j_the_release_gate_is_reachable_and_says_what_blocks_it`, `test_step_j_all_four_exports_are_served_and_agree` |
| 22.6.a | Desktop at 1440px | `test_no_screen_scrolls_sideways_at_any_supported_width` |
| 22.6.b | Laptop at 1280px | `test_no_screen_scrolls_sideways_at_any_supported_width` |
| 22.6.c | Tablet at 768px | `test_no_screen_scrolls_sideways_at_any_supported_width` |
| 22.6.d | Mobile at 390px | `test_no_screen_scrolls_sideways_at_any_supported_width` |
| 22.6.e | Long company names | `test_a_very_long_company_name_does_not_widen_any_screen`, `test_a_long_company_name_is_not_truncated_into_a_different_name` |
| 22.6.f | Negative values | `test_very_large_and_very_negative_figures_stay_inside_their_table` |
| 22.6.g | Very large values | `test_very_large_and_very_negative_figures_stay_inside_their_table` |
| 22.6.h | Empty and error states | `test_an_empty_state_renders_without_overflowing`, `test_an_error_state_is_announced_and_does_not_overflow` |
| 22.7.a | Keyboard-only full workflow | `test_a_reviewer_can_confirm_metadata_with_the_keyboard_alone`, `test_a_reviewer_can_accept_a_fact_with_the_keyboard_alone` |
| 22.7.b | Screen-reader labels | `test_every_interactive_control_has_an_accessible_name`, `test_the_action_buttons_resolve_by_role_and_name` |
| 22.7.c | Focus order | `test_focus_moves_down_the_page_not_around_it`, `test_the_navigation_comes_before_the_content_and_the_skip_link_before_both` |
| 22.7.d | Colour contrast | `test_text_meets_wcag_aa`, `test_interactive_boundaries_meet_non_text_contrast` |
| 22.7.e | Zoom to 200% | `test_the_layout_does_not_scroll_sideways_at_200_percent`, `test_the_forecast_screen_does_not_scroll_sideways_at_200_percent` |
| 22.7.f | Reduced motion | `test_reduced_motion_is_honoured`, `test_the_only_animation_stops_under_reduced_motion` |
| 22.8.a | Dashboard load <= 2.5s at p75 | — |
| 22.8.b | Recalculation <= 500ms | — |
| 22.8.c | Table interaction >= 50 FPS | — |
| 22.8.d | Long extraction jobs run asynchronously | — |

### Clauses with no test, and why

**22.1.j — Permission checks**

2.2.d: one user, one role, so 20.6's RBAC is not applicable rather than untested. What IS tested is 20.7's authorization on every read -- see test_security.py -- which is the requirement that survives a single-user deployment.

**22.3.f — Restated prior years**

2.3.a fixes one document per model version, so a restatement arrives as a SECOND document rather than as two readings inside one. 10.3's duplicate detection and the linked-duplicate path are tested; a single PDF carrying both an original and a restated prior year is a fixture nobody has built, and it is the honest gap in this row.

**22.8.a — Dashboard load <= 2.5s at p75**

22.8 scopes its own targets 'to be measured on documented hardware/data', and no deployment exists to document. A figure measured on CI runners would be a number about GitHub, presented as a number about this application.

**22.8.b — Recalculation <= 500ms**

As 22.8.a: 22.8 scopes its own targets to documented hardware and data, and no deployment exists to document. A recalculation time measured on a CI runner is a number about that runner.

**22.8.c — Table interaction >= 50 FPS**

As 22.8.a, and 'where measurable' is doing work in the clause: this application ships no JavaScript, so scrolling a table is the browser's own frame rate and nothing here influences it.

**22.8.d — Long extraction jobs run asynchronously**

Ingestion is a CLI (10.x makes it a pipeline with a custody trail), so there is no request to keep open and nothing to cancel. A queue worker is 3.2.f's and belongs with a deployment that needs one.


## Section 24, criterion by criterion

22 of 22 acceptance criteria are clear. Criterion 24.22 asks that this report record evidence for every criterion, so this table is that record.

A criterion that defers to a gate above takes **that gate's result** rather than asserting its own, so a criterion cannot read PASS while the gate under it is red. A criterion whose gate is absent from this run reads NOT RUN, never PASS.

| Criterion | What Section 24 requires | Result | Evidence |
|---|---|---|---|
| 24.1 | A user can upload a valid company PDF | **PASS** | item 160, `test_step_c_confirm_metadata` |
| 24.2 | The original PDF is preserved and hashed | **PASS** | `test_item_38_the_uploaded_pdf_is_unchanged`, `test_the_hash_is_of_the_bytes_as_received`, `test_a_hash_collision_path_is_refused_not_overwritten` |
| 24.3 | Every extracted value links to a page and location | **PASS** | `test_every_cell_carries_a_page_and_the_companys_own_wording`, `test_a_reported_line_traces_back_to_the_page_it_was_printed_on`, `test_a_filing_cited_without_a_page_is_not_a_citation` |
| 24.4 | Ambiguous metadata and values require review | **PASS** | `test_metadata_starts_unconfirmed`, `test_an_ambiguous_number_is_refused_while_the_locale_is_unconfirmed`, `test_accepting_while_the_scale_is_unconfirmed_is_refused`, `test_no_fact_starts_verified` |
| 24.5 | Historical statements reconcile or show explicit unresolved errors | **PASS** | item 158, `test_every_subtotal_reconciles_on_a_correctly_mapped_filing`, `test_the_balance_check_fails_rather_than_plugging`, `test_step_f_the_historical_checks_are_shown_and_pass` |
| 24.6 | Supporting schedules link to the statements | **PASS** | `test_step_f_the_schedules_build_and_reconcile`, `test_the_change_in_working_capital_reconciles_to_the_cash_flow`, `test_interest_is_linked_to_the_debt_schedule`, `test_every_section_13_schedule_is_present_or_explained` |
| 24.7 | Every forecast assumption is visible, sourced, dated, and owned | **PASS** | `test_step10_assumption_requires_source`, `test_a_record_with_no_recorded_owner_is_refused`, `test_step_g_enter_and_approve_every_required_assumption`, `test_market_data_without_an_observation_date_is_not_reproducible` |
| 24.8 | Forecast statements integrate and balance | **PASS** | item 157, `test_balance_sheet_balances_every_forecast_year`, `test_randomized_identity_sweep`, `test_a_broken_balance_sheet_fails_rather_than_being_plugged` |
| 24.9 | FCFF comes from the forecast model | **PASS** | `test_fcff_is_read_back_out_of_the_model`, `test_fcff_formula` |
| 24.10 | WACC and terminal assumptions are sourced | **PASS** | `test_step10_assumption_requires_source`, `test_capm_and_wacc`, `test_step31_wacc_must_exceed_terminal_growth` |
| 24.11 | DCF outputs reproduce from the stored model version | **PASS** | `test_the_same_model_exported_twice_carries_the_same_version`, `test_the_same_inputs_over_the_same_formulas_hash_the_same`, `test_changing_one_assumption_changes_the_version`, `test_the_export_produces_files_the_engine_loads` |
| 24.12 | All critical outputs have source/formula lineage | **PASS** | `test_every_cell_in_the_model_is_traceable`, `test_a_derived_line_traces_to_its_formula_not_to_a_page`, `test_an_absent_line_has_no_lineage_and_says_so` |
| 24.13 | Independent arithmetic checks satisfy Section 4 | **PASS** | item 164, `test_the_two_implementations_agree_on_the_golden_filing`, `test_the_two_implementations_agree_on_extreme_inputs` |
| 24.14 | The site never claims forecast accuracy of 0.0001% | **PASS** | `test_the_benchmark_panel_does_not_claim_a_result_it_did_not_see`, `test_a_failed_benchmark_makes_the_accuracy_contract_unproven`, `test_the_report_refuses_to_claim_the_suite_passed`, `test_the_disclaimer_is_on_every_page` |
| 24.15 | The dashboard works at desktop, tablet, and mobile widths | **PASS** | item 162, `test_no_screen_scrolls_sideways_at_any_supported_width`, `test_the_navigation_becomes_a_rail_on_tablet`, `test_the_navigation_moves_below_the_content_on_mobile` |
| 24.16 | Keyboard and automated accessibility checks pass WCAG 2.2 AA targets | **PASS** | item 161, `test_text_meets_wcag_aa`, `test_interactive_boundaries_meet_non_text_contrast`, `test_a_reviewer_can_accept_a_fact_with_the_keyboard_alone` |
| 24.17 | Exports match website outputs | **PASS** | `test_every_historical_figure_in_the_export_is_on_the_statements_page`, `test_every_dcf_figure_in_the_export_is_on_the_valuation_page`, `test_the_enterprise_value_on_the_screen_is_the_one_in_the_export`, `test_the_four_formats_agree_with_each_other` |
| 24.18 | Unauthorized users cannot access another model | **PASS** | `test_a_document_belonging_to_somebody_else_is_a_404_not_a_403`, `test_the_owner_is_read_from_the_record_not_from_the_request`, `test_an_unauthenticated_page_request_goes_to_the_login` |
| 24.19 | Secrets and private PDFs are absent from version control and logs | **PASS** | item 166, `test_no_source_pdf_and_no_secret_is_committed`, `test_the_scan_catches_a_committed_secret`, `test_a_failed_login_is_logged_and_the_password_is_not`, `test_every_redaction_pattern_is_exercised_by_a_test` |
| 24.20 | CI and production build pass from a clean checkout | **PASS** | item 163 |
| 24.21 | README and user guide contain exact start, test, review, export, and recovery instructions | **PASS** | item 167, [`README.md`](README.md) |
| 24.22 | A release-readiness report records evidence for every criterion | **PASS** | [`docs/release-readiness.md`](docs/release-readiness.md) |

### What the evidence does and does not establish

**24.1 — A user can upload a valid company PDF**

22.5.a and 22.5.b are the end-to-end suite's module fixture: it ingests `forecastable.pdf` through `ingest_pdf.py` **as a subprocess**, so the path under test is the upload path a person uses and not the library behind it. Every `test_step_*` below depends on that fixture, so any of them failing is also this criterion failing.

**24.2 — The original PDF is preserved and hashed**

Rule 1.12. The hash is taken of the bytes as received rather than of the stored copy, because hashing what was written proves the write, not the receipt.

**24.9 — FCFF comes from the forecast model**

The distinction the criterion is drawing is that FCFF is *read out of* the built forecast rather than recomputed beside it from the same assumptions. A second computation that agrees proves the arithmetic; only reading it back proves the figure on screen is the model's.

**24.11 — DCF outputs reproduce from the stored model version**

Reproduction is proved in two halves, because one without the other is worth little. The version is a **digest of what the model contains**, so the same model digests the same and a changed assumption digests differently (21.7); and the exported files load back into the engine, so the stored version is sufficient to re-run from rather than merely to label with.

**24.13 — Independent arithmetic checks satisfy Section 4**

The gate is item 164, and the 4.20 section below is the other half: the clause requires the dataset and the formulas be named, not merely that a suite went green.

**24.14 — The site never claims forecast accuracy of 0.0001%**

This is the one criterion phrased as a prohibition, and the tests are shaped accordingly: the claim is **absent** from every screen, and the two places that may state a benchmark result report UNPROVEN unless they observed the suite pass. 4.20 is about arithmetic reproduction, never about forecast accuracy.

**24.17 — Exports match website outputs**

21.8 compares at the same model version and the same display precision. The comparison runs figure by figure rather than on a spot check, in both directions: every figure in the export is on the screen it came from.

**24.18 — Unauthorized users cannot access another model**

Under decision 2.2.b there is one user, so this can never fail today. It is built and tested with a second owner anyway: the alternative is authorization that is a comment saying it would not matter, and the day it starts to matter is not the day to find out reads were never checked.

**24.20 — CI and production build pass from a clean checkout**

The gate is item 163, run here. **The 'clean checkout' half is CI's**, not this report's: this report runs in a working tree that may be dirty, and `/health` says `-dirty` when it is (item 178). What proves the clean-checkout claim is the GitHub Actions run on the commit, which clones fresh on four Python versions. A report cannot certify the environment it is running in.

**24.21 — README and user guide contain exact start, test, review, export, and recovery instructions**

Item 167's checks verify the claims in `README.md` that a program can check -- the test count, the phase range -- and `docs/deployment.md` carries the operational commands, each one run at least once. What is **not** mechanically checked is whether the instructions are *exact* in the sense of a reader following them successfully on a clean machine; that is a human reading, and it belongs to item 177's approval rather than to a green row here.

**24.22 — A release-readiness report records evidence for every criterion**

Satisfied by the section this table is in, which is a self-reference and so worth stating plainly rather than asserting: the criterion asks that evidence be *recorded*, and `every_criterion_is_evidenced()` is the test that the recording has no blank rows. It cannot and does not assert that the evidence is sufficient -- that is what the other twenty-one rows are for, and what a human approving item 177 is reading.


## The dataset and the formulas 4.20 requires be identified

4.20 permits the 0.0001% claim only once the benchmark suite passes **and** the report names the exact dataset and formulas tested. The suite's result is the item 164 row above; this is the other half.

**Dataset:** the committed golden fixtures — `apps/api/tests/fixtures/*.pdf`, each pinned by SHA-256 in `test_fixtures.py` and generated by `build_fixtures.py`; and `tests/fixtures/` for the engine. Plus 6 extreme-input cases and a randomized sweep across nine orders of magnitude.

**Formulas, one row per 4.16 output:**

| Output | Compared | Where | How |
|---|---|---|---|
| revenue | yes | `tests/test_precision.py::test_independent_recomputation` | recomputed from the YAML with its own Decimal loader |
| gross profit | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine's tree evaluation against Ledger._try_derive |
| EBITDA | **no** | — | the chart has no `ebitda` line (F-17), so there is nothing to compare |
| EBIT | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| EBT (pretax income) | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| taxes | yes | `tests/test_precision.py::test_independent_recomputation` | rate x pretax, recomputed longhand |
| net income | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| total assets | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| total liabilities | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| equity | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| CFO | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| CFI | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| CFF | yes | `apps/api/tests/integration/test_formula_catalog.py` | the formula engine against the engine's derivation table |
| ending cash | yes | `tests/test_precision.py::test_independent_recomputation` | the cash roll-forward, recomputed longhand |
| NOPAT | yes | `apps/api/tests/integration/test_valuation.py::test_the_benchmark_agrees_with_the_engine_exactly` | EBIT x (1 - tax), written out with built-in operators |
| change in NWC | yes | `apps/api/tests/integration/test_valuation.py::test_the_benchmark_agrees_with_the_engine_exactly` | working capital read off the ledgers and differenced |
| FCFF | yes | `apps/api/tests/integration/test_valuation.py::test_the_benchmark_agrees_with_the_engine_exactly` | NOPAT + D&A - CapEx - change in NWC, longhand |
| discount factors | yes | `apps/api/tests/integration/test_valuation.py::test_the_benchmark_agrees_with_the_engine_exactly` | 1 / (1 + WACC)^t, with `**` rather than the engine's helper |
| terminal value | yes | `apps/api/tests/integration/test_valuation.py::test_the_benchmark_agrees_with_the_engine_exactly` | terminal FCFF / (WACC - g), longhand |
| enterprise value | yes | `apps/api/tests/integration/test_valuation.py::test_the_benchmark_agrees_with_the_engine_exactly` | the sum of present values plus the discounted terminal value |
| equity value | yes | `apps/api/tests/integration/test_valuation.py::test_the_benchmark_agrees_with_the_engine_exactly` | enterprise value plus cash less debt |
| implied value per share | **no** | — | no verified diluted share count exists, so 16.20 withholds the figure and there is nothing to compare |

---

This model is an analytical tool, not investment, accounting, tax, or legal advice. Historical information may contain extraction or classification errors until reviewed. Forecasts and valuations depend on assumptions and are inherently uncertain. Verify all source data, assumptions, and outputs before relying on them.
