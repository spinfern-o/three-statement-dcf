"""Item 34: metadata detection, every field UNCONFIRMED.

Specification 10.10 lists what to detect: document title, company name,
reporting period, fiscal year-end, currency, scale, audited status, and
accounting standard. 10.11 is the rule that matters: **mark detected metadata
as UNCONFIRMED.** 10.12 present it to a reviewer. 10.13 require confirmation or
correction of every required field before anything downstream runs.

`docs/source-policy.md` §4 names the four fields that are load-bearing, because
getting them wrong produces a plausible, confident, wrong model:

    displayed_scale       rule 1.9    a 1000x error that looks entirely normal
    reporting_currency    rule 1.10   values mixed with no exchange-rate basis
    reporting period      rule 1.7    annual, quarterly and TTM in one column
    audited_status        STEP 1      unaudited figures with audited authority

So nothing here returns a value. Every detector returns a `DetectedField`
carrying the value, the page and text it came from, the detector that found it,
and `confirmed=False`. A field that could not be detected returns a
`DetectedField` with `value=None` -- present, required, and empty -- rather
than being absent, because a missing key is easy to skip and an empty required
field is not.

Two fields are detected beyond 10.10's list:

    filing_type     2.3.b is annual only, so a quarterly filing has to be
                    detectable in order to be refused at review.
    number_locale   10.26 requires the parse be driven by a locale. Detecting
                    a candidate is allowed; trusting it is not, and
                    `parsing.py` refuses every ambiguous cell until it is
                    confirmed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import Enum

import pymupdf

from .geometry import BoundingBox

#: How many pages the cover-page detectors look at. A cover, a contents page
#: and the audit report are the first few; scanning the whole filing would find
#: the word "unaudited" in an interim-comparison note and detect the wrong thing.
COVER_PAGES = 4


class ConfirmationState(str, Enum):
    """10.11. Every detected field begins UNCONFIRMED, without exception."""

    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"


@dataclass(frozen=True)
class Evidence:
    """Where a detected value came from, so a reviewer can look at it. 10.12."""

    page_number: int
    matched_text: str
    bounding_box: BoundingBox | None
    detector: str


@dataclass(frozen=True)
class DetectedField:
    """One metadata field. Never trusted, whatever its value."""

    name: str
    value: str | None
    required: bool
    state: ConfirmationState = ConfirmationState.UNCONFIRMED
    evidence: Evidence | None = None
    #: Set when the value was computed from another field rather than read.
    derived_from: str | None = None

    @property
    def confirmed(self) -> bool:
        return self.state in (ConfirmationState.CONFIRMED, ConfirmationState.CORRECTED)

    def confirm(self) -> DetectedField:
        """10.13. A reviewer accepts the detected value as it stands."""
        if self.value is None:
            raise ValueError(
                f"{self.name} has no detected value to confirm; correct it instead (10.13)"
            )
        return replace(self, state=ConfirmationState.CONFIRMED)

    def correct(self, value: str) -> DetectedField:
        """10.13/10.32. A reviewer supplies or replaces the value."""
        if not value or not value.strip():
            raise ValueError(f"{self.name} cannot be corrected to an empty value")
        return replace(self, state=ConfirmationState.CORRECTED, value=value.strip())

    def describe(self) -> str:
        shown = self.value if self.value is not None else "(not detected)"
        flag = "required" if self.required else "optional"
        where = (
            f" [p{self.evidence.page_number} via {self.evidence.detector}]" if self.evidence else ""
        )
        return f"{self.name:22} {self.state.value:12} {flag:8} {shown}{where}"


@dataclass(frozen=True)
class DetectedMetadata:
    """The 10.10 field set for one document."""

    fields: dict[str, DetectedField]

    def __getitem__(self, name: str) -> DetectedField:
        return self.fields[name]

    @property
    def unconfirmed_required(self) -> tuple[str, ...]:
        """What check `VAL-017-002` blocks on (10.13)."""
        return tuple(name for name, f in self.fields.items() if f.required and not f.confirmed)

    @property
    def all_required_confirmed(self) -> bool:
        return not self.unconfirmed_required

    def describe(self) -> str:
        return "\n".join(f.describe() for f in self.fields.values())


# --- detectors --------------------------------------------------------------

_SCALE = re.compile(
    r"(?i)\b(?:in|amounts?\s+in|expressed\s+in|\$\s*in)\s+"
    r"(thousands?|millions?|billions?|tausend|milliarden|millionen|miles|millones)\b"
)
_SCALE_WORDS = {
    "thousand": "thousands",
    "thousands": "thousands",
    "tausend": "thousands",
    "miles": "thousands",
    "million": "millions",
    "millions": "millions",
    "millionen": "millions",
    "millones": "millions",
    "billion": "billions",
    "billions": "billions",
    "milliarden": "billions",
}

_CURRENCY_WORDS = [
    (re.compile(r"(?i)\b(?:u\.?s\.?|united\s+states)\s+dollars?\b"), "USD"),
    (re.compile(r"(?i)\bcanadian\s+dollars?\b"), "CAD"),
    (re.compile(r"(?i)\baustralian\s+dollars?\b"), "AUD"),
    (re.compile(r"(?i)\beuros?\b|\beuro\b"), "EUR"),
    (re.compile(r"(?i)\bpounds?\s+sterling\b|\bpounds?\b"), "GBP"),
    (re.compile(r"(?i)\byen\b"), "JPY"),
    (re.compile(r"(?i)\bswiss\s+francs?\b"), "CHF"),
    (re.compile(r"\bUSD\b"), "USD"),
    (re.compile(r"\bEUR\b"), "EUR"),
    (re.compile(r"\bGBP\b"), "GBP"),
    (re.compile(r"\bJPY\b"), "JPY"),
]

_AUDITED = re.compile(
    r"(?i)report\s+of\s+independent\s+registered\s+public\s+accounting\s+firm"
    r"|independent\s+auditor'?s?\s+report"
    r"|have\s+been\s+audited"
)
_UNAUDITED = re.compile(r"(?i)\bunaudited\b")

_STANDARD = [
    (
        re.compile(r"(?i)\bu\.?s\.?\s*gaap\b|generally\s+accepted\s+accounting\s+principles"),
        "US_GAAP",
    ),
    (re.compile(r"(?i)\bifrs\b|international\s+financial\s+reporting\s+standards"), "IFRS"),
]

_FILING_TYPE = [
    (re.compile(r"(?i)form\s+10-?k\b|\bannual\s+report\b|\bjahresabschluss\b"), "annual"),
    (re.compile(r"(?i)form\s+10-?q\b|\bquarterly\s+report\b|\binterim\s+report\b"), "quarterly"),
]

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))

_PERIOD_END = re.compile(
    r"(?i)(?:fiscal\s+|financial\s+)?year\s+ended\s+"
    r"(?:(?P<m1>" + _MONTH_ALT + r")\s+(?P<d1>\d{1,2}),?\s*(?P<y1>\d{4})"
    r"|(?P<d2>\d{1,2})\s+(?P<m2>" + _MONTH_ALT + r")\s+(?P<y2>\d{4}))"
)

#: A number that only the comma-decimal convention can read, and one that only
#: the dot-decimal convention can read. Counting both across a document is
#: weak evidence -- which is why the result is UNCONFIRMED like everything else.
_ONLY_DOT_DECIMAL = re.compile(r"\b\d{1,3}(?:,\d{3})+\.\d+\b|\b\d{1,3}(?:,\d{3}){2,}\b")
_ONLY_COMMA_DECIMAL = re.compile(r"\b\d{1,3}(?:\.\d{3})+,\d+\b|\b\d{1,3}(?:\.\d{3}){2,}\b")


def _locate(page: pymupdf.Page, text: str) -> BoundingBox | None:
    """Find the matched text on the page so the reviewer sees it highlighted."""
    try:
        hits = page.search_for(text[:60])
    except Exception:  # pragma: no cover - search is best effort
        return None
    if not hits:
        return None
    r = hits[0]
    return BoundingBox.from_parser((r.x0, r.y0, r.x1, r.y1))


def _scan_pages(doc: pymupdf.Document, limit: int) -> list[tuple[int, str, pymupdf.Page]]:
    return [(n + 1, doc[n].get_text(), doc[n]) for n in range(min(limit, doc.page_count))]


def _first_match(pages, pattern, transform, detector, name, *, required=True) -> DetectedField:
    for number, text, page in pages:
        match = pattern.search(text)
        if match:
            value = transform(match)
            if value is None:
                continue
            return DetectedField(
                name=name,
                value=value,
                required=required,
                evidence=Evidence(
                    number, match.group(0).strip(), _locate(page, match.group(0)), detector
                ),
            )
    return DetectedField(name=name, value=None, required=required)


def _largest_span(doc: pymupdf.Document) -> tuple[str, int, BoundingBox] | None:
    """The biggest piece of text on page 1 -- a heuristic, and labelled as one."""
    if not doc.page_count:
        return None
    page = doc[0]
    best: tuple[float, str, tuple] | None = None
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                content = span["text"].strip()
                if len(content) < 3:
                    continue
                if best is None or span["size"] > best[0]:
                    best = (span["size"], content, span["bbox"])
    if best is None:
        return None
    return best[1], 1, BoundingBox.from_parser(best[2])


def detect_metadata(doc: pymupdf.Document) -> DetectedMetadata:
    """Run every detector. Returns UNCONFIRMED fields, never values. 10.10, 10.11."""
    pages = _scan_pages(doc, COVER_PAGES)
    whole = _scan_pages(doc, doc.page_count)
    fields: dict[str, DetectedField] = {}

    # --- company name and title: heuristics, and named as such -------------
    biggest = _largest_span(doc)
    fields["company_name"] = (
        DetectedField(
            "company_name",
            biggest[0],
            required=True,
            evidence=Evidence(1, biggest[0], biggest[2], "largest-font text span on page 1"),
        )
        if biggest
        else DetectedField("company_name", None, required=True)
    )

    pdf_title = (doc.metadata or {}).get("title") or None
    fields["document_title"] = DetectedField(
        "document_title",
        pdf_title,
        required=False,
        evidence=Evidence(0, pdf_title, None, "the PDF's own /Title entry") if pdf_title else None,
    )

    # --- the four load-bearing fields --------------------------------------
    fields["displayed_scale"] = _first_match(
        pages,
        _SCALE,
        lambda m: _SCALE_WORDS.get(m.group(1).lower()),
        "a scale statement such as 'in thousands'",
        "displayed_scale",
    )

    def _currency(text: str, number: int, page) -> DetectedField | None:
        for pattern, code in _CURRENCY_WORDS:
            match = pattern.search(text)
            if match:
                return DetectedField(
                    "reporting_currency",
                    code,
                    required=True,
                    evidence=Evidence(
                        number,
                        match.group(0),
                        _locate(page, match.group(0)),
                        "a currency named in the text",
                    ),
                )
        return None

    currency = None
    for number, text, page in pages:
        currency = _currency(text, number, page)
        if currency:
            break
    fields["reporting_currency"] = currency or DetectedField(
        "reporting_currency", None, required=True
    )

    period = _first_match(
        pages,
        _PERIOD_END,
        _period_end_iso,
        "a 'year ended ...' statement",
        "reporting_period_end",
    )
    fields["reporting_period_end"] = period
    if period.value:
        end = date.fromisoformat(period.value)
        start = _same_day_previous_year(end) + timedelta(days=1)
        fields["reporting_period_start"] = DetectedField(
            "reporting_period_start",
            start.isoformat(),
            required=True,
            evidence=period.evidence,
            derived_from="reporting_period_end, assuming the annual cadence 2.3.b fixes",
        )
        fields["fiscal_year_end"] = DetectedField(
            "fiscal_year_end",
            f"{end.month:02d}-{end.day:02d}",
            required=True,
            evidence=period.evidence,
            derived_from="reporting_period_end",
        )
    else:
        fields["reporting_period_start"] = DetectedField(
            "reporting_period_start", None, required=True
        )
        fields["fiscal_year_end"] = DetectedField("fiscal_year_end", None, required=True)

    audited = _first_match(
        pages,
        _AUDITED,
        lambda m: "audited",
        "an auditor's report or audit statement",
        "audited_status",
    )
    if audited.value is None:
        audited = _first_match(
            pages, _UNAUDITED, lambda m: "unaudited", "the word 'unaudited'", "audited_status"
        )
    fields["audited_status"] = audited

    # --- the two beyond 10.10 ----------------------------------------------
    standard = DetectedField("accounting_standard", None, required=True)
    for pattern, code in _STANDARD:
        found = _first_match(
            pages,
            pattern,
            lambda m, c=code: c,
            "an accounting-standard reference",
            "accounting_standard",
        )
        if found.value:
            standard = found
            break
    fields["accounting_standard"] = standard

    filing = DetectedField("filing_type", None, required=True)
    for pattern, kind in _FILING_TYPE:
        found = _first_match(
            pages, pattern, lambda m, k=kind: k, "a filing-type phrase", "filing_type"
        )
        if found.value:
            filing = found
            break
    fields["filing_type"] = filing

    fields["number_locale"] = _detect_locale(whole)
    return DetectedMetadata(fields=fields)


def _period_end_iso(match: re.Match[str]) -> str | None:
    month_name = match.group("m1") or match.group("m2")
    day = match.group("d1") or match.group("d2")
    year = match.group("y1") or match.group("y2")
    month = _MONTHS.get((month_name or "").lower())
    if not month or not day or not year:
        return None
    try:
        return date(int(year), month, int(day)).isoformat()
    except ValueError:  # pragma: no cover - e.g. "February 30"
        return None


def _same_day_previous_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:  # 29 February
        return value.replace(year=value.year - 1, day=28)


def _detect_locale(pages) -> DetectedField:
    """Count numbers only one convention can read. Weak evidence, stated as such."""
    dot = comma = 0
    example_page = None
    example_text = ""
    for number, text, _page in pages:
        dot_hits = _ONLY_DOT_DECIMAL.findall(text)
        comma_hits = _ONLY_COMMA_DECIMAL.findall(text)
        dot += len(dot_hits)
        comma += len(comma_hits)
        if example_page is None and (dot_hits or comma_hits):
            example_page = number
            example_text = (dot_hits or comma_hits)[0]

    if dot and not comma:
        value, detector = "dot_decimal", f"{dot} number(s) only the 1,234.56 convention can read"
    elif comma and not dot:
        value, detector = (
            "comma_decimal",
            f"{comma} number(s) only the 1.234,56 convention can read",
        )
    else:
        return DetectedField(
            "number_locale",
            None,
            required=True,
            evidence=Evidence(
                example_page or 0,
                example_text,
                None,
                f"inconclusive: {dot} dot-decimal and {comma} comma-decimal indicators",
            )
            if example_page
            else None,
        )

    return DetectedField(
        "number_locale",
        value,
        required=True,
        evidence=Evidence(example_page or 0, example_text, None, detector),
    )
