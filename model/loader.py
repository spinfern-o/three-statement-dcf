"""Load the input files into model objects, refusing anything incomplete.

Every loader here fails with a message naming the file, the YAML path, and
the workflow step that requires the field. A blank template therefore walks
you through what the workflow asks for, one error at a time, instead of
running to completion on defaults and producing a confident wrong number.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from . import accounts as A
from .accounts import Statement
from .assumptions import Assumptions, Assumption, Basis, Conflict
from .dcf import CostOfCapital, EquityBridge
from .profile import REQUIRED_SOURCE_MAP_KEYS, CompanyProfile, Periods, SourceMap, Units
from .provenance import Figure, ProvenanceError, Source
from .numeric import D, PrecisionError
from .schedules import TaxSchedule
from .statements import Ledger
from .yaml_exact import load_exact


class InputError(ProvenanceError):
    """An input file is missing something the workflow requires."""


def _load_yaml(path: Path) -> dict[str, Any]:
    """Parse with numeric scalars preserved as written (specification 4.2).

    `yaml.safe_load` would resolve them to floats here, and no later
    conversion could recover the digits the file actually contained.
    """
    if not path.exists():
        raise InputError(f"Input file not found: {path}")
    data = load_exact(path)
    if data is None:
        raise InputError(f"{path} is empty. Fill in the template before running the model.")
    if not isinstance(data, dict):
        raise InputError(f"{path} must contain a YAML mapping at the top level.")
    return data


def _req(data: dict, key: str, where: str, step: str) -> Any:
    """Fetch a required key, treating an unfilled template blank as missing."""
    if key not in data or data[key] is None or (isinstance(data[key], str) and not data[key].strip()):
        raise InputError(f"{where}.{key} is required by {step} and is blank. Fill it in -- do not leave it to a default.")
    return data[key]


def _section(data: dict, key: str, where: str, step: str) -> dict:
    value = _req(data, key, where, step)
    if not isinstance(value, dict):
        raise InputError(f"{where}.{key} must be a mapping ({step})")
    return value


def _num(value: Any, where: str) -> Decimal:
    """Exact Decimal from the text the file contained (4.2, 4.3)."""
    try:
        return D(value, what=where)
    except PrecisionError as exc:
        raise InputError(str(exc)) from None


# --- STEP 1-3 / 12 --------------------------------------------------------
def load_profile(path: Path) -> tuple[CompanyProfile, SourceMap, Periods]:
    data = _load_yaml(path)
    company = _section(data, "company", str(path), "STEP 1")

    units_raw = _req(company, "units", "company", "STEP 1")
    try:
        units = Units(str(units_raw).strip().lower())
    except ValueError:
        raise InputError(
            f"company.units must be one of {[u.value for u in Units]} (STEP 1), got {units_raw!r}. "
            "Whether the filing reports dollars, thousands or millions changes every number by 1000x."
        ) from None

    audited = _req(company, "audited", "company", "STEP 1")
    if not isinstance(audited, bool):
        raise InputError(f"company.audited must be true or false (STEP 1), got {audited!r}")

    profile = CompanyProfile(
        company_name=str(_req(company, "name", "company", "STEP 1")),
        reporting_period=str(_req(company, "reporting_period", "company", "STEP 1")),
        fiscal_year_end=str(_req(company, "fiscal_year_end", "company", "STEP 1")),
        reporting_currency=str(_req(company, "reporting_currency", "company", "STEP 1")),
        units=units,
        audited=audited,
    )

    sm_block = _section(data, "source_map", str(path), "STEP 2")
    pages_block = sm_block.get("pages") or {}
    if not isinstance(pages_block, dict):
        raise InputError("source_map.pages must be a mapping of section -> page number (STEP 2)")
    unknown = set(pages_block) - set(REQUIRED_SOURCE_MAP_KEYS)
    if unknown:
        raise InputError(f"source_map.pages has unrecognized key(s): {sorted(unknown)} (STEP 2)")
    source_map = SourceMap(
        document=str(_req(sm_block, "document", "source_map", "STEP 2")),
        pages={k: (int(str(v)) if v is not None else None) for k, v in pages_block.items()},
    )

    periods_block = _section(data, "periods", str(path), "STEP 3 / STEP 12")
    historical = _req(periods_block, "historical", "periods", "STEP 3")
    forecast = _req(periods_block, "forecast", "periods", "STEP 12")
    if not isinstance(historical, list) or not isinstance(forecast, list):
        raise InputError("periods.historical and periods.forecast must be lists of years (STEP 3 / STEP 12)")
    periods = Periods(tuple(str(y) for y in historical), tuple(str(y) for y in forecast))

    return profile, source_map, periods


# --- STEP 4-7 -------------------------------------------------------------
_STATEMENT_KEYS = {
    "income_statement": Statement.INCOME,
    "balance_sheet": Statement.BALANCE,
    "cash_flow_statement": Statement.CASHFLOW,
}


def load_historical(path: Path, periods: Periods) -> dict[Statement, Ledger]:
    """STEP 4-7: transcribed figures into three standardized ledgers."""
    data = _load_yaml(path)
    document = str(_req(data, "document", str(path), "STEP 4"))

    ledgers = {st: Ledger(st, periods.historical) for st in _STATEMENT_KEYS.values()}

    for key, statement in _STATEMENT_KEYS.items():
        block = data.get(key)
        if block is None:
            continue
        if not isinstance(block, dict):
            raise InputError(f"{key} must be a mapping of account -> block (STEP 5-7)")
        ledger = ledgers[statement]
        for account, spec in block.items():
            A.validate_account(statement, account)
            where = f"{key}.{account}"
            if not isinstance(spec, dict):
                raise InputError(f"{where} must be a mapping with line_item, page and values (STEP 4)")
            line_item = str(_req(spec, "line_item", where, "STEP 4"))
            default_page = spec.get("page")
            per_year_pages = spec.get("pages") or {}
            values = _section(spec, "values", where, "STEP 4")
            for year, raw in values.items():
                year = str(year)
                if raw is None:
                    continue  # a year the company does not report this line
                if year not in periods.historical:
                    raise InputError(
                        f"{where}.values has year {year!r}, which is not in periods.historical "
                        f"({', '.join(periods.historical)}). STEP 3: do not invent missing historical years."
                    )
                page = per_year_pages.get(year, default_page)
                ledger.set_reported(
                    account,
                    year,
                    Figure(
                        value=_num(raw, f"{where}.values.{year}"),
                        year=year,
                        source=Source(
                            document=document,
                            page=int(str(page)) if page is not None else None,
                            line_item=line_item,
                        ),
                    ),
                )

    for ledger in ledgers.values():
        ledger.fill_derivable()
    return ledgers


# --- STEP 10-11 / 16 ------------------------------------------------------
def load_assumptions(path: Path, periods: Periods) -> tuple[Assumptions, TaxSchedule, dict[str, Decimal]]:
    data = _load_yaml(path)
    assumptions = Assumptions()

    drivers = data.get("drivers") or []
    if not isinstance(drivers, list):
        raise InputError("assumptions.drivers must be a list (STEP 10)")
    for i, raw in enumerate(drivers):
        where = f"drivers[{i}]"
        if not isinstance(raw, dict):
            raise InputError(f"{where} must be a mapping (STEP 10)")
        basis_raw = _req(raw, "basis", where, "STEP 10")
        try:
            basis = Basis(str(basis_raw).strip().lower())
        except ValueError:
            raise InputError(
                f"{where}.basis must be one of {[b.value for b in Basis]} (STEP 10), got {basis_raw!r}"
            ) from None
        year = raw.get("year")
        if year is not None:
            year = str(year)
            if year not in periods.all_years:
                raise InputError(f"{where}.year {year!r} is not a modeled year")
        assumptions.add(
            Assumption(
                name=str(_req(raw, "name", where, "STEP 10")),
                value=_num(_req(raw, "value", where, "STEP 10"), f"{where}.value"),
                basis=basis,
                source=str(_req(raw, "source", where, "STEP 10")),
                year=year,
                note=str(raw.get("note") or ""),
            )
        )

    for i, raw in enumerate(data.get("conflicts") or []):
        where = f"conflicts[{i}]"
        if not isinstance(raw, dict):
            raise InputError(f"{where} must be a mapping (STEP 11)")
        assumptions.add_conflict(
            Conflict(
                topic=str(_req(raw, "topic", where, "STEP 11")),
                source_a=str(_req(raw, "source_a", where, "STEP 11")),
                date_a=str(_req(raw, "date_a", where, "STEP 11")),
                value_a=str(_req(raw, "value_a", where, "STEP 11")),
                source_b=str(_req(raw, "source_b", where, "STEP 11")),
                date_b=str(_req(raw, "date_b", where, "STEP 11")),
                value_b=str(_req(raw, "value_b", where, "STEP 11")),
                chosen=str(_req(raw, "chosen", where, "STEP 11")),
                rationale=str(_req(raw, "rationale", where, "STEP 11")),
            )
        )

    tax_block = _section(data, "tax", str(path), "STEP 16")
    _req(tax_block, "source", "tax", "STEP 16")
    rates_block = _section(tax_block, "rates", "tax", "STEP 16")
    rates = {str(y): _num(v, f"tax.rates.{y}") for y, v in rates_block.items() if v is not None}
    missing = [y for y in periods.forecast if y not in rates]
    if missing:
        raise InputError(f"STEP 16: no tax rate supplied for {', '.join(missing)}")
    taxes = TaxSchedule(basis=str(_req(tax_block, "basis", "tax", "STEP 16")), rate_by_year=rates)

    segments_block = data.get("segments") or {}
    if segments_block and not isinstance(segments_block, dict):
        raise InputError("assumptions.segments must be a mapping of segment -> last actual revenue (STEP 13)")
    segments = {str(k): _num(v, f"segments.{k}") for k, v in segments_block.items()}

    return assumptions, taxes, segments


# --- STEP 25-28 / 34-36 ---------------------------------------------------
def load_valuation(path: Path) -> dict[str, Any]:
    data = _load_yaml(path)

    coc_block = _section(data, "cost_of_capital", str(path), "STEP 25-28")
    sources_block = _section(coc_block, "sources", "cost_of_capital", "STEP 25-27")
    cost_of_capital = CostOfCapital(
        risk_free_rate=_num(_req(coc_block, "risk_free_rate", "cost_of_capital", "STEP 25"), "risk_free_rate"),
        beta=_num(_req(coc_block, "beta", "cost_of_capital", "STEP 25"), "beta"),
        equity_risk_premium=_num(
            _req(coc_block, "equity_risk_premium", "cost_of_capital", "STEP 25"), "equity_risk_premium"
        ),
        pretax_cost_of_debt=_num(
            _req(coc_block, "pretax_cost_of_debt", "cost_of_capital", "STEP 26"), "pretax_cost_of_debt"
        ),
        tax_rate=_num(_req(coc_block, "tax_rate", "cost_of_capital", "STEP 26"), "tax_rate"),
        market_value_equity=_num(
            _req(coc_block, "market_value_equity", "cost_of_capital", "STEP 27"), "market_value_equity"
        ),
        market_value_debt=_num(
            _req(coc_block, "market_value_debt", "cost_of_capital", "STEP 27"), "market_value_debt"
        ),
        sources={str(k): str(v or "") for k, v in sources_block.items()},
    )

    tg_block = _section(data, "terminal_growth", str(path), "STEP 30-31")
    _req(tg_block, "source", "terminal_growth", "STEP 10")
    terminal_growth = _num(_req(tg_block, "value", "terminal_growth", "STEP 30"), "terminal_growth.value")

    bridge_block = _section(data, "equity_bridge", str(path), "STEP 34")
    bridge = EquityBridge(
        cash=_num(_req(bridge_block, "cash", "equity_bridge", "STEP 34"), "equity_bridge.cash"),
        debt=_num(_req(bridge_block, "debt", "equity_bridge", "STEP 34"), "equity_bridge.debt"),
        non_operating_investments=_num(bridge_block.get("non_operating_investments") or 0, "non_operating_investments"),
        minority_interest=_num(bridge_block.get("minority_interest") or 0, "minority_interest"),
        preferred_stock=_num(bridge_block.get("preferred_stock") or 0, "preferred_stock"),
        pension_obligations=_num(bridge_block.get("pension_obligations") or 0, "pension_obligations"),
        other_claims=_num(bridge_block.get("other_claims") or 0, "other_claims"),
    )

    shares_block = data.get("shares") or {}
    diluted = shares_block.get("diluted_shares_outstanding")
    shares_source = shares_block.get("source")
    if diluted is not None:
        diluted = _num(diluted, "shares.diluted_shares_outstanding")
        if not shares_source or not str(shares_source).strip():
            raise InputError("STEP 35 requires the source and date for diluted shares outstanding.")
        shares_source = str(shares_source)

    sens_block = data.get("sensitivity") or {}
    wacc_values = [_num(v, "sensitivity.wacc") for v in (sens_block.get("wacc") or [])]
    growth_values = [_num(v, "sensitivity.terminal_growth") for v in (sens_block.get("terminal_growth") or [])]

    return {
        "cost_of_capital": cost_of_capital,
        "terminal_growth": terminal_growth,
        "equity_bridge": bridge,
        "diluted_shares": diluted,
        "shares_source": shares_source,
        "sensitivity_wacc": wacc_values,
        "sensitivity_growth": growth_values,
    }
