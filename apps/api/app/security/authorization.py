"""Item 146: 20.7's check, and the part of it that is easy to get wrong.

`security-model.md` fixed the design in Phase 2, before any endpoint existed:

  - checked **server-side on every request, including reads**;
  - on the **resource's owner, resolved from the resource**, never from a
    parameter the client supplied;
  - an unauthorized resource returns **the same response as a nonexistent
    one**, so identifiers do not leak existence.

The third is the one that gets dropped. Returning 403 for a document that
exists and 404 for one that does not tells an unauthenticated prober which
document identifiers are real, one request at a time -- and a document
identifier here is derived from a filing nobody has released. Both cases
return 404.

2.2.b says single user, so today every document has the same owner and this
check can never fail in production. It is built anyway, and tested with a
second owner, because the alternative is a system whose authorization is a
comment saying it would not matter -- and the day it starts to matter is the
day somebody adds a second user, which is not the day to discover that reads
were never checked.
"""

from __future__ import annotations

from fastapi import HTTPException

#: 2.2.d: one role, and it is the owner's. RBAC is N/A rather than deferred --
#: 20.6 applies it "if multi-user" and 2.2.b says single.
OWNER_ROLE = "owner"

#: What an unauthorized request is told. Identical to what a request for a
#: document that was never ingested is told.
NOT_FOUND = "No such document."


def owner_of(result) -> str:
    """The owner recorded on the resource itself.

    `company_id` is what `SourceDocument` carries, and under 2.2.b it is the
    owner. Read from the stored record rather than from the request, because a
    check against a value the client supplied is not a check.
    """
    return getattr(result.document, "company_id", "") or ""


def require_access(result, actor: str) -> None:
    """Raise 404 unless `actor` may see this document.

    404, not 403: see the module docstring. The exception carries no detail
    about which of the two it was.
    """
    if not _may_access(result, actor):
        raise HTTPException(status_code=404, detail=NOT_FOUND)


def _may_access(result, actor: str) -> bool:
    owner = owner_of(result)
    if not owner:
        # A document with no recorded owner is not one this check can pass.
        # Refusing is the safe direction: the alternative is treating "we do
        # not know who owns this" as "anybody may read it".
        return False
    return owner == actor or actor == OWNER_ROLE


def visible(results, actor: str) -> list:
    """Filter a listing. The portfolio must not list what a reader cannot open."""
    return [result for result in results if _may_access(result, actor)]
