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

from ..core.config import IngestionConfig
from ..display import FILTERS as DISPLAY_FILTERS
from ..extraction.storage import SourceStore
from ..persistence.json_store import JsonDocumentRepository
from .routes import router

HERE = Path(__file__).resolve().parent
PACKAGES = HERE.parents[3] / "packages"

PRODUCT_NAME = "Three-Statement DCF"  # decision 2.1.a
OWNER = "spinfern-o"  # decision 2.1.c
FOOTER = "Private model - not for distribution"  # decision 2.1.c


def create_app(storage_root: str | Path, *, actor: str = "owner") -> FastAPI:
    """Build the review application over one storage root."""
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
        product_name=PRODUCT_NAME, owner=OWNER, footer=FOOTER
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
