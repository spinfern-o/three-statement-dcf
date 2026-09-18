"""Item 145's enforcement: what happens to a request with no session.

**Middleware, not a per-route dependency.** A dependency has to be added to
every route, and the failure mode of forgetting one is an unprotected endpoint
that looks exactly like a protected one. There are over thirty routes here and
more arrive every phase. A middleware defaults to closed and names its
exceptions in one readable list, which is the direction to fail in.

`PUBLIC` is that list. Everything else -- every page, every download, every
POST -- requires a session.

**Two modes, and the boundary between them is hard.**

*Guarded*: a credential is configured. Sessions are required, CSRF is checked
on every POST, and login attempts are rate-limited.

*Local review*: no credential is configured. The application serves without
one, **and says so on every page**, and `review_server.py` refuses to bind
anywhere but loopback. This is not a way to turn authentication off on a
network: it is the development affordance that would otherwise be somebody
commenting out the middleware, made visible and constrained instead.

The banner is not decoration. A reviewer who cannot tell whether the thing in
front of them is protected will assume it is.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from . import csrf, sessions
from .ratelimit import RateLimited

#: Paths served without a session. Each one is here for a stated reason, so
#: that adding to this list is a decision somebody has to write down.
PUBLIC = {
    "/login": "the page where a credential is supplied",
    "/health": "a liveness probe carries no filing data and predates auth",
}

#: Prefixes served without a session, for the same kind of reason.
PUBLIC_PREFIXES = {
    "/static/": "stylesheets and fonts, which contain nothing confidential",
    "/tokens/": "design tokens, likewise",
}

#: What an unauthenticated browser is sent to, carrying where it was going so
#: the login does not also lose the reader's place.
LOGIN_PATH = "/login"


@dataclass(frozen=True)
class Guarded:
    """What the middleware resolved about one request."""

    session: sessions.Session | None
    csrf_token: str
    #: True when no credential is configured and the app is serving anyway.
    local_review: bool


def is_public(path: str) -> bool:
    if path in PUBLIC:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


MUTATIONS = ("POST", "PUT", "PATCH", "DELETE")


async def _read_body(receive) -> bytes:
    """Drain the request body, so it can be handed on twice."""
    chunks = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes):
    """A fresh `receive` that yields `body` once, then waits for a disconnect."""
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


class Guard:
    """A raw ASGI middleware, deliberately, because of the body.

    Checking a CSRF token means reading the form, and reading the form consumes
    the request body. Starlette's `BaseHTTPMiddleware` gives no supported way
    to hand that body on afterwards, so a guard written that way reads the
    token and then every route sees an empty body -- which does not fail
    loudly, it fails as a validation error on a field the browser did send.

    At the ASGI layer the body is bytes and replaying it is three lines. That
    is worth more than the convenience of the decorator.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        state = scope["app"].state
        key = state.signing_key

        session = None
        if state.credential is not None:
            try:
                session = sessions.verify(
                    key, request.cookies.get(sessions.COOKIE_NAME, "")
                )
            except sessions.SessionError:
                session = None

            if session is None and not is_public(scope["path"]):
                await self._refuse_unauthenticated(scope, receive, send, request)
                return

        nonce = session.nonce if session else "local-review"
        scope["state"] = dict(scope.get("state") or {})
        scope["state"]["guard"] = Guarded(
            session=session,
            csrf_token=csrf.token_for(key, nonce),
            local_review=state.credential is None,
        )

        body = b""
        if scope["method"] in MUTATIONS:
            body = await _read_body(receive)
            if not is_public(scope["path"]):
                supplied = await _token_in(scope, body)
                try:
                    csrf.check(key, nonce, supplied)
                except csrf.CsrfError as exc:
                    await _send_html(
                        send, 403, f"<h1>Refused</h1><p>{exc}</p>"
                    )
                    return
            receive = _replay(body)

        try:
            await self.app(scope, receive, send)
        except RateLimited as exc:
            await _send_html(
                send, 429, f"<h1>Too many requests</h1><p>{exc}</p>",
                headers=[(b"retry-after", str(exc.retry_after).encode("ascii"))],
            )

    async def _refuse_unauthenticated(self, scope, receive, send, request) -> None:
        if scope["method"] == "GET":
            target = scope["path"]
            if scope.get("query_string"):
                target = f"{target}?{scope['query_string'].decode('latin-1')}"
            await _send_redirect(send, f"{LOGIN_PATH}?next={_quote(target)}")
            return
        # A POST with no session is refused rather than redirected to a form it
        # would have to be re-submitted from: a stale tab must not silently
        # replay a mutation after the session it was opened under has ended.
        await _send_html(
            send, 401,
            "<h1>Session expired</h1><p>Sign in again, then repeat the action. "
            "It was not performed.</p>",
        )


async def _token_in(scope, body: bytes) -> str:
    """The CSRF field out of one request body, whatever it was encoded as."""
    form = await Request(scope, _replay(body)).form()
    try:
        return str(form.get(csrf.FIELD, ""))
    finally:
        await form.close()


async def _send_html(send, status: int, html: str, headers=None) -> None:
    payload = html.encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"content-length", str(len(payload)).encode("ascii")),
                *(headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


async def _send_redirect(send, location: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 303,
            "headers": [
                (b"location", location.encode("latin-1")),
                (b"content-length", b"0"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b""})


def install(app) -> None:
    """Add the guard to one application."""
    app.add_middleware(Guard)


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def safe_next(target: str) -> str:
    """Where to send a browser after login, refusing anywhere but here.

    An open redirect is 20.12's territory: `?next=https://elsewhere` turns this
    login into a credible-looking way to send somebody to another site. Only a
    path on this host is accepted, and anything else lands on the portfolio.
    """
    if not target.startswith("/") or target.startswith("//"):
        return "/"
    return target
