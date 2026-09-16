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

from ..extraction.records import confirm_metadata
from ..review.actions import ACCEPT, CORRECT, REJECT, ReviewError, accept_fact, correct_fact, reject_fact
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
