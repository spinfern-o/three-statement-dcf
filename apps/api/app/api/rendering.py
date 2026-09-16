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
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from ..extraction.storage import SourceStore

#: Readable on a laptop without making an A4 page a 4 MB PNG.
DEFAULT_DPI = 120


def render_page(
    store: SourceStore,
    immutable_hash: str,
    page_number: int,
    *,
    dpi: int = DEFAULT_DPI,
    cache_root: Path | None = None,
) -> bytes:
    """Return a PNG of one page, 1-based. Raises `IndexError` for a bad page."""
    cache = None
    if cache_root is not None:
        cache = cache_root / "renders" / immutable_hash[:2] / f"{immutable_hash}-p{page_number}-{dpi}.png"
        if cache.exists():
            return cache.read_bytes()

    data = store.read(immutable_hash)
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if not 1 <= page_number <= doc.page_count:
            raise IndexError(
                f"page {page_number} is outside this document's 1-{doc.page_count}"
            )
        pixmap = doc[page_number - 1].get_pixmap(dpi=dpi)
        png = pixmap.tobytes("png")

    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(png)
    return png
