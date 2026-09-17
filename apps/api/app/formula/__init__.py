"""Phase 8 (items 78-88): the formula engine of specification Section 18.

Formulas as versioned definitions rather than Python expressions, parsed into
a dependency graph, ordered, checked for cycles before evaluation, evaluated
exactly in `Decimal`, unit-checked, and fingerprinted so the same inputs over
the same formulas give the same answer and hash the same.

Nothing here evaluates arbitrary code. There is no `eval`, `exec`, `compile`
or `ast.literal_eval` in the package -- 18.3 is a property of the
implementation, not a promise about inputs.
"""

from .calculate import CalculatedCell, CalculatedModel, calculate, recalculate
from .catalog import computable_subset, derivation_formulas, ledger_environment
from .evaluate import (
    DivisionByZeroRefused,
    Environment,
    Evaluation,
    EvaluationError,
    MissingInput,
    Quantity,
    evaluate,
)
from .graph import CycleError, DependencyGraph
from .parse import FormulaSyntaxError, parse
from .registry import FormulaDefinition, FormulaSet, RegistryError, calculation_fingerprint
from .units import UnitError, unit_for

__all__ = [
    "CalculatedCell",
    "CalculatedModel",
    "CycleError",
    "DependencyGraph",
    "DivisionByZeroRefused",
    "Environment",
    "Evaluation",
    "EvaluationError",
    "FormulaDefinition",
    "FormulaSet",
    "FormulaSyntaxError",
    "MissingInput",
    "Quantity",
    "RegistryError",
    "UnitError",
    "calculate",
    "calculation_fingerprint",
    "computable_subset",
    "derivation_formulas",
    "evaluate",
    "ledger_environment",
    "parse",
    "recalculate",
    "unit_for",
]
