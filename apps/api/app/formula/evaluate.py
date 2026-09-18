"""Items 81, 83 and 86: the Decimal evaluator, its refusals, and its trace.

Three of Section 18's requirements are about what the evaluator must NOT do,
and they are the ones worth stating first.

**18.14 -- reject missing inputs; do not coerce them to zero.** This is the
same commitment `model/statements.py` makes about a sparse ledger, at the
level of a single expression. A formula referring to a value the environment
does not carry raises `MissingInput` naming the reference; it does not
evaluate to zero, and it does not evaluate at all.

**18.13 -- reject division by zero with a visible diagnostic.** Not NaN, not
infinity, not a silently skipped row. The message names the expression that
evaluated to zero, because "division by zero" in a model with forty formulas
is not enough to find it by.

**4.4 -- no binary floating point.** Every number in here is a `Decimal` built
from the characters of a literal or taken from the environment. There is no
`float` in the path, and `model/numeric.py:D` -- which refuses a float rather
than converting it -- guards the boundary where values arrive.

What the evaluator must do, beyond producing the number, is 18.10 and 18.11:
a human-readable formula for every calculated cell, and the exact input values
used. Both come back on every successful evaluation, as
`Evaluation.formula` and `Evaluation.substituted`, so a reviewer sees
`(1,250,000 - 750,000)` beside `(revenue - cogs)` rather than having to
reconstruct which revenue it meant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation

from model.numeric import ZERO, D

from .parse import Binary, Call, Literal, Node, Reference, Unary, parse
from .units import Unit, UnitError, add, divide, multiply, power, same


class EvaluationError(ValueError):
    """The formula is well-formed and could not be evaluated."""


class MissingInput(EvaluationError):
    """18.14. A reference the environment does not carry."""

    def __init__(self, path: str, available: tuple[str, ...]):
        self.path = path
        near = [name for name in available if name.split(".")[-1] == path.split(".")[-1]]
        hint = f" Did you mean {', '.join(sorted(near))}?" if near else ""
        super().__init__(
            f"{path!r} is not available, and this formula needs it. "
            f"It is not zero: a value the model does not have and a value of "
            f"zero are different claims, and substituting one for the other "
            f"changes every total built on it (18.14).{hint}"
        )


class DivisionByZeroRefused(EvaluationError):
    """18.13. Named, visible, and never a silent NaN."""

    def __init__(self, divisor_text: str, numerator: Decimal):
        super().__init__(
            f"division by zero: {divisor_text!r} evaluated to 0, with "
            f"{numerator:,} above the line. The result is not zero and not "
            "infinity -- it does not exist, and 4.12 says a relative measure "
            "against zero is undefined rather than large (18.13)."
        )


@dataclass(frozen=True)
class Quantity:
    """A number with a unit and a note about where it came from."""

    amount: Decimal
    unit: Unit
    origin: str = ""

    def __post_init__(self) -> None:
        # `D` refuses a float rather than converting it (4.4).
        object.__setattr__(self, "amount", D(self.amount, what=self.origin or "quantity"))


@dataclass
class Environment:
    """Reference path -> `Quantity`. A plain mapping, deliberately.

    Resolution is a dictionary lookup, never an attribute access, so a
    formula cannot reach a method or a dunder on anything (18.3).
    """

    values: dict[str, Quantity] = field(default_factory=dict)

    def put(self, path: str, amount, unit: Unit, origin: str = "") -> Environment:
        self.values[path] = Quantity(amount, unit, origin or path)
        return self

    def get(self, path: str) -> Quantity:
        if path not in self.values:
            raise MissingInput(path, tuple(self.values))
        return self.values[path]

    def has(self, path: str) -> bool:
        return path in self.values

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(sorted(self.values))


@dataclass(frozen=True)
class Evaluation:
    """What 18.10 and 18.11 ask be available for every calculated cell."""

    value: Decimal
    unit: Unit
    #: 18.10: the formula as written, fully parenthesised.
    formula: str
    #: 18.11: the same expression with each reference replaced by its value.
    substituted: str
    #: 18.11: the exact inputs used, by reference path.
    inputs: dict[str, Decimal]

    def explain(self) -> str:
        return f"{self.formula} = {self.substituted} = {self.value:,}"


def _format(value: Decimal) -> str:
    """A number as a reviewer reads it, without rounding it.

    `:,` groups thousands and prints every digit the Decimal holds, so the
    substituted formula in 18.11 is the exact input and not a display value.
    """
    return f"{value:,}"


def _evaluate(node: Node, environment: Environment, inputs: dict[str, Decimal]) -> tuple[Decimal, Unit, str]:
    """Returns the value, its unit, and the substituted text for this subtree."""
    if isinstance(node, Literal):
        return node.value, _literal_unit(node), node.raw

    if isinstance(node, Reference):
        quantity = environment.get(node.path)
        inputs[node.path] = quantity.amount
        return quantity.amount, quantity.unit, _format(quantity.amount)

    if isinstance(node, Unary):
        value, unit, text = _evaluate(node.operand, environment, inputs)
        return -value, unit, f"-{text}"

    if isinstance(node, Binary):
        return _binary(node, environment, inputs)

    if isinstance(node, Call):
        return _call(node, environment, inputs)

    raise EvaluationError(f"unknown node {node!r}")  # pragma: no cover


def _literal_unit(node: Literal) -> Unit:
    """A bare number is dimensionless.

    It is typed `ratio` rather than given a unit of its own, so `revenue * 2`
    works and `revenue + 2` is refused -- which is the right pair of answers:
    doubling a currency is meaningful, adding two of nothing to it is not.
    """
    from .units import RATIO

    return RATIO


def _binary(node: Binary, environment: Environment, inputs) -> tuple[Decimal, Unit, str]:
    left, left_unit, left_text = _evaluate(node.left, environment, inputs)

    if node.op == "^":
        return _power(node, left, left_unit, left_text, environment, inputs)

    right, right_unit, right_text = _evaluate(node.right, environment, inputs)
    text = f"({left_text} {node.op} {right_text})"

    if node.op == "+":
        return left + right, add(left_unit, right_unit, "+"), text
    if node.op == "-":
        return left - right, add(left_unit, right_unit, "-"), text
    if node.op == "*":
        return left * right, multiply(left_unit, right_unit), text
    if node.op == "/":
        if right == ZERO:
            raise DivisionByZeroRefused(node.right.text(), left)
        try:
            return left / right, divide(left_unit, right_unit), text
        except (DivisionByZero, InvalidOperation) as exc:  # pragma: no cover
            raise DivisionByZeroRefused(node.right.text(), left) from exc
    raise EvaluationError(f"unknown operator {node.op!r}")  # pragma: no cover


def _power(node: Binary, base, base_unit, base_text, environment, inputs):
    """`^` with an integer exponent only (4.12's "integer exponentiation").

    A non-integer power is not exact in decimal arithmetic, and 4.4 makes the
    authoritative engine exact. A formula that needs one needs a decision about
    its precision before it needs an operator.
    """
    exponent, exponent_unit, exponent_text = _evaluate(node.right, environment, inputs)
    if exponent != exponent.to_integral_value():
        raise EvaluationError(
            f"the exponent in {node.text()!r} evaluated to {exponent}, which is "
            "not an integer. Only integer exponentiation is exact in decimal "
            "arithmetic (4.12), so a fractional power is refused rather than "
            "silently rounded."
        )
    if not exponent_unit.is_dimensionless:
        raise EvaluationError(
            f"the exponent in {node.text()!r} is {exponent_unit.describe()}; "
            "an exponent must be a plain number (18.12)"
        )
    whole = int(exponent)
    if whole < 0 and base == ZERO:
        raise DivisionByZeroRefused(node.left.text(), D(1))
    return base ** whole, power(base_unit, whole), f"({base_text} ^ {exponent_text})"


def _call(node: Call, environment: Environment, inputs) -> tuple[Decimal, Unit, str]:
    evaluated = [_evaluate(argument, environment, inputs) for argument in node.arguments]
    values = [item[0] for item in evaluated]
    texts = [item[2] for item in evaluated]
    unit = evaluated[0][1]
    if node.function == "abs":
        return abs(values[0]), unit, f"abs({texts[0]})"
    for _, other_unit, _ in evaluated[1:]:
        unit = same(unit, other_unit)
    chosen = min(values) if node.function == "min" else max(values)
    return chosen, unit, f"{node.function}({', '.join(texts)})"


def evaluate(
    formula: str | Node, environment: Environment, expected_unit: Unit | None = None
) -> Evaluation:
    """Evaluate one formula, exactly, and return it with its trace.

    `expected_unit` is the unit a formula DECLARES it produces. It is verified
    against the unit the arithmetic computed rather than inferred from it: a
    dimensionless result may be a margin or a multiple, and no algebra recovers
    which one was meant.
    """
    node = parse(formula) if isinstance(formula, str) else formula
    inputs: dict[str, Decimal] = {}
    value, unit, substituted = _evaluate(node, environment, inputs)

    if expected_unit is not None and unit.exponents != expected_unit.exponents:
        raise UnitError(
            f"{node.text()} produces {unit.describe()}, but the formula declares "
            f"{expected_unit.describe()} (18.12). One of the two is wrong, and "
            "guessing which would make the declaration worthless."
        )
    return Evaluation(
        value=value,
        unit=expected_unit or unit,
        formula=node.text(),
        substituted=substituted,
        inputs=dict(inputs),
    )
