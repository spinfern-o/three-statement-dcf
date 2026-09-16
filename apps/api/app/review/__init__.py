"""Source review -- specification Phase 4, items 39-49.

Phase 3 produced facts. None of them is worth anything yet: an extracted
number is a machine's reading of a page, and specification Section 10 spends
most of its length insisting that a human look at it. This package is the
domain half of that.

    45  actions.py   accept, correct, reject
    46  actions.py   every one of them requires a reason
    47  actions.py   every one of them writes an audit event
    48  progress.py  review progress and the unresolved count

The interface half -- the source room, the page viewer, the highlighted
boxes -- is in `apps/api/app/api/`.
"""
