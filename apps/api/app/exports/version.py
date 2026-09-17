"""Item 142: the model version ID, and the timestamp beside it.

21.7: "Every export must include generation timestamp and immutable model
version ID." Two words in that sentence do the work.

**Immutable.** A counter that increments on save is not immutable -- it names
an event, not a state, so two exports can carry the same number and different
numbers, and a reader who re-exports to check a figure has no way to tell
whether the model moved. So the version is a *digest of what the model
contains*: the document's own hash, the approved mapping set, the scenario, the
value and status of every assumption, and the fingerprint of the formulas that
turn them into statements. One changed digit anywhere changes it, and the same
model exported twice a week apart produces the same version both times.

**Model, not document.** The document hash alone would call two different
valuations of the same filing the same version, which is the failure 21.8
exists to prevent: a reader comparing an export against the screen needs to
know the screen is showing the same *model*, not merely the same PDF.

The timestamp is separate and deliberately so. It says when this file was
written; the version says what was in it. Conflating them would make every
export a new version, which is the counter's failure again.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

#: Bumped when the *meaning* of a component changes, so that an old export and
#: a new one of an unchanged model are not silently claimed to be identical.
VERSION_SCHEME = "msv1"

#: Printed wherever a version appears in a fixed-width column.
SHORT = 16


def _digest(*parts: str) -> str:
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ModelVersion:
    """21.7's immutable identifier, and the parts it was computed from."""

    version_id: str
    #: Each `(component, digest_or_value)` that went into it, in order.
    components: "tuple[tuple[str, str], ...]"
    document_hash: str
    scenario_id: str

    @property
    def short(self) -> str:
        return self.version_id[:SHORT]

    def describe(self) -> str:
        return f"{VERSION_SCHEME}:{self.version_id}"


def _assumption_parts(scenarios, scenario_id: str) -> "list[str]":
    """Every resolved assumption, as `code@periods=value:status`, in code order.

    Resolved rather than raw: what the model *is* includes which scenario's
    override won, so two scenarios differing only in one override must not
    produce the same version. `periods` is part of the key because the same
    code scoped to one year and to every year are different assumptions, and
    the engine resolves them by that distinction.
    """
    if scenarios is None:
        return ["assumptions:none"]
    resolved = scenarios.resolve(scenario_id)
    parts = []
    for code in sorted(resolved):
        item = resolved[code].assumption
        periods = ",".join(item.periods) or "all"
        parts.append(f"{code}@{periods}={item.value}:{item.status.value}")
    return parts


def _mapping_part(result) -> str:
    """The approved mapping, digested from the decisions rather than the version.

    `MappingSet.version` increments on every saved set, so it moves when the
    mapping moves -- but it also moves when nothing about the *values* changed
    (a reviewer note, a re-approval), and a version that changes without the
    numbers changing tells a reader the model moved when it did not. So the
    digest is over the fields that can move a figure: which line a fact becomes,
    whether it was split and by how much, whether its sign was flipped, and
    whether a human approved it -- because an unapproved mapping does not reach
    the statements at all.
    """
    mappings = getattr(result, "mappings", None)
    if mappings is None:
        return "mapping:none"
    rows = []
    for mapping in mappings.mappings:
        rows.append(
            "|".join(
                (
                    mapping.reported_fact_id,
                    mapping.canonical_code,
                    mapping.mapping_type.value,
                    "" if mapping.allocation_amount is None else str(mapping.allocation_amount),
                    mapping.sign_normalization.value,
                    "approved" if mapping.approved else "unapproved",
                )
            )
        )
    return f"mapping:{_digest(*sorted(rows))}"


def model_version(
    result,
    scenarios=None,
    scenario_id: str = "base",
    *,
    formula_fingerprint: str = "",
) -> ModelVersion:
    """Compute 21.7's identifier from what this model contains."""
    document_hash = result.document.immutable_hash
    components: "list[tuple[str, str]]" = [
        ("scheme", VERSION_SCHEME),
        ("document", document_hash),
        ("mapping", _mapping_part(result)),
        ("scenario", scenario_id),
        ("assumptions", _digest(*_assumption_parts(scenarios, scenario_id))),
    ]
    if formula_fingerprint:
        components.append(("formulas", formula_fingerprint))
    return ModelVersion(
        version_id=_digest(*(f"{name}={value}" for name, value in components)),
        components=tuple(components),
        document_hash=document_hash,
        scenario_id=scenario_id,
    )


def generated_at(now: datetime | None = None) -> str:
    """21.7's timestamp, in UTC with the offset written out.

    A local timestamp with no offset is the one thing a reader cannot check a
    year later, and an export outlives the machine that wrote it.
    """
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")
