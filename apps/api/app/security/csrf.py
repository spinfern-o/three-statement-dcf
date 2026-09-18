"""20.12's CSRF half, for an application with no JavaScript.

Every mutation here is a form POST followed by a redirect -- that has been the
shape since Phase 4, because 10.32 requires a reviewer note on every
correction and a GET that changes state is a change with no note. Form POSTs
are also precisely what a cross-site request can forge: another page can
submit a form to this one, and the browser will attach the session cookie.

`SameSite=Strict` on the session cookie already stops the standard version of
that attack. This is the second layer, and it exists because SameSite is a
browser behaviour and the token is an application one: a browser that does not
implement it, or a future relaxation of the cookie, must not be the only thing
between a filing and a forged approval.

**The token is derived from the session, not stored.** HMAC of the session's
nonce under the same signing key: it changes when the session changes, it
cannot be computed by anybody who has not seen the session, and there is
nothing to expire or clean up. A stored per-request token would need a table,
and a table for a single user is a thing to back up rather than a defence.

**Compared in constant time**, like every other secret comparison here.
"""

from __future__ import annotations

import hashlib
import hmac

#: The form field every POST carries. Named in full rather than abbreviated,
#: because a reader of the HTML should be able to tell what it is.
FIELD = "csrf_token"


class CsrfError(ValueError):
    """The request carried no valid token."""


def token_for(key: bytes, nonce: str) -> str:
    """The token this session's forms must carry."""
    return hmac.new(key, f"csrf|{nonce}".encode("utf-8"), hashlib.sha256).hexdigest()


def check(key: bytes, nonce: str, supplied: str) -> None:
    """Raise unless `supplied` is this session's token."""
    if not supplied:
        raise CsrfError(
            "this form carried no CSRF token. Every state-changing request "
            "needs one (20.12); a form submitted from another page will not "
            "have it."
        )
    if not hmac.compare_digest(token_for(key, nonce), supplied):
        raise CsrfError("the CSRF token does not match this session")
