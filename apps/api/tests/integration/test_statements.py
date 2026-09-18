"""Phase 6 end to end: items 59-68, on the three-statement fixture.

Item 68 asks for golden historical-model tests. `GOLDEN` below is that: every
cell of all three statements, as exact decimals, built from a PDF through
extraction, review, mapping and approval. If any stage changes what it
produces, this says which number moved.

The fixture ties -- retained earnings rolls forward, PP&E rolls forward, the
balance sheet balances and cash reconciles. That is deliberate and it is what
makes the checks meaningful: a fixture that does not tie cannot tell a working
check from a broken one.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.app.extraction.records import confirm_metadata
from apps.api.app.review.actions import correct_fact
from apps.api.app.statements.build import BuildError, build_statements, engine_year
from apps.api.app.statements.checks import run_historical_checks, summarize
from apps.api.app.statements.export import ExportError, build_engine_inputs
from apps.api.app.statements.reported import citations, reported_strings
from apps.api.app.statements.views import (
    equity_statement_status,
    statement_view,
)
from model import accounts
from model.checks import Status

D = Decimal

#: Item 68. The golden historical model, as printed in the fixture filing.
GOLDEN = {
    accounts.Statement.INCOME: {
        "revenue": ("1100000", "1250000"),
        "cogs": ("660000", "750000"),
        "gross_profit": ("440000", "500000"),
        "operating_expenses": ("270000", "300000"),
        "ebit": ("170000", "200000"),
        "interest_expense": ("20000", "18000"),
        "pretax_income": ("150000", "182000"),
        "taxes": ("37500", "45500"),
        "net_income": ("112500", "136500"),
    },
    accounts.Statement.BALANCE: {
        "cash": ("142000", "164500"),
        "accounts_receivable": ("180500", "205000"),
        "inventory": ("155000", "160000"),
        "ppe_net": ("588000", "620000"),
        "total_assets": ("1065500", "1149500"),
        "accounts_payable": ("121000", "130000"),
        "debt": ("425000", "400000"),
        "total_liabilities": ("546000", "530000"),
        "common_equity": ("50000", "50000"),
        "retained_earnings": ("469500", "569500"),
        "total_equity": ("519500", "619500"),
    },
    accounts.Statement.CASHFLOW: {
        "net_income": ("112500", "136500"),
        "depreciation_amortization": ("68000", "75000"),
        "change_in_nwc": ("-15000", "-20500"),
        "cash_flow_from_operations": ("165500", "191000"),
        "capex": ("-95000", "-107000"),
        "cash_flow_from_investing": ("-95000", "-107000"),
        "debt_repayment": ("-20000", "-25000"),
        "dividends": ("-30000", "-36500"),
        "cash_flow_from_financing": ("-50000", "-61500"),
    },
}

YEARS = ("2024A", "2025A")


# --- items 59, 60, 61 -------------------------------------------------------


def test_the_years_are_the_ones_the_filing_presents(built):
    assert built.years == YEARS


@pytest.mark.parametrize("statement", list(GOLDEN), ids=lambda s: s.value)
def test_the_golden_historical_model(built, statement):
    """Item 68. Every cell, exact, straight from the PDF."""
    ledger = built.ledgers[statement]
    for code, values in GOLDEN[statement].items():
        for year, expected in zip(YEARS, values):
            actual = ledger.get(code, year)
            assert actual is not None, f"{statement.value} {code} {year} is absent"
            assert actual == D(expected), f"{statement.value} {code} {year}"


@pytest.mark.parametrize("statement", list(GOLDEN), ids=lambda s: s.value)
def test_no_line_appears_that_the_filing_did_not_report(built, statement):
    """STEP 5. A canonical line with no mapped fact stays absent."""
    ledger = built.ledgers[statement]
    for year in YEARS:
        assert set(ledger.accounts_present(year)) == set(GOLDEN[statement])


def test_net_income_is_on_both_statements_and_they_are_separate_cells(built):
    """The duplication is the linkage, not a double count."""
    income = built.ledgers[accounts.Statement.INCOME]
    cashflow = built.ledgers[accounts.Statement.CASHFLOW]
    assert income.get("net_income", "2025A") == cashflow.get("net_income", "2025A")
    assert income._cells[("net_income", "2025A")].source.page == 2
    assert cashflow._cells[("net_income", "2025A")].source.page == 4


def test_every_cell_carries_a_page_and_the_companys_own_wording(built):
    """STEP 4 and acceptance criterion 24.3."""
    for _statement, ledger in built.ledgers.items():
        for year in YEARS:
            for code in ledger.accounts_present(year):
                cell = ledger._cells[(code, year)]
                assert cell.origin == "reported"
                assert cell.source.page and cell.source.page >= 1
                assert cell.source.line_item
                assert "p." in cell.cite()


def test_an_aggregate_names_every_line_it_summed(mapped_aggregate):
    """11.5, carried into the citation rather than lost at the boundary.

    `operating_expenses` is 345,500 in the two-statement fixture, and the
    filing printed three numbers. The citation has to say so, or the reader
    cannot find any of them on the page.
    """
    built = build_statements(mapped_aggregate)
    cell = built.ledgers[accounts.Statement.INCOME]._cells[(accounts.OPERATING_EXPENSES, "2025A")]
    assert cell.value == D("345500")
    assert "Selling, general and administrative" in cell.source.line_item
    assert "Research and development" in cell.source.line_item
    assert "Restructuring charges" in cell.source.line_item


def test_engine_year_adds_the_actual_suffix():
    """STEP 12. A forecast year that looks like an actual is how a projection
    gets quoted as a fact (rule 1.19)."""
    assert engine_year("2025") == "2025A"
    assert engine_year("2025A") == "2025A"
    assert engine_year("2030E") == "2030E"


# --- items 66, 67 -----------------------------------------------------------


def test_every_historical_check_passes_on_a_filing_that_ties(built):
    results = run_historical_checks(built)
    assert summarize(results) == "6 PASS   0 FAIL   0 SKIP"


def test_the_balance_check_fails_rather_than_plugging(three_statements):
    """STEP 6: find the mapping error, do not plug it."""
    fact = _fact(three_statements, "Total equity", "2025")
    broken = correct_fact(
        three_statements, fact.id, "600000", actor="owner", reason="deliberately wrong"
    )
    results = run_historical_checks(build_statements(broken, strict=False))
    balance = _named(results, "Historical balance sheet balances (17.8)")
    assert balance.status is Status.FAIL
    assert "do not plug it" in balance.detail
    # And the reported total is untouched.
    ledger = build_statements(broken, strict=False).ledgers[accounts.Statement.BALANCE]
    assert ledger.get("total_assets", "2025A") == D("1149500")


def test_the_cash_roll_forward_fails_when_a_flow_is_wrong(three_statements):
    """The roll-forward reads the reported subtotals, so corrupting one of
    those is what it is there to catch. Corrupting a component breaks the
    subtotal check instead, which is a different check for a different error."""
    fact = _fact(three_statements, "Net cash used in financing activities", "2025")
    broken = correct_fact(
        three_statements, fact.id, "-50000", actor="owner", reason="deliberately wrong"
    )
    results = run_historical_checks(build_statements(broken, strict=False))
    assert _named(results, "Historical cash flow reconciliation (17.9)").status is Status.FAIL


def test_the_net_income_linkage_compares_two_different_facts(three_statements):
    """It would be worthless if it compared one figure with itself."""
    fact = _fact(three_statements, "Net income", "2025", page=4)
    broken = correct_fact(
        three_statements, fact.id, "999", actor="owner", reason="deliberately wrong"
    )
    results = run_historical_checks(build_statements(broken, strict=False))
    linkage = _named(results, "Net income linkage (IS -> CF)")
    assert linkage.status is Status.FAIL
    assert "136,500" in linkage.detail and "999" in linkage.detail


def test_a_check_with_nothing_to_check_skips(extracted):
    """Rule 1.14: an unresolved requirement must not appear as PASS."""
    from apps.api.app.mapping.actions import propose_all
    from apps.api.app.review.actions import accept_fact

    result = confirm_metadata(
        extracted,
        {n: None for n, f in extracted.document.metadata.fields.items() if f.value is not None},
        actor="owner",
        reason="cover",
    )
    for fact in list(result.facts):
        if fact.value is not None:
            result = accept_fact(result, fact.id, actor="owner", reason="checked")
    result = propose_all(result)
    # The two-statement fixture has no cash flow statement at all.
    built = build_statements(result, strict=False)
    cash = _named(run_historical_checks(built), "Historical cash flow reconciliation (17.9)")
    assert cash.status is Status.SKIP
    assert "1.14" in cash.detail


def _mapped_without_confirming(extracted):
    """Every mapping approved, and the document's metadata still UNCONFIRMED.

    The two-statement fixture presents three operating expense categories, so
    the aggregation has to be declared before anything can be approved -- 11.6
    refuses to approve a double count. What is deliberately NOT done here is
    confirming the scale and currency.
    """
    from apps.api.app.mapping.actions import approve_all, combine_facts, propose_all

    labels = {
        "Selling, general and administrative",
        "Research and development",
        "Restructuring charges",
    }
    result = propose_all(extracted)
    for period in ("2025", "2024"):
        ids = [f.id for f in result.facts if f.raw_label in labels and f.period_label == period]
        result = combine_facts(
            result,
            ids,
            accounts.OPERATING_EXPENSES,
            actor="owner",
            note="three categories, one line",
        )
    return approve_all(result, actor="owner", note="definitions align")


def test_an_unapproved_mapping_stops_a_strict_build(extracted):
    """11.11. Strict means the whole document or none of it -- quietly
    producing empty statements would be the worse failure."""
    from apps.api.app.mapping.actions import propose_all

    result = propose_all(extracted)
    with pytest.raises(BuildError) as exc:
        build_statements(result, strict=True)
    assert "human-approved" in str(exc.value)

    lenient = build_statements(result, strict=False)
    assert lenient.omitted  # named, not silently dropped


def test_unverified_cells_are_reported_not_hidden(extracted):
    """Approved mappings, unconfirmed metadata: the facts are not VERIFIED."""
    result = _mapped_without_confirming(extracted)
    with pytest.raises(BuildError) as exc:
        build_statements(result, strict=True)
    assert "unverified" in str(exc.value)

    lenient = build_statements(result, strict=False)
    assert lenient.unverified
    assert not lenient.is_verified


# --- items 62, 63, 64 -------------------------------------------------------


def test_common_size_uses_revenue_for_the_income_statement(built):
    rows = {r.item.canonical_code: r for r in statement_view(built, accounts.Statement.INCOME)}
    revenue = rows["revenue"].cells[1]
    assert revenue.common_size == D("100.0")
    assert rows["cogs"].cells[1].common_size == D("60.0")


def test_common_size_uses_total_assets_for_the_balance_sheet(built):
    rows = {r.item.canonical_code: r for r in statement_view(built, accounts.Statement.BALANCE)}
    assert rows["total_assets"].cells[1].common_size == D("100.0")


def test_a_cash_flow_line_is_shown_against_revenue(built):
    """Revenue lives on a different ledger; the base still resolves."""
    rows = {r.item.canonical_code: r for r in statement_view(built, accounts.Statement.CASHFLOW)}
    assert rows["cash_flow_from_operations"].cells[1].common_size == D("15.3")


def test_growth_is_undefined_in_the_first_year(built):
    rows = {r.item.canonical_code: r for r in statement_view(built, accounts.Statement.INCOME)}
    first = rows["revenue"].cells[0]
    assert first.growth is None
    assert "no prior year" in first.growth_note


def test_growth_against_a_zero_base_is_undefined_not_infinite(three_statements):
    """4.12, applied to a percentage instead of an error."""
    fact = _fact(three_statements, "Interest expense", "2024")
    zeroed = correct_fact(three_statements, fact.id, "0", actor="owner", reason="test")
    built = build_statements(zeroed, strict=False)
    rows = {r.item.canonical_code: r for r in statement_view(built, accounts.Statement.INCOME)}
    cell = rows["interest_expense"].cells[1]
    assert cell.growth is None
    assert "4.12" in cell.growth_note


def test_the_reported_view_shows_what_was_printed(built, three_statements):
    """63. Parentheses and all -- the filing printed an expense negative."""
    raw = reported_strings(three_statements)
    assert raw[("cogs", "2025A")] == "(750,000)"
    assert built.ledgers[accounts.Statement.INCOME].get("cogs", "2025A") == D("750000")


def test_a_citation_records_the_sign_flip(three_statements):
    """11.8. The reader can see that the chart's convention differs."""
    found = citations(three_statements)[("cogs", "2025A")]
    assert found[0]["mapping"].sign_normalization.value == "negated"
    assert found[0]["page"] == 2


def test_the_equity_statement_says_it_is_not_available():
    """62. An empty table would imply the filing did not present one."""
    note = equity_statement_status()
    assert "Not available" in note and "12.2.l" in note


# --- the last mile ----------------------------------------------------------


def test_the_export_produces_files_the_engine_loads(three_statements, tmp_path):
    """The join, end to end, through the engine's own loaders."""
    from model.accounts import Statement
    from model.loader import load_historical, load_profile

    inputs = build_engine_inputs(three_statements)
    profile_path, historical_path = inputs.write(tmp_path)

    profile, source_map, periods = load_profile(profile_path)
    assert profile.company_name == "MERIDIAN COMPONENTS INC."
    assert profile.units.value == "thousands"
    assert profile.reporting_currency == "USD"
    assert profile.audited is True
    assert periods.historical == YEARS
    assert len(periods.forecast) == 5

    ledgers = load_historical(historical_path, periods)
    assert ledgers[Statement.INCOME].get("revenue", "2025A") == D("1250000")
    assert ledgers[Statement.BALANCE].cross_check() == []
    cite = ledgers[Statement.INCOME]._cells[("revenue", "2025A")].cite()
    assert "p.2" in cite and "Revenue" in cite


def test_the_source_map_gaps_are_named_not_hidden(three_statements):
    """STEP 2. A page is recorded only where a caption named the section."""
    inputs = build_engine_inputs(three_statements)
    assert "statement_of_shareholders_equity" in inputs.source_map_gaps
    assert "income_statement" not in inputs.source_map_gaps
    assert "still unmapped" in inputs.company_profile


def test_the_export_refuses_while_metadata_is_unconfirmed(extracted):
    """Rule 1.4. An export is where a detected guess starts looking official.

    The document below is fully mapped and every mapping approved; what it
    lacks is a reviewer confirming the scale and currency. The refusal comes
    from verification rather than from the export's own metadata guard, and
    that ordering is not an accident: `accept_fact` already refuses while the
    scale is unconfirmed, so "accepted facts on an unconfirmed document" is a
    state this system cannot reach. The export's guard is defensive, and
    `export.py` says so.
    """
    result = _mapped_without_confirming(extracted)
    with pytest.raises((ExportError, BuildError)) as exc:
        build_engine_inputs(result)
    assert "unverified" in str(exc.value).lower()


def test_the_export_does_not_invent_assumptions(three_statements, tmp_path):
    """A beta and a risk-free rate are not lines in a filing."""
    inputs = build_engine_inputs(three_statements)
    inputs.write(tmp_path)
    assert not (tmp_path / "assumptions.yaml").exists()
    assert not (tmp_path / "valuation.yaml").exists()


def test_the_engine_still_halts_on_what_a_filing_cannot_supply(three_statements, tmp_path):
    """The right failure: the historical half loaded, the forecast half did not."""
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    build_engine_inputs(three_statements).write(tmp_path)
    for name in ("assumptions.yaml", "valuation.yaml"):
        shutil.copy(Path("inputs") / name, tmp_path / name)

    process = subprocess.run(
        [sys.executable, "run_model.py", "--inputs", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 2
    assert "MODEL HALTED" in process.stderr
    assert "STEP" in process.stderr


# --- helpers ----------------------------------------------------------------


def _fact(result, label, period, page=None):
    for fact in result.facts:
        if fact.raw_label != label or fact.period_label != period:
            continue
        if page is None:
            return fact
        location = result.location(fact.source_location_id)
        if location and location.page_number == page:
            return fact
    raise AssertionError(f"no fact {label!r} {period} on page {page}")


def _named(results, name):
    for result in results:
        if result.name == name:
            return result
    raise AssertionError(f"no check named {name!r}")
