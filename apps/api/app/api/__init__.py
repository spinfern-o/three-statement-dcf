"""The web application -- specification Phase 4, items 39 to 44.

    39  routes.py   source-room navigation
    40  rendering.py  the PDF page viewer
    41  bookmarks.py  statement and page bookmarks
    42  templates/  highlighted source bounding boxes
    43  templates/  the raw-versus-parsed fact view
    44  routes.py   metadata confirmation

# A deviation from 3.1, recorded rather than slipped in

Specification 3.1.a recommends Next.js with TypeScript for the front end.
This phase is server-rendered HTML from FastAPI instead, and the reasoning is
3.1.b's own: "React Server Components only where they do not complicate
financial state."

The source room has no financial state to complicate. It is a document
annotation surface -- a page image, rectangles drawn on it, a list of values,
and forms that post one decision with one reason. There is no recalculation,
no derived model, nothing that changes as you type. A server-rendered page is
the simpler correct tool for that, it has no build step, and every one of
6.6's accessibility requirements is easier to meet in semantic HTML than in a
component tree.

Where a React application earns its place is Phase 12's dashboard: live
recalculation, charts, unsaved assumption edits marked as you type (6.5.c).
That is the right place to introduce it, and this deviation is recorded in
`docs/decision-ledger.md` so it is a decision rather than a drift.
"""
