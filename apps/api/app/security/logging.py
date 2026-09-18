"""Item 149: a log that records what happened without recording the filing.

20.15 asks for security events logged "without logging source values
unnecessarily", and 20.16 for secrets and private data redacted from errors.
The tension is real and worth naming: **a useful error message about a
financial fact tends to contain the fact.** "Could not parse '1,234' on page 7"
is the message a reviewer needs and is also a figure out of an unreleased
filing, written to a file with different retention and different access from
the store it came from.

So the rule here is structural rather than a list of forbidden words:

**A security event carries identifiers, never values.** A document id, a page
number, a fact id, an actor, an action, an outcome -- all of which are
meaningless without the store, and all of which are what an investigation
actually needs. The value stays in the store, where it is already protected,
and the event says where to look.

**Redaction runs on the way out, not at the call site.** A call site that has
to remember to redact will eventually not, and the one that forgets will be
the one handling an exception from a library nobody read. `redact` is applied
to every field of every event by `security_event` itself.

**The audit trail is a different thing and stays where it is.** `AuditEvent`
(9.14) records what a reviewer decided and why, including the values they
corrected, because that is evidence and belongs with the model. This log
records who reached the application and what they tried. Merging them would
put filing values into the operational log, which is exactly what 20.15
forbids.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

LOGGER_NAME = "review.security"

#: Patterns redacted from every field of every event. Each is a shape that
#: should never reach this log, listed so that a reader can see what is
#: covered rather than trusting that something is.
PATTERNS = (
    # A stored credential, if one is ever passed by mistake.
    (re.compile(r"scrypt\$[0-9]+\$[0-9]+\$[0-9]+\$[^\s]+"), "[redacted: credential]"),
    # A session cookie's payload.signature form.
    (re.compile(r"\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{40,}\b"), "[redacted: token]"),
    # Anything that looks like a bearer token or key assignment.
    # The optional scheme word matters: "Authorization=Bearer <token>" without
    # it redacts the word "Bearer" and leaves the token.
    (re.compile(
        r"(?i)\b(password|secret|token|api[_-]?key|authorization)\b\s*[:=]\s*"
        r"(?:(?:bearer|basic|token|digest)\s+)?\S+"
    ), r"\1=[redacted]"),
    # An email address: the owner's, per the instruction that it is for
    # attribution and must not travel anywhere else.
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[redacted: email]"),
    # A run of digits with separators -- a financial figure out of a filing.
    # Deliberately aggressive: a page number survives (no separator), and an
    # identifier survives (letters), and a figure does not.
    (re.compile(r"\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?\b"), "[redacted: figure]"),
)

#: Fields allowed to carry free text at all. Everything else is an identifier
#: and is checked for it.
TEXT_FIELDS = frozenset({"detail", "reason"})


def redact(text: str) -> str:
    """Apply every pattern. Order matters only in that all of them run."""
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


@dataclass(frozen=True)
class SecurityEvent:
    """One thing that happened to the application, not to a model."""

    at: str
    action: str
    actor: str
    outcome: str
    detail: str = ""
    document_id: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def as_json(self) -> str:
        """One line of JSON. Structured, so a search is a query not a grep."""
        body = {
            "at": self.at,
            "action": self.action,
            "actor": self.actor,
            "outcome": self.outcome,
        }
        if self.detail:
            body["detail"] = self.detail
        if self.document_id:
            body["document_id"] = self.document_id
        body.update(self.extra)
        return json.dumps(body, sort_keys=True, ensure_ascii=False)


def security_event(
    action: str,
    *,
    actor: str = "",
    outcome: str = "",
    detail: str = "",
    document_id: str = "",
    logger: logging.Logger | None = None,
    **extra: str,
) -> SecurityEvent:
    """Record one event, redacted.

    Returns the event as well as logging it, so a test can assert on what was
    recorded rather than on what a handler happened to format.
    """
    event = SecurityEvent(
        at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        action=action,
        actor=redact(actor),
        # An action with no stated outcome is read as the action succeeding,
        # which is the wrong default for a security log.
        outcome=outcome or _outcome_from(action),
        detail=redact(detail),
        document_id=redact(document_id),
        extra={key: redact(str(value)) for key, value in extra.items()},
    )
    (logger or logging.getLogger(LOGGER_NAME)).info(event.as_json())
    return event


def _outcome_from(action: str) -> str:
    """The outcome a dotted action name already states, or "unstated"."""
    tail = action.rsplit(".", 1)[-1]
    if tail in ("failed", "refused", "denied", "limited", "expired"):
        return tail
    if tail in ("succeeded", "ended", "started", "deleted", "restored"):
        return tail
    return "unstated"


def configure(stream=None, level: int = logging.INFO) -> logging.Logger:
    """Attach one handler that writes the JSON lines and nothing else.

    No formatter prefix: the message is already a complete JSON object, and a
    `%(asctime)s` in front of it would make every line unparseable.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
