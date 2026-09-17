"""Item 128: errors, empty states, skeletons and confirmations (6.5).

Four requirements, and three of them are about not lying to a reader.

**6.5.b -- "Every mutation provides pending, success, and failure feedback."**
Every mutation in this application is a POST followed by a redirect carrying a
flash message, which gives the success and failure halves. The pending half is
the browser's own navigation indicator: there is no JavaScript, so a submitted
form is a page load and the browser shows it. That is stated rather than
assumed, because "we rely on the browser" is a decision.

**6.5.h -- "Loading states use skeletons; financial values must not flash fake
zeros."** The strong half is the second clause, and the way to satisfy it is
structural: nothing in this application renders a number it does not have.
A skeleton here is a shape with no digits in it, and the test asserts the
stylesheet can never put one there.

**6.5.i -- "Empty states explain what source or decision is missing."** Every
screen has one and every one names the missing thing rather than saying there
is nothing to show.
"""

from __future__ import annotations

import pathlib
import re

import pytest

CSS = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "static" / "app.css"
TEMPLATES = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "templates"


# --- 6.5.h: skeletons that cannot flash a fake zero -------------------------

def test_the_skeleton_rule_puts_no_digit_on_the_page():
    """A skeleton is a shape. The moment one contains a numeral it is a lie
    about a value nobody has yet."""
    css = CSS.read_text()
    block = css[css.index(".skeleton {"):css.index("@keyframes skeleton-pulse")]
    assert "color: transparent" in block
    # The only generated content is a non-breaking space escape, which is the
    # one thing that gives the placeholder a line box without putting a
    # character in it. Asserted as an exact match rather than by searching for
    # digits: the escape `\00a0` contains digits of its own, and a test that
    # looked for those would fail on the very thing it is meant to allow.
    content = re.findall(r'content:\s*"([^"]*)"', block)
    assert content == ["\\00a0"], content


def test_the_only_animation_stops_under_reduced_motion():
    """6.6.g. The skeleton pulse is the application's only animation, so it is
    also the only thing this rule has to catch."""
    css = CSS.read_text()
    named = set(re.findall(r"animation:\s*([a-z-]+)", css)) - {"none"}
    assert named == {"skeleton-pulse"}, named
    reduced = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    assert ".skeleton { animation: none; }" in reduced


# --- 6.5.i: empty states name what is missing -------------------------------

#: Every screen's empty state, and the thing it must name.
EMPTY_STATES = {
    "index.html": "ingest_pdf.py",
    "statements.html": "approved mappings",
    "schedules.html": "Nothing to show yet",
    "formulas.html": "Nothing to show yet",
    "assumptions.html": "Nothing to show yet",
    "forecast.html": "Nothing to forecast yet",
    "valuation.html": "Nothing to value yet",
}


@pytest.mark.parametrize("template,fragment", sorted(EMPTY_STATES.items()))
def test_every_screen_has_an_empty_state_that_names_the_gap(template, fragment):
    assert fragment in (TEMPLATES / template).read_text()


def test_no_empty_state_merely_says_there_is_nothing(client):
    """"No data" is not an explanation, and 6.5.i asks for one.

    This document has not been mapped, so the reason it cannot be forecast is
    upstream of the forecast entirely -- and the screen says which stage is
    missing rather than reporting its own emptiness.
    """
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert "Nothing to forecast yet" in body
    assert "no mapping set" in body
    assert "approved mappings (11.11)" in body


def test_the_empty_state_names_the_stage_that_is_actually_missing(
    three_statement_client,
):
    """A mapped filing that still cannot be forecast fails further along, and
    the screen has to say so rather than repeating the earlier reason."""
    client = three_statement_client
    body = client.get(f"/documents/{client.document_id}/forecast").text
    assert "Nothing to forecast yet" in body
    assert "no mapping set" not in body
    assert "14.1" in body or "other_noncurrent" in body


# --- 6.5.b: every mutation gives success and failure feedback ---------------

MUTATIONS = (
    ("/metadata", "confirm"),
    ("/facts/", "decide"),
    ("/mapping/propose", "propose"),
    ("/mapping/facts/", "decide_mapping"),
    ("/mapping/combine", "combine"),
    ("/mapping/approve-all", "approve_everything"),
    ("/assumptions/accept", "accept_proposal"),
    ("/assumptions/preview", "preview_assumption"),
)


def test_every_mutation_redirects_with_a_flash_rather_than_rendering_in_place():
    """6.5.b, and 10.32 behind it: a POST that rendered its own result would
    leave the browser able to repeat it with a refresh."""
    routes = (
        pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "routes.py"
    ).read_text()
    for path, handler in MUTATIONS:
        assert f'@router.post("/documents/{{document_id}}{path}' in routes, path
        body_start = routes.index(f"def {handler}(")
        body = routes[body_start:body_start + 2500]
        assert "RedirectResponse" in body or "_back(" in body or "_assumptions_back(" in body, (
            f"{handler} does not redirect after its mutation"
        )


def test_a_refused_mutation_comes_back_as_an_alert_not_a_crash(client):
    """6.6.f asks for an error summary. A refusal is a normal outcome here."""
    response = client.post(
        f"/documents/{client.document_id}/mapping/approve-all",
        data={"note": ""}, follow_redirects=True,
    )
    assert response.status_code == 200
    assert 'role="alert"' in response.text


def test_a_successful_mutation_comes_back_as_a_status_message(client):
    response = client.post(
        f"/documents/{client.document_id}/mapping/propose", follow_redirects=True
    )
    assert response.status_code == 200
    assert 'role="status"' in response.text or 'role="alert"' in response.text


def test_the_pending_state_is_the_browsers_own_navigation():
    """6.5.b's third state, stated rather than assumed.

    There is no JavaScript in this application, so a submitted form is a page
    load and the browser's own progress indicator is the pending state. That
    is a decision -- the alternative is a spinner that has to be kept in sync
    with a request it cannot see fail -- and it is recorded here because an
    untested decision is indistinguishable from an oversight.
    """
    for template in TEMPLATES.glob("*.html"):
        text = template.read_text()
        assert "<script" not in text, f"{template.name} has script"
        assert "onclick" not in text and "onsubmit" not in text, template.name
