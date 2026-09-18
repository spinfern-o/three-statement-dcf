"""Items 54 and 55: duplicate-count prevention and subtotal reconciliation.

11.6: "Prevent double counting of components and subtotals."
11.7: "Preserve reported totals as separate validation targets."
10.30: "Require manual review for every value that fails a subtotal or
cross-statement reconciliation."

These are the checks that turn `SUBTOTAL_MISMATCH` and
`CROSS_STATEMENT_MISMATCH` from enum members into findings. Both codes were
defined in Phase 3 and never raised, for a reason that is worth stating: a
subtotal has nothing to reconcile against until its components are mapped.
Mapping is what gives them something to disagree about.

**A mismatch is never corrected here.** 12.4's instruction and STEP 6's are
the same one: report the difference, do not plug it. A difference between a
reported total and the sum of its mapped components is usually a mapping
error -- a line filed under the wrong canonical code, or one counted twice --
and silently adjusting either side destroys the evidence that would find it.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from decimal import Decimal

from model import accounts
from model.checks import Tolerance
from model.numeric import relative_error

from ..extraction.reasons import ReasonCode
from ..extraction.records import ExtractionResult
from .chart import StatementType, in_sum_relationship, line_item
from .normalized import normalize, statement_of_fact
from .sets import MappingSet, MappingType


@dataclass(frozen=True)
class Finding:
    """One reconciliation or double-count failure, and who is implicated."""

    code: ReasonCode
    canonical_code: str
    period_label: str
    message: str
    fact_ids: tuple[str, ...]
    expected: Decimal | None = None
    actual: Decimal | None = None

    def describe(self) -> str:
        return f"[{self.code.value}] {self.canonical_code} {self.period_label}: {self.message}"


# --- item 54: 11.6 ----------------------------------------------------------


def duplicate_counting(
    result: ExtractionResult, mappings: MappingSet | None = None
) -> tuple[Finding, ...]:
    """Find every way the mappings would count one figure twice."""
    mapping_set = mappings if mappings is not None else result.mappings
    if mapping_set is None:
        return ()

    facts = {f.id: f for f in result.facts}
    findings: list[Finding] = []

    # (a) One fact mapped to two codes where one is counted inside the other.
    by_fact: dict[str, list] = {}
    for mapping in mapping_set.mappings:
        if mapping.contributes:
            by_fact.setdefault(mapping.reported_fact_id, []).append(mapping)

    for fact_id, mapped in by_fact.items():
        fact = facts.get(fact_id)
        if fact is None:
            continue
        codes = [m.canonical_code for m in mapped]
        for i, first in enumerate(codes):
            for second in codes[i + 1 :]:
                if first == second:
                    findings.append(
                        Finding(
                            code=ReasonCode.DOUBLE_COUNTED,
                            canonical_code=first,
                            period_label=fact.period_label,
                            message=(
                                f"{fact.raw_label!r} is mapped to {first} twice. "
                                f"A split divides a value across DIFFERENT lines; "
                                f"two mappings to one line add it up twice."
                            ),
                            fact_ids=(fact_id,),
                        )
                    )
                elif in_sum_relationship(first, second):
                    inner, outer = (
                        (first, second) if second in _ancestors(first) else (second, first)
                    )
                    findings.append(
                        Finding(
                            code=ReasonCode.DOUBLE_COUNTED,
                            canonical_code=outer,
                            period_label=fact.period_label,
                            message=(
                                f"{fact.raw_label!r} is mapped to both {inner} and "
                                f"{outer}, and {inner} is already counted inside "
                                f"{outer}. Mapping it to both adds it twice (11.6)."
                            ),
                            fact_ids=(fact_id,),
                        )
                    )

    # (b) Two facts on one canonical line and period, not declared an aggregate.
    grouped: dict[tuple[str, str], list] = {}
    for mapping in mapping_set.mappings:
        fact = facts.get(mapping.reported_fact_id)
        if fact is None or not mapping.contributes:
            continue
        grouped.setdefault((mapping.canonical_code, fact.period_label), []).append((fact, mapping))

    for (code, period), pairs in grouped.items():
        if len(pairs) < 2:
            continue
        if all(m.mapping_type is MappingType.AGGREGATE for _, m in pairs):
            continue  # 11.5: declared, and the aggregation is shown
        if _is_cross_statement_duplicate(result, code, pairs):
            continue  # net income on two statements: a check, not a double count
        labels = ", ".join(sorted({f"{f.raw_label!r}" for f, _ in pairs}))
        findings.append(
            Finding(
                code=ReasonCode.DOUBLE_COUNTED,
                canonical_code=code,
                period_label=period,
                message=(
                    f"{len(pairs)} facts map to {code} for {period} ({labels}) "
                    f"without being declared an aggregate. 11.5 requires an "
                    f"aggregation be shown as one; otherwise this is two "
                    f"figures added where one was reported."
                ),
                fact_ids=tuple(f.id for f, _ in pairs),
            )
        )

    return tuple(findings)


def _ancestors(code: str) -> frozenset[str]:
    from .chart import ancestors

    return ancestors(code)


def _is_cross_statement_duplicate(result, code: str, pairs) -> bool:
    """`net_income` is printed on two statements. That is a linkage, not a sum."""
    if len(line_item(code).statement_types) < 2:
        return False
    statements = {statement_of_fact(result, fact) for fact, _ in pairs}
    statements.discard(None)
    return len(statements) > 1


# --- item 55: 11.7, 12.4.i --------------------------------------------------


def subtotal_reconciliation(
    result: ExtractionResult,
    mappings: MappingSet | None = None,
    tolerance: Tolerance | None = None,
) -> tuple[Finding, ...]:
    """Compare every reported subtotal against the sum of its mapped components."""
    tol = tolerance or Tolerance()
    ledger = normalize(result, mappings)
    findings: list[Finding] = []

    for code, (plus, minus) in accounts.DERIVED.items():
        # The subtotal's own statement governs the whole derivation. Deriving
        # operating cash flow uses the cash flow statement's net income;
        # deriving net income uses the income statement's. Same code, two
        # printings, and picking the wrong one compares a figure to itself.
        statement = _derivation_statement(code)
        for period in sorted({key[1] for key in ledger}):
            reported = ledger.get((code, period, statement))
            if reported is None or reported.value is None:
                continue  # nothing reported: 11.7's target is absent, not failed

            terms: list[Decimal] = []
            missing: list[str] = []
            for component in plus:
                value = _term(ledger, component, period, statement, missing)
                if value is not None:
                    terms.append(value)
            for component in minus:
                value = _term(ledger, component, period, statement, missing)
                if value is not None:
                    terms.append(-value)
            if missing:
                continue  # STEP 5: an absent component is unknown, not zero
            if not terms:
                # Not one component mapped. This module's first line says a
                # subtotal has nothing to reconcile against until its
                # components are mapped, and this is that case -- reachable
                # only for a derivation whose every term is optional, which
                # `operating_expenses` became when 12.1.d's categories were
                # added. Summing no terms to zero would report the whole
                # reported subtotal as a discrepancy against a figure nobody
                # supplied, which is rule 1.3's prohibition wearing a
                # reconciliation's clothes.
                continue

            derived = sum(terms[1:], terms[0])
            if tol.close(reported.value, derived):
                continue

            error = relative_error(derived, reported.value)
            findings.append(
                Finding(
                    code=ReasonCode.SUBTOTAL_MISMATCH,
                    canonical_code=code,
                    period_label=period,
                    message=(
                        f"the filing reports {reported.value:,} and its mapped "
                        f"components sum to {derived:,}, a difference of "
                        f"{reported.value - derived:,} ({error}% relative). "
                        f"Do not plug it -- a subtotal that disagrees with its "
                        f"components is usually a line mapped to the wrong "
                        f"canonical code, or one mapped twice."
                    ),
                    fact_ids=reported.contributors
                    + tuple(
                        fid
                        for component in plus + minus
                        for fid in _contributors(ledger, component, period, statement)
                    ),
                    expected=derived,
                    actual=reported.value,
                )
            )
    return tuple(findings)


def _derivation_statement(code: str) -> StatementType:
    """Where a subtotal's derivation is defined. `net_income` is the income
    statement's, even though it is also printed on the cash flow statement."""
    types = line_item(code).statement_types
    return types[0] if len(types) == 1 else StatementType.INCOME


def _term(ledger, code: str, period: str, statement, missing: list[str]) -> Decimal | None:
    entry = ledger.get((code, period, statement))
    if entry is None or entry.value is None:
        if code not in accounts.OPTIONAL_IN_DERIVATION:
            missing.append(code)
        return None
    return entry.value


def _contributors(ledger, code: str, period: str, statement) -> tuple[str, ...]:
    entry = ledger.get((code, period, statement))
    return entry.contributors if entry else ()


# --- cross-statement: 17.9 and the net-income linkage -----------------------

_YEAR = re.compile(r"^(19|20)\d{2}$")


def cross_statement_reconciliation(
    result: ExtractionResult,
    mappings: MappingSet | None = None,
    tolerance: Tolerance | None = None,
) -> tuple[Finding, ...]:
    """Two checks that need both statements at once.

    The cash roll-forward (`cash_(t-1) + CFO + CFI + CFF = cash_t`) is the
    strongest test in the whole system, because it fails when ANY flow was
    mapped to the wrong side. The net-income linkage is the cheaper one: the
    same figure is printed on two statements, and they should agree.
    """
    tol = tolerance or Tolerance()
    mapping_set = mappings if mappings is not None else result.mappings
    if mapping_set is None:
        return ()
    ledger = normalize(result, mapping_set)
    findings: list[Finding] = []

    findings.extend(_net_income_linkage(ledger, tol))

    years = sorted(p for p in {key[1] for key in ledger} if _YEAR.match(p))
    for earlier, later in itertools.pairwise(years):
        if int(later) != int(earlier) + 1:
            continue
        opening = ledger.get((accounts.CASH, earlier, StatementType.BALANCE))
        closing = ledger.get((accounts.CASH, later, StatementType.BALANCE))
        flows = [
            ledger.get((code, later, StatementType.CASHFLOW))
            for code in (accounts.CFO, accounts.CFI, accounts.CFF)
        ]
        if opening is None or closing is None:
            continue
        # Each flow named, rather than `any(f is None for f in flows)`: both
        # guard the same thing, and only this form lets a checker -- or a
        # reader adding a fourth subtotal -- see that the three values added
        # below are present. An unguarded None here is a TypeError on the
        # first filing that omits a cash-flow subtotal.
        cfo, cfi, cff = flows
        if cfo is None or cfi is None or cff is None:
            continue
        opening_value, closing_value = opening.value, closing.value
        if opening_value is None or closing_value is None:
            continue
        if cfo.value is None or cfi.value is None or cff.value is None:
            continue

        expected = opening_value + cfo.value + cfi.value + cff.value
        if tol.close(expected, closing_value):
            continue
        findings.append(
            Finding(
                code=ReasonCode.CROSS_STATEMENT_MISMATCH,
                canonical_code=accounts.CASH,
                period_label=later,
                message=(
                    f"opening cash {opening_value:,} plus the three {later} cash-flow "
                    f"subtotals gives {expected:,}, but the balance sheet reports "
                    f"{closing_value:,}. A cash roll-forward that does not close "
                    f"means a flow is mapped to the wrong side, or a flow is "
                    f"missing entirely."
                ),
                fact_ids=opening.contributors
                + closing.contributors
                + tuple(fid for flow in (cfo, cfi, cff) for fid in flow.contributors),
                expected=expected,
                actual=closing_value,
            )
        )
    return tuple(findings)


def _net_income_linkage(ledger, tol) -> list[Finding]:
    """The same figure printed on two statements. They should agree.

    This compares the income statement's net income against the cash flow
    statement's. It is meaningful only because `normalize` keys on the
    statement: grouping them would have made this a comparison of a figure
    with itself, which is a check that cannot fail and therefore is not one.
    """
    findings: list[Finding] = []
    for period in sorted({key[1] for key in ledger}):
        on_income = ledger.get((accounts.NET_INCOME, period, StatementType.INCOME))
        on_cashflow = ledger.get((accounts.NET_INCOME, period, StatementType.CASHFLOW))
        if on_income is None or on_cashflow is None:
            continue
        if on_income.value is None or on_cashflow.value is None:
            continue
        if tol.close(on_income.value, on_cashflow.value):
            continue
        findings.append(
            Finding(
                code=ReasonCode.CROSS_STATEMENT_MISMATCH,
                canonical_code=accounts.NET_INCOME,
                period_label=period,
                message=(
                    f"net income is {on_income.value:,} on the income statement and "
                    f"{on_cashflow.value:,} at the top of the cash flow statement "
                    f"for {period}. The same figure is printed twice and the two "
                    f"readings disagree."
                ),
                fact_ids=on_income.contributors + on_cashflow.contributors,
                expected=on_income.value,
                actual=on_cashflow.value,
            )
        )
    return findings


def all_findings(
    result: ExtractionResult,
    mappings: MappingSet | None = None,
    tolerance: Tolerance | None = None,
) -> tuple[Finding, ...]:
    """Every mapping-level finding, in the order a reviewer should read them."""
    return (
        duplicate_counting(result, mappings)
        + subtotal_reconciliation(result, mappings, tolerance)
        + cross_statement_reconciliation(result, mappings, tolerance)
    )


# --- applying the findings to the facts -------------------------------------


def apply_findings(
    result: ExtractionResult, tolerance: Tolerance | None = None
) -> ExtractionResult:
    """Recompute every mapping finding and write it onto the facts. 10.30, 11.12.

    Recomputed from scratch, not accumulated. That is what 11.12's "invalidate
    dependent model results when changed" means in practice here: a mismatch
    raised against an old mapping must not survive the mapping being fixed, and
    the only way to guarantee that is to derive the whole set each time rather
    than adding to it.

    Idempotent: running it twice on the same state produces the same state.
    """
    from dataclasses import replace

    findings = all_findings(result, tolerance=tolerance)

    codes: dict[str, list[ReasonCode]] = {}
    notes: dict[str, list[str]] = {}
    for finding in findings:
        for fact_id in finding.fact_ids:
            bucket = codes.setdefault(fact_id, [])
            if finding.code not in bucket:
                bucket.append(finding.code)
            notes.setdefault(fact_id, []).append(finding.describe())

    facts = tuple(
        replace(
            fact,
            mapping_codes=tuple(codes.get(fact.id, ())),
            mapping_notes=tuple(notes.get(fact.id, ())),
        )
        for fact in result.facts
    )
    return replace(result, facts=facts)
