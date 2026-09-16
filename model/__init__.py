"""A three-statement model to DCF, built to the 37-step workflow in
`three_statement_model_to_dcf_step_by_step.txt` at the repository root.

The spec's recurring instruction is negative -- do not invent, do not plug,
do not hide, do not assume. This package is organized around enforcing
those refusals in code rather than relying on discipline:

  provenance.py  every historical figure carries page and line item (STEP 4)
  accounts.py    a line the company does not report stays absent (STEP 5)
  profile.py     no modeling until the filing is identified (STEP 1-3, 12)
  statements.py  reported vs derived vs forecast, tracked per cell (STEP 5-7)
  schedules.py   roll-forwards that refuse to break their chain (STEP 8)
  assumptions.py no driver without a basis and a source (STEP 10-11)
  forecast.py    cash falls out of the cash flow statement (STEP 12-22)
  dcf.py         FCFF read back out of the model (STEP 23-35)
  sensitivity.py WACC x terminal growth grid (STEP 36)
  checks.py      the twelve PASS/FAIL checks (STEP 9, 37)
"""

from .numeric import use_calculation_context as _use_calculation_context

# Install the 50-digit ROUND_HALF_EVEN context (specification 4.7, 4.8) for
# this thread at import time.
#
# This is deliberate, and it is load-bearing. Python's decimal context is
# thread-local and defaults to 28 digits, so without it some operations ran
# inside an explicit 50-digit context while the arithmetic around them ran
# at 28 -- a discount factor computed at one precision and divided at
# another. Mixed precision is precisely the class of error this port exists
# to remove, so the context is set once, for the whole package, rather than
# wrapped around individual call sites where one could be missed.
#
# Code that calls the engine from a worker thread must call
# `model.numeric.use_calculation_context()` on that thread.
_use_calculation_context()

__all__ = [
    "accounts", "assumptions", "checks", "dcf", "forecast",
    "loader", "numeric", "profile", "provenance", "report", "schedules",
    "sensitivity", "statements", "yaml_exact",
]

__version__ = "0.1.0"
