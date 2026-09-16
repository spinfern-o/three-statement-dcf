"""Items 30 (part) and 31: page classification, and the OCR decision.

Specification 10.6 requires detecting whether each page is text-native,
image-only, or mixed. 10.8 says "OCR image-only pages".

**Decision 2.3.c is text-native only.** The decision ledger records the
reasoning: OCR brings Tesseract, a job queue, and a confidence-scoring model
whose scoring function the specification never defines. `docs/source-policy.md`
§3 states the consequence -- "an image-only page is a hard rejection with an
explanatory message rather than a silent empty extraction" -- and that is what
`classify_pages` enforces.

So item 31 is implemented as a refusal. That is not the same as skipping it. A
skipped OCR step would produce an empty extraction from a scanned filing and
call it a filing with no numbers in it; the refusal names the pages and says
why nothing was read from them.

A MIXED page -- text and images together -- is extracted, and the image regions
are recorded as not read (`IMAGE_REGION_NOT_EXTRACTED`). A chart is usually
what they contain; a table rendered as a picture is the dangerous case, and
saying so on the page is more honest than either refusing the filing or
pretending the page was fully read.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pymupdf

from ..core.errors import IMAGE_ONLY_PAGE, NO_TEXT_LAYER, IngestionRefusal
from .geometry import BoundingBox, PageGeometry, from_parser_number


class PageKind(str, Enum):
    TEXT_NATIVE = "text_native"
    IMAGE_ONLY = "image_only"
    MIXED = "mixed"
    #: Neither text nor images. A separator or section-divider page.
    EMPTY = "empty"


@dataclass(frozen=True)
class PageProfile:
    """What one page is made of. 10.6."""

    geometry: PageGeometry
    kind: PageKind
    character_count: int
    image_count: int
    #: Where the images are, for the reviewer to see what was not read.
    image_boxes: tuple[BoundingBox, ...] = ()

    @property
    def page_number(self) -> int:
        return self.geometry.page_number


def profile_page(page: "pymupdf.Page", *, min_chars: int) -> PageProfile:
    """Classify one page by what it actually carries."""
    geometry = PageGeometry(
        page_number=page.number + 1,
        width=from_parser_number(page.rect.width, what="page width"),
        height=from_parser_number(page.rect.height, what="page height"),
        rotation=page.rotation % 360,
    )

    text = page.get_text().strip()
    images = page.get_images(full=True)
    boxes: list[BoundingBox] = []
    for image in images:
        for rect in page.get_image_rects(image[0]):
            boxes.append(BoundingBox.from_parser((rect.x0, rect.y0, rect.x1, rect.y1)))

    has_text = len(text) >= min_chars
    has_images = bool(images)

    if has_text and has_images:
        kind = PageKind.MIXED
    elif has_text:
        kind = PageKind.TEXT_NATIVE
    elif has_images:
        kind = PageKind.IMAGE_ONLY
    else:
        kind = PageKind.EMPTY

    return PageProfile(
        geometry=geometry,
        kind=kind,
        character_count=len(text),
        image_count=len(images),
        image_boxes=tuple(boxes),
    )


def classify_pages(doc: "pymupdf.Document", *, min_chars: int) -> tuple[PageProfile, ...]:
    """Classify every page, and apply decision 2.3.c.

    Refuses the document when any page is image-only, naming the pages. Refuses
    when no page has a text layer at all, which is the same condition stated
    more usefully for an entirely scanned filing.
    """
    profiles = tuple(profile_page(doc[n], min_chars=min_chars) for n in range(doc.page_count))

    readable = [p for p in profiles if p.kind in (PageKind.TEXT_NATIVE, PageKind.MIXED)]
    image_only = [p for p in profiles if p.kind is PageKind.IMAGE_ONLY]

    if not readable:
        raise IngestionRefusal(
            NO_TEXT_LAYER,
            f"none of this document's {len(profiles)} page(s) carries an "
            f"extractable text layer. It is a scan. Decision 2.3.c puts OCR out "
            f"of scope, so there is nothing this system can read from it -- "
            f"supply a text-native copy of the filing.",
        )

    if image_only:
        numbers = ", ".join(str(p.page_number) for p in image_only)
        raise IngestionRefusal(
            IMAGE_ONLY_PAGE,
            f"page(s) {numbers} carry images but no text layer. Decision 2.3.c "
            f"is text-native only, so those pages cannot be read, and a filing "
            f"extracted with pages silently missing is worse than one refused. "
            f"Supply a text-native copy, or split the readable pages out "
            f"deliberately and say so.",
        )

    return profiles
