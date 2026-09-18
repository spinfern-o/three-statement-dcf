"""The application factory.

    uvicorn apps.api.app.api.main:app          # reads INGEST_STORAGE_ROOT
    python3 review_server.py --store var/sources

`create_app` takes the storage root explicitly so tests can point it at a
temporary directory. Nothing in this module reads configuration at import
time, because a module that does cannot be imported by a test that has not
set the environment first.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from model.disclaimer import DISCLAIMER

from ..core.config import IngestionConfig
from ..display import FILTERS as DISPLAY_FILTERS
from ..extraction.storage import SourceStore
from ..persistence.json_store import JsonDocumentRepository
from ..security.credentials import Credential, signing_key
from ..security.guard import install as install_guard
from ..security.headers import install as install_headers
from ..security.ratelimit import Limiters
from ..verification.build_info import collect as collect_build_info
from .routes import router

HERE = Path(__file__).resolve().parent
PACKAGES = HERE.parents[3] / "packages"

PRODUCT_NAME = "Three-Statement DCF"  # decision 2.1.a
OWNER = "spinfern-o"  # decision 2.1.c
FOOTER = "Private model - not for distribution"  # decision 2.1.c


def create_app(
    storage_root: str | Path,
    *,
    actor: str = "owner",
    credential: Credential | None = None,
    key: bytes | None = None,
    environ=None,
) -> FastAPI:
    """Build the review application over one storage root.

    `credential` is 2.2.c's. Passed explicitly so a test can build a guarded
    application without setting an environment variable, and read from the
    environment when it is not -- never read at import time, because a module
    that reads configuration on import cannot be imported by a test that has
    not set the environment first.

    **When no credential is configured the application still serves**, in
    local-review mode, with a banner on every page saying so. That is not a way
    to turn 2.2.c off: `review_server.py` refuses to bind anywhere but loopback
    without one. The alternative -- refusing to start -- would be a development
    experience somebody works around by commenting out the middleware, which is
    the same hole with nobody watching it.
    """
    root = Path(storage_root)
    root.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title=PRODUCT_NAME,
        description="Source review for extracted financial facts (specification Phase 4).",
        docs_url=None,  # 20.x: no interactive API explorer on a private deployment
        redoc_url=None,
    )
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.globals.update(
        product_name=PRODUCT_NAME,
        owner=OWNER,
        footer=FOOTER,
        # Section 25 requires this in the model, the release flow and the
        # exports. One global rather than one string per template, so the
        # three surfaces cannot drift apart.
        disclaimer=DISCLAIMER,
    )
    # 4.18, 4.19 and 21.8: one display precision, registered once, so a
    # template cannot reach a different formatter by accident and an export
    # cannot disagree with the page it claims to equal.
    templates.env.filters.update(DISPLAY_FILTERS)

    app.state.storage_root = root
    app.state.config = IngestionConfig(storage_root=str(root))
    app.state.store = SourceStore(root)
    app.state.repository = JsonDocumentRepository(root)
    app.state.templates = templates
    app.state.actor = actor
    app.state.credential = credential if credential is not None else Credential.load(environ)
    app.state.signing_key = key or signing_key(environ)
    app.state.limiters = Limiters.build()
    # Item 180, read once at startup rather than per request: a
    # subprocess call on a liveness probe is a liveness probe that
    # can fail for a reason unrelated to liveness.
    app.state.build_info = collect_build_info()
    templates.env.globals.update(
        local_review=app.state.credential is None,
    )
    install_guard(app)
    # Added after the guard, so it wraps it: the guard's own 401s,
    # 403s and redirects are responses too, and a header a route
    # sets cannot cover them.
    install_headers(app)

    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.mount("/tokens", StaticFiles(directory=str(PACKAGES / "design-tokens")), name="tokens")
    app.include_router(router)
    return app


def _from_env() -> FastAPI:
    import os

    root = os.environ.get("INGEST_STORAGE_ROOT")
    if not root:
        raise RuntimeError(
            "INGEST_STORAGE_ROOT is not set. The review application will not "
            "pick a directory for uploaded filings -- see .env.example."
        )
    return create_app(root)


def __getattr__(name: str):
    """`uvicorn ...main:app` builds the app from the environment, lazily."""
    if name == "app":
        return _from_env()
    raise AttributeError(name)
