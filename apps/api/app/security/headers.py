"""Item 175's application half: the response headers a deployment can verify.

20.12 lists XSS among the classes to protect against, and Phase 17 item 175
says to verify TLS and security headers before release. TLS is the deployment's
(a reverse proxy or a load balancer terminates it); the headers are this
application's, and it was sending **none**.

**The Content-Security-Policy here is unusually strong, and for an unusual
reason: this application ships no JavaScript at all.** So `script-src 'none'`
is not a compromise between safety and function -- it is simply true, and it
turns the whole class of injected-script attacks into a policy violation the
browser refuses. Almost no web application can say that. This one can, and a
policy that merely restricted script sources would be throwing that away.

Every directive below is the tightest value that still serves the pages:

  `default-src 'none'`   nothing loads unless a directive below allows it.
  `script-src 'none'`    there is no JavaScript. Not "self" -- none.
  `style-src 'self'`     two stylesheets, both served from this origin. No
                         inline styles... except three, and that is recorded
                         below rather than waved away with 'unsafe-inline'.
  `img-src 'self'`       the rendered page images, from this origin.
  `font-src 'self'`      the vendored woff2 files (F-24). Self-hosted, so a
                         third party never learns when a filing is being read.
  `form-action 'self'`   a form cannot be retargeted at another origin, which
                         is where a posted reviewer note would otherwise go.
  `frame-ancestors 'none'`  nobody frames this. Clickjacking a one-click
                         "approve all mappings" is the attack that matters.
  `base-uri 'none'`      an injected `<base>` cannot silently repoint every
                         relative URL on the page.
  `connect-src 'none'`   no fetch, no XHR, no beacon. There is no script to
                         make one, and this is what makes that checkable.

**The three inline styles are declared, not excused.** `style-src-attr
'unsafe-inline'` permits inline `style=` attributes and nothing else -- no
inline `<style>` blocks, no inline script. Three templates position SVG chart
elements with computed coordinates, which is geometry rather than styling and
cannot be a class name. Narrowing the exception to the attribute form is the
difference between "inline styles are allowed" and "these three are".
"""

from __future__ import annotations

from dataclasses import dataclass

#: Built from a list rather than a string so each directive can carry its
#: reason in the module docstring above and be asserted individually in a test.
CSP_DIRECTIVES = (
    ("default-src", "'none'"),
    ("script-src", "'none'"),
    ("style-src", "'self'"),
    ("style-src-attr", "'unsafe-inline'"),
    ("img-src", "'self'"),
    ("font-src", "'self'"),
    ("form-action", "'self'"),
    ("frame-ancestors", "'none'"),
    ("base-uri", "'none'"),
    ("connect-src", "'none'"),
)

CSP = "; ".join(f"{name} {value}" for name, value in CSP_DIRECTIVES)

#: How long a browser remembers to use HTTPS for this host. One year, with
#: subdomains, which is what a preload list requires and what makes the header
#: worth sending at all -- a short max-age leaves a window on every new device.
HSTS = "max-age=31536000; includeSubDomains"

#: Every header, with the reason it is here.
HEADERS = {
    "Content-Security-Policy": CSP,
    # A filing's page image must not be sniffed into something executable.
    "X-Content-Type-Options": "nosniff",
    # Redundant with frame-ancestors for modern browsers, and the one that an
    # older one actually honours.
    "X-Frame-Options": "DENY",
    # A referrer leaks a document id to whatever a reader clicks through to,
    # and a document id belongs to an unreleased filing.
    "Referrer-Policy": "no-referrer",
    # Nothing here uses a camera, a microphone, geolocation or a payment
    # handler, so nothing should be permitted to ask.
    "Permissions-Policy": ("camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
    # 20.1: a filing is confidential, so no shared cache may hold a response.
    "Cache-Control": "no-store",
}

#: Sent only over HTTPS. Over plain HTTP it is ignored by browsers and would be
#: a header that looks like a control and is not.
HTTPS_ONLY = {"Strict-Transport-Security": HSTS}

#: Paths whose responses may be cached. The stylesheets and the fonts carry
#: nothing confidential and are fetched on every page load.
CACHEABLE_PREFIXES = ("/static/", "/tokens/")
CACHEABLE = "public, max-age=3600"


@dataclass(frozen=True)
class Headers:
    """What to add to one response."""

    values: dict[str, str]

    def apply(self, response) -> None:
        for name, value in self.values.items():
            response.headers[name] = value


def for_request(path: str, *, is_https: bool) -> dict[str, str]:
    """The headers for one response.

    `Cache-Control` is the only one that varies by path: a stylesheet is not
    confidential and is requested on every page load, and `no-store` on it
    would mean re-fetching the fonts on every navigation.
    """
    headers = dict(HEADERS)
    if any(path.startswith(prefix) for prefix in CACHEABLE_PREFIXES):
        headers["Cache-Control"] = CACHEABLE
    if is_https:
        headers.update(HTTPS_ONLY)
    return headers


class SecurityHeaders:
    """Adds the headers to every response, including error responses.

    Middleware rather than a dependency, for the same reason `guard.py` is: a
    header added per route is a header some route will not have, and the route
    that forgets is as likely to be one that renders a filing as one that
    renders a stylesheet. This also covers the 404s and 403s the guard itself
    returns, which a route-level hook would miss entirely.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_https = scope.get("scheme") == "https"
        extra = for_request(scope.get("path", "/"), is_https=is_https)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                for name, value in extra.items():
                    key = name.lower().encode("latin-1")
                    if key in present:
                        # A route that set its own Cache-Control meant it --
                        # the page-image route sets `private, max-age=3600`
                        # deliberately -- so it is not overwritten here.
                        continue
                    headers.append((key, value.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


def install(app) -> None:
    app.add_middleware(SecurityHeaders)
