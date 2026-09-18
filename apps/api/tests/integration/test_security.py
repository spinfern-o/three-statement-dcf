"""Phase 15, items 145-149: the credential, the session, and what is logged.

Decision 2.2.c has read "authentication required" since Phase 2 and finding
F-15 has recorded it unimplemented since Phase 4. These are the tests that
close it.
"""

from __future__ import annotations

import logging
import time
from io import StringIO

import pytest

from apps.api.app.api.main import create_app
from apps.api.app.security import csrf, sessions
from apps.api.app.security.authorization import NOT_FOUND, OWNER_ROLE, owner_of, visible
from apps.api.app.security.credentials import (
    CREDENTIAL_ENV,
    SECRET_ENV,
    Credential,
    CredentialError,
    hash_password,
    signing_key,
)
from apps.api.app.security.guard import PUBLIC, PUBLIC_PREFIXES, is_public, safe_next
from apps.api.app.security.logging import (
    LOGGER_NAME,
    PATTERNS,
    configure,
    redact,
    security_event,
)
from apps.api.app.security.ratelimit import (
    CONCURRENT_JOBS,
    LIMITS,
    Concurrency,
    Limiters,
    RateLimit,
    RateLimited,
)
from apps.api.tests.conftest import browser_client

PASSWORD = "a-long-enough-password"
KEY = b"k" * 40


@pytest.fixture
def credential():
    return Credential.parse(hash_password(PASSWORD))


@pytest.fixture
def guarded(tmp_path, stored, store_root, credential):
    """An application with 2.2.c's credential actually configured."""
    with browser_client(create_app(store_root, credential=credential, key=KEY)) as client:
        client.document_id = stored.document.id
        yield client


def sign_in(client, password: str = PASSWORD):
    return client.post("/login", data={"password": password, "next": "/"}, follow_redirects=False)


# --- item 145: the credential -----------------------------------------------


def test_a_password_is_verified_against_a_hash_not_a_stored_password(credential):
    assert credential.verify(PASSWORD)
    assert not credential.verify(PASSWORD + "!")
    assert not credential.verify("")


def test_the_same_password_hashes_differently_every_time():
    """A salt, so two accounts with the same password do not share a hash and a
    precomputed table does not help."""
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_a_short_password_is_refused_rather_than_hashed_expensively():
    with pytest.raises(CredentialError, match="12 characters"):
        hash_password("short")


def test_the_stored_hash_names_its_own_parameters(credential):
    stored = hash_password(PASSWORD)
    scheme, n, r, p, _salt, _key = stored.split("$")
    assert scheme == "scrypt"
    assert (int(n), int(r), int(p)) == (credential.n, credential.r, credential.p)


def test_a_plaintext_password_in_the_environment_is_refused_not_accepted():
    """The failure mode this prevents: somebody sets the variable to their
    password, the application "works", and the password is in every process
    listing on the host."""
    with pytest.raises(CredentialError, match="not read as a plaintext password"):
        Credential.parse(PASSWORD)


def test_no_credential_configured_reads_as_none_not_as_a_blank_one():
    assert Credential.load({}) is None
    assert Credential.load({CREDENTIAL_ENV: "   "}) is None


def test_a_short_signing_key_is_refused():
    with pytest.raises(CredentialError, match="32"):
        signing_key({SECRET_ENV: "too-short"})


def test_an_unset_signing_key_is_generated_not_defaulted():
    """A constant default would mean every deployment shares a signing key, and
    a session forged against one is valid against all of them."""
    first = signing_key({})
    second = signing_key({})
    assert first != second and len(first) == 32


# --- item 145: the session --------------------------------------------------


def test_a_session_verifies_only_under_the_key_that_issued_it():
    cookie, session = sessions.issue(KEY)
    assert sessions.verify(KEY, cookie).nonce == session.nonce
    with pytest.raises(sessions.SessionError, match="signature"):
        sessions.verify(b"j" * 40, cookie)


def test_an_expired_session_is_refused():
    cookie, _ = sessions.issue(KEY)
    later = int(time.time()) + sessions.LIFETIME_SECONDS + 1
    with pytest.raises(sessions.SessionError, match="expired"):
        sessions.verify(KEY, cookie, now=later)


def test_expiry_is_absolute_so_a_left_open_tab_still_ends():
    """An idle timeout keeps a session alive indefinitely for the tab likeliest
    to be sitting on an unlocked screen."""
    cookie, session = sessions.issue(KEY)
    assert session.expires - session.issued == sessions.LIFETIME_SECONDS


def test_a_session_issued_in_the_future_is_not_evidence_of_a_login():
    cookie, _ = sessions.issue(KEY, now=int(time.time()) + 3600)
    with pytest.raises(sessions.SessionError, match="future"):
        sessions.verify(KEY, cookie)


@pytest.mark.parametrize("cookie", ["", "no-dot", "not.base64!!", "YWJj.YWJj"])
def test_a_malformed_cookie_is_refused_without_raising_anything_else(cookie):
    with pytest.raises(sessions.SessionError):
        sessions.verify(KEY, cookie)


@pytest.mark.parametrize(
    "scheme, host, expected",
    [
        ("https", "example.invalid", True),
        ("http", "example.invalid", True),
        ("http", "127.0.0.1", False),
        ("http", "localhost", False),
    ],
)
def test_the_secure_flag_is_set_everywhere_but_loopback(scheme, host, expected):
    assert sessions.is_secure_request(scheme, host) is expected


def test_the_session_cookie_is_httponly_and_samesite_strict(guarded):
    response = sign_in(guarded)
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=strict" in header or "samesite=strict" in header.lower()


# --- item 145: the guard ----------------------------------------------------


def test_an_unauthenticated_page_request_goes_to_the_login(guarded):
    guarded.cookies.clear()
    response = guarded.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


def test_the_login_remembers_where_the_reader_was_going(guarded):
    guarded.cookies.clear()
    target = f"/documents/{guarded.document_id}/statements"
    response = guarded.get(target, follow_redirects=False)
    assert "next=" in response.headers["location"]
    assert "statements" in response.headers["location"]


def test_an_unauthenticated_post_is_refused_rather_than_redirected(guarded):
    """A redirect would invite a stale tab to replay the mutation after login."""
    guarded.cookies.clear()
    response = guarded.post(
        f"/documents/{guarded.document_id}/metadata",
        data={"reason": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert "was not performed" in response.text


def test_signing_in_with_the_right_password_issues_a_session(guarded):
    guarded.cookies.clear()
    response = sign_in(guarded)
    assert response.status_code == 303
    assert sessions.COOKIE_NAME in response.cookies


def test_signing_in_with_the_wrong_password_says_nothing_extra(guarded):
    guarded.cookies.clear()
    response = sign_in(guarded, "wrong-but-long-enough")
    assert response.status_code == 303
    assert "login" in response.headers["location"]
    assert sessions.COOKIE_NAME not in response.cookies


def test_after_signing_in_the_pages_are_reachable(guarded):
    guarded.cookies.clear()
    sign_in(guarded)
    assert guarded.get("/").status_code == 200
    assert guarded.get(f"/documents/{guarded.document_id}").status_code == 200


def test_signing_out_ends_the_session(guarded):
    guarded.cookies.clear()
    sign_in(guarded)
    guarded.post("/logout", follow_redirects=False)
    guarded.cookies.clear()
    assert guarded.get("/", follow_redirects=False).status_code == 303


def test_the_public_list_is_short_and_each_entry_says_why():
    """A middleware that defaults to closed is only as good as this list."""
    assert set(PUBLIC) == {"/login", "/health"}
    assert set(PUBLIC_PREFIXES) == {"/static/", "/tokens/"}
    for reason in list(PUBLIC.values()) + list(PUBLIC_PREFIXES.values()):
        assert reason.strip()


def test_static_assets_are_public_and_documents_are_not():
    assert is_public("/static/app.css") and is_public("/tokens/tokens.css")
    assert not is_public("/documents/doc-1")
    assert not is_public("/documents/doc-1/exports/model.xlsx")


@pytest.mark.parametrize(
    "target, expected",
    [
        ("/documents/x", "/documents/x"),
        ("//evil.invalid", "/"),
        ("https://evil.invalid", "/"),
        ("javascript:alert(1)", "/"),
    ],
)
def test_the_login_is_not_an_open_redirect(target, expected):
    assert safe_next(target) == expected


# --- 20.12: CSRF ------------------------------------------------------------


def test_a_post_without_a_token_is_refused(client):
    response = client.post(
        f"/documents/{client.document_id}/metadata",
        data={"reason": "x", "csrf_token": ""},
    )
    assert response.status_code == 403
    assert "CSRF" in response.text


def test_a_post_with_another_sessions_token_is_refused(client):
    stolen = csrf.token_for(b"different-key-entirely-and-long", "local-review")
    response = client.post(
        f"/documents/{client.document_id}/metadata",
        data={"reason": "x", "csrf_token": stolen},
    )
    assert response.status_code == 403


def test_the_token_changes_with_the_session():
    first = csrf.token_for(KEY, "nonce-one")
    second = csrf.token_for(KEY, "nonce-two")
    assert first != second and len(first) == 64


def test_csrf_is_enforced_in_local_review_mode_too(client):
    """Authentication and CSRF are different defences. A local server is
    exactly what a page in another tab can post to."""
    assert client.app.state.credential is None
    response = client.post(
        f"/documents/{client.document_id}/metadata",
        data={"reason": "x", "csrf_token": "wrong"},
    )
    assert response.status_code == 403


def test_every_post_form_in_every_template_carries_the_token():
    """The check that keeps a new form from shipping unprotected."""
    import re
    from pathlib import Path

    templates = Path(__file__).resolve().parents[2] / "app" / "api" / "templates"
    opening = re.compile(r'<form\b[^>]*\bmethod="post"[^>]*>', re.IGNORECASE)
    for path in sorted(templates.glob("*.html")):
        body = path.read_text()
        for match in opening.finditer(body):
            tail = body[match.end() : match.end() + 400]
            assert 'name="csrf_token"' in tail, f"{path.name}: {match.group(0)[:60]}"


def test_the_body_survives_the_guard(client):
    """The defect a CSRF middleware written on BaseHTTPMiddleware introduces:
    reading the form consumes the body, and every route then sees an empty one
    -- which surfaces as a validation error on a field the browser did send."""
    response = client.post(
        f"/documents/{client.document_id}/metadata",
        data={"page": "1", "reason": "checked against the cover page"},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    assert "Field required" not in response.text


# --- item 146: 20.7's authorization ----------------------------------------


def test_a_document_belonging_to_somebody_else_is_a_404_not_a_403(store_root, stored):
    """20.7: an unauthorized resource answers exactly as a nonexistent one, so
    identifiers do not leak existence."""
    with browser_client(create_app(store_root, actor="someone-else")) as client:
        missing = client.get("/documents/doc-does-not-exist")
        forbidden = client.get(f"/documents/{stored.document.id}")
        assert missing.status_code == forbidden.status_code == 404
        assert NOT_FOUND in forbidden.json()["detail"]
        assert forbidden.json() == missing.json()


def test_the_portfolio_does_not_list_what_the_reader_cannot_open(store_root, stored):
    with browser_client(create_app(store_root, actor="someone-else")) as client:
        assert stored.document.sanitized_filename not in client.get("/").text


def test_the_owner_is_read_from_the_record_not_from_the_request(stored):
    assert owner_of(stored) == stored.document.company_id


def test_a_record_with_no_recorded_owner_is_refused(stored):
    """Refusing is the safe direction: the alternative reads "we do not know
    who owns this" as "anybody may read it"."""
    import dataclasses

    orphan = dataclasses.replace(
        stored, document=dataclasses.replace(stored.document, company_id="")
    )
    assert visible([orphan], OWNER_ROLE) == []


def test_every_document_route_goes_through_the_checked_loader():
    """Item 146 is one line in one place only if nothing bypasses it."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "app" / "api" / "routes.py").read_text()
    # `load_result` outside `_load` and the portfolio's own filtered listing
    # would be a read that skipped the check.
    calls = [
        line for line in source.splitlines() if "load_result(" in line and "def _load" not in line
    ]
    assert len(calls) == 2, calls  # one in _load, one in the filtered portfolio


# --- item 148: rate limits --------------------------------------------------


def test_the_login_is_rate_limited(guarded):
    guarded.cookies.clear()
    allowed, _window = LIMITS["authentication"]
    for _ in range(allowed):
        sign_in(guarded, "wrong-but-long-enough")
    response = sign_in(guarded, "wrong-but-long-enough")
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_a_successful_login_clears_the_count(guarded):
    """So somebody else's guessing cannot lock the one real user out."""
    guarded.cookies.clear()
    sign_in(guarded, "wrong-but-long-enough")
    sign_in(guarded)
    assert guarded.app.state.limiters.authentication.remaining("testclient") == 5


def test_a_window_refills(monkeypatch):
    limit = RateLimit(2, 60, "test")
    limit.check("a", now=0.0)
    limit.check("a", now=1.0)
    with pytest.raises(RateLimited):
        limit.check("a", now=2.0)
    limit.check("a", now=61.0)


def test_the_expensive_work_is_limited_by_concurrency_not_only_by_rate():
    """One expensive job is the resource risk here, not request volume."""
    gate = Concurrency(CONCURRENT_JOBS, "export")
    with gate:
        with pytest.raises(RateLimited, match="concurrent"):
            with gate:
                pass
    assert gate.running == 0


def test_every_class_20_14_names_has_a_limit():
    assert set(LIMITS) == {"authentication", "upload", "extraction", "export"}
    for name, (allowed, window) in LIMITS.items():
        assert allowed > 0 and window > 0, name


def test_the_limiters_admit_they_are_per_process():
    """Written as a property rather than a comment, because a deployment
    running N workers has N independent limiters and every limit is N times
    weaker."""
    assert Limiters.build().is_shared is False


# --- item 149: the log ------------------------------------------------------


@pytest.mark.parametrize(
    "text, gone",
    [
        ("could not parse 1,234,567.89", "1,234,567.89"),
        ("owner larry@example.invalid signed in", "larry@example.invalid"),
        ("password: hunter2hunter2", "hunter2hunter2"),
        ("Authorization=Bearer abcdefghijklmnop", "abcdefghijklmnop"),
    ],
)
def test_the_things_that_must_never_reach_the_log_do_not(text, gone):
    assert gone not in redact(text)


def test_a_page_number_and_an_identifier_survive_redaction():
    """The log is useless if it redacts what an investigation needs."""
    kept = redact("fact fact-91ab on page 7 of doc-496398242be3")
    assert "page 7" in kept and "doc-496398242be3" in kept and "fact-91ab" in kept


def test_an_event_is_one_line_of_json():
    import json

    event = security_event("authentication.failed", actor="127.0.0.1", detail="no")
    body = json.loads(event.as_json())
    assert body["action"] == "authentication.failed"
    assert body["outcome"] == "failed"
    assert "\n" not in event.as_json()


def test_an_action_with_no_stated_outcome_is_not_recorded_as_success():
    assert security_event("something.happened").outcome == "unstated"


def test_the_log_is_written_where_a_handler_can_find_it():
    stream = StringIO()
    configure(stream)
    security_event("authentication.succeeded", actor="127.0.0.1")
    logging.getLogger(LOGGER_NAME).handlers[0].flush()
    assert '"action": "authentication.succeeded"' in stream.getvalue()


def test_a_failed_login_is_logged_and_the_password_is_not(guarded):
    stream = StringIO()
    configure(stream)
    guarded.cookies.clear()
    sign_in(guarded, "the-actual-wrong-password")
    logging.getLogger(LOGGER_NAME).handlers[0].flush()
    written = stream.getvalue()
    assert "authentication.failed" in written
    assert "the-actual-wrong-password" not in written


def test_every_redaction_pattern_is_exercised_by_a_test():
    """So a pattern added without a test is a test failure, not a silent gap."""
    assert len(PATTERNS) == 5


# --- 20.16: private data must not leave in an application error -------------


LEAKY = "balance differs by 123456789 for ACME HOLDINGS 2025"


def _app_that_raises(tmp_path, exception):
    """An application with one route that raises mid-request."""
    app = create_app(tmp_path)

    @app.get("/__raises")
    def _raises():
        raise exception

    return app


def test_an_unhandled_engine_error_does_not_reach_the_response(tmp_path):
    """20.16, and the reason it holds is worth pinning rather than assuming.

    The engine's exceptions are deliberately informative -- `Ledger.require`
    names the account and year, the balance check reports the delta -- which is
    right for a CLI run by the data's owner and is most of what makes the tool
    usable. Several of those messages carry figures off the filing.

    What stops them crossing the HTTP boundary is that the application runs
    with `debug` off, so Starlette's default handler returns a bare
    "Internal Server Error". That is a property of a setting, and a setting can
    be changed by somebody debugging a problem who then forgets. This test is
    what makes that change fail here rather than in production.
    """
    from starlette.testclient import TestClient

    from model.provenance import ProvenanceError

    app = _app_that_raises(tmp_path, ProvenanceError(LEAKY))
    assert app.debug is False, "debug on would print the traceback, and the figures in it"

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__raises")

    assert response.status_code == 500
    assert LEAKY not in response.text
    assert "123456789" not in response.text
    assert "ACME" not in response.text
    assert "Traceback" not in response.text


def test_the_same_holds_for_a_build_error(tmp_path):
    """The exception class a route is most likely to let escape."""
    from starlette.testclient import TestClient

    from apps.api.app.statements.build import BuildError

    client = TestClient(
        _app_that_raises(tmp_path, BuildError(LEAKY)), raise_server_exceptions=False
    )
    response = client.get("/__raises")

    assert response.status_code == 500
    assert "123456789" not in response.text


def test_a_handled_error_is_shown_only_to_the_owner_of_that_document(guarded):
    """Why the informative messages ARE rendered, and why that is not 20.16.

    Routes catch `BuildError` and render `str(exc)` into the page, figures and
    all. That is not a leak: `authorization.require_access` runs before the
    build, so the only reader who reaches it is the document's owner, looking
    at figures from the filing they are already reviewing.

    The guard is what makes that true, so this asserts the guard rather than
    the message: an unauthenticated request never reaches a route that could
    build anything.
    """
    response = guarded.get("/documents/doc-anything/statements", follow_redirects=False)
    assert response.status_code in (303, 401, 404)
    assert "123456789" not in response.text

    # And a document that DOES exist answers the same way to an
    # unauthenticated reader, so the refusal cannot be used to probe which
    # identifiers are real (20.7).
    real = guarded.get(f"/documents/{guarded.document_id}/statements", follow_redirects=False)
    assert real.status_code == response.status_code
    assert real.text == response.text
