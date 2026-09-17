"""Normalization and mapping -- specification Phase 5, items 50 to 58.

This is the stage that makes the rest of the system mean anything. Extraction
produces "Selling, general and administrative" with a number beside it. The
calculation engine consumes `operating_expenses`. Nothing carries the first to
the second until a human says the two are the same thing, and 11.3 puts it
exactly that way: map one raw line to one normalized line **only when
definitions align**.

    50  chart.py      the canonical chart, with a written definition per line
    51  proposals.py  system-proposed mappings, never auto-approved
    52  (web)         the review table, in apps/api/app/api/
    53  actions.py    split and combine
    54  checks.py     duplicate-count prevention
    55  checks.py     subtotal reconciliation
    56  actions.py    approval, which is what gates verification
    57  sets.py       versioned mapping sets
    58  (tests)       changing a mapping invalidates what depended on it

It is also the phase that finishes two things left open elsewhere:

- **`VERIFIED` becomes reachable.** source-policy.md §9's seventh condition is
  a human-approved mapping. Until this package existed, no fact could satisfy
  it and the review room correctly reported zero verified facts forever.
- **`SUBTOTAL_MISMATCH` and `CROSS_STATEMENT_MISMATCH` become raisable.** Both
  codes were defined in Phase 3 and never fired, because a subtotal has no
  components to compare against until its components are mapped.
"""
