"""Items 45, 46 and 47: what a reviewer can do to a fact, and what it costs.

Specification 10.32: "Allow correction only with a reviewer note." 10.33:
"Record every acceptance, correction, split, combination, and rejection in the
audit log." Rule 1.13: "Never alter a verified historical value without
creating an audit entry."

Three actions, and the reasoning for each boundary:

**accept** -- the extracted value is right as printed. Permitted only when the
fact has a value. Accepting a fact whose cell held an em dash would be
accepting nothing, and the thing a reviewer actually means in that case is a
*correction* to zero, which is a different action with a different audit
entry. Rule 1.5 allows the dash to become zero only when the source defines it
or a reviewer confirms it -- so the reviewer says so, in words, as a
correction.

**correct** -- supply or replace the value. Takes a decimal string (4.2), never
a float. `parsed` is not overwritten: 10.25 makes the raw string and its parse
evidence, and evidence is not edited. The correction sits beside it.

**reject** -- this is not a usable fact. A page number the table finder caught,
a row that is really a heading. It takes no further part.

**What none of them can do: clear an unconfirmed scale or currency.** Those are
document-level (10.11-10.13) and are confirmed once, on the document, not
fact by fact. Accepting a fact while they are outstanding is refused, because
the number is not yet a number -- it is a number times one thousand, or not.

**Re-deciding is allowed**, and audited. 1.13 asks for the audit entry, not for
the decision to be frozen. The previous decision is named in the new entry.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation

from model.numeric import D, PrecisionError

from ..extraction.jobs import FactVerificationState, utc_now
from ..extraction.records import (
    DOCUMENT_CODES,
    AuditEvent,
    ExtractionResult,
    ReportedFact,
    Resolution,
    ReviewDecision,
)

ACCEPT = "accept"
CORRECT = "correct"
REJECT = "reject"

STATUS_FOR_ACTION = {
    ACCEPT: FactVerificationState.ACCEPTED,
    CORRECT: FactVerificationState.CORRECTED,
    REJECT: FactVerificationState.REJECTED,
}


class ReviewError(Exception):
    """A reviewer action was refused, and this says why."""


def _require_reason(reason: str, action: str) -> str:
    text = (reason or "").strip()
    if not text:
        raise ReviewError(
            f"a reason is required to {action} a fact (10.32). A change with no "
            f"stated basis is indistinguishable from a typo six months later."
        )
    return text


def _find(result: ExtractionResult, fact_id: str) -> ReportedFact:
    for fact in result.facts:
        if fact.id == fact_id:
            return fact
    raise ReviewError(f"no fact {fact_id!r} in document {result.document.id}")


def outstanding_document_codes(fact: ReportedFact) -> tuple:
    """Blocking codes on this fact that only a document-level decision clears."""
    return tuple(c for c in fact.blocking_codes if c in DOCUMENT_CODES)


def _apply(
    result: ExtractionResult,
    fact: ReportedFact,
    *,
    action: str,
    actor: str,
    reason: str,
    corrected_value: Decimal | None = None,
) -> ExtractionResult:
    """Record the decision, resolve the fact-level blocking codes, audit it."""
    now = utc_now()
    previous = fact.decision

    # A rejection does not resolve anything -- the fact is out, not fixed.
    resolutions = fact.resolutions
    if action in (ACCEPT, CORRECT):
        already = set(fact.resolved_codes)
        resolutions = fact.resolutions + tuple(
            Resolution(code=code, actor=actor, note=reason, at=now)
            for code in fact.blocking_codes
            if code not in already and code not in DOCUMENT_CODES
        )

    decision = ReviewDecision(
        action=action,
        actor=actor,
        reason=reason,
        at=now,
        previous_value=fact.parsed.value if action == CORRECT else None,
        new_value=corrected_value if action == CORRECT else None,
    )

    updated = replace(
        fact,
        decision=decision,
        resolutions=resolutions,
        verification_status=STATUS_FOR_ACTION[action],
        corrected_value=corrected_value if action == CORRECT else fact.corrected_value,
        reviewer_id=actor,
    )

    detail = f"{decision.describe()}"
    if previous is not None:
        detail += f" (replacing an earlier decision: {previous.describe()})"
    if resolutions != fact.resolutions:
        cleared = ", ".join(r.code.value for r in resolutions[len(fact.resolutions):])
        detail += f" [resolved: {cleared}]"

    event = AuditEvent.create(
        actor=actor,
        action=f"{action}_fact",
        entity_type="ReportedFact",
        entity_id=fact.id,
        detail=f"{fact.raw_label!r} {fact.period_label}: {detail}",
    )

    facts = tuple(updated if f.id == fact.id else f for f in result.facts)
    return replace(result, facts=facts, audit=result.audit + (event,))


def accept_fact(
    result: ExtractionResult, fact_id: str, *, actor: str, reason: str
) -> ExtractionResult:
    """The value is right as printed. 10.32."""
    reason = _require_reason(reason, "accept")
    fact = _find(result, fact_id)

    if fact.value is None:
        raise ReviewError(
            f"{fact.raw_label!r} {fact.period_label} has no value to accept -- it "
            f"was printed as {fact.raw_value!r}. Rule 1.5 allows that to become a "
            f"number only when the source defines it or a reviewer confirms it, "
            f"so correct it to the value you mean and say why."
        )

    blocked = outstanding_document_codes(fact)
    if blocked:
        names = ", ".join(c.value for c in blocked)
        raise ReviewError(
            f"{names} is outstanding on this document. Scale and currency are "
            f"confirmed once, on the document (10.11-10.13), not fact by fact -- "
            f"until they are, this is a number times one thousand, or not. "
            f"Confirm the metadata first."
        )

    return _apply(result, fact, action=ACCEPT, actor=actor, reason=reason)


def correct_fact(
    result: ExtractionResult, fact_id: str, value: str, *, actor: str, reason: str
) -> ExtractionResult:
    """Supply or replace the value. 10.32.

    `value` is a decimal string. A float is refused by `D()` for the reason
    `model/numeric.py` gives at length: converting one preserves its error
    rather than removing it.
    """
    reason = _require_reason(reason, "correct")
    fact = _find(result, fact_id)

    if isinstance(value, float):
        raise ReviewError(
            f"a corrected value must be a decimal string, not a float "
            f"(specification 4.2). {value!r} would be stored as {Decimal(value)}."
        )
    try:
        corrected = D(str(value).strip(), what=f"the corrected value for {fact.raw_label!r}")
    except (PrecisionError, InvalidOperation, ValueError) as exc:
        raise ReviewError(f"{value!r} is not a decimal value: {exc}") from exc

    return _apply(
        result, fact, action=CORRECT, actor=actor, reason=reason, corrected_value=corrected
    )


def reject_fact(
    result: ExtractionResult, fact_id: str, *, actor: str, reason: str
) -> ExtractionResult:
    """This is not a usable fact. 10.32, 10.33."""
    reason = _require_reason(reason, "reject")
    fact = _find(result, fact_id)
    return _apply(result, fact, action=REJECT, actor=actor, reason=reason)


APPLY = {ACCEPT: accept_fact, CORRECT: correct_fact, REJECT: reject_fact}
