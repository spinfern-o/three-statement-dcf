"""Item 57: mapping sets, versioned. Section 9.7's `FactMapping`.

11.12: "Version the mapping set and invalidate dependent model results when
changed."

Both halves are here. A `MappingSet` is immutable: every change returns a new
one with `version` incremented and `supersedes` pointing at the old one, so
"which mapping produced this number" has an answer that survives the next
edit. What the invalidation means in practice is in `checks.py` and in the
verification gate -- a fact whose mapping changed is no longer verified,
because the approval was of a different mapping.

11.10 wants each mapping recorded as system-proposed or human-approved, and
the two are separate fields rather than one status, because they are separate
facts: the machine proposed `operating_expenses`, and a person either agreed
or did not. Collapsing them loses the record of what the machine suggested,
which is the only way to find out later that it suggests the wrong thing.

11.8 wants sign normalization recorded separately from the source sign. A
filing that prints "Purchases of property and equipment 113,400" has printed a
magnitude; this chart stores capex negative. `sign_normalization` records that
flip on the mapping, where a reviewer can see it, rather than silently in the
arithmetic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum

from ..extraction.jobs import utc_now


class MappingType(str, Enum):
    """9.7. How one raw line relates to the canonical line it maps to."""

    #: One raw line, one canonical line. The ordinary case.
    ONE_TO_ONE = "one_to_one"
    #: Several raw lines summed into one canonical line (11.5).
    AGGREGATE = "aggregate"
    #: One raw line divided across several canonical lines (11.4). Permitted
    #: only with an allocation whose parts sum exactly to the printed value.
    SPLIT = "split"
    #: Mapped to nothing, deliberately. A page number, a heading, a memo line.
    REJECTED = "rejected"


class SignNormalization(str, Enum):
    """11.8. Whether the chart's convention differs from what was printed."""

    AS_PRINTED = "as_printed"
    NEGATED = "negated"


class Origin(str, Enum):
    """11.10."""

    SYSTEM_PROPOSED = "system_proposed"
    HUMAN = "human"


class MappingError(Exception):
    """A mapping was refused, and this says why."""


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class FactMapping:
    """Section 9.7. One reported fact, and the canonical line it becomes."""

    id: str
    reported_fact_id: str
    canonical_code: str
    mapping_type: MappingType
    reviewer_note: str
    origin: Origin = Origin.SYSTEM_PROPOSED
    sign_normalization: SignNormalization = SignNormalization.AS_PRINTED
    #: Required when `mapping_type` is SPLIT: this mapping's share of the
    #: printed value, as an exact Decimal. Null otherwise.
    allocation_amount: Decimal | None = None
    #: 9.7's `allocation_formula_optional`. The disclosure a split rests on --
    #: 11.4 permits a split only when "the PDF notes provide a defensible
    #: split", and this is where the reviewer names it.
    allocation_basis: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    #: What the proposer scored this at, kept so a wrong proposal is findable.
    proposal_score: Decimal | None = None
    proposal_rule: str = ""

    @property
    def approved(self) -> bool:
        """11.10, 11.11, check 17.6. What gates verification."""
        return self.approved_by is not None and self.approved_at is not None

    @property
    def contributes(self) -> bool:
        """False for a rejected mapping, which takes no part in a statement."""
        return self.mapping_type is not MappingType.REJECTED

    def approve(self, *, actor: str, note: str) -> FactMapping:
        """11.11. A human agrees. Requires a note (7.4.e)."""
        if not note.strip():
            raise MappingError(
                "approving a mapping requires a note (7.4.e). 11.3 maps a raw "
                "line to a canonical one 'only when definitions align' -- the "
                "note is where you say that they do."
            )
        return replace(
            self,
            origin=Origin.HUMAN,
            reviewer_note=note.strip(),
            approved_by=actor,
            approved_at=utc_now(),
        )

    def describe(self) -> str:
        state = "approved" if self.approved else self.origin.value
        extra = ""
        if self.mapping_type is MappingType.SPLIT:
            extra = f" [{self.allocation_amount} of the printed value]"
        elif self.sign_normalization is SignNormalization.NEGATED:
            extra = " [sign flipped to the chart's convention]"
        return f"{self.canonical_code} ({self.mapping_type.value}, {state}){extra}"


@dataclass(frozen=True)
class MappingSet:
    """A versioned collection. 11.12.

    Never mutated. Every change produces the next version, and the previous
    one remains addressable, because "which mapping produced this number" must
    have an answer after the next edit.
    """

    version: int
    created_at: datetime
    created_by: str
    reason: str
    mappings: tuple[FactMapping, ...] = ()
    supersedes: int | None = None

    @classmethod
    def empty(cls, *, actor: str = "system") -> MappingSet:
        return cls(
            version=1,
            created_at=utc_now(),
            created_by=actor,
            reason="initial empty mapping set",
        )

    # --- reading -----------------------------------------------------------

    def for_fact(self, fact_id: str) -> tuple[FactMapping, ...]:
        """Every mapping of one fact. More than one means a split (11.4)."""
        return tuple(m for m in self.mappings if m.reported_fact_id == fact_id)

    def for_code(self, code: str) -> tuple[FactMapping, ...]:
        return tuple(m for m in self.mappings if m.canonical_code == code and m.contributes)

    def get(self, mapping_id: str) -> FactMapping:
        for mapping in self.mappings:
            if mapping.id == mapping_id:
                return mapping
        raise MappingError(f"no mapping {mapping_id!r} in version {self.version}")

    @property
    def mapped_fact_ids(self) -> frozenset[str]:
        return frozenset(m.reported_fact_id for m in self.mappings)

    @property
    def unapproved(self) -> tuple[FactMapping, ...]:
        """Check 17.6 counts these."""
        return tuple(m for m in self.mappings if not m.approved)

    def is_approved(self, fact_id: str) -> bool:
        """True when this fact has an approved mapping that CONTRIBUTES. 11.11.

        A deliberately rejected mapping can be approved -- "I looked at this
        and it is not a statement line" is a decision worth recording -- but it
        does not make the fact verified. Verification is a claim about a number
        that is in the model, and a rejected line is not in the model.
        """
        mappings = self.for_fact(fact_id)
        contributing = [m for m in mappings if m.contributes]
        return bool(contributing) and all(m.approved for m in mappings)

    def is_excluded(self, fact_id: str) -> bool:
        """True when this fact was mapped to nothing, deliberately."""
        mappings = self.for_fact(fact_id)
        return bool(mappings) and all(not m.contributes for m in mappings)

    # --- writing: each returns the NEXT version ----------------------------

    def _next(self, mappings, *, actor: str, reason: str) -> MappingSet:
        if not reason.strip():
            raise MappingError("a mapping-set version needs a reason (11.12, 10.33)")
        return MappingSet(
            version=self.version + 1,
            created_at=utc_now(),
            created_by=actor,
            reason=reason.strip(),
            mappings=tuple(mappings),
            supersedes=self.version,
        )

    def add(self, *new: FactMapping, actor: str, reason: str) -> MappingSet:
        return self._next(self.mappings + new, actor=actor, reason=reason)

    def replace_fact(self, fact_id: str, *new: FactMapping, actor: str, reason: str) -> MappingSet:
        """Replace every mapping of one fact. The edit path, and the split path."""
        kept = tuple(m for m in self.mappings if m.reported_fact_id != fact_id)
        return self._next(kept + new, actor=actor, reason=reason)

    def update(self, mapping: FactMapping, *, actor: str, reason: str) -> MappingSet:
        self.get(mapping.id)
        swapped = tuple(mapping if m.id == mapping.id else m for m in self.mappings)
        return self._next(swapped, actor=actor, reason=reason)

    def remove_fact(self, fact_id: str, *, actor: str, reason: str) -> MappingSet:
        kept = tuple(m for m in self.mappings if m.reported_fact_id != fact_id)
        if len(kept) == len(self.mappings):
            raise MappingError(f"fact {fact_id!r} has no mappings to remove")
        return self._next(kept, actor=actor, reason=reason)

    def describe(self) -> str:
        return (
            f"mapping set v{self.version}"
            + (f" (supersedes v{self.supersedes})" if self.supersedes else "")
            + f": {len(self.mappings)} mapping(s), "
            f"{len(self.unapproved)} unapproved -- {self.reason}"
        )


def proposal(
    *,
    fact_id: str,
    code: str,
    rule: str,
    score: Decimal,
    note: str,
    sign_normalization: SignNormalization = SignNormalization.AS_PRINTED,
) -> FactMapping:
    """A system proposal: unapproved by construction. 11.10."""
    return FactMapping(
        id=_new_id("map"),
        reported_fact_id=fact_id,
        canonical_code=code,
        mapping_type=MappingType.ONE_TO_ONE,
        reviewer_note=note,
        origin=Origin.SYSTEM_PROPOSED,
        sign_normalization=sign_normalization,
        proposal_score=score,
        proposal_rule=rule,
    )


def manual(
    *,
    fact_id: str,
    code: str,
    note: str,
    mapping_type: MappingType = MappingType.ONE_TO_ONE,
    sign_normalization: SignNormalization = SignNormalization.AS_PRINTED,
    allocation_amount: Decimal | None = None,
    allocation_basis: str | None = None,
) -> FactMapping:
    """A mapping a person made. Still unapproved until they approve it."""
    return FactMapping(
        id=_new_id("map"),
        reported_fact_id=fact_id,
        canonical_code=code,
        mapping_type=mapping_type,
        reviewer_note=note,
        origin=Origin.HUMAN,
        sign_normalization=sign_normalization,
        allocation_amount=allocation_amount,
        allocation_basis=allocation_basis,
    )
