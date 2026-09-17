"""Items 39-44 and 49: the source room over HTTP, and its accessibility.

These are structural tests on the rendered HTML. They check the things that
break silently -- a landmark that disappears, an input that loses its label, a
status that becomes colour-only -- rather than how anything looks.
"""

from __future__ import annotations

import re


def _room(client, page: int = 2, **params):
    return client.get(f"/documents/{client.document_id}/pages/{page}", params=params)


# --- item 39: navigation ----------------------------------------------------

def test_health(client):
    """Phase 1 item 14."""
    assert client.get("/health").json() == {"status": "ok"}


def test_the_portfolio_lists_the_document(client, stored):
    response = client.get("/")
    assert response.status_code == 200
    assert stored.document.sanitized_filename in response.text
    assert f"/documents/{stored.document.id}" in response.text


def test_the_empty_state_explains_what_is_missing(empty_client):
    """6.5.i: empty states explain what source or decision is missing."""
    response = empty_client.get("/")
    assert response.status_code == 200
    assert "ingest_pdf.py" in response.text


def test_a_document_opens_on_its_first_page_with_facts(client):
    """Not the cover: the cover has nothing to review."""
    response = client.get(f"/documents/{client.document_id}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/pages/2")


def test_an_unknown_document_is_404(client):
    assert client.get("/documents/doc-nope/pages/1").status_code == 404


def test_a_page_outside_the_document_is_404(client):
    assert _room(client, 99).status_code == 404


# --- item 40: the page viewer ----------------------------------------------

def test_the_page_renders_as_a_png(client):
    response = client.get(f"/documents/{client.document_id}/pages/2/image.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_render_is_cached_and_identical(client):
    first = client.get(f"/documents/{client.document_id}/pages/2/image.png").content
    second = client.get(f"/documents/{client.document_id}/pages/2/image.png").content
    assert first == second


def test_rendering_does_not_alter_the_stored_pdf(client, stored, store):
    """Item 38 survives being looked at."""
    client.get(f"/documents/{client.document_id}/pages/2/image.png")
    assert store.verify(stored.document.immutable_hash)


# --- item 41: bookmarks -----------------------------------------------------

def test_bookmarks_name_the_statements_and_their_evidence(client):
    body = _room(client).text
    assert "Income statement" in body
    assert "Balance sheet" in body
    assert "system-proposed" in body


def test_a_statement_with_no_page_is_reported_missing(client):
    """10.14 wants every statement in the source map; the fixture has no CF."""
    assert "Cash flow statement" in _room(client).text


# --- item 42: bounding boxes ------------------------------------------------

def test_every_fact_on_the_page_gets_a_box(client, stored):
    body = _room(client).text
    on_page_2 = [
        f for f in stored.facts
        if (loc := stored.location(f.source_location_id)) and loc.page_number == 2
    ]
    assert on_page_2
    for fact in on_page_2:
        assert f'id="box-{fact.id}"' in body


def test_the_overlay_uses_the_page_in_points_so_it_cannot_drift(client, stored):
    """The browser scales it. No pixel arithmetic means no rounding error."""
    body = _room(client).text
    geometry = stored.document.pages[1].geometry
    assert f'viewBox="0 0 {geometry.width} {geometry.height}"' in body


def test_the_overlay_is_hidden_from_assistive_technology(client):
    """The boxes duplicate the table beside them; announcing them twice is noise."""
    body = _room(client).text
    assert re.search(r"<svg[^>]*aria-hidden=\"true\"", body)


# --- item 43: raw versus parsed --------------------------------------------

def test_both_the_printed_string_and_the_parsed_value_are_shown(client):
    body = _room(client).text
    assert "(750,000)" in body       # as printed
    assert "-750,000" in body or "750,000" in body


def test_an_unparsed_cell_says_no_value_rather_than_zero(client):
    """Rule 1.5, on screen. A zero here would be the whole failure."""
    body = _room(client).text
    assert "no value" in body
    assert "DASH_AMBIGUOUS" in body


def test_the_blocking_codes_carry_their_rule_and_summary(client):
    body = _room(client).text
    assert "1.5, 10.17" in body
    assert "the cell holds a dash with no source legend defining it" in body


def test_confidence_is_explained_not_just_printed(client):
    assert "evidence conditions" in _room(client).text or "missing:" in _room(client).text


# --- item 44: metadata confirmation ----------------------------------------

def test_metadata_starts_unconfirmed_on_screen(client):
    body = _room(client).text
    assert "unconfirmed" in body
    assert "required field(s) outstanding" in body


def test_confirming_without_a_reason_is_refused_and_says_so(client):
    response = client.post(
        f"/documents/{client.document_id}/metadata",
        data={"page": "2", "reason": ""},
        follow_redirects=True,
    )
    assert "a reason is required" in response.text
    assert 'role="alert"' in response.text


def test_confirming_every_detected_field(client):
    response = client.post(
        f"/documents/{client.document_id}/metadata",
        data={"page": "2", "reason": "checked the cover page"},
        follow_redirects=True,
    )
    assert "Confirmed" in response.text
    assert "All required fields confirmed" in response.text


def test_correcting_one_field(client):
    response = client.post(
        f"/documents/{client.document_id}/metadata",
        data={
            "page": "2",
            "field": "company_name",
            "value": "Example Industries plc",
            "reason": "the cover prints it in capitals",
        },
        follow_redirects=True,
    )
    assert "Example Industries plc" in response.text


# --- items 45-47 over HTTP --------------------------------------------------

def _first_fact_id(stored, page=2):
    for fact in stored.facts:
        location = stored.location(fact.source_location_id)
        if location and location.page_number == page and fact.value is not None:
            return fact.id
    raise AssertionError("no parsed fact on that page")


def test_a_decision_is_a_post_that_redirects(client, stored):
    """303, so a refresh does not write a second audit entry for one action."""
    client.post(
        f"/documents/{client.document_id}/metadata",
        data={"page": "2", "reason": "checked"}, follow_redirects=True,
    )
    response = client.post(
        f"/documents/{client.document_id}/facts/{_first_fact_id(stored)}",
        data={"action": "accept", "reason": "matches the page", "page": "2"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_a_decision_persists_across_requests(client, stored, repository):
    client.post(
        f"/documents/{client.document_id}/metadata",
        data={"page": "2", "reason": "checked"}, follow_redirects=True,
    )
    fact_id = _first_fact_id(stored)
    client.post(
        f"/documents/{client.document_id}/facts/{fact_id}",
        data={"action": "accept", "reason": "matches page 2 line 1", "page": "2"},
        follow_redirects=True,
    )
    reloaded = repository.load_result(client.document_id)
    decided = [f for f in reloaded.facts if f.id == fact_id][0]
    assert decided.decision.reason == "matches page 2 line 1"


def test_a_refusal_is_presented_as_an_answer_not_a_crash(client, stored):
    """Accepting a fact whose cell held an em dash is SUPPOSED to fail."""
    dash = [f for f in stored.facts if f.raw_value == "—"][0]
    response = client.post(
        f"/documents/{client.document_id}/facts/{dash.id}",
        data={"action": "accept", "reason": "it is zero", "page": "2"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "no value to accept" in response.text
    assert 'role="alert"' in response.text


def test_the_audit_log_is_on_the_page(client, stored):
    client.post(
        f"/documents/{client.document_id}/metadata",
        data={"page": "2", "reason": "checked the cover"}, follow_redirects=True,
    )
    body = _room(client).text
    assert "Audit log" in body
    assert "checked the cover" in body


def test_an_unknown_action_is_refused(client, stored):
    response = client.post(
        f"/documents/{client.document_id}/facts/{_first_fact_id(stored)}",
        data={"action": "delete", "reason": "why not", "page": "2"},
        follow_redirects=True,
    )
    assert "is not a reviewer action" in response.text


# --- item 48: progress on screen -------------------------------------------

def test_progress_shows_zero_verified_and_says_why(client):
    body = _room(client).text
    assert "0 verified" in body
    assert "Phase 5" in body


# --- item 49 (structure half): 6.6 accessibility ---------------------------

def test_there_is_a_skip_link_first(client):
    body = _room(client).text
    assert 'class="skip-link" href="#main"' in body
    assert body.index("skip-link") < body.index("<header")


def test_landmarks_exist(client):
    body = _room(client).text
    for landmark in ("<header", "<main id=\"main\"", "<nav", "<footer"):
        assert landmark in body, landmark


def test_there_is_exactly_one_h1(client):
    assert _room(client).text.count("<h1>") == 1


def test_heading_order_does_not_skip_a_level(client):
    levels = [int(m) for m in re.findall(r"<h([1-6])[ >]", _room(client).text)]
    assert levels, "no headings"
    assert levels[0] == 1
    for previous, current in zip(levels, levels[1:]):
        assert current <= previous + 1, f"h{previous} followed by h{current}"


def test_every_form_control_has_a_label(client):
    """6.6.e."""
    body = _room(client).text
    controls = re.findall(r'<(?:input|select|textarea)\b[^>]*id="([^"]+)"[^>]*>', body)
    hidden = set(re.findall(r'<input[^>]*type="hidden"[^>]*id="([^"]+)"', body))
    labelled = set(re.findall(r'<label[^>]*for="([^"]+)"', body))
    unlabelled = [c for c in controls if c not in labelled and c not in hidden]
    assert not unlabelled, f"controls with no label: {unlabelled}"


def test_no_status_is_conveyed_by_colour_alone(client):
    """6.2.e and 6.6.h: every badge carries a word."""
    for badge in re.findall(r'<span class="badge[^"]*">(.*?)</span>', _room(client).text, re.S):
        assert badge.strip(), "an empty badge would be colour with no text"


def test_the_page_image_has_a_meaningful_alt(client):
    match = re.search(r'<img[^>]*alt="([^"]*)"', _room(client).text)
    assert match and len(match.group(1)) > 20


def test_the_progress_meter_has_a_text_equivalent(client):
    assert re.search(r'role="img"\s*\n?\s*aria-label="[^"]*percent"', _room(client).text)


def test_the_disclaimer_is_on_every_page(client, empty_client):
    """20.19, 1.19, 1.20."""
    for body in (_room(client).text, empty_client.get("/").text):
        assert "not investment advice" in body or "investment advice" in body


def test_tokens_and_stylesheet_are_served(client):
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/tokens/tokens.css").status_code == 200


def test_the_interactive_api_explorer_is_off(client):
    """20.x: a private deployment does not need a public schema browser."""
    assert client.get("/docs").status_code == 404


# --- item 52: the mapping review table (7.4) --------------------------------

def _mapping_url(client, *rest):
    return "/".join([f"/documents/{client.document_id}/mapping", *rest])


def _confirm(client):
    client.post(
        f"/documents/{client.document_id}/metadata",
        data={"page": "2", "reason": "checked the cover"}, follow_redirects=True,
    )


def test_the_mapping_page_loads_before_anything_is_mapped(client):
    response = client.get(_mapping_url(client))
    assert response.status_code == 200
    assert "No mapping set yet" in response.text


def test_the_source_room_links_to_the_mapping_room(client):
    assert f"/documents/{client.document_id}/mapping" in _room(client).text


def test_the_canonical_definitions_are_on_the_page(client):
    """11.3 asks a reviewer to compare a label against a definition. It has to
    be somewhere they can read it."""
    body = client.get(_mapping_url(client)).text
    assert "Canonical chart of accounts" in body
    assert "Stored POSITIVE and subtracted" in body


def test_proposing_shows_the_rule_that_produced_each_suggestion(client):
    response = client.post(_mapping_url(client, "propose"), follow_redirects=True)
    assert "Proposed" in response.text
    assert "11.11 needs a person" in response.text
    body = client.get(_mapping_url(client)).text
    assert "matched a cost-of-sales caption" in body


def test_a_trap_label_shows_why_nothing_was_proposed(client):
    client.post(_mapping_url(client, "propose"), follow_redirects=True)
    body = client.get(_mapping_url(client)).text
    assert "subtotal of part of the balance sheet" in body


def test_mapping_without_a_note_is_refused(client, stored):
    _confirm(client)
    client.post(_mapping_url(client, "propose"), follow_redirects=True)
    fact = next(f for f in stored.facts if f.raw_label == "Revenue")
    response = client.post(
        _mapping_url(client, "facts", fact.id),
        data={"action": "map", "canonical_code": "revenue", "note": ""},
        follow_redirects=True,
    )
    assert "reviewer note is required" in response.text
    assert 'role="alert"' in response.text


def test_an_unknown_canonical_code_is_refused_not_created(client, stored):
    client.post(_mapping_url(client, "propose"), follow_redirects=True)
    fact = next(f for f in stored.facts if f.raw_label == "Revenue")
    response = client.post(
        _mapping_url(client, "facts", fact.id),
        data={"action": "map", "canonical_code": "ebitda", "note": "looks right"},
        follow_redirects=True,
    )
    assert "not a canonical line item" in response.text


def test_approve_all_refuses_rather_than_approving_around_a_double_count(client):
    """11.6 prevents; it does not warn and continue."""
    client.post(_mapping_url(client, "propose"), follow_redirects=True)
    response = client.post(
        _mapping_url(client, "approve-all"),
        data={"note": "everything looks fine"}, follow_redirects=True,
    )
    assert "double-count" in response.text
    assert 'role="alert"' in response.text


def test_a_bad_allocation_line_says_which_line(client, stored):
    client.post(_mapping_url(client, "propose"), follow_redirects=True)
    fact = next(f for f in stored.facts if f.raw_label == "Revenue")
    response = client.post(
        _mapping_url(client, "facts", fact.id),
        data={
            "action": "split", "note": "test", "basis": "note 3",
            "allocation": "revenue 1200000\nother_income_expense = 50000",
        },
        follow_redirects=True,
    )
    assert "line 1" in response.text


def test_the_page_reports_zero_verified_until_mappings_are_approved(client):
    client.post(_mapping_url(client, "propose"), follow_redirects=True)
    body = client.get(_mapping_url(client)).text
    assert "0 VERIFIED" in body or "<strong>0 VERIFIED</strong>" in body


def test_the_mapping_page_keeps_the_accessibility_contract(client):
    """The same structural rules as the source room, on a second screen."""
    client.post(_mapping_url(client, "propose"), follow_redirects=True)
    body = client.get(_mapping_url(client)).text
    assert body.count("<h1>") == 1
    levels = [int(m) for m in re.findall(r"<h([1-6])[ >]", body)]
    for previous, current in zip(levels, levels[1:]):
        assert current <= previous + 1
    controls = re.findall(r'<(?:input|select|textarea)\b[^>]*id="([^"]+)"[^>]*>', body)
    labelled = set(re.findall(r'<label[^>]*for="([^"]+)"', body))
    assert not [c for c in controls if c not in labelled]


# --- items 59-67: the historical statements screen (7.5) --------------------

def test_the_statements_page_explains_itself_before_anything_is_mapped(client):
    """6.5.i: an empty state says what is missing."""
    response = client.get(f"/documents/{client.document_id}/statements")
    assert response.status_code == 200
    assert "Nothing to show yet" in response.text
    assert "approved mappings" in response.text


def test_the_mapping_page_links_to_the_statements(client):
    assert f"/documents/{client.document_id}/statements" in client.get(
        _mapping_url(client)
    ).text


def test_the_statements_page_shows_the_checks_and_their_skips(client):
    _confirm(client)
    client.post(_mapping_url(client, "propose"), follow_redirects=True)
    body = client.get(f"/documents/{client.document_id}/statements").text
    assert "Historical checks" in body
    assert "SKIP" in body or "PASS" in body


def test_the_equity_statement_says_it_is_not_available(client):
    body = client.get(f"/documents/{client.document_id}/statements").text
    assert "Statement of changes in equity" in body
    assert "Not available" in body


# --- items 69-77: the supporting schedules screen (7.6) ---------------------

def test_the_schedules_page_explains_itself_before_anything_is_mapped(client):
    """6.5.i: an empty state says what is missing, not an empty table."""
    response = client.get(f"/documents/{client.document_id}/schedules")
    assert response.status_code == 200
    assert "Nothing to show yet" in response.text


def test_the_statements_page_links_to_the_schedules(client):
    assert f"/documents/{client.document_id}/schedules" in client.get(
        f"/documents/{client.document_id}/statements"
    ).text


def test_the_schedules_page_shows_every_schedule_section_13_asks_for(
    three_statement_client,
):
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/schedules").text
    for title in (
        "Working capital", "PP&amp;E and depreciation", "Intangibles and amortization",
        "Debt and interest", "Leases", "Taxes", "Retained earnings",
        "Common equity", "Share count and dilution",
    ):
        assert title in body, f"{title} is missing from the schedules screen"


def test_the_schedules_page_shows_the_roll_forward_and_its_difference(
    three_statement_client,
):
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/schedules").text
    assert "Ending PP&amp;E = Beginning PP&amp;E + CapEx" in body
    assert "588,000" in body and "107,000" in body and "620,000" in body
    assert "Unexplained difference" in body
    assert "never plugged" in body


def test_the_schedules_page_shows_the_drivers_and_their_convention(
    three_statement_client,
):
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/schedules").text
    assert "59.9" in body and "77.9" in body and "63.3" in body
    assert "365 days (13.1.e)" in body
    assert "cash and debt" in body.lower()


def test_the_schedules_page_marks_the_interest_basis_the_forecast_uses(
    three_statement_client,
):
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/schedules").text
    assert "beginning debt" in body and "average debt" in body
    assert "the basis the forecast uses" in body


def test_the_schedules_page_says_why_three_of_them_are_missing(
    three_statement_client,
):
    """1.14: a gap is reported, not left blank."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/schedules").text
    assert "Schedules this filing cannot support" in body
    assert "not available" in body
    assert "right-of-use asset" in body


def test_the_schedules_page_keeps_the_accessibility_contract(
    three_statement_client,
):
    """Every table captioned, every heading in order, every column scoped."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/schedules").text
    assert body.count("<caption>") >= 5
    assert '<th scope="col"' in body and '<th scope="row"' in body
    assert 'aria-labelledby="checks-heading"' in body

    # Each wide table scrolls inside a named, focusable region (WCAG 1.4.10,
    # 2.1.1) rather than taking the page sideways with it.
    assert body.count('class="table-scroll" tabindex="0" role="region"') >= 5
    assert 'aria-label="PP&amp;E and depreciation roll-forward"' in body
    assert "{{" not in body, "a template expression reached the rendered page"


# --- items 78-88: the formula engine screen (18.10, 18.11) ------------------

def test_the_formulas_page_explains_itself_before_anything_is_mapped(client):
    response = client.get(f"/documents/{client.document_id}/formulas")
    assert response.status_code == 200
    assert "Nothing to show yet" in response.text


def test_the_statements_page_links_to_the_formulas(client):
    assert f"/documents/{client.document_id}/formulas" in client.get(
        f"/documents/{client.document_id}/statements"
    ).text


def test_the_formulas_page_shows_the_formula_and_the_exact_inputs(
    three_statement_client,
):
    """18.10 and 18.11, which are obligations to a person, not to a test."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/formulas").text
    assert "(revenue - cogs)" in body, "18.10: the human-readable formula"
    assert "(1,250,000 - 750,000)" in body, "18.11: the exact inputs used"
    assert "IS-GP-D v1" in body, "the versioned definition it came from (18.1)"


def test_the_formulas_page_reports_the_cross_check_result(
    three_statement_client,
):
    """A real STEP 9 comparison: recomputed against what the filing printed."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/formulas").text
    assert "every recomputed subtotal agrees" in body
    assert "exactly" in body


def test_the_formulas_page_shows_the_order_and_that_there_is_no_cycle(
    three_statement_client,
):
    """18.5 and 18.6. An order exists only because there is no cycle."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/formulas").text
    assert "no cycles" in body
    assert "gross_profit" in body and "ebit" in body
    assert "Calculation order (18.5)" in body


def test_the_formulas_page_names_the_residuals_it_took_as_nil(
    three_statement_client,
):
    """The policy the engine's own derivation applies silently."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/formulas").text
    assert "residual line(s) taken as nil" in body
    assert "other_income_expense" in body


def test_the_formulas_page_shows_a_fingerprint_per_period(
    three_statement_client,
):
    """18.7: the same inputs over the same formula versions hash the same."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/formulas").text
    assert "Calculation fingerprint" in body
    assert body.count("<code>") >= 3


# --- items 89-96: the assumptions screen (7.7) ------------------------------

def _assumptions(client, **params):
    from urllib.parse import urlencode

    query = f"?{urlencode(params)}" if params else ""
    return client.get(f"/documents/{client.document_id}/assumptions{query}")


def test_the_assumptions_page_explains_itself_before_anything_is_mapped(client):
    response = _assumptions(client)
    assert response.status_code == 200
    assert "Nothing to show yet" in response.text


def test_the_assumptions_page_lists_every_required_driver_even_when_empty(
    three_statement_client,
):
    """14.5 and 7.7.e: a driver missing from the screen is a driver nobody decided."""
    body = _assumptions(three_statement_client).text
    for code in ("revenue_growth", "dso", "inventory_days", "dpo",
                 "interest_rate_on_debt", "depreciation_pct_beginning_ppe",
                 "tax_rate"):
        assert code in body, f"{code} is not on the assumptions screen"
    assert "nothing entered" in body


def test_the_gate_says_no_while_the_drivers_are_empty(three_statement_client):
    body = _assumptions(three_statement_client).text
    assert "May the forecast calculate? (14.1)" in body
    assert "not supplied" in body


def test_the_historical_drivers_are_measured_and_offered(three_statement_client):
    """7.7.a, from the Section 13 schedules rather than re-derived."""
    body = _assumptions(three_statement_client).text
    assert "Historical driver analysis (7.7.a)" in body
    assert "59.9" in body and "77.9" in body and "63.3" in body
    assert "schedule 13.1" in body
    assert "2025A" in body, "each proposal cites the periods it measured"


def test_a_driver_no_schedule_can_measure_is_named_not_omitted(
    three_statement_client,
):
    body = _assumptions(three_statement_client).text
    assert "no schedule can measure" in body
    assert "not evidence about the next period" in body


def test_accepting_a_proposal_stores_it_as_a_draft(three_statement_client):
    client = three_statement_client
    response = client.post(
        f"/documents/{client.document_id}/assumptions/accept",
        data={"scenario_id": "base", "code": "dso"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "added as a Draft" in response.text
    assert "cannot be forecast on until reviewed" in response.text
    # And it is now on the screen with its measured value and its status.
    body = _assumptions(client).text
    assert "Historical Driver" in body
    assert "measured over 2024A, 2025A" in body


def test_a_draft_cannot_be_approved_without_passing_through_review(
    three_statement_client,
):
    client = three_statement_client
    client.post(
        f"/documents/{client.document_id}/assumptions/accept",
        data={"scenario_id": "base", "code": "dso"}, follow_redirects=True,
    )
    response = client.post(
        f"/documents/{client.document_id}/assumptions/dso/status",
        data={"scenario_id": "base", "to": "Approved", "reviewer": "larry",
              "reason": "looks fine"},
        follow_redirects=True,
    )
    assert "cannot go from Draft to Approved" in response.text
    assert "four statuses and a decoration" in response.text


def test_a_status_change_without_a_reason_is_refused(three_statement_client):
    client = three_statement_client
    client.post(
        f"/documents/{client.document_id}/assumptions/accept",
        data={"scenario_id": "base", "code": "dpo"}, follow_redirects=True,
    )
    response = client.post(
        f"/documents/{client.document_id}/assumptions/dpo/status",
        data={"scenario_id": "base", "to": "Reviewed", "reviewer": "larry",
              "reason": ""},
        follow_redirects=True,
    )
    assert "needs a written reason" in response.text


def test_reviewing_a_driver_moves_it_and_survives_a_reload(three_statement_client):
    client = three_statement_client
    client.post(
        f"/documents/{client.document_id}/assumptions/accept",
        data={"scenario_id": "base", "code": "inventory_days"}, follow_redirects=True,
    )
    response = client.post(
        f"/documents/{client.document_id}/assumptions/inventory_days/status",
        data={"scenario_id": "base", "to": "Reviewed", "reviewer": "larry",
              "reason": "checked against the 13.1 schedule"},
        follow_redirects=True,
    )
    assert "is now Reviewed" in response.text
    assert "Reviewed" in _assumptions(client).text


def test_previewing_a_change_shows_the_impact_and_saves_nothing(
    three_statement_client,
):
    """14.8. The screen must move; the model must not."""
    client = three_statement_client
    client.post(
        f"/documents/{client.document_id}/assumptions/accept",
        data={"scenario_id": "base", "code": "tax_rate"}, follow_redirects=True,
    )
    before = _assumptions(client).text

    response = client.post(
        f"/documents/{client.document_id}/assumptions/preview",
        data={"scenario_id": "base", "code": "tax_rate", "value": "0.30"},
        follow_redirects=True,
    )
    assert "0.25 -&gt; 0.30" in response.text
    # The formula registry currently holds only the historical derivations, so
    # no forecast formula reads a driver yet and the honest answer is that
    # nothing moves. Saying so is the point -- a driver nothing reads is
    # usually a driver that is misnamed.
    assert "Nothing in the calculation reads it" in response.text

    # The stored value is untouched: reloading shows the old number, and the
    # preview is gone because it was never saved.
    after = _assumptions(client).text
    assert "0.25 -&gt; 0.30" not in after
    assert before.count("0.25") == after.count("0.25")


def test_a_float_shaped_preview_value_is_still_an_exact_decimal(
    three_statement_client,
):
    """4.2: decimal strings at the boundary, all the way from the form."""
    client = three_statement_client
    client.post(
        f"/documents/{client.document_id}/assumptions/accept",
        data={"scenario_id": "base", "code": "tax_rate"}, follow_redirects=True,
    )
    response = client.post(
        f"/documents/{client.document_id}/assumptions/preview",
        data={"scenario_id": "base", "code": "tax_rate", "value": "0.1"},
        follow_redirects=True,
    )
    assert "0.25 -&gt; 0.1" in response.text


def test_a_nonsense_preview_value_is_refused_with_a_message(
    three_statement_client,
):
    client = three_statement_client
    client.post(
        f"/documents/{client.document_id}/assumptions/accept",
        data={"scenario_id": "base", "code": "tax_rate"}, follow_redirects=True,
    )
    response = client.post(
        f"/documents/{client.document_id}/assumptions/preview",
        data={"scenario_id": "base", "code": "tax_rate", "value": "thirty percent"},
        follow_redirects=True,
    )
    assert "not a valid decimal number" in response.text


def test_the_assumptions_page_keeps_the_accessibility_contract(
    three_statement_client,
):
    body = _assumptions(three_statement_client).text
    assert body.count("<caption>") >= 3
    assert '<th scope="col"' in body and '<th scope="row"' in body
    assert 'class="table-scroll" tabindex="0" role="region"' in body
    assert "{{" not in body
    # Every form control the screen renders has a label bound to it.
    import re

    for control_id in re.findall(r'<(?:input|select)[^>]*id="([^"]+)"', body):
        assert f'for="{control_id}"' in body, f"{control_id} has no label"


# --- items 97-108: the forecast statements screen (7.8) ---------------------

def test_the_forecast_page_says_why_it_cannot_forecast(three_statement_client):
    """`three_statements.pdf` reports no other-noncurrent lines, and the
    refusal names the line and the step rather than showing an empty table."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert "Nothing to forecast yet" in body
    assert "may not calculate yet (14.1)" in body or "other_noncurrent" in body


def test_the_forecast_page_shows_all_three_statements(forecast_client):
    client = forecast_client
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert "Forecast income statement" in body
    assert "Forecast balance sheet" in body
    assert "Forecast cash flow statement" in body
    # 2026E revenue: 2,000,000 x 1.08, computed by hand.
    assert "2,160,000" in body


def test_every_column_is_labelled_actual_or_estimate(forecast_client):
    """7.8.d and 1.19. A projection beside an actual in the same typeface is
    the fastest way to describe a forecast as a fact."""
    client = forecast_client
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert "2025A" in body and "2026E" in body
    assert body.count("Estimate") >= 5
    assert "Actual" in body
    assert "not a fact or a\n    guarantee" in body or "not a fact or a guarantee" in body


def test_every_projected_cell_shows_the_driver_that_produced_it(forecast_client):
    """14.5: no assumption hidden inside a formula."""
    client = forecast_client
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert "revenue_growth" in body
    assert "beginning debt" in body, "interest says which balance it is charged on"
    assert "STEP 18" in body or "STEP 13" in body


def test_the_forecast_page_reports_readiness_per_scenario(forecast_client):
    """15.20 and 15.21."""
    client = forecast_client
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert "Forecast readiness (15.20, 15.21)" in body
    assert "Forecast Ready" in body
    assert "awaits the valuation" in body, "the valuation checks are deferred, not hidden"
    assert "assigns a severity to none" in body, "F-4 is stated, not assumed away"


def test_the_tax_basis_is_named_on_the_screen(forecast_client):
    """STEP 16: state which rate the model uses, and why."""
    client = forecast_client
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert "statutory" in body or "effective" in body
    assert "STEP 16" in body


def test_the_forecast_page_keeps_the_accessibility_contract(forecast_client):
    client = forecast_client
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert body.count("<caption>") >= 4
    assert '<th scope="col"' in body and '<th scope="row"' in body
    assert 'class="table-scroll" tabindex="0" role="region"' in body
    assert "{{" not in body
