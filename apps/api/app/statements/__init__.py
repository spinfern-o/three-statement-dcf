"""Historical statements -- specification Phase 6, items 59 to 68.

    59  build.py   the normalized income statement
    60  build.py   the normalized balance sheet
    61  build.py   the normalized cash flow statement
    62  views.py   the equity statement, when available -- it is not, and the
                   screen says so rather than showing an empty table
    63  views.py   reported and normalized views
    64  views.py   common-size and growth views
    65  (web)      source drill-down per cell
    66  checks.py  the historical checks
    67  checks.py  keep differences visible; do not plug
    68  (tests)    golden historical-model tests

**This package is the join.** Until now the two halves of the repository
agreed and did not touch: `model/` built statements from YAML a human typed,
and `apps/api/` read a PDF into verified, mapped facts. `build.py` takes the
second and produces the first -- real `model.statements.Ledger` objects whose
every cell carries a `Figure` with the page it was printed on.

That it works at all is a claim about both halves, so it is worth naming what
had to be true first. A `Figure` cannot exist without a page and the
company's own wording, which extraction records. A `Ledger` refuses an account
outside the chart, which mapping guarantees. And a value must be an exact
`Decimal`, which the parser produces from the printed string and never from a
float. Phase 6 is short because Phases 3, 4 and 5 did the work.
"""
