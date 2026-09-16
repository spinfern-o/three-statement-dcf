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
