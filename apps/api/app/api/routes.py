"""Items 39 and 44: source-room navigation and metadata confirmation.

Every mutation is a POST followed by a redirect, and every one of them carries
a reason the reviewer typed. That is not a stylistic choice about forms: 10.32
permits correction "only with a reviewer note", and a GET that changes a
verification status would be a change with no note, performed by a link
preview.

Errors come back as a message on the page the reviewer was already on, in an
`role="alert"` region at the top (6.6.f asks for an error summary). A refused
action is a normal outcome here -- accepting a fact whose cell held an em dash
is *supposed* to fail -- so it is presented as an answer, not as a crash.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from model.numeric import D, PrecisionError

from ..extraction.records import confirm_metadata
from ..mapping.actions import (
    approve_all,
    approve_fact_mapping,
    combine_facts,
    map_fact,
    propose_all,
    proposals_for,
    reject_mapping,
    split_fact,
    why_no_proposal,
)
from ..mapping.chart import CHART
from model.accounts import Statement
from ..mapping.checks import all_findings, apply_findings
from ..mapping.normalized import normalize, periods as ledger_periods, statement_of_fact
from ..mapping.sets import MappingError
from ..assumptions.gate import evaluate as evaluate_gate
from ..assumptions.impact import preview as preview_change
from ..assumptions.proposals import propose_from_schedules, unproposable
from ..assumptions.schema import AssumptionError, Status
from ..assumptions.scenarios import BASE, ScenarioError
from ..assumptions.store import ScenarioStore
from ..assumptions.views import (
    optional_rows,
    required_rows,
    scenario_rows,
    status_choices,
)
from ..assumptions.workflow import WorkflowError, transition
from ..formula.catalog import derivation_formulas, ledger_environment
from ..formula.views import formula_report
from ..schedules.build import build_schedules
from ..schedules.checks import run_schedule_checks
from ..schedules.checks import summarize as summarize_schedule_checks
from ..schedules.views import driver_rows, working_capital_rows
from ..review.actions import ACCEPT, CORRECT, REJECT, ReviewError, accept_fact, correct_fact, reject_fact
from ..statements.build import BuildError, build_statements
from ..statements.checks import run_historical_checks, summarize
from ..statements.export import ExportError, build_engine_inputs
from ..statements.reported import citations, reported_strings
from ..statements.views import equity_statement_status, statement_view
from ..review.progress import review_progress, verification_gates
from .bookmarks import bookmarks, unmapped_statements
from .rendering import render_page

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


def _repository(request: Request):
    return request.app.state.repository


def _store(request: Request):
    return request.app.state.store


def _load(request: Request, document_id: str):
    try:
        return _repository(request).load_result(document_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"no document {document_id}") from None


def _back(document_id: str, page: int, **flash) -> RedirectResponse:
    query = urlencode({k: v for k, v in flash.items() if v})
    url = f"/documents/{document_id}/pages/{page}" + (f"?{query}" if query else "")
    # 303: the browser must follow a POST with a GET, or a refresh resubmits
    # the decision and writes a second audit entry for one action.
    return RedirectResponse(url, status_code=303)


@router.get("/health")
def health() -> dict:
    """Phase 1 item 14. Liveness only -- it asserts nothing about the data."""
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    """7.1 Portfolio. Every document held, and how far its review has got."""
    repository = _repository(request)
    documents = []
    for document_id in repository.document_ids():
        result = repository.load_result(document_id)
        documents.append((result.document, review_progress(result)))
    return _templates(request).TemplateResponse(
        request=request, name="index.html", context={"documents": documents}
    )


@router.get("/documents/{document_id}", response_class=HTMLResponse)
def document(request: Request, document_id: str):
    result = _load(request, document_id)
    first = _first_interesting_page(result)
    return RedirectResponse(f"/documents/{document_id}/pages/{first}", status_code=303)


def _first_interesting_page(result) -> int:
    """Open on the first page that has facts on it, not on the cover."""
    pages = {
        result.location(f.source_location_id).page_number
        for f in result.facts
        if result.location(f.source_location_id)
    }
    return min(pages) if pages else 1


@router.get("/documents/{document_id}/pages/{page}", response_class=HTMLResponse)
def source_room(request: Request, document_id: str, page: int, error: str = "", ok: str = ""):
    """7.3 Source Room. 6.3.f: the page on the left, the values on the right."""
    result = _load(request, document_id)
    if not 1 <= page <= result.document.page_count:
        raise HTTPException(status_code=404, detail=f"no page {page} in {document_id}")

    facts = [
        (fact, result.location(fact.source_location_id))
        for fact in result.facts
        if (loc := result.location(fact.source_location_id)) and loc.page_number == page
    ]
    geometry = next(
        (p.geometry for p in result.document.pages if p.page_number == page), None
    )
    profile = next((p for p in result.document.pages if p.page_number == page), None)

    return _templates(request).TemplateResponse(
        request=request,
        name="source_room.html",
        context={
            "result": result,
            "document": result.document,
            "page": page,
            "geometry": geometry,
            "profile": profile,
            "facts": facts,
            "progress": review_progress(result),
            "bookmarks": bookmarks(result),
            "unmapped": unmapped_statements(result),
            "error": error,
            "ok": ok,
            "gates": {f.id: verification_gates(f, result) for f, _ in facts},
        },
    )


@router.get("/documents/{document_id}/pages/{page}/image.png")
def page_image(request: Request, document_id: str, page: int):
    """Item 40. Rendered from the stored bytes, which are re-hashed on read."""
    result = _load(request, document_id)
    try:
        png = render_page(
            _store(request),
            result.document.immutable_hash,
            page,
            cache_root=Path(request.app.state.storage_root),
        )
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/documents/{document_id}/metadata")
def confirm(
    request: Request,
    document_id: str,
    page: int = Form(...),
    reason: str = Form(""),
    field: str = Form(""),
    value: str = Form(""),
):
    """Item 44. Confirm one detected field, or correct it. 10.12, 10.13."""
    result = _load(request, document_id)
    try:
        if not reason.strip():
            raise ReviewError("a reason is required to confirm or correct metadata (10.32)")
        if field:
            replacement = value.strip() or None
            updated = confirm_metadata(
                result, {field: replacement}, actor=_actor(request), reason=reason
            )
        else:
            detected = {
                name: None
                for name, f in result.document.metadata.fields.items()
                if f.value is not None and not f.confirmed
            }
            if not detected:
                raise ReviewError("every detected field is already confirmed")
            updated = confirm_metadata(
                result, detected, actor=_actor(request), reason=reason
            )
    except (ReviewError, ValueError, KeyError) as exc:
        return _back(document_id, page, error=str(exc))

    _repository(request).save(updated)
    confirmed = field or f"{len(updated.document.metadata.fields)} detected field(s)"
    return _back(document_id, page, ok=f"Confirmed {confirmed}.")


@router.post("/documents/{document_id}/facts/{fact_id}")
def decide(
    request: Request,
    document_id: str,
    fact_id: str,
    action: str = Form(...),
    reason: str = Form(""),
    value: str = Form(""),
    page: int = Form(...),
):
    """Items 45, 46, 47. Accept, correct or reject -- each with a reason."""
    result = _load(request, document_id)
    actor = _actor(request)
    try:
        if action == ACCEPT:
            updated = accept_fact(result, fact_id, actor=actor, reason=reason)
        elif action == CORRECT:
            updated = correct_fact(result, fact_id, value, actor=actor, reason=reason)
        elif action == REJECT:
            updated = reject_fact(result, fact_id, actor=actor, reason=reason)
        else:
            raise ReviewError(f"{action!r} is not a reviewer action")
    except ReviewError as exc:
        return _back(document_id, page, error=str(exc))

    _repository(request).save(updated)
    return _back(document_id, page, ok=f"Recorded: {action}.")


def _actor(request: Request) -> str:
    """Decision 2.2.b is single user, and 2.2.d is one role: owner.

    Authentication (2.2.c) is a deployment concern and is NOT implemented --
    see the security note in docs/decision-ledger.md. Every audit entry is
    attributed to the owner because there is exactly one person, and that is
    recorded rather than assumed silently.
    """
    return request.app.state.actor


# --- item 52: the mapping review table (7.4) --------------------------------


def _mapping_back(document_id: str, **flash) -> RedirectResponse:
    query = urlencode({k: v for k, v in flash.items() if v})
    return RedirectResponse(
        f"/documents/{document_id}/mapping" + (f"?{query}" if query else ""),
        status_code=303,
    )


@router.get("/documents/{document_id}/mapping", response_class=HTMLResponse)
def mapping_review(request: Request, document_id: str, error: str = "", ok: str = ""):
    """7.4 Mapping Review. Every raw line beside the canonical line it becomes."""
    result = _load(request, document_id)
    mappings = result.mappings

    rows = []
    for fact in result.facts:
        location = result.location(fact.source_location_id)
        existing = mappings.for_fact(fact.id) if mappings else ()
        rows.append(
            {
                "fact": fact,
                "location": location,
                "statement": statement_of_fact(result, fact),
                "mappings": existing,
                "candidates": proposals_for(result, fact),
                "why_none": why_no_proposal(result, fact) if not existing else "",
                "approved": bool(mappings and mappings.is_approved(fact.id)),
                "excluded": bool(mappings and mappings.is_excluded(fact.id)),
            }
        )

    ledger = normalize(result)
    return _templates(request).TemplateResponse(
        request=request,
        name="mapping.html",
        context={
            "result": result,
            "document": result.document,
            "rows": rows,
            "mappings": mappings,
            "chart": CHART,
            "findings": all_findings(result),
            "ledger_rows": _ledger_rows(ledger),
            "ledger_periods": ledger_periods(ledger),
            "progress": review_progress(result),
            "error": error,
            "ok": ok,
        },
    )


@router.post("/documents/{document_id}/mapping/propose")
def propose(request: Request, document_id: str):
    """Item 51. Runs the proposer; approves nothing."""
    result = _load(request, document_id)
    before = len(result.mappings.mappings) if result.mappings else 0
    updated = apply_findings(propose_all(result, actor="system"))
    _repository(request).save(updated)
    added = (len(updated.mappings.mappings) if updated.mappings else 0) - before
    return _mapping_back(
        document_id,
        ok=f"Proposed {added} mapping(s). None is approved -- 11.11 needs a person.",
    )


@router.post("/documents/{document_id}/mapping/facts/{fact_id}")
def decide_mapping(
    request: Request,
    document_id: str,
    fact_id: str,
    action: str = Form(...),
    note: str = Form(""),
    canonical_code: str = Form(""),
    allocation: str = Form(""),
    basis: str = Form(""),
):
    """Items 53 and 56. Map, split, reject, or approve one fact's mapping."""
    result = _load(request, document_id)
    actor = _actor(request)
    try:
        if action == "map":
            updated = map_fact(result, fact_id, canonical_code, actor=actor, note=note)
        elif action == "split":
            updated = split_fact(
                result, fact_id, _parse_allocation(allocation),
                basis=basis, actor=actor, note=note,
            )
        elif action == "reject":
            updated = reject_mapping(result, fact_id, actor=actor, note=note)
        elif action == "approve":
            updated = approve_fact_mapping(result, fact_id, actor=actor, note=note)
        else:
            raise MappingError(f"{action!r} is not a mapping action")
    except (MappingError, KeyError) as exc:
        return _mapping_back(document_id, error=str(exc))

    _repository(request).save(apply_findings(updated))
    return _mapping_back(document_id, ok=f"Recorded: {action}.")


def _parse_allocation(text: str) -> "list[tuple[str, str]]":
    """`code = amount` per line. Refuses anything it cannot read."""
    allocations = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        if "=" not in line:
            raise MappingError(
                f"line {number} of the allocation, {line.strip()!r}, is not "
                f"`canonical_code = amount`"
            )
        code, _, amount = line.partition("=")
        allocations.append((code.strip(), amount.strip()))
    if not allocations:
        raise MappingError("a split needs an allocation: one `code = amount` per line")
    return allocations


@router.post("/documents/{document_id}/mapping/combine")
def combine(
    request: Request,
    document_id: str,
    canonical_code: str = Form(...),
    note: str = Form(""),
    fact_ids: "list[str]" = Form(default=[]),
):
    """Item 53, 11.5. Several raw lines onto one canonical line."""
    result = _load(request, document_id)
    try:
        updated = combine_facts(
            result, list(fact_ids), canonical_code, actor=_actor(request), note=note
        )
    except (MappingError, KeyError) as exc:
        return _mapping_back(document_id, error=str(exc))
    _repository(request).save(apply_findings(updated))
    return _mapping_back(
        document_id, ok=f"Combined {len(fact_ids)} line(s) into {canonical_code}."
    )


@router.post("/documents/{document_id}/mapping/approve-all")
def approve_everything(request: Request, document_id: str, note: str = Form("")):
    """11.11 in bulk. Refuses rather than approving around a double count."""
    result = _load(request, document_id)
    try:
        updated = approve_all(result, actor=_actor(request), note=note)
    except MappingError as exc:
        return _mapping_back(document_id, error=str(exc))
    _repository(request).save(apply_findings(updated))
    return _mapping_back(document_id, ok="Approved every outstanding mapping.")


def _ledger_rows(ledger: dict) -> list[dict]:
    """The normalized ledger as rows a template can iterate.

    Keyed by (canonical line, statement) rather than by code alone, because
    `net_income` is printed on two statements and the two are separate rows --
    which is the whole reason `normalize` keys on the statement.
    """
    order = {item.canonical_code: index for index, item in enumerate(CHART)}
    grouped: dict = {}
    for (code, period, statement), value in ledger.items():
        grouped.setdefault((code, statement), {})[period] = value
    rows = []
    for (code, statement), cells in grouped.items():
        item = next(i for i in CHART if i.canonical_code == code)
        rows.append({"item": item, "statement": statement, "cells": cells})
    rows.sort(key=lambda row: (order[row["item"].canonical_code], row["statement"].value))
    return rows


# --- items 59-67: the historical statements screen (7.5) --------------------

STATEMENT_ORDER = (
    (Statement.INCOME, "Income statement", "12.1"),
    (Statement.BALANCE, "Balance sheet", "12.2"),
    (Statement.CASHFLOW, "Cash flow statement", "12.3"),
)


@router.get("/documents/{document_id}/statements", response_class=HTMLResponse)
def statements(request: Request, document_id: str, error: str = "", ok: str = ""):
    """7.5 Historical Statements. Every cell traces back to a page."""
    result = _load(request, document_id)

    try:
        built = build_statements(result, strict=False)
    except BuildError as exc:
        return _templates(request).TemplateResponse(
            request=request, name="statements.html",
            context={
                "document": result.document, "result": result, "built": None,
                "blocked": str(exc), "error": error, "ok": ok,
                "equity_note": equity_statement_status(),
            },
        )

    raw = reported_strings(result)
    tables = [
        {
            "statement": statement,
            "title": title,
            "rule": rule,
            "rows": statement_view(built, statement, raw_values=raw),
        }
        for statement, title, rule in STATEMENT_ORDER
    ]
    checks = run_historical_checks(built)

    export_error = ""
    engine_inputs = None
    try:
        engine_inputs = build_engine_inputs(result, build_statements(result, strict=True))
    except (BuildError, ExportError) as exc:
        export_error = str(exc)

    return _templates(request).TemplateResponse(
        request=request, name="statements.html",
        context={
            "document": result.document,
            "result": result,
            "built": built,
            "blocked": "",
            "tables": tables,
            "checks": checks,
            "check_summary": summarize(checks),
            "citations": citations(result),
            "equity_note": equity_statement_status(),
            "engine_inputs": engine_inputs,
            "export_error": export_error,
            "error": error,
            "ok": ok,
        },
    )


# --- items 69-77: the supporting schedules screen (7.6) ---------------------

#: 7.6's order, minus the three that are never built and the tax schedule,
#: which has its own shape. These are the roll-forwards, and the screen renders
#: them from one template block.
ROLLFORWARD_KEYS = ("ppe", "debt", "retained_earnings", "common_equity")


@router.get("/documents/{document_id}/schedules", response_class=HTMLResponse)
def schedules(request: Request, document_id: str, error: str = "", ok: str = ""):
    """7.6 Supporting Schedules.

    Built with `strict=False`, like the statements screen: a reviewer should
    watch the schedules fill in as they work rather than meet a blank page
    until the last fact is verified. The reconciliation results say what rests
    on an unverified figure, and the export -- which is the thing that must not
    move on unverified data -- builds strictly and separately.
    """
    result = _load(request, document_id)

    try:
        built = build_statements(result, strict=False)
    except BuildError as exc:
        return _templates(request).TemplateResponse(
            request=request, name="schedules.html",
            context={
                "document": result.document, "result": result, "schedules": None,
                "blocked": str(exc), "error": error, "ok": ok,
            },
        )

    schedule_set = build_schedules(built)
    checks = run_schedule_checks(schedule_set)

    return _templates(request).TemplateResponse(
        request=request, name="schedules.html",
        context={
            "document": result.document,
            "result": result,
            "schedules": schedule_set,
            "rollforwards": [schedule_set.by_key(key) for key in ROLLFORWARD_KEYS],
            "wc_table": working_capital_rows(schedule_set.working_capital),
            "wc_drivers": driver_rows(schedule_set.working_capital),
            "checks": checks,
            "check_summary": summarize_schedule_checks(checks),
            "blocked": "",
            "error": error,
            "ok": ok,
        },
    )


# --- items 78-88: the formula engine screen (18.10, 18.11) ------------------

@router.get("/documents/{document_id}/formulas", response_class=HTMLResponse)
def formulas(request: Request, document_id: str, error: str = ""):
    """Section 18's two "provide" clauses, provided.

    18.10 asks for a human-readable formula for every calculated cell and
    18.11 for the exact input values used. Both are written as obligations to
    a person, and a trace that exists only inside a test satisfies neither.
    """
    result = _load(request, document_id)

    try:
        built = build_statements(result, strict=False)
    except BuildError as exc:
        return _templates(request).TemplateResponse(
            request=request, name="formulas.html",
            context={
                "document": result.document, "result": result, "report": None,
                "blocked": str(exc), "error": error,
            },
        )

    return _templates(request).TemplateResponse(
        request=request, name="formulas.html",
        context={
            "document": result.document,
            "result": result,
            "report": formula_report(built),
            "blocked": "",
            "error": error,
        },
    )


# --- items 89-96: the assumptions screen (7.7) ------------------------------

#: The forecast periods this system plans for. `export.py` already fixes five
#: (FORECAST_YEARS), and the gate has to ask about each one separately: a
#: driver scoped to 2026E alone is missing from the other four.
def _forecast_periods(built) -> "tuple[str, ...]":
    from ..statements.export import FORECAST_YEARS

    last = int(built.years[-1][:4]) if built.years else 0
    return tuple(f"{last + offset}E" for offset in range(1, FORECAST_YEARS + 1))


def _scenario_store(request: Request) -> ScenarioStore:
    return ScenarioStore(request.app.state.storage_root)


def _assumptions_back(document_id: str, scenario_id: str, **flash) -> RedirectResponse:
    query = urlencode({"scenario_id": scenario_id, **{k: v for k, v in flash.items() if v}})
    return RedirectResponse(
        f"/documents/{document_id}/assumptions?{query}", status_code=303
    )


def _assumptions_context(request: Request, document_id: str, scenario_id: str):
    """Everything the screen needs, or the reason there is nothing to show."""
    result = _load(request, document_id)
    try:
        built = build_statements(result, strict=False)
    except BuildError as exc:
        return result, None, str(exc)
    return result, built, ""


@router.get("/documents/{document_id}/assumptions", response_class=HTMLResponse)
def assumptions(
    request: Request,
    document_id: str,
    scenario_id: str = BASE,
    error: str = "",
    ok: str = "",
):
    """7.7 Assumptions: the drivers, their evidence, and the 14.1 gate."""
    result, built, blocked = _assumptions_context(request, document_id, scenario_id)
    if blocked:
        return _templates(request).TemplateResponse(
            request=request, name="assumptions.html",
            context={
                "document": result.document, "result": result, "blocked": blocked,
                "error": error, "ok": ok, "scenario_id": scenario_id,
            },
        )

    scenarios = _scenario_store(request).load(document_id, owner=_actor(request))
    periods = _forecast_periods(built)
    rows = required_rows(scenarios, scenario_id)
    # The status form needs the legal moves for each row's own assumption.
    rows = tuple(
        _with_statuses(row) for row in rows
    )
    schedules = build_schedules(built)

    return _templates(request).TemplateResponse(
        request=request, name="assumptions.html",
        context={
            "document": result.document,
            "result": result,
            "blocked": "",
            "scenario_id": scenario_id,
            "scenario_rows": scenario_rows(scenarios),
            "required_rows": rows,
            "satisfied_count": sum(1 for row in rows if row.is_satisfied),
            "optional_rows": optional_rows(scenarios, scenario_id),
            "proposals": propose_from_schedules(schedules, owner=_actor(request)),
            "unmeasurable": unproposable(schedules),
            "gate": evaluate_gate(scenarios, scenario_id, periods),
            "periods": periods,
            "editable_codes": sorted(scenarios.resolve(scenario_id)),
            "impact": request.app.state.last_impact.pop(document_id, None)
            if hasattr(request.app.state, "last_impact") else None,
            "error": error,
            "ok": ok,
        },
    )


class _RowWithStatuses:
    """A view row plus the statuses its assumption may legally move to."""

    def __init__(self, row, statuses):
        self._row = row
        self.statuses = statuses

    def __getattr__(self, name):
        return getattr(self._row, name)


def _with_statuses(row):
    return _RowWithStatuses(
        row, status_choices(row.assumption) if row.assumption is not None else ()
    )


@router.post("/documents/{document_id}/assumptions/accept")
def accept_proposal(
    request: Request,
    document_id: str,
    scenario_id: str = Form(BASE),
    code: str = Form(...),
):
    """7.7.a: take a measured historical driver into the scenario, as a Draft."""
    result, built, blocked = _assumptions_context(request, document_id, scenario_id)
    if blocked:
        return _assumptions_back(document_id, scenario_id, error=blocked)

    proposals = propose_from_schedules(
        build_schedules(built), owner=_actor(request)
    )
    match = next((p for p in proposals if p.assumption.code == code), None)
    if match is None:
        return _assumptions_back(
            document_id, scenario_id,
            error=f"{code!r} is not a driver the schedules measured.",
        )

    store = _scenario_store(request)
    scenarios = store.load(document_id, owner=_actor(request))
    try:
        from dataclasses import replace

        scenarios = scenarios.with_assumption(
            replace(match.assumption, scenario_id=scenario_id)
        )
    except (AssumptionError, ScenarioError) as exc:
        return _assumptions_back(document_id, scenario_id, error=str(exc))
    store.save(document_id, scenarios)
    return _assumptions_back(
        document_id, scenario_id,
        ok=f"{code} added as a Draft. It cannot be forecast on until reviewed (14.1).",
    )


@router.post("/documents/{document_id}/assumptions/{code}/status")
def change_status(
    request: Request,
    document_id: str,
    code: str,
    scenario_id: str = Form(BASE),
    to: str = Form(...),
    reviewer: str = Form(""),
    reason: str = Form(""),
):
    """Item 95: a status change, with an actor and a written reason."""
    store = _scenario_store(request)
    scenarios = store.load(document_id, owner=_actor(request))
    resolved = scenarios.resolve(scenario_id).get(code)
    if resolved is None or resolved.from_scenario != scenario_id:
        return _assumptions_back(
            document_id, scenario_id,
            error=f"{code!r} is not an assumption {scenario_id!r} holds of its own.",
        )
    try:
        moved, _change = transition(
            resolved.assumption, Status(to),
            actor=_actor(request), reason=reason, reviewer=reviewer,
        )
    except (WorkflowError, ValueError) as exc:
        return _assumptions_back(document_id, scenario_id, error=str(exc))

    store.save(document_id, scenarios.with_assumption(moved))
    return _assumptions_back(
        document_id, scenario_id, ok=f"{code} is now {moved.status.value}."
    )


@router.post("/documents/{document_id}/assumptions/preview")
def preview_assumption(
    request: Request,
    document_id: str,
    scenario_id: str = Form(BASE),
    code: str = Form(...),
    value: str = Form(...),
):
    """14.8: show what a change would do, WITHOUT doing it.

    The impact is held for exactly one render and then dropped. Storing it
    would make it a saved thing, which is the opposite of what 14.8 asks for.
    """
    result, built, blocked = _assumptions_context(request, document_id, scenario_id)
    if blocked:
        return _assumptions_back(document_id, scenario_id, error=blocked)

    scenarios = _scenario_store(request).load(document_id, owner=_actor(request))
    formulas = derivation_formulas()
    environment, _ = ledger_environment(built.ledgers, built.years[-1])

    try:
        impact = preview_change(
            formulas=formulas,
            base_environment=environment,
            scenarios=scenarios,
            scenario_id=scenario_id,
            code=code,
            proposed=D(value, what=f"proposed {code}"),
        )
    except (KeyError, PrecisionError, ValueError) as exc:
        return _assumptions_back(document_id, scenario_id, error=str(exc))

    if not hasattr(request.app.state, "last_impact"):
        request.app.state.last_impact = {}
    request.app.state.last_impact[document_id] = impact
    return _assumptions_back(document_id, scenario_id)
