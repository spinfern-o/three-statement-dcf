"""Items 66 and 67: the historical checks, and the rule about differences.

12.4 lists what a historical build must verify. 12.5 and STEP 6 say the same
thing twice: **keep differences visible; do not plug**. Everything here
reports and nothing here adjusts.

These are the *historical* half of the engine's STEP 37 panel. The engine's
own `run_all_checks` needs a forecast and a valuation, which do not exist at
this stage; these run on the two or three ledgers a filing gives you, and
they use the engine's `Tolerance` and `CheckResult` so a reviewer reads one
vocabulary rather than two.

A check that cannot run returns SKIP with the reason. That distinction
carries real weight: a cash-flow reconciliation on a filing whose cash flow
statement was never extracted is not a pass, and reporting it as one is the
failure rule 1.14 names.
"""

from __future__ import annotations

from model import accounts
from model.checks import CheckResult, Status, Tolerance
from model.statements import Ledger

from .build import BuiltStatements


def _result(name: str, status: Status, detail: str = "") -> CheckResult:
    return CheckResult(name, status, detail)


def balance_sheet_balances(built: BuiltStatements, tol: Tolerance) -> CheckResult:
    """12.4.a / check 17.8. A = L + E, on the reported figures.

    Cash is not a plug here any more than it is in the forecast: the three
    totals come from the filing, and whether they agree is a real question.
    """
    name = "Historical balance sheet balances (17.8)"
    ledger = built.ledgers[accounts.Statement.BALANCE]
    checked, failures = 0, []

    for year in built.years:
        assets = ledger.get(accounts.TOTAL_ASSETS, year)
        liabilities = ledger.get(accounts.TOTAL_LIABILITIES, year)
        equity = ledger.get(accounts.TOTAL_EQUITY, year)
        if assets is None or liabilities is None or equity is None:
            continue
        checked += 1
        if not tol.close(assets, liabilities + equity):
            delta = assets - (liabilities + equity)
            failures.append(
                f"{year}: assets {assets:,} vs liabilities + equity "
                f"{liabilities + equity:,}, out by {delta:,}"
            )

    if not checked:
        return _result(
            name,
            Status.SKIP,
            "no year reports all three of total assets, total liabilities and total equity",
        )
    if failures:
        return _result(
            name,
            Status.FAIL,
            "; ".join(failures) + " -- find the mapping error, do not plug it (STEP 6)",
        )
    return _result(name, Status.PASS, f"{checked} year(s) balance")


def cash_reconciles(built: BuiltStatements, tol: Tolerance) -> CheckResult:
    """12.4.b / check 17.9. cash(t-1) + CFO + CFI + CFF = cash(t)."""
    name = "Historical cash flow reconciliation (17.9)"
    balance = built.ledgers[accounts.Statement.BALANCE]
    cashflow = built.ledgers[accounts.Statement.CASHFLOW]
    checked, failures = 0, []

    for earlier, later in zip(built.years, built.years[1:]):
        opening = balance.get(accounts.CASH, earlier)
        closing = balance.get(accounts.CASH, later)
        cfo = cashflow.get(accounts.CFO, later)
        cfi = cashflow.get(accounts.CFI, later)
        cff = cashflow.get(accounts.CFF, later)
        # Each named rather than `any(f is None for f in flows)`: both guard
        # the same thing, and only this form shows that the three values added
        # below are present.
        if opening is None or closing is None or cfo is None or cfi is None or cff is None:
            continue
        checked += 1
        expected = opening + cfo + cfi + cff
        if not tol.close(expected, closing):
            failures.append(
                f"{later}: {opening:,} + the three subtotals gives {expected:,}, "
                f"and the balance sheet reports {closing:,}"
            )

    if not checked:
        return _result(
            name,
            Status.SKIP,
            "no consecutive pair of years has both an opening and closing cash "
            "balance and all three cash-flow subtotals. A filing whose cash flow "
            "statement was not extracted cannot pass this, and reporting it as a "
            "pass would be rule 1.14's failure",
        )
    if failures:
        return _result(name, Status.FAIL, "; ".join(failures) + " -- do not plug it")
    return _result(name, Status.PASS, f"{checked} year(s) reconcile")


def subtotals_reconcile(built: BuiltStatements, tol: Tolerance) -> CheckResult:
    """12.4.i / check 17.10, through the engine's own `Ledger.cross_check`."""
    name = "Reported subtotals reconcile (17.10)"
    discrepancies = []
    compared = 0
    for ledger in built.ledgers.values():
        found = ledger.cross_check(rel_tol=tol.rel, abs_tol=tol.abs)
        compared += _comparable(ledger, built.years)
        discrepancies.extend(found)

    if not compared:
        return _result(name, Status.SKIP, "no subtotal is both reported and derivable")
    if discrepancies:
        return _result(
            name,
            Status.FAIL,
            "; ".join(str(d) for d in discrepancies)
            + " -- a subtotal disagreeing with its own components is usually a "
            "mapping error, not a rounding one",
        )
    return _result(
        name, Status.PASS, f"{compared} reported subtotal(s) agree with their components"
    )


def _comparable(ledger: Ledger, years) -> int:
    count = 0
    for code, (plus, minus) in accounts.DERIVED.items():
        for year in years:
            if not ledger.has(code, year):
                continue
            required = [c for c in plus + minus if c not in accounts.OPTIONAL_IN_DERIVATION]
            if all(ledger.has(c, year) for c in required):
                count += 1
    return count


def net_income_links(built: BuiltStatements, tol: Tolerance) -> CheckResult:
    """The same figure is printed on two statements. They should agree."""
    name = "Net income linkage (IS -> CF)"
    income = built.ledgers[accounts.Statement.INCOME]
    cashflow = built.ledgers[accounts.Statement.CASHFLOW]
    checked, failures = 0, []

    for year in built.years:
        on_income = income.get(accounts.NET_INCOME, year)
        on_cashflow = cashflow.get(accounts.NET_INCOME, year)
        if on_income is None or on_cashflow is None:
            continue
        checked += 1
        if not tol.close(on_income, on_cashflow):
            failures.append(f"{year}: {on_income:,} vs {on_cashflow:,}")

    if not checked:
        return _result(name, Status.SKIP, "net income is not mapped on both statements")
    if failures:
        return _result(name, Status.FAIL, "; ".join(failures))
    return _result(name, Status.PASS, f"{checked} year(s) tie")


def every_cell_is_cited(built: BuiltStatements, tol: Tolerance) -> CheckResult:
    """Acceptance criterion 24.3: every value links to a page and a location.

    This is cheap to check and impossible to satisfy by accident, which makes
    it worth checking: a cell with no citation means something was written
    into the statements by a path that did not come from a filing.
    """
    name = "Every historical cell cites a page (24.3)"
    missing = []
    for statement, ledger in built.ledgers.items():
        for year in built.years:
            for code in ledger.accounts_present(year):
                cell = ledger._cells[(code, year)]
                if cell.origin != "reported" or cell.source is None or cell.source.page is None:
                    missing.append(f"{statement.value} {code} {year}")
    if missing:
        return _result(name, Status.FAIL, ", ".join(missing[:5]))
    total = sum(
        len(ledger.accounts_present(y)) for ledger in built.ledgers.values() for y in built.years
    )
    return _result(
        name, Status.PASS, f"{total} cell(s), each with a document, page and reported label"
    )


def verification_is_complete(built: BuiltStatements, tol: Tolerance) -> CheckResult:
    """11.11 / check 17.5. The historical model is Verified only if this."""
    name = "Every historical cell is VERIFIED (17.5, 11.11)"
    if built.unverified:
        shown = ", ".join(f"{code} {year}" for code, year in built.unverified[:5])
        return _result(
            name,
            Status.FAIL,
            f"{len(built.unverified)} cell(s) rest on facts that have not met all "
            f"seven conditions of source-policy.md §9: {shown}",
        )
    return _result(name, Status.PASS, "every cell rests on a verified, approved-mapped fact")


HISTORICAL_CHECKS = (
    verification_is_complete,
    every_cell_is_cited,
    balance_sheet_balances,
    cash_reconciles,
    subtotals_reconcile,
    net_income_links,
)


def run_historical_checks(
    built: BuiltStatements, tolerance: Tolerance | None = None
) -> tuple[CheckResult, ...]:
    """12.4. Every check, in reading order. Differences reported, never plugged."""
    tol = tolerance or Tolerance()
    return tuple(check(built, tol) for check in HISTORICAL_CHECKS)


def summarize(results: tuple[CheckResult, ...]) -> str:
    counts = {status: sum(1 for r in results if r.status is status) for status in Status}
    return f"{counts[Status.PASS]} PASS   {counts[Status.FAIL]} FAIL   {counts[Status.SKIP]} SKIP"
