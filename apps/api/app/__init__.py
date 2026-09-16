"""Service code.

The calculation engine is not duplicated here. `model/` remains the single
authoritative implementation of the 37-step workflow, and this package imports
its Decimal context from `model.numeric` so there is exactly one.
"""

from model.numeric import use_calculation_context as _use_calculation_context

# Specification 4.7/4.8. `model/__init__.py` does the same thing for the same
# reason: a context installed per-module leaves arithmetic running at whatever
# precision the importing thread happened to have.
_use_calculation_context()
