"""Item 40: render a stored PDF page for the viewer.

Two properties matter more than the rendering itself.

**The original is never touched.** The page is rendered from the bytes the
store holds, read through `SourceStore.read()`, which re-hashes them first and
refuses to return anything that has changed (rule 1.12). A render is a
read-only derivative; item 38's guarantee is not weakened by looking at it.

**The overlay needs no pixel arithmetic.** The rendered image is placed at
whatever size the layout gives it, and the bounding boxes are drawn in an
inline SVG whose `viewBox` is the page in PDF points. The browser does the
scaling, exactly, at any zoom -- so a highlight cannot drift from the number
it points at, which is the one thing 10.31 is for.

Renders are cached on disk under the storage root. They are derivatives, not
evidence: deleting the cache costs a re-render and nothing else.

**20.10: the parsing runs in a child process.** This is the one place the web
process feeds an untrusted PDF to a large C library on a request from a
browser, which is exactly what that clause is about. `_render` is a
module-level function so a spawned interpreter can import it; a crash, a
runaway allocation or an endless loop inside it ends there and the request gets
a refusal instead of the server getting a signal. `security/sandbox.py` says in
full what that does and does not protect against.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from ..extraction.storage import SourceStore
from ..security.sandbox import SandboxError, run_isolated

#: Readable on a laptop without making an A4 page a 4 MB PNG.
DEFAULT_DPI = 120


def render_page(
    store: SourceStore,
    immutable_hash: str,
    page_number: int,
    *,
    dpi: int = DEFAULT_DPI,
    cache_root: Path | None = None,
    isolate: bool = True,
) -> bytes:
    """Return a PNG of one page, 1-based. Raises `IndexError` for a bad page.

    `isolate` is True in every caller. It exists as a parameter so a test can
    compare the isolated render against the in-process one byte for byte, and
    prove the separation changed nothing about the output.
    """
    cache = None
    if cache_root is not None:
        cache = cache_root / "renders" / immutable_hash[:2] / f"{immutable_hash}-p{page_number}-{dpi}.png"
        if cache.exists():
            return cache.read_bytes()

    data = store.read(immutable_hash)
    if isolate:
        try:
            png = run_isolated(_render, data, page_number, dpi)
        except SandboxError as exc:
            # An IndexError raised inside the child arrives here as text, so
            # the one outcome a caller distinguishes is recovered by name
            # rather than swallowed into a generic failure.
            if "IndexError" in str(exc):
                raise IndexError(str(exc).split(": ", 2)[-1]) from None
            raise
    else:
        png = _render(data, page_number, dpi)

    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(png)
    return png


def _render(data: bytes, page_number: int, dpi: int) -> bytes:
    """The part that touches the PDF. Module-level so `spawn` can import it."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 1 <= page_number <= doc.page_count:
            raise IndexError(
                f"page {page_number} is outside this document's 1-{doc.page_count}"
            )
        pixmap = doc[page_number - 1].get_pixmap(dpi=dpi)
        return pixmap.tobytes("png")
