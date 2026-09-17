"""Item 132: source-to-output lineage, and 17.30's claim that it exists.

The chain this application can actually show, end to end:

    a page of the filing
      -> a located ReportedFact with its printed label and raw text
        -> a human decision (accept, correct or reject) with a written reason
          -> an approved FactMapping onto a canonical line
            -> a Cell in the engine's ledger, carrying a Figure and a Source
              -> a forecast cell whose basis names the driver that produced it
                -> an FCFF year, a discount factor, an enterprise value

`trace` walks it in either direction. Forwards from a page answers "what did
this page become"; backwards from a canonical line answers "where did this
number come from", which is the question 24.12 and 17.30 are really about.

**The chain stops being per-fact at the forecast.** A projected cell rests on
the whole last actual year plus a driver, not on one page, and pretending
otherwise would be a lineage that looks more precise than it is. So the
forward chain reports the join explicitly: this is the last reported figure,
this is the driver, and everything after it descends from both.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from model.accounts import Statement


@dataclass(frozen=True)
class Step:
    """One link in the chain, and what it rests on."""

    stage: str
    label: str
    detail: str
    #: The specification clause that makes this step reviewable.
    rule: str = ""


@dataclass(frozen=True)
class Trace:
    """Everything behind one canonical line in one period."""

    code: str
    period: str
    statement: str
    steps: "tuple[Step, ...]" = field(default_factory=tuple)
    #: Set when the chain cannot be completed, with the reason.
    incomplete: str = ""

    @property
    def is_complete(self) -> bool:
        return not self.incomplete


def trace(result, built, code: str, period: str) -> Trace:
    """Walk one value back to the page it was printed on."""
    statement = _statement_for(code)
    ledger = built.ledgers.get(statement) if built is not None else None
    cell = ledger.cell(code, period) if ledger is not None else None

    if cell is None:
        return Trace(
            code=code, period=period, statement=statement.value,
            incomplete=(
                f"{code} has no value for {period}. An absent line has no "
                "lineage, and inventing one would be the failure 17.30 exists "
                "to catch."
            ),
        )

    steps = [
        Step(
            "value", f"{code} {period}", f"{cell.value:,}",
            rule="9.12 CalculatedValue",
        ),
        Step("origin", cell.origin, cell.cite(), rule="17.30"),
    ]

    if cell.origin != "reported":
        steps.append(
            Step(
                "derivation", "computed, not transcribed",
                cell.basis or "no basis recorded",
                rule="18.10",
            )
        )
        return Trace(code, period, statement.value, tuple(steps))

    # Reported: walk back through the mapping to the facts and their pages.
    contributors = _contributors(result, code, period, statement)
    if not contributors:
        return Trace(
            code=code, period=period, statement=statement.value,
            steps=tuple(steps),
            incomplete=(
                "this cell is marked reported and no approved mapping points at "
                "it, which should be impossible -- it means the ledger and the "
                "mapping set disagree."
            ),
        )

    for fact in contributors:
        location = result.location(fact.source_location_id)
        steps.append(
            Step(
                "fact", fact.raw_label or "(no printed label)",
                f"printed as {fact.raw_value!r}"
                + (f" on page {location.page_number}" if location else ""),
                rule="10.x, STEP 4",
            )
        )
        decision = fact.decision
        steps.append(
            Step(
                "decision",
                decision.action if decision else "undecided",
                f"{decision.actor}: {decision.reason}" if decision else
                "nobody has decided this fact",
                rule="10.32",
            )
        )
    return Trace(code, period, statement.value, tuple(steps))


def _statement_for(code: str) -> Statement:
    from model import accounts

    for statement, names in (
        (Statement.INCOME, accounts.INCOME_ACCOUNTS),
        (Statement.BALANCE, accounts.BALANCE_ACCOUNTS),
        (Statement.CASHFLOW, accounts.CASHFLOW_ACCOUNTS),
    ):
        if code in names:
            return statement
    raise KeyError(f"{code!r} is not a canonical line")


def _contributors(result, code: str, period: str, statement: Statement):
    """The facts whose approved mappings produced this cell."""
    from ..mapping.chart import StatementType
    from ..mapping.normalized import normalize

    chart_statement = {
        Statement.INCOME: StatementType.INCOME,
        Statement.BALANCE: StatementType.BALANCE,
        Statement.CASHFLOW: StatementType.CASHFLOW,
    }[statement]

    ledger = normalize(result)
    raw_period = period[:-1] if period.endswith(("A", "E")) else period
    value = ledger.get((code, raw_period, chart_statement))
    if value is None:
        return ()
    by_id = {fact.id: fact for fact in result.facts}
    return tuple(by_id[fid] for fid in value.contributors if fid in by_id)


def traceable_lines(built) -> "tuple[tuple[str, str, str], ...]":
    """Every `(statement, code, period)` this model can trace."""
    if built is None:
        return ()
    out = []
    for statement, ledger in built.ledgers.items():
        for period in built.years:
            for code in ledger.accounts_present(period):
                out.append((statement.value, code, period))
    return tuple(out)
