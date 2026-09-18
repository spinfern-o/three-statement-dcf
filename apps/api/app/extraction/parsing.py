"""Item 35: deterministic unit, sign and locale parsing.

This is where rule 1.5 lives, and rule 1.5 is the one most likely to be
violated by accident:

> Never treat a blank, dash, em dash, "N/A," or missing table cell as zero
> unless the source explicitly defines it as zero or a reviewer confirms it.

Every one of those produces `value=None` here, with a blocking reason code.
`None` is never coerced to zero to let something downstream proceed -- that is
the same commitment the sparse `Ledger` in `model/statements.py` makes, one
stage earlier in the pipeline.

Two design rules, both from specification 10.25-10.27:

  1. **The raw string is retained, always.** `ParsedValue.raw_value` is the
     characters as printed, including parentheses, dashes and footnote
     markers. `(1,234)` parses to -1234 AND keeps `"(1,234)"`, because the
     parentheses are the evidence for the sign; discarding the string
     discards the justification.
  2. **Ambiguity is refused, not guessed.** `1,234` is 1234 in the US and
     1.234 in Germany. With the document's locale unconfirmed, this parser
     does not pick. It returns `None` with `SEPARATOR_AMBIGUOUS` and a message
     naming both readings (10.27).

The ambiguity test is mechanical rather than a list of special cases: each
candidate locale is applied independently, and the cell is ambiguous **iff
two candidates both succeed and disagree**. `12` is unambiguous because both
readings give 12. `1,234` is ambiguous because they give 1234 and 1.234.
`1,23` is unambiguous because the US reading is invalid -- a thousands group
must hold exactly three digits.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from model.numeric import D

from .reasons import ReasonCode


class NumberLocale(str, Enum):
    """Which separator convention a document prints its numbers in."""

    #: Not yet confirmed. The parser refuses anything genuinely ambiguous.
    UNKNOWN = "unknown"
    #: `1,234.56` -- comma groups, dot decimal. en-US, en-GB, ja, zh.
    DOT_DECIMAL = "dot_decimal"
    #: `1.234,56` -- dot groups, comma decimal. de, es, it, pt, nl, id.
    COMMA_DECIMAL = "comma_decimal"


class SignSource(str, Enum):
    """Where the sign came from. 10.16 requires parentheses be kept as evidence."""

    POSITIVE_AS_PRINTED = "positive_as_printed"
    LEADING_MINUS = "leading_minus"
    TRAILING_MINUS = "trailing_minus"
    LEADING_PLUS = "leading_plus"
    PARENTHESES = "parentheses"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class UnitMarker(str, Enum):
    NONE = "none"
    CURRENCY = "currency"
    PERCENT = "percent"


#: Every dash a filing might print in a numeric cell. 10.17 requires these be
#: distinguished from zero; they are all treated as unknown until a reviewer or
#: a source legend says otherwise.
DASHES = "-‐‑‒–—―−­"

#: Spaces that are not U+0020. Filings use these as thousands separators and as
#: padding, and a NBSP that survives into the numeric string breaks the parse.
SPACES = "              　"

#: Group separators other than , and . -- Swiss apostrophe and the space forms.
GROUP_CHARS = " '’"

_NOT_APPLICABLE = {
    "n/a",
    "na",
    "n.a.",
    "n.a",
    "not applicable",
    "n/m",
    "nm",
    "n.m.",
    "n.m",
    "not meaningful",
    "not disclosed",
    "not reported",
}

#: source-policy.md: "A written zero is a zero." These spell it in words; the
#: `-0-` form is the accounting convention for a printed nil.
_WRITTEN_ZERO = {"nil", "none", "zero", "-0-", "0-", "-0"}

#: Currency symbols seen at the head or tail of a statement cell.
_CURRENCY_SYMBOLS = "$€£¥₹₩₺₽₦฿₪៛₼"

_SUPERSCRIPTS = "¹²³⁰⁴⁵⁶⁷⁸⁹⁽⁾*†‡§¶"

#: A complete number followed by a parenthesized 1-2 digit group is a number
#: with a footnote marker, not a negative: the number already ended.
_TRAILING_FOOTNOTE = re.compile(r"(?<=[0-9)])\s*\((\d{1,2})\)\s*$")
_TRAILING_SYMBOL_FOOTNOTE = re.compile(rf"(?<=[0-9)])\s*([{re.escape(_SUPERSCRIPTS)}]+)\s*$")

_ISO_CODE = re.compile(r"^(?P<code>[A-Z]{3})\b|\b(?P<tail>[A-Z]{3})$")


@dataclass(frozen=True)
class ParsedValue:
    """The outcome of parsing one cell. 9.5's `raw_value`/`parsed_decimal` pair."""

    raw_value: str
    value: Decimal | None
    sign_source: SignSource = SignSource.NOT_APPLICABLE
    locale_used: NumberLocale = NumberLocale.UNKNOWN
    unit_marker: UnitMarker = UnitMarker.NONE
    currency_symbol: str | None = None
    #: Digits printed after the decimal separator. 4.14 reconciles statements
    #: "to the precision available in the source document"; this is that.
    decimals: int | None = None
    footnote_markers: tuple[str, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    #: Why there is no value, in words a reviewer can act on.
    note: str = ""

    @property
    def is_parsed(self) -> bool:
        return self.value is not None

    @property
    def needs_review(self) -> bool:
        return any(c.blocking for c in self.reason_codes)


#: Full-width forms, folded explicitly. NFKC would do this and more -- and the
#: "more" includes turning the superscript footnote marker in `1,234`+U+00B9
#: into the digit 1, producing 12341 from a number that was 1234. An explicit
#: table folds what needs folding and touches nothing else.
_FULLWIDTH = str.maketrans(
    {
        **{chr(0xFF10 + i): str(i) for i in range(10)},
        "\uff0c": ",",
        "\uff0e": ".",
        "\uff05": "%",
        "\uff08": "(",
        "\uff09": ")",
        "\uff0d": "-",
        "\uff04": "$",
    }
)


def _normalize(text: str) -> str:
    """Fold exotic spaces and full-width forms. Deliberately NOT NFKC."""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_FULLWIDTH)
    for space in SPACES:
        text = text.replace(space, " ")
    return text.strip()


def _strip_footnotes(text: str) -> tuple[str, tuple[str, ...]]:
    """Remove trailing footnote markers, returning them. 10.18."""
    markers: list[str] = []
    changed = True
    while changed:
        changed = False
        match = _TRAILING_SYMBOL_FOOTNOTE.search(text)
        if match:
            markers.append(match.group(1))
            text = text[: match.start()].rstrip()
            changed = True
            continue
        match = _TRAILING_FOOTNOTE.search(text)
        if match:
            markers.append(f"({match.group(1)})")
            text = text[: match.start()].rstrip()
            changed = True
    return text, tuple(reversed(markers))


def _strip_currency(text: str) -> tuple[str, str | None]:
    """Remove a leading or trailing currency symbol or ISO code, returning it."""
    symbol: str | None = None
    for _ in range(3):  # `US$`, `C$`, `CHF ` -- at most a few layers
        stripped = text.strip()
        if not stripped:
            break
        if stripped[0] in _CURRENCY_SYMBOLS:
            symbol = (symbol or "") + stripped[0]
            text = stripped[1:]
            continue
        if stripped[-1] in _CURRENCY_SYMBOLS:
            symbol = (symbol or "") + stripped[-1]
            text = stripped[:-1]
            continue
        match = _ISO_CODE.search(stripped)
        if match:
            code = match.group("code") or match.group("tail")
            remainder = (stripped[: match.start()] + stripped[match.end() :]).strip()
            # Only a currency code if a number is left behind. Otherwise the
            # cell is three letters, and three letters are not a currency just
            # because they are uppercase.
            if code and code.isalpha() and any(ch.isdigit() for ch in remainder):
                symbol = (symbol or "") + code
                text = remainder
                continue
        break
    return text.strip(), symbol


def _interpret(core: str, locale: NumberLocale) -> tuple[str, int] | None:
    """Read `core` under one locale. Returns (decimal string, decimals) or None.

    None means the string is not a valid number under that convention -- which
    is what makes the ambiguity test work.
    """
    if locale is NumberLocale.DOT_DECIMAL:
        group_sep, decimal_sep = ",", "."
    else:
        group_sep, decimal_sep = ".", ","

    text = core
    for ch in GROUP_CHARS:
        text = text.replace(ch, group_sep)

    if not text or any(ch not in f"0123456789{group_sep}{decimal_sep}" for ch in text):
        return None

    if text.count(decimal_sep) > 1:
        return None
    integer_part, found_decimal, fraction = text.partition(decimal_sep)

    if decimal_sep in fraction or group_sep in fraction:
        return None
    if found_decimal and not fraction:
        return None  # a trailing decimal separator with no digits after it

    if group_sep in integer_part:
        groups = integer_part.split(group_sep)
        head, rest = groups[0], groups[1:]
        if not head or len(head) > 3 or not head.isdigit():
            return None
        if any(len(g) != 3 or not g.isdigit() for g in rest):
            return None
        digits = "".join(groups)
    else:
        digits = integer_part
        if digits and not digits.isdigit():
            return None

    if not digits and not fraction:
        return None
    if fraction and not fraction.isdigit():
        return None

    return (f"{digits or '0'}.{fraction}" if fraction else (digits or "0")), len(fraction)


def parse_reported_value(
    raw: str,
    *,
    locale: NumberLocale = NumberLocale.UNKNOWN,
) -> ParsedValue:
    """Parse one table cell as printed. Deterministic; never guesses. 10.25-10.27.

    `locale` is the document's *confirmed* separator convention. Leaving it
    UNKNOWN is the honest state before metadata confirmation (10.11), and the
    parser then refuses anything the two conventions read differently.
    """
    if raw is None:
        return ParsedValue(
            raw_value="",
            value=None,
            reason_codes=(ReasonCode.BLANK_CELL,),
            note="no cell content was supplied",
        )

    text = _normalize(raw)
    if not text:
        return ParsedValue(
            raw_value=raw,
            value=None,
            reason_codes=(ReasonCode.BLANK_CELL,),
            note="the cell is empty. Rule 1.5 forbids reading that as zero.",
        )

    lowered = text.lower().strip(". ")
    if lowered in _WRITTEN_ZERO:
        return ParsedValue(
            raw_value=raw,
            value=D("0"),
            sign_source=SignSource.POSITIVE_AS_PRINTED,
            locale_used=locale,
            decimals=0,
            reason_codes=(ReasonCode.WRITTEN_ZERO,),
            note=f"{text!r} is a written zero, so it is read as 0 (source-policy.md §6).",
        )

    body, footnotes = _strip_footnotes(text)
    body, currency = _strip_currency(body)

    unit = UnitMarker.CURRENCY if currency else UnitMarker.NONE
    if body.endswith("%"):
        body = body[:-1].strip()
        unit = UnitMarker.PERCENT

    stripped = body.strip()
    inner = (
        stripped[1:-1].strip() if stripped.startswith("(") and stripped.endswith(")") else stripped
    )

    if inner and all(ch in DASHES + " " for ch in inner):
        return ParsedValue(
            raw_value=raw,
            value=None,
            currency_symbol=currency,
            unit_marker=unit,
            footnote_markers=footnotes,
            reason_codes=(ReasonCode.DASH_AMBIGUOUS,),
            note=(
                f"the cell holds {inner!r}. A dash in a filing may mean zero, "
                f"blank, or not applicable (10.17). Until the document's legend "
                f"defines it or a reviewer confirms it, it is not a number and "
                f"it is not zero (rule 1.5)."
            ),
        )

    if lowered in _NOT_APPLICABLE or inner.lower().strip(". ") in _NOT_APPLICABLE:
        return ParsedValue(
            raw_value=raw,
            value=None,
            currency_symbol=currency,
            unit_marker=unit,
            footnote_markers=footnotes,
            reason_codes=(ReasonCode.NOT_APPLICABLE,),
            note=f"the cell holds {text!r}, which is not a number and is not zero (rule 1.5).",
        )

    # --- sign ---------------------------------------------------------------
    negative = False
    sign_source = SignSource.POSITIVE_AS_PRINTED
    markers = 0
    core = stripped

    if core.startswith("(") and core.endswith(")"):
        negative, sign_source, markers = True, SignSource.PARENTHESES, markers + 1
        core = core[1:-1].strip()
    if core[:1] in DASHES:
        negative, sign_source, markers = True, SignSource.LEADING_MINUS, markers + 1
        core = core[1:].strip()
    elif core[:1] == "+":
        sign_source, markers = SignSource.LEADING_PLUS, markers + 1
        core = core[1:].strip()
    if core[-1:] in DASHES:
        negative, markers = True, markers + 1
        sign_source = SignSource.TRAILING_MINUS if markers == 1 else sign_source
        core = core[:-1].strip()

    core, more_footnotes = _strip_footnotes(core)
    footnotes = footnotes + more_footnotes
    core, currency_inner = _strip_currency(core)
    currency = currency or currency_inner
    if currency and unit is UnitMarker.NONE:
        unit = UnitMarker.CURRENCY

    if markers > 1:
        return ParsedValue(
            raw_value=raw,
            value=None,
            sign_source=SignSource.UNRESOLVED,
            currency_symbol=currency,
            unit_marker=unit,
            footnote_markers=footnotes,
            reason_codes=(ReasonCode.SIGN_UNRESOLVED,),
            note=(
                f"{text!r} carries {markers} sign markers. Parentheses and a "
                f"minus sign together are a contradiction, not a double "
                f"negative (10.16)."
            ),
        )

    if not core:
        return ParsedValue(
            raw_value=raw,
            value=None,
            currency_symbol=currency,
            unit_marker=unit,
            footnote_markers=footnotes,
            reason_codes=(ReasonCode.NOT_NUMERIC,),
            note=f"{text!r} has no digits once markers are removed.",
        )

    # --- separators ---------------------------------------------------------
    candidates: dict[NumberLocale, tuple[str, int]] = {}
    for candidate in (NumberLocale.DOT_DECIMAL, NumberLocale.COMMA_DECIMAL):
        result = _interpret(core, candidate)
        if result is not None:
            candidates[candidate] = result

    base_codes: tuple[ReasonCode, ...] = ()
    if footnotes:
        base_codes += (ReasonCode.FOOTNOTE_MARKER_STRIPPED,)

    if not candidates:
        return ParsedValue(
            raw_value=raw,
            value=None,
            currency_symbol=currency,
            unit_marker=unit,
            footnote_markers=footnotes,
            reason_codes=base_codes + (ReasonCode.NOT_NUMERIC,),
            note=(
                f"{core!r} is not a number under either separator convention. "
                f"Thousands groups must hold exactly three digits and a number "
                f"may carry at most one decimal separator."
            ),
        )

    if locale is not NumberLocale.UNKNOWN:
        if locale not in candidates:
            other = next(iter(candidates))
            return ParsedValue(
                raw_value=raw,
                value=None,
                currency_symbol=currency,
                unit_marker=unit,
                footnote_markers=footnotes,
                reason_codes=base_codes + (ReasonCode.SEPARATOR_AMBIGUOUS,),
                note=(
                    f"{core!r} is not valid under the document's confirmed "
                    f"{locale.value} convention. It would read as "
                    f"{candidates[other][0]} under {other.value}. The document's "
                    f"locale or this cell is wrong; the parser does not choose (10.27)."
                ),
            )
        chosen, decimals = candidates[locale]
        used: NumberLocale = locale
    else:
        readings = {value for value, _ in candidates.values()}
        if len(readings) > 1:
            both = "; ".join(
                f"{loc.value} reads it as {val}" for loc, (val, _) in sorted(candidates.items())
            )
            return ParsedValue(
                raw_value=raw,
                value=None,
                currency_symbol=currency,
                unit_marker=unit,
                footnote_markers=footnotes,
                reason_codes=base_codes + (ReasonCode.SEPARATOR_AMBIGUOUS,),
                note=(
                    f"{core!r} has no single reading while the document's locale "
                    f"is unconfirmed: {both}. 10.27 sends this to manual review "
                    f"rather than picking one."
                ),
            )
        used = next(iter(candidates)) if len(candidates) == 1 else NumberLocale.UNKNOWN
        chosen, decimals = next(iter(candidates.values()))

    value = D(("-" if negative else "") + chosen, what=f"the cell {raw!r}")
    if negative and sign_source is SignSource.POSITIVE_AS_PRINTED:  # pragma: no cover
        sign_source = SignSource.LEADING_MINUS

    return ParsedValue(
        raw_value=raw,
        value=value,
        sign_source=sign_source,
        locale_used=used,
        unit_marker=unit,
        currency_symbol=currency,
        decimals=decimals,
        footnote_markers=footnotes,
        reason_codes=base_codes,
        note="",
    )
