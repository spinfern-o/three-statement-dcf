"""Item 89 and 91: the assumption schema (14.2, 14.3, 14.4).

14.4 lists ten things every assumption must contain. The engine's own
`model/assumptions.py:Assumption` carries four of them -- name, value, a
three-way basis and a source string -- which is enough for a model run by the
person who built it and not enough for one someone else has to review. This is
the fuller record Section 14 asks for, and it is a superset: `to_engine()`
narrows it back down, so there is still exactly one place a number enters the
forecast.

**The evidence rules are the reason this is worth building.** 14.4.f asks for
"source document/page or URL" and 14.4.g for a publication or observation
date. Taken literally those are two more string fields, and an assumption
citing "the 10-K" with no page satisfies them. It should not: STEP 2 makes a
page number the unit of evidence for anything read from a filing, and Phase 3
refuses a fact without a location for the same reason. So the requirement is
per source type:

  Company filing      -> a document and a page. "The 10-K" is not a citation.
  Company guidance    -> a document and page, or a URL, plus the date said.
  External market data-> a URL and an observation date. A beta without the
                         date it was observed is not reproducible, and 2.5's
                         market assumptions are facts about a date.
  Historical driver   -> the periods it was measured over. A DSO of 59.9 days
                         means nothing without saying 59.9 days of which year.
  Analyst assumption  -> a rationale. It has no external evidence by
                         definition, which makes the reasoning the evidence.
  Scenario override   -> the scenario it overrides and what it departs from.

**Self-review is recorded, not refused.** 14.4.i asks for an owner and a
reviewer. This system is single-user, so requiring them to differ would block
every approval. Instead both are required, they may be the same person, and
`is_self_reviewed` says so -- a control weakness named is a control weakness a
reader can weigh, and one refused is a field someone fills in with a second
name they made up.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from model.numeric import D

from ..formula.units import UNITS, UnitError, unit_for


class AssumptionError(ValueError):
    """An assumption is not usable as written, and this says what is missing."""


class Status(str, Enum):
    """14.2's five, and no others."""

    DRAFT = "Draft"
    NEEDS_SOURCE = "Needs Source"
    REVIEWED = "Reviewed"
    APPROVED = "Approved"
    REJECTED = "Rejected"

    @property
    def blocks_calculation(self) -> bool:
        """14.1: a forecast may not calculate on one of these.

        `Draft` and `Needs Source` are work in progress, not answers, and
        `Rejected` is an answer of no. Rule 1.14's shape: an unresolved
        requirement must not pass as resolved.
        """
        return self in (Status.DRAFT, Status.NEEDS_SOURCE, Status.REJECTED)


class SourceType(str, Enum):
    """14.3's six, and no others."""

    COMPANY_GUIDANCE = "Company Guidance"
    COMPANY_FILING = "Company Filing"
    EXTERNAL_MARKET_DATA = "External Market Data"
    HISTORICAL_DRIVER = "Historical Driver"
    ANALYST_ASSUMPTION = "Analyst Assumption"
    SCENARIO_OVERRIDE = "Scenario Override"


#: STEP 10's three categories, which the engine's report groups by. Every one
#: of 14.3's six maps onto exactly one of them, so the fuller vocabulary here
#: does not lose the engine's distinction.
ENGINE_BASIS = {
    SourceType.COMPANY_GUIDANCE: "company_guidance",
    SourceType.COMPANY_FILING: "company_guidance",
    SourceType.EXTERNAL_MARKET_DATA: "external_research",
    SourceType.HISTORICAL_DRIVER: "external_research",
    SourceType.ANALYST_ASSUMPTION: "model_assumption",
    SourceType.SCENARIO_OVERRIDE: "model_assumption",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Evidence:
    """14.4.f and 14.4.g: where the number came from, and when.

    Which of these fields are required depends on the source type; see
    `Assumption._check_evidence`.
    """

    #: The ingested source document this rests on, if any.
    document_id: str = ""
    #: 1-based PDF page. STEP 2's unit of evidence.
    page: int | None = None
    url: str = ""
    #: Publication or observation date, ISO 8601. 14.4.g.
    date: str = ""
    #: For a historical driver: the periods it was measured over.
    measured_over: "tuple[str, ...]" = ()

    def describe(self) -> str:
        parts = []
        if self.document_id:
            parts.append(
                f"{self.document_id} p.{self.page}" if self.page else self.document_id
            )
        if self.url:
            parts.append(self.url)
        if self.measured_over:
            parts.append("measured over " + ", ".join(self.measured_over))
        if self.date:
            parts.append(f"as at {self.date}")
        return " | ".join(parts) or "(no evidence recorded)"


@dataclass(frozen=True)
class Assumption:
    """14.4's ten requirements, as ten groups of fields.

    Immutable. An edit produces a new object with a new `updated_at` and the
    previous one preserved by the register, because 9.14 wants an audit trail
    and a mutable record cannot supply one.
    """

    # a. Code and clear name.
    code: str
    name: str
    # b. Decimal value and unit.
    value: Decimal
    unit: str
    # c. Applicable period(s). Empty means every forecast period.
    periods: "tuple[str, ...]" = ()
    # d. Applicable scenario.
    scenario_id: str = "base"
    # e. Source type.
    source_type: SourceType = SourceType.ANALYST_ASSUMPTION
    # f, g. Source document/page or URL, and its date.
    evidence: Evidence = field(default_factory=Evidence)
    # h. Rationale.
    rationale: str = ""
    # i. Owner and reviewer.
    owner: str = ""
    reviewer: str = ""
    # j. Status and timestamps.
    status: Status = Status.DRAFT
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    #: 14.7: the scenario this was inherited from, if it was.
    inherited_from: str = ""
    #: 14.7 again: set when a scenario overrides an inherited value.
    overrides: str = ""

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise AssumptionError("an assumption needs a code (14.4.a)")
        if not self.name.strip():
            raise AssumptionError(f"{self.code}: an assumption needs a clear name (14.4.a)")
        object.__setattr__(
            self, "value", D(self.value, what=f"assumption {self.code!r} value")
        )
        try:
            unit_for(self.unit)
        except UnitError as exc:
            raise AssumptionError(
                f"{self.code}: {exc} A value without a unit cannot be checked "
                "against the formula that reads it (14.4.b, 18.12)."
            ) from None
        if not isinstance(self.source_type, SourceType):
            raise AssumptionError(
                f"{self.code}: source type must be one of "
                f"{[s.value for s in SourceType]} (14.3)"
            )
        if not isinstance(self.status, Status):
            raise AssumptionError(
                f"{self.code}: status must be one of {[s.value for s in Status]} (14.2)"
            )
        if not self.owner.strip():
            raise AssumptionError(f"{self.code}: an assumption needs an owner (14.4.i)")
        if not self.rationale.strip():
            raise AssumptionError(
                f"{self.code}: an assumption needs a rationale (14.4.h). "
                "14.5: do not hide assumptions inside formulas -- a number with "
                "no stated reasoning is hidden wherever it is written."
            )
        self._check_evidence()

    # --- 14.4.f, 14.4.g, per source type ------------------------------------
    def _check_evidence(self) -> None:
        kind, evidence = self.source_type, self.evidence

        def need(condition: bool, what: str, why: str) -> None:
            if not condition:
                raise AssumptionError(f"{self.code}: {what} ({kind.value}). {why}")

        if kind is SourceType.COMPANY_FILING:
            need(
                bool(evidence.document_id) and evidence.page is not None,
                "a source document and page are required",
                "STEP 2 makes the page the unit of evidence for anything read "
                "from a filing; 'the 10-K' is not a citation a reviewer can check.",
            )
        elif kind is SourceType.COMPANY_GUIDANCE:
            need(
                (bool(evidence.document_id) and evidence.page is not None)
                or bool(evidence.url),
                "a document and page, or a URL, are required",
                "Guidance is a thing a company said somewhere on a date.",
            )
            need(
                bool(evidence.date),
                "the date the guidance was given is required",
                "Guidance is superseded; a figure with no date cannot be known "
                "to be current (14.4.g).",
            )
        elif kind is SourceType.EXTERNAL_MARKET_DATA:
            need(bool(evidence.url), "a URL is required", "2.5's market assumptions "
                 "must be reproducible, and a number with no source is not.")
            need(
                bool(evidence.date),
                "an observation date is required",
                "A beta or a risk-free rate is a fact about a date, and the same "
                "field observed a month later is a different number.",
            )
        elif kind is SourceType.HISTORICAL_DRIVER:
            need(
                bool(evidence.measured_over),
                "the periods it was measured over are required",
                "A DSO of 59.9 days means nothing without saying 59.9 days of "
                "which year -- and whether it was one year or an average of "
                "three changes what it is (13.1.e).",
            )
        elif kind is SourceType.SCENARIO_OVERRIDE:
            need(
                bool(self.overrides),
                "the assumption it overrides is required",
                "14.7: a copied scenario must retain inherited assumption "
                "lineage, and an override with no lineage has thrown it away.",
            )

    # --- reading ------------------------------------------------------------
    @property
    def key(self) -> "tuple[str, str, tuple[str, ...]]":
        return (self.scenario_id, self.code, self.periods)

    @property
    def applies_to_every_period(self) -> bool:
        return not self.periods

    def applies_to(self, period: str) -> bool:
        return self.applies_to_every_period or period in self.periods

    @property
    def is_self_reviewed(self) -> bool:
        """14.4.i. Recorded rather than refused; see the module docstring."""
        return bool(self.reviewer) and self.reviewer.strip() == self.owner.strip()

    @property
    def is_inherited(self) -> bool:
        return bool(self.inherited_from)

    @property
    def engine_basis(self) -> str:
        return ENGINE_BASIS[self.source_type]

    def describe(self) -> str:
        scope = ", ".join(self.periods) if self.periods else "all forecast periods"
        return (
            f"{self.code} [{self.scenario_id}/{scope}] = {self.value} {self.unit} "
            f"-- {self.source_type.value}: {self.evidence.describe()} "
            f"[{self.status.value}]"
        )

    def with_status(self, status: Status, reviewer: str = "") -> "Assumption":
        return replace(
            self,
            status=status,
            reviewer=reviewer or self.reviewer,
            updated_at=_now(),
        )

    def with_value(self, value) -> "Assumption":
        return replace(self, value=value, updated_at=_now())


#: The units an assumption may declare, from the formula engine's vocabulary.
#: Shared deliberately: an assumption declaring `percent` and a formula
#: expecting `ratio` is the factor-of-100 error 18.12 exists to catch, and it
#: can only be caught if both sides speak one vocabulary.
ASSUMPTION_UNITS = tuple(sorted(UNITS))
