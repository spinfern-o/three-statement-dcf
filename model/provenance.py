"""Provenance for every hardcoded historical figure.

STEP 4 of the workflow requires that each transcribed number record its
figure, reporting year, PDF page, and the line-item name exactly as the
company reported it. This module makes that non-optional: a `Figure`
cannot be constructed without its source.
"""

from __future__ import annotations

from dataclasses import dataclass


class ProvenanceError(ValueError):
    """A figure was supplied without usable provenance."""


@dataclass(frozen=True)
class Source:
    """Where a reported number came from.

    `line_item` is the company's own wording, not the model's. STEP 4 is
    explicit that reclassification happens later (STEP 5-7), so the raw
    layer preserves the original label to keep the mapping auditable.
    """

    document: str
    page: int | None
    line_item: str

    def __post_init__(self) -> None:
        if not self.document or not self.document.strip():
            raise ProvenanceError("Source.document is required (STEP 2: source map)")
        if not self.line_item or not self.line_item.strip():
            raise ProvenanceError(
                "Source.line_item is required and must be the company's own "
                "reported wording (STEP 4)"
            )
        if self.page is not None and self.page < 1:
            raise ProvenanceError(f"Source.page must be a positive page number, got {self.page!r}")

    def cite(self) -> str:
        page = f" p.{self.page}" if self.page is not None else " (page not recorded)"
        return f"{self.document}{page}: “{self.line_item}”"


@dataclass(frozen=True)
class Figure:
    """A single transcribed historical value, with its origin attached.

    Values are stored in the reporting units declared on the CompanyProfile
    (STEP 1). No scaling happens here; converting thousands to millions
    silently is exactly the kind of unrecorded transformation the workflow
    forbids.
    """

    value: float
    year: str
    source: Source

    def __post_init__(self) -> None:
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
            raise ProvenanceError(f"Figure.value must be numeric, got {self.value!r}")
        if not self.year or not str(self.year).strip():
            raise ProvenanceError("Figure.year is required (STEP 4)")

    def cite(self) -> str:
        return f"{self.value:,.1f} [{self.year}] ← {self.source.cite()}"


def require(value: object, what: str, step: str) -> object:
    """Fail loudly instead of defaulting.

    The workflow repeatedly forbids inventing absent data ("Do not invent
    missing historical years", "do not invent it", "Do not use a plug").
    Every place the model would otherwise reach for a default calls this.
    """

    if value is None:
        raise ProvenanceError(f"{what} is required by {step} and was not provided. Supply it or stop.")
    return value
