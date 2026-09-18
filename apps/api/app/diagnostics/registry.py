"""Item 131: Section 17's thirty checks, as data.

`docs/validation-policy.md` catalogued all thirty in Phase 2 -- a stable code,
the clause, what each one compares, a severity, and what the engine did about
it at the time. This module is that registry as code, **generated from the
document** so the two cannot drift, and a test regenerates it and asserts they
still agree.

**The severity column is the open question, and it is stated as one.**
Section 17 supplies four levels -- CRITICAL blocks calculation and export,
ERROR blocks release, WARNING permits release with an acknowledged rationale,
INFO is informational -- and assigns none of the thirty checks to a level.
Only five are forced by a rule elsewhere in the specification, each with its
citation; the other twenty-five are proposals awaiting the owner. A rule counts
as forcing only when it states a consequence -- block calculation, block
release, do not compute -- because that is what fixes a level. A rule that
merely uses the word "critical" does not, which is F-26. That is
finding **F-4**, and item 137 ("prevent release when CRITICAL/ERROR checks
remain") cannot be built on a proposal without saying so.

So `Check.forced` is carried on every row, `is_proposal` is its inverse, and
the release gate in `release.py` reads both rather than treating a proposed
severity as settled.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """Section 17's four levels, in its own words."""

    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

    @property
    def meaning(self) -> str:
        return {
            "CRITICAL": "calculation and export are blocked",
            "ERROR": "the model cannot be released",
            "WARNING": "the model may be released only with an acknowledged rationale",
            "INFO": "informational",
        }[self.value]

    @property
    def blocks_release(self) -> bool:
        """137: release is prevented while a CRITICAL or ERROR check remains."""
        return self in (Severity.CRITICAL, Severity.ERROR)

    @property
    def tone(self) -> str:
        return {
            "CRITICAL": "danger", "ERROR": "danger",
            "WARNING": "warning", "INFO": "neutral",
        }[self.value]


@dataclass(frozen=True)
class Check:
    """One row of the Section 17 registry."""

    code: str
    #: The specification clause, e.g. "17.8".
    clause: str
    severity: Severity
    #: True when a rule elsewhere in the specification forces this severity.
    forced: bool
    #: What that rule is, when one exists.
    forced_by: str = ""
    #: What the check compares, in a sentence.
    compares: str = ""

    @property
    def is_proposal(self) -> bool:
        """F-4. A severity nobody ratified is a severity, not a decision."""
        return not self.forced


#: Generated from docs/validation-policy.md section 4. A test regenerates this
#: and fails if the two disagree, because a registry that drifts from the
#: document describing it is worse than either alone.
REGISTRY: tuple[Check, ...] = (
    Check(
        code="VAL-017-001",
        clause="17.1",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "A SourceDocument.immutable_hash exists and matches a rehash "
            "of the stored bytes"
        ),
    ),
    Check(
        code="VAL-017-002",
        clause="17.2",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Every required metadata field is CONFIRMED, not UNCONFIRMED "
            "(10.11–10.13)"
        ),
    ),
    Check(
        code="VAL-017-003",
        clause="17.3",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Every period resolves to one unambiguous basis and date "
            "range (1.7, 10.24)"
        ),
    ),
    Check(
        code="VAL-017-004",
        clause="17.4",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "reporting_currency and displayed_scale are confirmed for "
            "every document (1.9, 1.10)"
        ),
    ),
    Check(
        code="VAL-017-005",
        clause="17.5",
        severity=Severity.CRITICAL,
        # F-26: 1.14 forbids an unresolved *critical* error appearing as PASS.
        # It presupposes that some checks are critical; it does not say which.
        # A word in common with 17.5's "critical fact" is not a forcing rule.
        forced=False,
        compares=(
            "Every critical fact has verification_status = VERIFIED per "
            "[source-policy.md](source-policy.md) §9"
        ),
    ),
    Check(
        code="VAL-017-006",
        clause="17.6",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Every FactMapping has approved_by set (11.10–11.11)"
        ),
    ),
    Check(
        code="VAL-017-007",
        clause="17.7",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "No source fact contributes to a subtotal both directly and "
            "through a component (11.6)"
        ),
    ),
    Check(
        code="VAL-017-008",
        clause="17.8",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "total_assets = total_liabilities + total_equity, every "
            "historical period"
        ),
    ),
    Check(
        code="VAL-017-009",
        clause="17.9",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "cash_(t−1) + CFO + CFI + CFF = cash_t, historical"
        ),
    ),
    Check(
        code="VAL-017-010",
        clause="17.10",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Every reported subtotal equals its mapped components (11.7, "
            "12.4.i)"
        ),
    ),
    Check(
        code="VAL-017-011",
        clause="17.11",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "SCH-PPE-01 ending balance = ppe_net on the balance sheet"
        ),
    ),
    Check(
        code="VAL-017-012",
        clause="17.12",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "SCH-INTANGIBLES ending balance = intangibles on the balance "
            "sheet (13.3)"
        ),
    ),
    Check(
        code="VAL-017-013",
        clause="17.13",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "SCH-DEBT-01 ending balance = debt on the balance sheet"
        ),
    ),
    Check(
        code="VAL-017-014",
        clause="17.14",
        severity=Severity.WARNING,
        forced=False,
        compares=(
            "Tax schedule reconciles where data permits (13.6)"
        ),
    ),
    Check(
        code="VAL-017-015",
        clause="17.15",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Equity schedule reconciles (13.7)"
        ),
    ),
    Check(
        code="VAL-017-016",
        clause="17.16",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "total_assets = total_liabilities + total_equity, every "
            "forecast period"
        ),
    ),
    Check(
        code="VAL-017-017",
        clause="17.17",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "cash_(t−1) + CFO + CFI + CFF = cash_t, forecast"
        ),
    ),
    Check(
        code="VAL-017-018",
        clause="17.18",
        severity=Severity.CRITICAL,
        forced=True,
        forced_by="14.1: 'No forecast may calculate until all required assumptions have a status'",
        compares=(
            "No required forecast assumption is missing (14.1)"
        ),
    ),
    Check(
        code="VAL-017-019",
        clause="17.19",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "No assumption with status = Rejected is used (14.2)"
        ),
    ),
    Check(
        code="VAL-017-020",
        clause="17.20",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "No hardcoded number inside a forecast formula (1.17)"
        ),
    ),
    Check(
        code="VAL-017-021",
        clause="17.21",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "The formula graph contains no cycles (18.4–18.6)"
        ),
    ),
    Check(
        code="VAL-017-022",
        clause="17.22",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "DCF FCFF equals the three-statement FCFF bridge"
        ),
    ),
    Check(
        code="VAL-017-023",
        clause="17.23",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Every WACC component has a source **and a date**"
        ),
    ),
    Check(
        code="VAL-017-024",
        clause="17.24",
        severity=Severity.CRITICAL,
        forced=True,
        forced_by="16.16, 1.18",
        compares=(
            "WACC > terminal_growth"
        ),
    ),
    Check(
        code="VAL-017-025",
        clause="17.25",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Every enterprise-to-equity adjustment is sourced (16.19)"
        ),
    ),
    Check(
        code="VAL-017-026",
        clause="17.26",
        severity=Severity.CRITICAL,
        forced=True,
        forced_by="16.20",
        compares=(
            "Diluted shares are nonzero and sourced before per-share "
            "value is shown"
        ),
    ),
    Check(
        code="VAL-017-027",
        clause="17.27",
        severity=Severity.CRITICAL,
        forced=True,
        forced_by="17.27; 4.4",
        compares=(
            "No NaN, Infinity or null in a released calculation"
        ),
    ),
    Check(
        code="VAL-017-028",
        clause="17.28",
        severity=Severity.ERROR,
        forced=True,
        forced_by="4.20",
        compares=(
            "Primary and independent benchmark results meet the Section 4 "
            "tolerance (4.15–4.16)"
        ),
    ),
    Check(
        code="VAL-017-029",
        clause="17.29",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Every displayed rounded value ties to its full-precision "
            "stored value (4.18, 4.19)"
        ),
    ),
    Check(
        code="VAL-017-030",
        clause="17.30",
        severity=Severity.ERROR,
        forced=False,
        compares=(
            "Every released output has source and formula lineage (24.12)"
        ),
    ),)

BY_CODE = {check.code: check for check in REGISTRY}
BY_CLAUSE = {check.clause: check for check in REGISTRY}

#: F-4, as a number a screen can show.
PROPOSED = tuple(check for check in REGISTRY if check.is_proposal)
FORCED = tuple(check for check in REGISTRY if check.forced)


def check(code: str) -> Check:
    if code not in BY_CODE:
        raise KeyError(f"{code!r} is not a Section 17 check")
    return BY_CODE[code]
