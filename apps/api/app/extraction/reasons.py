"""Item 36: reason codes and confidence.

Specification 10.28 requires every extracted fact carry a confidence score and
reason codes; 10.29 requires manual review for every low-confidence fact;
10.30 requires manual review for every fact that fails a subtotal or
cross-statement reconciliation regardless of its score.

`docs/source-policy.md` §7 enumerates the codes and splits them into
**blocking** (forces review on its own) and **advisory** (reduces confidence,
shown to the reviewer). That split is implemented here verbatim, with two
additions noted below.

# The confidence model, and why it looks like this

source-policy.md left the scoring *function* OPEN, on the ground that the
specification requires a score without defining one, and that inventing a
formula would be unjustified precision. That was right about the danger and
wrong to stop there: item 36 cannot ship without a score.

So the score is defined to be the one thing that is defensible without
calibration data: **the fraction of named evidence conditions the fact
satisfies.** Eight conditions, listed in `EvidenceCheck`, each a yes/no fact
about how the value was obtained. Confidence is `passed / 8`, exactly.

What that buys:

  * It is **monotonic in evidence, not in plausibility** -- source-policy.md's
    first requirement. A round number in the right place scores no higher for
    looking right.
  * It is **explainable**. A reviewer does not see 0.625, they see which three
    conditions failed. `explain()` returns exactly that.
  * It **cannot be gamed by a downstream success**, because no downstream
    result is an input.

What it explicitly is NOT: a probability. 0.75 does not mean a three-in-four
chance the number is right. It means six of eight evidence conditions hold.
Nothing downstream may treat it as a likelihood, and the diagnostics page
should show the failed conditions rather than the number alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable, Mapping

from model.numeric import D


class ReasonCode(Enum):
    """Why a fact needs attention. `blocking` codes force review on their own."""

    def __new__(cls, code: str, blocking: bool, rule: str, summary: str) -> "ReasonCode":
        obj = object.__new__(cls)
        obj._value_ = code
        obj.blocking = blocking
        obj.rule = rule
        obj.summary = summary
        return obj

    # --- blocking: manual review required (10.29, 10.30) -------------------
    BLANK_CELL = ("BLANK_CELL", True, "1.5, 10.17", "the cell is empty")
    DASH_AMBIGUOUS = (
        "DASH_AMBIGUOUS",
        True,
        "1.5, 10.17",
        "the cell holds a dash with no source legend defining it",
    )
    NOT_APPLICABLE = ("NOT_APPLICABLE", True, "1.5", "the cell holds N/A or equivalent")
    NOT_NUMERIC = (
        "NOT_NUMERIC",
        True,
        "10.25, 10.26",
        "the cell holds characters that are not a number",
    )
    SEPARATOR_AMBIGUOUS = (
        "SEPARATOR_AMBIGUOUS",
        True,
        "10.27",
        "decimal and thousands separators cannot be resolved for the confirmed locale",
    )
    SCALE_UNCONFIRMED = ("SCALE_UNCONFIRMED", True, "1.9, 10.11", "displayed_scale is UNCONFIRMED")
    CURRENCY_UNCONFIRMED = (
        "CURRENCY_UNCONFIRMED",
        True,
        "1.10, 10.11",
        "reporting_currency is UNCONFIRMED",
    )
    PERIOD_AMBIGUOUS = (
        "PERIOD_AMBIGUOUS",
        True,
        "1.7, 10.19, 10.24",
        "the column's period cannot be resolved, or mixes bases",
    )
    SUBTOTAL_MISMATCH = ("SUBTOTAL_MISMATCH", True, "10.30", "the fact fails a subtotal reconciliation")
    CROSS_STATEMENT_MISMATCH = (
        "CROSS_STATEMENT_MISMATCH",
        True,
        "10.30",
        "the fact fails a cross-statement reconciliation",
    )
    RESTATEMENT_CONFLICT = (
        "RESTATEMENT_CONFLICT",
        True,
        "10.20, 10.21",
        "two columns report the same period with different values",
    )
    SCOPE_AMBIGUOUS = (
        "SCOPE_AMBIGUOUS",
        True,
        "1.11, 10.23",
        "consolidated versus segment cannot be determined",
    )
    SIGN_UNRESOLVED = (
        "SIGN_UNRESOLVED",
        True,
        "10.16",
        "the sign cannot be determined from parentheses, position or legend",
    )
    OCR_LOW_CONFIDENCE = (
        "OCR_LOW_CONFIDENCE",
        True,
        "10.8, 10.29",
        "the OCR engine's own confidence is below its threshold",
    )
    MULTI_CONCEPT_LINE = (
        "MULTI_CONCEPT_LINE",
        True,
        "11.4",
        "one raw line contains several concepts with no defensible split",
    )
    LOW_CONFIDENCE = (
        "LOW_CONFIDENCE",
        True,
        "10.29",
        "the confidence score is below the configured review threshold",
    )

    # --- advisory: recorded and shown, not individually blocking -----------
    OCR_DERIVED = ("OCR_DERIVED", False, "10.8", "the value came from OCR, not an embedded text layer")
    FOOTNOTE_MARKER_STRIPPED = (
        "FOOTNOTE_MARKER_STRIPPED",
        False,
        "10.18",
        "a footnote marker was removed from the numeric string",
    )
    HEADER_REPEATED = (
        "HEADER_REPEATED",
        False,
        "10.15",
        "the row came from a table whose header repeats across pages",
    )
    TABLE_SPLIT_ACROSS_PAGES = (
        "TABLE_SPLIT_ACROSS_PAGES",
        False,
        "22.3.h",
        "the source table spans a page break",
    )
    PAGE_ROTATED = ("PAGE_ROTATED", False, "22.3.g", "the source page is rotated")
    DISCONTINUED_OPERATIONS = (
        "DISCONTINUED_OPERATIONS",
        False,
        "10.22",
        "the fact belongs to discontinued operations",
    )
    ADJUSTED_MEASURE = (
        "ADJUSTED_MEASURE",
        False,
        "1.8",
        "the fact is an adjusted or non-GAAP figure and must not be mixed with reported ones",
    )
    RESTATED_VALUE = ("RESTATED_VALUE", False, "10.20, 10.21", "the fact comes from a restated column")
    # Added in Phase 3; see the module note and docs/source-policy.md.
    IMAGE_REGION_NOT_EXTRACTED = (
        "IMAGE_REGION_NOT_EXTRACTED",
        False,
        "10.6",
        "the page mixes text and images, and the image regions were not read",
    )
    WRITTEN_ZERO = (
        "WRITTEN_ZERO",
        False,
        "1.5",
        "the cell spells a zero in words (nil, none) rather than printing a digit",
    )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


BLOCKING_CODES = frozenset(c for c in ReasonCode if c.blocking)
ADVISORY_CODES = frozenset(c for c in ReasonCode if not c.blocking)


def has_blocking(codes: Iterable[ReasonCode]) -> bool:
    """10.29/10.30: any blocking code forces review, whatever the score."""
    return any(c.blocking for c in codes)


class EvidenceCheck(str, Enum):
    """The eight conditions confidence counts. Each is a fact about provenance."""

    TEXT_LAYER = "value read from the embedded text layer rather than OCR"
    IN_TABLE = "the cell sits inside a detected table, not a loose text span"
    ROW_LABEL = "the row carries a non-empty label in the company's own wording"
    COLUMN_PERIOD = "the column header resolves to one unambiguous period"
    PARSED = "the deterministic parser produced a value"
    SIGN_EXPLICIT = "the sign follows from digits, a sign character or parentheses, with no conflict"
    CLEAN_NUMERIC = "no footnote marker had to be stripped from the numeric string"
    TABLE_INTACT = "the source table neither split across a page break nor repeated its header"


ALL_EVIDENCE: tuple[EvidenceCheck, ...] = tuple(EvidenceCheck)
EVIDENCE_COUNT = len(ALL_EVIDENCE)

assert EVIDENCE_COUNT == 8, "the docstring, the threshold default and this list must agree"


@dataclass(frozen=True)
class Confidence:
    """A score, and the reason it is not 1."""

    score: Decimal
    passed: tuple[EvidenceCheck, ...]
    failed: tuple[EvidenceCheck, ...]

    def explain(self) -> str:
        if not self.failed:
            return f"{self.score} - all {EVIDENCE_COUNT} evidence conditions hold"
        missing = "\n".join(f"  - {c.value}" for c in self.failed)
        return (
            f"{self.score} - {len(self.passed)} of {EVIDENCE_COUNT} evidence "
            f"conditions hold. Missing:\n{missing}"
        )

    def needs_review(self, threshold: Decimal) -> bool:
        """10.29. Compared with `<`, so a fact exactly at the threshold passes."""
        return self.score < threshold


def score_confidence(evidence: Mapping[EvidenceCheck, bool]) -> Confidence:
    """`passed / 8`, exactly. Every condition must be stated.

    A missing condition is an error rather than a default: "we did not record
    whether this came from OCR" is not the same as "it did not come from OCR",
    and letting it default would make the score quietly optimistic.
    """
    missing = [c for c in ALL_EVIDENCE if c not in evidence]
    if missing:
        raise ValueError(
            "confidence needs every evidence condition stated; missing: "
            + ", ".join(c.name for c in missing)
        )
    passed = tuple(c for c in ALL_EVIDENCE if evidence[c])
    failed = tuple(c for c in ALL_EVIDENCE if not evidence[c])
    score = (D(len(passed)) / D(EVIDENCE_COUNT)).quantize(D("0.0001"))
    return Confidence(score=score, passed=passed, failed=failed)
