"""Phase 16, items 154-168: final verification, and the report that evidences it.

Item 168 is the deliverable — "produce a release-readiness report with PASS/FAIL
evidence" — and the word that shapes this package is **evidence**. A report
whose rows a person typed is a claim about the code; a report whose rows come
from running the code is evidence about it. So nothing here is written by hand:
[`plan.py`](plan.py) maps every Section 22 clause onto the tests that cover it
and is asserted against the test files, and [`report.py`](report.py) runs the
suites and reports what they returned.

**This is the one place 4.20's claim can legitimately be made.** The in-app
benchmark panel cannot make it: "never claim less than 0.0001% error until the
benchmark suite passes and the test report identifies the exact dataset and
formulas tested", and a web process does not observe the test suite. A report
generator *runs* it. So the panel reports coverage and this reports the result
— and when the suite has not been run, this says so rather than carrying the
claim forward from the last time somebody looked.
"""
