"""The last mile: a mapped, verified document becomes an engine input.

Until this file existed the two halves of the repository agreed and did not
touch. `model/` built statements from YAML a human typed; `apps/api/` read a
PDF into verified, mapped facts. This writes the second as the first.

It is deliberately small, and it is the piece that makes the system one thing
rather than two that happen to share a repository. It is also the piece most
likely to be used carelessly, so it refuses in three places:

- **Nothing unconfirmed.** Rule 1.4 forbids choosing a currency, unit or
  fiscal year-end silently, so the export refuses while any of them is still
  UNCONFIRMED rather than writing the detected guess into a file that looks
  authoritative.
- **Nothing unverified.** `build_statements(strict=True)` is what produces the
  ledgers, so every exported figure has satisfied all seven of
  source-policy.md §9's conditions.
- **Nothing invented.** The forecast years are the five decision 2.4.e fixes,
  and the assumption and valuation files are NOT written: a risk-free rate, a
  beta and a terminal growth rate are facts about a market on a date, and the
  engine is supposed to refuse to run without them. Writing blanks would be
  honest; writing values would not, and the blanks already ship in `inputs/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from model import accounts
from model.profile import REQUIRED_SOURCE_MAP_KEYS, Units

from ..api.bookmarks import bookmarks
from ..extraction.records import ExtractionResult
from .build import BuiltStatements, build_statements, document_label

#: 10.10's `displayed_scale` values, in the engine's vocabulary (STEP 1).
SCALE_TO_UNITS = {
    "units": Units.DOLLARS.value,
    "thousands": Units.THOUSANDS.value,
    "millions": Units.MILLIONS.value,
}

#: Which bookmark label answers which STEP 2 source-map key.
BOOKMARK_TO_SOURCE_MAP = {
    "Income statement": "income_statement",
    "Balance sheet": "balance_sheet",
    "Cash flow statement": "cash_flow_statement",
    "Statement of equity": "statement_of_shareholders_equity",
    "Notes": "revenue_notes",
}

#: Decision 2.4.e. Five explicit forecast years.
FORECAST_YEARS = 5


class ExportError(Exception):
    """The document is not ready to leave this system, and this says why."""


@dataclass(frozen=True)
class EngineInputs:
    """The two files the historical half of the engine reads."""

    company_profile: str
    raw_historical: str
    #: STEP 2 keys with no page. Reported, never silently tolerated.
    source_map_gaps: tuple[str, ...]

    def write(self, directory: str | Path) -> tuple[Path, Path]:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        profile = target / "company_profile.yaml"
        historical = target / "raw_historical.yaml"
        profile.write_text(self.company_profile)
        historical.write_text(self.raw_historical)
        return profile, historical


def _confirmed(result: ExtractionResult, name: str) -> str:
    """Refuse an unconfirmed field. Defensive rather than load-bearing.

    Verification already requires confirmed metadata (source-policy.md §9
    condition 3), and `accept_fact` refuses while the scale is unconfirmed, so
    a document that survives `build_statements(strict=True)` has confirmed
    metadata by construction. This guard exists because the export is the
    boundary where a detected guess would start looking authoritative, and a
    boundary that trusts an invariant it does not check is one refactor away
    from not having it.
    """
    field = result.document.metadata.fields.get(name)
    if field is None or not field.confirmed or not field.value:
        raise ExportError(
            f"{name} is not confirmed. Rule 1.4 forbids choosing a currency, "
            f"unit, fiscal year-end or period silently, and an export is the "
            f"point at which a detected guess would start looking "
            f"authoritative. Confirm it in the source room first."
        )
    return field.value


def _fiscal_year_end(value: str) -> str:
    """`12-31` -> `December 31`, which is what STEP 1 asks a human to write."""
    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    try:
        month, day = value.split("-")
        return f"{months[int(month) - 1]} {int(day)}"
    except (ValueError, IndexError):
        return value


def _yaml_scalar(value: str | int | None) -> str:
    if value is None:
        return ""
    text = str(value)
    return f'"{text}"' if any(c in text for c in ":#{}[],&*?|>%@`") else text


def build_engine_inputs(
    result: ExtractionResult, built: BuiltStatements | None = None
) -> EngineInputs:
    """Write this document's historical half as the engine's two input files."""
    statements = built if built is not None else build_statements(result, strict=True)
    if statements.unverified:
        raise ExportError(
            f"{len(statements.unverified)} cell(s) rest on unverified facts. The "
            f"export is the boundary at which a figure stops being reviewable, "
            f"so it takes only what has met all seven conditions."
        )

    currency = _confirmed(result, "reporting_currency")
    scale = _confirmed(result, "displayed_scale")
    if scale not in SCALE_TO_UNITS:
        raise ExportError(f"{scale!r} is not a scale the engine knows (STEP 1)")
    name = _confirmed(result, "company_name")
    period_end = _confirmed(result, "reporting_period_end")
    year_end = _fiscal_year_end(_confirmed(result, "fiscal_year_end"))
    audited = _confirmed(result, "audited_status") == "audited"
    label = document_label(result)

    pages = dict.fromkeys(REQUIRED_SOURCE_MAP_KEYS)
    for bookmark in bookmarks(result):
        key = BOOKMARK_TO_SOURCE_MAP.get(bookmark.label)
        if key and pages.get(key) is None:
            pages[key] = bookmark.page_number
    gaps = tuple(key for key in REQUIRED_SOURCE_MAP_KEYS if pages[key] is None)

    last_actual = int(statements.years[-1][:4])
    forecast = [f"{last_actual + n}E" for n in range(1, FORECAST_YEARS + 1)]

    profile = _profile_yaml(
        name=name,
        period=f"FY{period_end[:4]}",
        year_end=year_end,
        currency=currency,
        units=SCALE_TO_UNITS[scale],
        audited=audited,
        document=label,
        pages=pages,
        historical=statements.years,
        forecast=forecast,
        gaps=gaps,
    )
    historical = _historical_yaml(statements, label)
    return EngineInputs(company_profile=profile, raw_historical=historical, source_map_gaps=gaps)


def _profile_yaml(**k) -> str:
    lines = [
        "# STEP 1-3 and STEP 12. Written by apps/api/app/statements/export.py",
        "# from a document whose metadata was confirmed and whose facts are",
        "# VERIFIED. Every value here traces to a page of the filing.",
        "",
        "company:",
        f"  name: {_yaml_scalar(k['name'])}",
        f"  reporting_period: {_yaml_scalar(k['period'])}",
        f"  fiscal_year_end: {_yaml_scalar(k['year_end'])}",
        f"  reporting_currency: {_yaml_scalar(k['currency'])}",
        f"  units: {k['units']}",
        f"  audited: {'true' if k['audited'] else 'false'}",
        "",
        "# STEP 2. A page is recorded only where a table caption named that",
        "# section; the rest are left null, and the report lists them as",
        "# missing rather than pretending the map is complete.",
        "source_map:",
        f"  document: {_yaml_scalar(k['document'])}",
        "  pages:",
    ]
    for key in REQUIRED_SOURCE_MAP_KEYS:
        page = k["pages"][key]
        lines.append(f"    {key}: {page if page is not None else ''}".rstrip())
    if k["gaps"]:
        lines.append(f"    # {len(k['gaps'])} section(s) still unmapped: {', '.join(k['gaps'])}")
    lines += [
        "",
        "periods:",
        f"  historical: [{', '.join(k['historical'])}]",
        "  # Decision 2.4.e: five explicit forecast years. The engine refuses",
        "  # to run until assumptions.yaml and valuation.yaml are filled in,",
        "  # which is correct -- a beta and a risk-free rate are not in a filing.",
        f"  forecast: [{', '.join(k['forecast'])}]",
        "",
    ]
    return "\n".join(lines)


STATEMENT_BLOCKS = (
    ("income_statement", accounts.Statement.INCOME, accounts.INCOME_ACCOUNTS),
    ("balance_sheet", accounts.Statement.BALANCE, accounts.BALANCE_ACCOUNTS),
    ("cash_flow_statement", accounts.Statement.CASHFLOW, accounts.CASHFLOW_ACCOUNTS),
)


def _historical_yaml(built: BuiltStatements, document: str) -> str:
    lines = [
        "# STEP 4-7. Written by apps/api/app/statements/export.py.",
        "#",
        "# Every figure below was extracted from the filing, reviewed by a",
        "# person, mapped to a canonical line and approved. `line_item` is the",
        "# company's own wording and `page` is where it was printed, both",
        "# carried through from the extraction rather than retyped.",
        "#",
        "# A line the filing does not report is ABSENT here, not zero (STEP 5).",
        "",
        f"document: {_yaml_scalar(document)}",
    ]

    for block, statement, order in STATEMENT_BLOCKS:
        ledger = built.ledgers[statement]
        present = [code for code in order if any(ledger.has(code, year) for year in built.years)]
        lines.append("")
        lines.append(f"{block}:")
        if not present:
            lines.append(f"  # the filing presents no {block.replace('_', ' ')}")
            continue
        for code in present:
            cells = [
                (year, ledger._cells[(code, year)])
                for year in built.years
                if ledger.has(code, year)
            ]
            first = cells[0][1]
            source = first.source
            lines.append(f"  {code}:")
            lines.append(f"    line_item: {_yaml_scalar(source.line_item if source else '')}")
            lines.append(f"    page: {source.page if source and source.page else ''}".rstrip())
            lines.append("    values:")
            for year, cell in cells:
                lines.append(f"      {year}: {cell.value}")
    lines.append("")
    return "\n".join(lines)
