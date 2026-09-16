"""Exact decimal arithmetic for the authoritative calculation path.

Specification rules 1.15 and 4.4 prohibit binary floating point here, and
4.2 requires monetary inputs to arrive as decimal strings. Both matter for
the same reason: `0.08` parsed as a float is not 0.08, it is

    0.08000000000000000166533453693773481063544750213623046875

so converting a float to Decimal preserves the error rather than removing
it. A port that accepted floats would look compliant and not be.

`D()` therefore REFUSES floats outright. That is the same stance the rest
of this codebase takes toward missing data: fail loudly rather than accept
something that looks close enough. There is no code path that silently
turns a float into a Decimal.

Context policy (specification 4.7, 4.8):

  precision  50 significant digits. The rule requires at least 28; 50 is
             chosen for headroom, because the discount chain compounds
             `(1 + WACC) ** t` and then divides by it, and the cost of the
             extra digits is negligible at the few thousand operations a
             model performs.
  rounding   ROUND_HALF_EVEN, which 4.8 names as the default. It is the
             standard choice in financial systems because, unlike
             half-up, it does not bias a long series of roundings upward.
  traps      InvalidOperation, DivisionByZero and Overflow all raise
             rather than producing NaN or Infinity, which 17.27 forbids in
             a released calculation and 18.13 requires be diagnosed.

Intermediate values are never rounded (4.9). Rounding happens only at
display, via `quantize_for_display`.
"""

from __future__ import annotations

import decimal
from decimal import Decimal, DivisionByZero, InvalidOperation, Overflow
from typing import Union

# Specification 4.7 requires at least 28 significant digits.
MINIMUM_PRECISION = 28
CALCULATION_PRECISION = 50

ROUNDING = decimal.ROUND_HALF_EVEN

CALCULATION_CONTEXT = decimal.Context(
    prec=CALCULATION_PRECISION,
    rounding=ROUNDING,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)

assert CALCULATION_PRECISION >= MINIMUM_PRECISION, "violates specification 4.7"

#: What `D()` will accept. Note the absence of `float`.
Numeric = Union[str, int, Decimal]


class PrecisionError(ValueError):
    """A value entered the calculation path in a form that loses exactness."""


def use_calculation_context() -> None:
    """Install the calculation context for the current thread."""
    decimal.setcontext(CALCULATION_CONTEXT)


def D(value: Numeric, *, what: str = "value") -> Decimal:
    """Convert to Decimal, refusing anything that has already lost precision.

    Accepts a decimal string (4.2's required boundary form), an int, or an
    existing Decimal. Refuses float, bool, and None.
    """
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise PrecisionError(f"{what} is {value}, which cannot appear in a calculation (17.27)")
        return value
    if isinstance(value, bool):
        raise PrecisionError(f"{what} is a bool, not a number")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise PrecisionError(
            f"{what} arrived as a float ({value!r}). Specification 1.15 and 4.4 prohibit "
            f"binary floating point in the authoritative calculation path, and converting "
            f"it here would preserve the error rather than remove it: "
            f"Decimal({value!r}) is {Decimal(value)}. "
            f"Supply it as a decimal string instead (4.2)."
        )
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise PrecisionError(f"{what} is an empty string")
        try:
            result = Decimal(text)
        except InvalidOperation:
            raise PrecisionError(f"{what} is not a valid decimal number: {value!r}") from None
        if not result.is_finite():
            raise PrecisionError(f"{what} is {text!r}, which cannot appear in a calculation (17.27)")
        return result
    raise PrecisionError(f"{what} has unsupported type {type(value).__name__}")


ZERO = Decimal(0)
ONE = Decimal(1)


def quantize_for_display(value: Decimal, places: int = 1) -> Decimal:
    """Round for presentation only (4.9, 4.18).

    The stored value is never replaced by this; the display layer calls it
    and the full-precision value remains available for the tooltip 4.19
    requires.
    """
    exponent = Decimal(1).scaleb(-places)
    return value.quantize(exponent, rounding=ROUNDING, context=CALCULATION_CONTEXT)


def relative_error(actual: Decimal, expected: Decimal) -> Decimal:
    """Specification 4.10, as a Decimal so the comparison is itself exact.

    Undefined when `expected` is zero; 4.12 governs that case, and callers
    handle it with an absolute bound instead.
    """
    if expected == 0:
        raise PrecisionError("relative error is undefined when the expected value is zero (4.12)")
    with decimal.localcontext(CALCULATION_CONTEXT):
        return abs(actual - expected) / abs(expected) * Decimal(100)


def power(base: Decimal, exponent: int) -> Decimal:
    """Integer exponentiation inside the calculation context (4.13).

    Integer exponents keep this exact to the context's precision; the
    discounting path never needs a fractional power under the year-end
    convention the engine implements.
    """
    if not isinstance(exponent, int) or isinstance(exponent, bool):
        raise PrecisionError(f"exponent must be an int, got {exponent!r}")
    with decimal.localcontext(CALCULATION_CONTEXT):
        return base ** exponent
