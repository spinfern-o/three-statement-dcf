"""Item 145's first half: one credential, and where it is allowed to live.

**A password, not an API key.** 2.2.b says single user and 2.2.d says one role,
so there is one person to authenticate and they use a browser. A bearer token
would have to be pasted into a URL or stored by hand, and neither survives
20.4's rule against secrets in files a person edits.

**Hashed with `hashlib.scrypt`, from the standard library.** A password hash
must be slow and memory-hard, because the threat is an offline attack on a
stolen hash and a fast hash makes that attack cheap. scrypt is both, it is in
the standard library, and using it means no new dependency in the one place a
dependency would be most costly to get wrong. The parameters below are the
interactive-login set from the scrypt paper, and each one says what it buys.

**The hash lives in the environment, never in the repository** (20.3, 20.4).
`.env.example` carries the name; the value is set where the application runs.
A credential committed to git is compromised from the commit that adds it, and
rotating it does not un-publish it.

**There is no "no credential" mode that reaches a network.** `Credential.load`
returns `None` when the environment is unset, and `create_app` then serves
only to loopback and says so on every page. That is a development affordance
with a hard edge, not a configuration option: `review_server.py` refuses to
bind anywhere else without one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

#: scrypt's cost parameters. N is the CPU/memory cost, r the block size, p the
#: parallelism; memory used is roughly 128 * N * r bytes, so these ask for
#: 32 MiB per verification. That is a fraction of a second for the one person
#: logging in, and 32 MiB per guess for somebody working through a stolen hash.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32

#: The environment variable holding the hash. Named for what it is, so nobody
#: puts a plaintext password in it by reading the name as an invitation.
CREDENTIAL_ENV = "REVIEW_PASSWORD_HASH"
#: The key that signs session cookies. Separate from the credential, because
#: rotating one should not force the other.
SECRET_ENV = "REVIEW_SECRET_KEY"

#: What a stored credential looks like. Self-describing, so a hash produced by
#: different parameters is rejected loudly rather than silently mis-verified.
SCHEME = "scrypt"


class CredentialError(ValueError):
    """The credential is unusable, and this says how."""


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Produce the string that goes in the environment.

    Run by `python3 -m apps.api.app.security.credentials` so the owner never
    has to type a password into a file that might be committed.
    """
    if len(password) < 12:
        raise CredentialError(
            "a password shorter than 12 characters is not worth hashing "
            "expensively; the attack is offline guessing, and length is the "
            "only defence that scales with it"
        )
    salt = salt or secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=KEY_BYTES,
        maxmem=132 * SCRYPT_N * SCRYPT_R,
    )
    return "$".join(
        (
            SCHEME,
            str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(key).decode("ascii"),
        )
    )


@dataclass(frozen=True)
class Credential:
    """One stored password hash, and the parameters it was produced with."""

    n: int
    r: int
    p: int
    salt: bytes
    key: bytes

    @classmethod
    def parse(cls, stored: str) -> Credential:
        parts = stored.split("$")
        if len(parts) != 6 or parts[0] != SCHEME:
            raise CredentialError(
                f"{CREDENTIAL_ENV} is not a {SCHEME} hash produced by "
                "`python3 -m apps.api.app.security.credentials`. It is not "
                "read as a plaintext password: a password in an environment "
                "variable is a password in every process listing."
            )
        try:
            return cls(
                n=int(parts[1]), r=int(parts[2]), p=int(parts[3]),
                salt=base64.b64decode(parts[4], validate=True),
                key=base64.b64decode(parts[5], validate=True),
            )
        except (ValueError, TypeError) as exc:
            raise CredentialError(f"{CREDENTIAL_ENV} is malformed: {exc}") from exc

    @classmethod
    def load(cls, environ=None) -> Credential | None:
        """The configured credential, or None when none is configured."""
        stored = (environ or os.environ).get(CREDENTIAL_ENV, "").strip()
        return cls.parse(stored) if stored else None

    def verify(self, password: str) -> bool:
        """Constant-time check.

        `compare_digest` rather than `==`: an early-exit comparison leaks how
        many leading bytes matched, one request at a time, and a login endpoint
        is the one place an attacker can ask that question repeatedly.
        """
        candidate = hashlib.scrypt(
            password.encode("utf-8"), salt=self.salt,
            n=self.n, r=self.r, p=self.p, dklen=len(self.key),
            maxmem=132 * self.n * self.r,
        )
        return hmac.compare_digest(candidate, self.key)


def signing_key(environ=None) -> bytes:
    """The session-signing key, or a per-process one when unset.

    A generated key is not a fallback that makes the application work anyway:
    it invalidates every session on restart, which is correct for a process
    with no configured secret and obvious to whoever is using it.
    """
    configured = (environ or os.environ).get(SECRET_ENV, "").strip()
    if configured:
        if len(configured) < 32:
            raise CredentialError(
                f"{SECRET_ENV} is {len(configured)} characters. A signing key "
                "shorter than 32 is a key an attacker can search; generate one "
                "with `python3 -m apps.api.app.security.credentials --key`."
            )
        return configured.encode("utf-8")
    return secrets.token_bytes(32)


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import getpass

    parser = argparse.ArgumentParser(
        description="Produce the values REVIEW_PASSWORD_HASH and "
                    "REVIEW_SECRET_KEY are set to. Neither is ever written to "
                    "a file by this program.",
    )
    parser.add_argument("--key", action="store_true",
                        help="print a new signing key instead of hashing a password")
    args = parser.parse_args(argv)

    if args.key:
        print(f"{SECRET_ENV}={secrets.token_urlsafe(48)}")
        return 0

    password = getpass.getpass("Password (at least 12 characters): ")
    if password != getpass.getpass("Again: "):
        print("They do not match.")
        return 1
    try:
        print(f"{CREDENTIAL_ENV}={hash_password(password)}")
    except CredentialError as exc:
        print(f"Refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
