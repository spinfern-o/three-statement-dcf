"""Items 53 and 56: split, combine, and the approval that gates verification.

11.4: "When one raw line contains multiple concepts, keep it combined unless
the PDF notes provide a defensible split."
11.5: "When multiple raw lines map to one normalized line, show the
aggregation."
11.10/11.11: record proposed versus approved, and require approval before the
historical model is Verified.

The shape of every function here is the same as everywhere else in this
repository: it takes the current state, refuses if the change would be
unjustifiable, and otherwise returns a new state with an audit entry. Nothing
mutates.

Two refusals carry real weight:

**A split must account for the whole value, exactly.** 11.4 permits dividing
one raw line across several canonical lines only when the notes defend it, so
this requires the basis in words AND requires the parts to sum to the printed
figure with no remainder. A split that loses 3 units has invented a
reconciling difference that no filing contains.

**A mapping that would double-count cannot be approved.** 11.6 says *prevent*,
not *report*. `checks.duplicate_counting` finds them; this refuses to approve
one, so the prevention is structural rather than advisory.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation

from model.numeric import D, PrecisionError

from ..extraction.jobs import FactVerificationState
from ..extraction.records import AuditEvent, ExtractionResult, ReportedFact
from .chart import line_item
from .checks import duplicate_counting
from .proposals import explain_no_proposal, infer_sign, propose
from .normalized import statement_of_fact
from .sets import (
    FactMapping,
    MappingError,
    MappingSet,
    MappingType,
    SignNormalization,
    manual,
    proposal,
)


def _mappings(result: ExtractionResult) -> MappingSet:
    current = result.mappings
    if current is None:
        return MappingSet.empty()
    if not isinstance(current, MappingSet):  # pragma: no cover - defensive
        raise MappingError(f"expected a MappingSet, found {type(current).__name__}")
    return current


def _fact(result: ExtractionResult, fact_id: str) -> ReportedFact:
    for fact in result.facts:
        if fact.id == fact_id:
            return fact
    raise MappingError(f"no fact {fact_id!r} in document {result.document.id}")


def _sign(fact: ReportedFact, code: str, override: "bool | None", amount=None):
    """11.8. Infer the flip from the chart's convention unless told otherwise.

    A filing printing "(300,000)" for SG&A has printed an expense as negative;
    the chart stores operating expenses POSITIVE and subtracts them. Leaving
    that to the caller to remember is how a whole statement ends up with its
    operating costs added to its gross profit -- so the default is to work it
    out, and an explicit `flip_sign` overrides it.
    """
    if override is not None:
        return SignNormalization.NEGATED if override else SignNormalization.AS_PRINTED
    return infer_sign(code, fact.value if amount is None else amount)


def _require_note(note: str, what: str) -> str:
    text = (note or "").strip()
    if not text:
        raise MappingError(
            f"a reviewer note is required to {what} (7.4.e). 11.3 maps a raw "
            f"line to a canonical one only when their definitions align, and "
            f"the note is where you say that they do."
        )
    return text


def _commit(
    result: ExtractionResult,
    mappings: MappingSet,
    *,
    actor: str,
    action: str,
    entity_id: str,
    detail: str,
) -> ExtractionResult:
    event = AuditEvent.create(
        actor=actor,
        action=action,
        entity_type="FactMapping",
        entity_id=entity_id,
        detail=f"{detail} [mapping set v{mappings.version}]",
    )
    return replace(result, mappings=mappings, audit=result.audit + (event,))


# --- item 51 applied: propose for everything --------------------------------

def propose_all(result: ExtractionResult, *, actor: str = "system") -> ExtractionResult:
    """Run the proposer over every undecided fact. Proposes; approves nothing."""
    current = _mappings(result)
    already = current.mapped_fact_ids
    new: list[FactMapping] = []
    unmatched = 0

    for fact in result.facts:
        if fact.id in already:
            continue
        if fact.verification_status is FactVerificationState.REJECTED:
            continue
        statement = statement_of_fact(result, fact)
        candidates = propose(fact.raw_label, statement=statement, value=fact.value)
        if not candidates:
            unmatched += 1
            continue
        best = candidates[0]
        new.append(
            proposal(
                fact_id=fact.id,
                code=best.code,
                rule=best.rule,
                score=best.score,
                note=f"system proposal: {best.rule}",
                sign_normalization=best.sign_normalization,
            )
        )

    if not new:
        return result
    mappings = current.add(
        *new, actor=actor, reason=f"proposed {len(new)} mapping(s); {unmatched} unmatched"
    )
    return _commit(
        result, mappings, actor=actor, action="propose_mappings",
        entity_id=result.document.id,
        detail=(
            f"{len(new)} mapping(s) proposed, {unmatched} fact(s) matched no rule and "
            f"were left unmapped (rule 1.3)"
        ),
    )


def proposals_for(result: ExtractionResult, fact: ReportedFact):
    """The ranked candidates for one fact, for the review table."""
    statement = statement_of_fact(result, fact)
    return propose(fact.raw_label, statement=statement, value=fact.value)


def why_no_proposal(result: ExtractionResult, fact: ReportedFact) -> str:
    return explain_no_proposal(fact.raw_label, statement_of_fact(result, fact))


# --- the ordinary mapping ---------------------------------------------------

def map_fact(
    result: ExtractionResult,
    fact_id: str,
    canonical_code: str,
    *,
    actor: str,
    note: str,
    flip_sign: bool | None = None,
) -> ExtractionResult:
    """Map one raw line to one canonical line. 11.3.

    `flip_sign` defaults to None, which means "work it out from the chart's
    expected sign" (11.8). Pass True or False to override.
    """
    note = _require_note(note, "map a fact")
    fact = _fact(result, fact_id)
    line_item(canonical_code)
    _refuse_if_fact_rejected(fact)

    mapping = manual(
        fact_id=fact_id,
        code=canonical_code,
        note=note,
        sign_normalization=_sign(fact, canonical_code, flip_sign),
    )
    mappings = _mappings(result).replace_fact(
        fact_id, mapping, actor=actor, reason=f"mapped {fact.raw_label!r} to {canonical_code}"
    )
    return _commit(
        result, mappings, actor=actor, action="map_fact", entity_id=mapping.id,
        detail=f"{fact.raw_label!r} {fact.period_label} -> {canonical_code}: {note}",
    )


# --- item 53: split ---------------------------------------------------------

def split_fact(
    result: ExtractionResult,
    fact_id: str,
    allocations: "list[tuple[str, str]]",
    *,
    basis: str,
    actor: str,
    note: str,
) -> ExtractionResult:
    """Divide one raw line across several canonical lines. 11.4.

    `allocations` is [(canonical_code, decimal string), ...]. The amounts must
    sum to the printed value exactly. `basis` is the disclosure that defends
    the split -- 11.4 permits a split only when the notes provide one.
    """
    note = _require_note(note, "split a fact")
    basis = (basis or "").strip()
    if not basis:
        raise MappingError(
            "a split needs the disclosure it rests on. 11.4: keep a multi-concept "
            "line combined UNLESS the notes provide a defensible split -- name "
            "the note, or leave the line combined."
        )

    fact = _fact(result, fact_id)
    _refuse_if_fact_rejected(fact)
    if fact.value is None:
        raise MappingError(
            f"{fact.raw_label!r} has no parsed value ({fact.raw_value!r}), so there "
            f"is nothing to divide. Resolve the value in source review first."
        )
    if len(allocations) < 2:
        raise MappingError("a split needs at least two canonical lines to split across")

    parsed: list[tuple[str, Decimal]] = []
    for code, amount in allocations:
        line_item(code)
        try:
            parsed.append((code, D(str(amount).strip(), what=f"the allocation to {code}")))
        except (PrecisionError, InvalidOperation, ValueError) as exc:
            raise MappingError(f"{amount!r} is not a decimal amount: {exc}") from exc

    codes = [code for code, _ in parsed]
    if len(set(codes)) != len(codes):
        raise MappingError("a split allocates to each canonical line once, not twice")

    total = sum((amount for _, amount in parsed[1:]), parsed[0][1])
    if total != fact.value:
        raise MappingError(
            f"the allocation sums to {total}, and {fact.raw_label!r} is "
            f"{fact.value}. A split must account for the whole printed value "
            f"exactly -- a remainder of {fact.value - total} is a reconciling "
            f"difference the filing does not contain."
        )

    mappings_for_fact = [
        manual(
            fact_id=fact_id,
            code=code,
            note=note,
            mapping_type=MappingType.SPLIT,
            allocation_amount=amount,
            allocation_basis=basis,
            sign_normalization=_sign(fact, code, None, amount=amount),
        )
        for code, amount in parsed
    ]
    mappings = _mappings(result).replace_fact(
        fact_id, *mappings_for_fact, actor=actor,
        reason=f"split {fact.raw_label!r} across {len(parsed)} lines",
    )
    breakdown = ", ".join(f"{code}={amount}" for code, amount in parsed)
    return _commit(
        result, mappings, actor=actor, action="split_fact", entity_id=fact_id,
        detail=f"{fact.raw_label!r} {fact.period_label} split {breakdown}; basis: {basis}",
    )


# --- item 53: combine -------------------------------------------------------

def combine_facts(
    result: ExtractionResult,
    fact_ids: "list[str]",
    canonical_code: str,
    *,
    actor: str,
    note: str,
    flip_sign: bool | None = None,
) -> ExtractionResult:
    """Map several raw lines onto one canonical line. 11.5.

    The aggregation is *shown*, not hidden: each contributing fact keeps its
    own mapping row, so the normalized value lists what went into it.
    """
    note = _require_note(note, "combine facts")
    line_item(canonical_code)
    if len(fact_ids) < 2:
        raise MappingError("combining needs at least two facts")

    facts = [_fact(result, fact_id) for fact_id in fact_ids]
    for fact in facts:
        _refuse_if_fact_rejected(fact)

    periods = {fact.period_label for fact in facts}
    if len(periods) > 1:
        raise MappingError(
            f"these facts span {sorted(periods)}. Rule 1.7 forbids mixing periods; "
            f"combine within one period and repeat for the others."
        )

    mappings_for_facts = [
        manual(
            fact_id=fact.id,
            code=canonical_code,
            note=note,
            mapping_type=MappingType.AGGREGATE,
            sign_normalization=_sign(fact, canonical_code, flip_sign),
        )
        for fact in facts
    ]
    mappings = _mappings(result)
    for fact, mapping in zip(facts, mappings_for_facts):
        mappings = mappings.replace_fact(
            fact.id, mapping, actor=actor,
            reason=f"aggregated {fact.raw_label!r} into {canonical_code}",
        )
    labels = ", ".join(repr(f.raw_label) for f in facts)
    return _commit(
        result, mappings, actor=actor, action="combine_facts", entity_id=canonical_code,
        detail=f"{labels} -> {canonical_code} for {facts[0].period_label}: {note}",
    )


# --- reject -----------------------------------------------------------------

def reject_mapping(
    result: ExtractionResult, fact_id: str, *, actor: str, note: str
) -> ExtractionResult:
    """This fact is not a statement line. It takes no part in the model."""
    note = _require_note(note, "reject a mapping")
    fact = _fact(result, fact_id)
    mapping = manual(
        fact_id=fact_id, code=_nearest_code(result, fact), note=note,
        mapping_type=MappingType.REJECTED,
    )
    mappings = _mappings(result).replace_fact(
        fact_id, mapping, actor=actor, reason=f"rejected the mapping of {fact.raw_label!r}"
    )
    return _commit(
        result, mappings, actor=actor, action="reject_mapping", entity_id=fact_id,
        detail=f"{fact.raw_label!r} {fact.period_label} maps to nothing: {note}",
    )


def _nearest_code(result: ExtractionResult, fact: ReportedFact) -> str:
    """A rejected mapping still needs a code column; use what was proposed."""
    candidates = proposals_for(result, fact)
    return candidates[0].code if candidates else "revenue"


# --- item 56: approval ------------------------------------------------------

def approve_fact_mapping(
    result: ExtractionResult, fact_id: str, *, actor: str, note: str
) -> ExtractionResult:
    """11.10, 11.11. A human agrees, and only then does verification unblock."""
    note = _require_note(note, "approve a mapping")
    fact = _fact(result, fact_id)
    current = _mappings(result)
    existing = current.for_fact(fact_id)
    if not existing:
        raise MappingError(
            f"{fact.raw_label!r} has no mapping to approve. Map it first, or "
            f"reject it if it is not a statement line."
        )

    problems = [
        finding for finding in duplicate_counting(result, current)
        if fact_id in finding.fact_ids
    ]
    if problems:
        raise MappingError(
            "this mapping would double-count, and 11.6 says prevent it rather "
            "than report it:\n  "
            + "\n  ".join(finding.message for finding in problems)
        )

    mappings = current
    for mapping in existing:
        mappings = mappings.update(
            mapping.approve(actor=actor, note=note), actor=actor,
            reason=f"approved the mapping of {fact.raw_label!r}",
        )
    return _commit(
        result, mappings, actor=actor, action="approve_mapping", entity_id=fact_id,
        detail=(
            f"{fact.raw_label!r} {fact.period_label} -> "
            + ", ".join(m.canonical_code for m in existing)
            + f": {note}"
        ),
    )


def approve_all(result: ExtractionResult, *, actor: str, note: str) -> ExtractionResult:
    """Approve every unapproved mapping that does not double-count."""
    note = _require_note(note, "approve mappings")
    updated = result
    approved = 0
    refused: list[str] = []
    for fact_id in sorted(_mappings(result).mapped_fact_ids):
        if _mappings(updated).is_approved(fact_id):
            continue
        try:
            updated = approve_fact_mapping(updated, fact_id, actor=actor, note=note)
            approved += 1
        except MappingError as exc:
            refused.append(f"{fact_id}: {exc}")
    if refused:
        raise MappingError(
            f"approved {approved} mapping(s) before stopping. "
            f"{len(refused)} could not be approved:\n  " + "\n  ".join(refused)
        )
    return updated


def _refuse_if_fact_rejected(fact: ReportedFact) -> None:
    if fact.verification_status is FactVerificationState.REJECTED:
        raise MappingError(
            f"{fact.raw_label!r} was rejected in source review, so it takes no "
            f"part in the model. Reopen the fact if that was wrong."
        )
