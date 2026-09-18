"""Phase 15, items 145-153: security and operations.

Decision 2.2.c has read **"authentication required"** since Phase 2, and
finding F-15 has recorded it unimplemented since Phase 4 -- with the mitigation
that `review_server.py` binds to localhost. A mitigation is not the
requirement, and a mitigation that depends on a reader passing the right flag
is not even a good one.

This package is the requirement: a credential, a session, a CSRF token, an
ownership check on every resource, rate limits on the endpoints 20.14 names,
and a log that does not contain the filing.

**No cryptography is invented here.** 20.2's note in `security-model.md` is
explicit that this application must not implement its own, and nothing below
does: `hashlib.scrypt`, `hmac.compare_digest` and `secrets.token_urlsafe` are
the standard library's, and the one construction that is assembled rather than
called -- a signed cookie -- is HMAC-SHA256 over a payload, compared in
constant time, which is the same construction every framework uses and is
small enough to read in full.
"""
