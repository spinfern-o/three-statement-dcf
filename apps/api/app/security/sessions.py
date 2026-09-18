"""Item 145's second half: a session that survives a page load and nothing more.

**A signed cookie, not a server-side session table.** There is one user (2.2.b)
and the only thing a session needs to carry is "this browser proved it knows
the password, at this time". A table would add a store to back up, expire and
restore for a single boolean. The cookie carries its own expiry and is signed,
so the server keeps no state and a forged cookie is rejected arithmetically
rather than by lookup.

The construction is HMAC-SHA256 over `issued|expires|nonce`, compared with
`compare_digest`. That is assembled here rather than imported because it is
twelve lines and a reader can check it; nothing else in this package invents
cryptography, and this does not either -- HMAC is the standard library's.

**Three cookie attributes, each load-bearing:**

  `HttpOnly`   the cookie is unreachable from scripts. This application ships
               no JavaScript at all, so the only script that could read it is
               one somebody injected -- which is exactly the case to stop.
  `SameSite`   `Strict`, so the cookie is not sent on a request another site
               initiated. That is CSRF defence in depth beneath `csrf.py`,
               and Strict rather than Lax because nothing here is a safe
               cross-site entry point.
  `Secure`     set unless the request arrived over plain HTTP to loopback.
               Hard-coding it would break local review over http://127.0.0.1;
               omitting it would let a hosted deployment send the session in
               clear text, which 20.2 forbids.

**Expiry is absolute, not idle.** An idle timeout keeps a session alive
indefinitely for somebody who leaves a tab open, and the tab is the thing
likeliest to be left open on an unlocked screen.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

COOKIE_NAME = "review_session"

#: Eight hours: one working day, after which the password is asked for again.
#: Absolute, so it expires whether or not the tab was used.
LIFETIME_SECONDS = 8 * 60 * 60

#: How far ahead of `issued` a clock may be and still be believed. A cookie
#: issued in the future is a forged one or a clock that moved; either way it is
#: not evidence of a login.
CLOCK_SKEW_SECONDS = 60


class SessionError(ValueError):
    """The cookie is not a valid session, and this says why."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class Session:
    """One authenticated browser, and when it stops being one."""

    issued: int
    expires: int
    nonce: str

    @property
    def seconds_left(self) -> int:
        return max(0, self.expires - int(time.time()))


def issue(key: bytes, *, now: int | None = None,
          lifetime: int = LIFETIME_SECONDS) -> tuple[str, Session]:
    """Mint a cookie value for a browser that has just proved the password."""
    moment = int(time.time() if now is None else now)
    session = Session(
        issued=moment,
        expires=moment + lifetime,
        # A nonce so two sessions minted in the same second are different
        # strings; it carries no meaning and is never looked up.
        nonce=secrets.token_urlsafe(12),
    )
    payload = f"{session.issued}|{session.expires}|{session.nonce}"
    signature = hmac.new(key, payload.encode("ascii"), hashlib.sha256).digest()
    return f"{_b64(payload.encode('ascii'))}.{_b64(signature)}", session


def verify(key: bytes, cookie: str, *, now: int | None = None) -> Session:
    """Return the session, or raise. Never returns a partly trusted result."""
    if not cookie or "." not in cookie:
        raise SessionError("no session cookie")
    encoded, _, signature = cookie.partition(".")
    try:
        payload = _unb64(encoded)
        supplied = _unb64(signature)
    except (ValueError, TypeError) as exc:
        raise SessionError(f"malformed session cookie: {exc}") from exc

    expected = hmac.new(key, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, supplied):
        raise SessionError("session signature does not verify")

    try:
        issued_text, expires_text, nonce = payload.decode("ascii").split("|")
        session = Session(int(issued_text), int(expires_text), nonce)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SessionError(f"session payload is not a session: {exc}") from exc

    moment = int(time.time() if now is None else now)
    if session.issued > moment + CLOCK_SKEW_SECONDS:
        raise SessionError("session was issued in the future")
    if session.expires <= moment:
        raise SessionError("session has expired")
    return session


def is_secure_request(url_scheme: str, hostname: str | None) -> bool:
    """Whether the `Secure` attribute may be set on this response's cookie.

    True for HTTPS. Also true for anything that is not loopback, because a
    session travelling over plain HTTP to a remote host is one 20.2 forbids,
    and refusing to set the flag there would make that failure quieter.
    """
    if url_scheme == "https":
        return True
    return hostname not in ("127.0.0.1", "localhost", "::1", None)


def set_cookie(response, value: str, *, secure: bool, lifetime: int = LIFETIME_SECONDS) -> None:
    response.set_cookie(
        COOKIE_NAME, value,
        max_age=lifetime, httponly=True, samesite="strict", secure=secure,
        path="/",
    )


def clear_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
