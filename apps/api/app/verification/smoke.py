"""Items 172 and 179: smoke tests against a deployed URL, exposing nothing.

    python3 -m apps.api.app.verification.smoke https://review.example.invalid

172 asks for staging smoke tests and 179 for production ones **"without
exposing private data"**. Those are the same checks with one difference, and
the difference is the interesting part: a production smoke test must not print,
log or fetch a filing. So this asks only questions whose answers are properties
of the *deployment*:

  - is it alive, and which commit is it (180);
  - does it require a credential (2.2.c), checked by asking for a page and
    seeing where it sends you;
  - are the security headers there (175);
  - is it on HTTPS, and does it say so with HSTS (20.2);
  - are the stylesheet and the fonts served (F-24: they were once named and
    absent);
  - is the interactive API explorer off (20.x).

**It never authenticates**, which is what keeps it safe to run against
production. An unauthenticated client cannot reach a filing, so a smoke test
that stays unauthenticated cannot expose one — and "does an unauthenticated
request get refused" is precisely the most important thing to check after a
deployment.

That is also its limit, stated plainly: this proves the deployment is up,
guarded and correctly configured. It does not prove a valuation is right. The
suite does that, and item 178 is why it is the *same tested version* being
deployed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from ..security.headers import HEADERS, HTTPS_ONLY

#: Seconds. A smoke test that hangs is a deployment nobody can verify.
TIMEOUT = 15

#: Where an unauthenticated browser must end up.
LOGIN_PATH = "/login"


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

    def line(self) -> str:
        return f"  {'PASS' if self.passed else 'FAIL'}  {self.name}: {self.detail}"


class _Headers(dict):
    """Case-insensitive lookup.

    HTTP header names are case-insensitive and servers disagree about case --
    uvicorn sends them lowercase. The first version of this file looked up
    "Content-Security-Policy" in a plain dict and reported every header absent
    on a deployment that was sending all of them, which is the worst kind of
    wrong for a smoke test: it fails on a correct deployment, so somebody
    "fixes" the deployment.
    """

    def __init__(self, pairs) -> None:
        super().__init__({str(name).lower(): value for name, value in pairs})

    def get(self, name, default=None):
        return super().get(str(name).lower(), default)

    def __contains__(self, name) -> bool:
        return super().__contains__(str(name).lower())


def _get(url: str, *, follow: bool = False):
    """One request. Never sends a credential and never follows off-host."""
    request = urllib.request.Request(url, headers={"User-Agent": "smoke/1"})

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return (
                None
                if not follow
                else super().redirect_request(req, fp, code, msg, headers, newurl)
            )

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            return response.status, _Headers(response.headers.items()), response.read(65536)
    except urllib.error.HTTPError as exc:
        return exc.code, _Headers(exc.headers.items()), exc.read(65536)


def run(base: str) -> list[Check]:
    """Every check, against one deployment."""
    checks: list[Check] = []
    parsed = urlparse(base)
    is_https = parsed.scheme == "https"

    # --- alive, and which commit (item 180) --------------------------------
    try:
        status, _, body = _get(urljoin(base, "/health"))
    except (urllib.error.URLError, OSError) as exc:
        return [Check("reachable", False, f"{base} did not answer: {exc}")]

    checks.append(Check("alive", status == 200, f"/health returned {status}"))

    try:
        health = json.loads(body)
    except ValueError:
        health = {}
    checks.append(
        Check(
            "identifies its commit (180)",
            bool(health.get("identified")),
            health.get("commit_source", "no commit in /health"),
        )
    )
    checks.append(
        Check(
            "records the schema and formula versions (180)",
            bool(health.get("schema_version")) and bool(health.get("formula_version")),
            f"schema {health.get('schema_version', '?')}, "
            f"formulas {str(health.get('formula_version', '?'))[:12]}",
        )
    )
    # A dirty tree is not the tested version, which is item 178's requirement.
    checks.append(
        Check(
            "deploys a clean tree (178)",
            not str(health.get("commit", "")).endswith("-dirty"),
            "the deployed commit carries uncommitted changes"
            if str(health.get("commit", "")).endswith("-dirty")
            else "the deployed commit is a committed revision",
        )
    )

    # --- guarded (2.2.c) ---------------------------------------------------
    status, _headers, body = _get(urljoin(base, "/"))
    guarded = status in (301, 302, 303, 307, 308) and LOGIN_PATH in str(
        _headers.get("Location", "")
    )
    checks.append(
        Check(
            "requires a credential (2.2.c)",
            guarded,
            f"an unauthenticated request for / returned {status}"
            + (
                f" to {_headers.get('Location')}"
                if guarded
                else " -- it should redirect to /login. A deployment serving a filing "
                "without a credential is the thing 2.2.c exists to prevent"
            ),
        )
    )
    # 20.1: and it must not have served any of the filing while doing so.
    leaked = [
        word for word in (b"Enterprise value", b"canonical", b"immutable_hash") if word in body
    ]
    checks.append(
        Check(
            "leaks nothing to an unauthenticated request (20.1)",
            not leaked,
            "no filing content in the unauthenticated response"
            if not leaked
            else f"the response contained {leaked}",
        )
    )

    # --- headers (item 175) -------------------------------------------------
    status, page_headers, _body = _get(urljoin(base, LOGIN_PATH))
    for name in HEADERS:
        present = name in page_headers
        checks.append(Check(f"sends {name} (175)", present, page_headers.get(name, "absent")[:80]))
    if is_https:
        for name in HTTPS_ONLY:
            checks.append(
                Check(
                    f"sends {name} (20.2)", name in page_headers, page_headers.get(name, "absent")
                )
            )
    else:
        loopback = parsed.hostname in ("127.0.0.1", "localhost", "::1")
        checks.append(
            Check(
                "is served over HTTPS (20.2)",
                # A loopback URL is a local review session, which 20.2 does not
                # bind for -- it is written "for hosted deployments". Reporting
                # it as a failure would make every local run of this script red
                # and teach a reader to ignore the row.
                loopback,
                f"{base} is loopback, so 20.2 does not bind"
                if loopback
                else f"{base} is not HTTPS. 20.2 binds for hosted deployments, and a "
                f"session cookie's Secure flag is not set off HTTPS",
            )
        )

    # --- the assets that were once named and absent (F-24) ------------------
    for path, what in (("/static/app.css", "stylesheet"), ("/tokens/tokens.css", "design tokens")):
        status, _headers, _body = _get(urljoin(base, path))
        checks.append(Check(f"serves the {what}", status == 200, f"{path} -> {status}"))

    # --- the explorer is off (20.x) ----------------------------------------
    #
    # 404 when `docs_url=None` removed the route, or a redirect to /login when
    # the guard catches it first. What must not happen is a 200 with a Swagger
    # page on it: asserting 404 alone reported a FAIL on a deployment where the
    # guard was doing MORE than required.
    status, _headers, body = _get(urljoin(base, "/docs"))
    checks.append(
        Check(
            "has no interactive API explorer (20.x)",
            status != 200 and b"swagger" not in body.lower(),
            f"/docs -> {status}"
            + (
                " (refused by the guard before the route)"
                if status in (301, 302, 303, 307, 308)
                else ""
            ),
        )
    )

    return checks


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Items 172 and 179: smoke-test a deployment. Never "
        "authenticates, so it is safe to run against production "
        "and cannot expose a filing.",
    )
    parser.add_argument("base", help="the deployment's base URL")
    args = parser.parse_args(argv)

    checks = run(args.base)
    for check in checks:
        print(check.line())

    failed = [check for check in checks if not check.passed]
    print()
    if failed:
        print(f"{len(failed)} of {len(checks)} check(s) failed.")
        return 1
    print(
        f"All {len(checks)} checks passed. This says the deployment is up, "
        f"guarded and configured -- not that a valuation is right."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
