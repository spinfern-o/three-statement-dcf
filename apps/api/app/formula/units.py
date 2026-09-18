"""Item 82: unit checking (18.12).

"Provide unit checking so percentages, currency, shares, and multiples cannot
be combined nonsensically."

The design question is how much of a unit system to build. Too little and the
check is a list of ad-hoc pair rules that grows a hole every time a formula is
added. Too much and every formula author spends their time arguing with a
dimensional algebra about whether days are time.

What is here is the smaller half of a dimensional system, plus one rule that
catches the error a dimensional system alone would miss.

**Dimensions.** Four base dimensions -- currency, shares, days, years -- and a
unit is a vector of their exponents. Multiplication adds exponents, division
subtracts them, and `^` with an integer literal multiplies them. That much is
mechanical and catches `revenue * revenue` (currency squared, which nothing
declares) and `revenue + shares_outstanding`.

**The rule dimensions alone would miss.** `ratio`, `percent` and `multiple`
all have no dimensions, so a dimensional system says a growth rate may be
added to a P/E multiple, and that a 5 stored as "5 percent" may be multiplied
by revenue. Both are wrong and both are plausible typing mistakes. So
addition and subtraction additionally require the two operands to be the SAME
NAMED UNIT, not merely dimensionally equal; and `percent` refuses to
participate in multiplication at all, because a percent's numeric value is a
hundred times the ratio it means and no formula should have to remember that.

**The declared output unit is checked, not inferred.** A formula declares what
it produces, and the engine verifies the declaration against the dimensions it
computed. That is deliberate: `currency / currency` is dimensionless, and
whether that dimensionless thing is a margin (ratio) or an EV/EBITDA
(multiple) is a fact about intent that no algebra recovers.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnitError(ValueError):
    """Two quantities were combined in a way that has no meaning."""


#: The base dimensions, in the order the exponent vector carries them.
DIMENSIONS = ("currency", "shares", "days", "years")


@dataclass(frozen=True)
class Unit:
    """A named unit with its dimensional exponents.

    `name` is what a person reads and what a formula declares. `exponents` is
    what the arithmetic checks. Two units may share exponents and differ in
    name -- `ratio` and `multiple` both being dimensionless is the whole
    reason the declared output unit is verified rather than inferred.
    """

    name: str
    exponents: tuple[int, ...]

    @property
    def is_dimensionless(self) -> bool:
        return all(exponent == 0 for exponent in self.exponents)

    def describe(self) -> str:
        if self.is_dimensionless:
            return f"{self.name} (dimensionless)"
        parts = [
            f"{dimension}{'' if exponent == 1 else f'^{exponent}'}"
            for dimension, exponent in zip(DIMENSIONS, self.exponents)
            if exponent
        ]
        return f"{self.name} ({' '.join(parts)})"


def _unit(name: str, **dimensions: int) -> Unit:
    return Unit(name, tuple(dimensions.get(d, 0) for d in DIMENSIONS))


#: The vocabulary data-dictionary.md §9.10 proposes, which the formula
#: catalogue's `output_unit` column already uses.
CURRENCY = _unit("currency", currency=1)
SHARES = _unit("shares", shares=1)
DAYS = _unit("days", days=1)
YEARS = _unit("years", years=1)
RATIO = _unit("ratio")
MULTIPLE = _unit("multiple")
PERCENT = _unit("percent")
#: `currency / shares`. Named because STEP 34's last division produces it and
#: an unnamed unit cannot be declared by a formula.
CURRENCY_PER_SHARE = _unit("currency_per_share", currency=1, shares=-1)

UNITS = {
    unit.name: unit
    for unit in (
        CURRENCY, SHARES, DAYS, YEARS, RATIO, MULTIPLE, PERCENT, CURRENCY_PER_SHARE
    )
}

#: Dimensionless units that a formula may multiply by. `percent` is absent on
#: purpose: 5 percent is stored as 5, and `revenue * growth_percent` would be
#: a hundred times the intended answer with no error anywhere to catch it.
SCALING_UNITS = frozenset({RATIO.name, MULTIPLE.name})


def unit_for(name: str) -> Unit:
    if name not in UNITS:
        raise UnitError(
            f"{name!r} is not a declared unit. Declared: {', '.join(sorted(UNITS))} "
            "(data-dictionary.md §9.10)"
        )
    return UNITS[name]


def _combine(left: Unit, right: Unit, sign: int) -> tuple[int, ...]:
    return tuple(a + sign * b for a, b in zip(left.exponents, right.exponents))


def _named(exponents: tuple[int, ...]) -> Unit:
    """The declared unit with these exponents, or an anonymous one.

    An anonymous unit is not an error by itself -- an intermediate result in a
    longer expression may legitimately have no name. It becomes an error only
    if it is what the formula claims to produce.
    """
    for unit in UNITS.values():
        if unit.exponents == exponents and unit.name not in ("multiple", "percent"):
            return unit
    parts = [
        f"{d}^{e}" for d, e in zip(DIMENSIONS, exponents) if e
    ]
    return Unit("(" + " ".join(parts) + ")" if parts else "(dimensionless)", exponents)


def add(left: Unit, right: Unit, operator: str = "+") -> Unit:
    """18.12 for `+` and `-`: the same named unit, not merely the same dimensions."""
    if left.name != right.name:
        detail = ""
        if left.exponents == right.exponents:
            detail = (
                " They have the same dimensions, which is exactly why this is "
                "refused: a value's name carries its scale, and adding a percent "
                "to a ratio is out by a factor of 100 with nothing to catch it."
            )
        raise UnitError(
            f"cannot {'add' if operator == '+' else 'subtract'} "
            f"{right.describe()} {'to' if operator == '+' else 'from'} "
            f"{left.describe()} (18.12).{detail}"
        )
    return left


def multiply(left: Unit, right: Unit) -> Unit:
    """18.12 for `*`. Percentages are refused outright; see SCALING_UNITS."""
    for side, unit in (("left", left), ("right", right)):
        if unit.name == PERCENT.name:
            raise UnitError(
                f"a percent cannot be multiplied ({side}-hand side of a `*`). "
                "A percent is stored as the number a person reads -- 5, not "
                "0.05 -- so multiplying by it is out by a factor of 100. "
                "Convert it to a ratio in the formula that declares it (18.12)."
            )
    if not left.is_dimensionless and not right.is_dimensionless:
        raise UnitError(
            f"cannot multiply {left.describe()} by {right.describe()}: the "
            "result has dimensions no declared unit carries, so nothing can "
            "state what it means (18.12)."
        )
    if right.is_dimensionless and right.name in SCALING_UNITS:
        return left if not left.is_dimensionless else _scaled(left, right)
    if left.is_dimensionless and left.name in SCALING_UNITS:
        return right
    return _named(_combine(left, right, 1))


def _scaled(left: Unit, right: Unit) -> Unit:
    """ratio x ratio, ratio x multiple, and so on: dimensionless either way."""
    return RATIO if RATIO.name in (left.name, right.name) else MULTIPLE


def divide(left: Unit, right: Unit) -> Unit:
    if right.name == PERCENT.name or left.name == PERCENT.name:
        raise UnitError(
            "a percent cannot take part in a division: its numeric value is a "
            "hundred times the ratio it means. Convert it to a ratio first "
            "(18.12)."
        )
    return _named(_combine(left, right, -1))


def power(base: Unit, exponent: int) -> Unit:
    """`^` with an integer. A unit raised to a non-integer has no meaning here."""
    if base.name == PERCENT.name:
        raise UnitError("a percent cannot be raised to a power (18.12)")
    if base.is_dimensionless:
        return base
    return _named(tuple(e * exponent for e in base.exponents))


def same(left: Unit, right: Unit) -> Unit:
    """`min`, `max`: every argument must be the same named unit."""
    return add(left, right, "+")
