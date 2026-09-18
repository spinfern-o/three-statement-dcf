"""Item 134: the audit log, filterable.

9.14 and 10.33 have produced an `AuditEvent` on every mutation since Phase 3:
who, what, which entity, when, and the reason they typed. Nothing read them
back except a count. This makes the log a thing a person can search, which is
the difference between a record and an archive.

The filters are the four questions somebody actually asks of an audit log --
who did this, what kind of thing happened, to which entity, and in what
window -- and they compose, because the useful question is usually two of them
at once ("what did I change on the balance sheet yesterday").

**Ordering is newest first and stable.** Two events in the same second are
ordered by their id, which is monotonic within a document, so a log read twice
reads the same way. A log whose order drifts is one nobody can cite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..extraction.records import AuditEvent


@dataclass(frozen=True)
class Filters:
    """The four questions, composable."""

    actor: str = ""
    action: str = ""
    entity_type: str = ""
    entity_id: str = ""
    since: str = ""
    until: str = ""
    #: Free text, matched against the reason the actor typed.
    text: str = ""

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.actor,
                self.action,
                self.entity_type,
                self.entity_id,
                self.since,
                self.until,
                self.text,
            )
        )

    def describe(self) -> str:
        parts = []
        for label, value in (
            ("actor", self.actor),
            ("action", self.action),
            ("entity type", self.entity_type),
            ("entity", self.entity_id),
            ("since", self.since),
            ("until", self.until),
            ("text", self.text),
        ):
            if value:
                parts.append(f"{label} {value!r}")
        return ", ".join(parts) if parts else "no filter"


def _when(event) -> datetime:
    return event.at


def _matches(event, filters: Filters) -> bool:
    if filters.actor and filters.actor.lower() not in event.actor.lower():
        return False
    if filters.action and filters.action != event.action:
        return False
    if filters.entity_type and filters.entity_type != event.entity_type:
        return False
    if filters.entity_id and filters.entity_id not in event.entity_id:
        return False
    if filters.text and filters.text.lower() not in event.detail.lower():
        return False
    stamp = event.at.isoformat()
    if filters.since and stamp < filters.since:
        return False
    if filters.until and stamp > filters.until:
        return False
    return True


@dataclass(frozen=True)
class Log:
    events: tuple[AuditEvent, ...]
    filters: Filters
    #: How many events exist before filtering, so a reader knows what was hidden.
    total: int

    @property
    def actors(self) -> tuple[str, ...]:
        return tuple(sorted({e.actor for e in self.events}))

    @property
    def hidden(self) -> int:
        return self.total - len(self.events)


def filter_events(result, filters: Filters | None = None) -> Log:
    """9.14's events, newest first, narrowed by whichever filters were given."""
    filters = filters or Filters()
    events = list(result.audit)
    matching = [event for event in events if _matches(event, filters)]
    matching.sort(key=lambda e: (_when(e), e.id), reverse=True)
    return Log(tuple(matching), filters, len(events))


def choices(result) -> dict[str, tuple[str, ...]]:
    """The values actually present, so the filter controls offer real options.

    A select populated from a fixed list offers filters that match nothing;
    one populated from the data cannot.
    """
    events = result.audit
    return {
        "actor": tuple(sorted({e.actor for e in events})),
        "action": tuple(sorted({e.action for e in events})),
        "entity_type": tuple(sorted({e.entity_type for e in events})),
    }
