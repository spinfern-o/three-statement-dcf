"""Items 78 and 84: formulas as versioned definitions (18.1), and their
fingerprints (18.7).

18.1 says "store formulas as versioned definitions". The engine in `model/`
stores them as Python expressions, which is a perfectly good way to compute
them and a poor way to answer the questions Section 18 asks: what version of
this formula produced that number, what exactly did it depend on, and would
the same inputs produce the same answer tomorrow.

A `FormulaDefinition` is the row `docs/formula-catalog.md` describes: a stable
code, the target it computes, the expression, the unit it declares, a version,
and the specification clause it comes from. The catalogue is the source, and
`catalog.py` holds the rows; a test asserts the registry and
`model/accounts.py:DERIVED` cannot drift apart, because two chart definitions
that disagree is worse than one.

**Fingerprints (18.7).** A fingerprint answers "is this the same
calculation?" and nothing else -- it is not a signature and proves nothing
about who ran it. Two are produced:

- a *formula* fingerprint over the code, version, expression and declared
  unit, so editing an expression changes it and reformatting a docstring does
  not; and
- a *calculation* fingerprint over the formula fingerprints plus every input
  value used, so the same model re-run on the same inputs hashes identically
  and a single changed input does not.

Values are hashed as their exact decimal strings. `Decimal("1.0")` and
`Decimal("1")` are equal numbers and different strings, so the fingerprint
distinguishes them -- which is right: 4.14 makes the precision a filing was
reported to a fact about the calculation, not an accident of formatting.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from .parse import Node, parse
from .units import Unit, unit_for


class RegistryError(ValueError):
    """A formula definition is not usable as written."""


def _digest(*parts: str) -> str:
    """SHA-256 over length-prefixed parts, so no separator can be forged."""
    hasher = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        hasher.update(str(len(encoded)).encode("ascii"))
        hasher.update(b":")
        hasher.update(encoded)
    return hasher.hexdigest()


@dataclass(frozen=True)
class FormulaDefinition:
    """One row of `docs/formula-catalog.md`, as data the engine can run."""

    code: str
    #: The reference path this formula computes.
    target: str
    expression: str
    output_unit: str
    version: int = 1
    #: The specification clause or workflow step it implements.
    rule: str = ""
    #: What it means, in a sentence. 11.3's lesson: a definition nobody wrote
    #: is a definition nobody can check a mapping against.
    definition: str = ""
    #: "exact" or "ctx", as the catalogue's Rounding column defines them.
    rounding: str = "exact"

    # None until `__post_init__` parses the expression. Declared optional,
    # because the default is None and a non-optional annotation over a None
    # default is a lie the checker was the first to notice.
    _tree: Node | None = field(init=False, repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise RegistryError("a formula definition needs a stable code (18.1)")
        if not self.target.strip():
            raise RegistryError(f"{self.code}: a formula must say what it computes")
        if self.version < 1:
            raise RegistryError(f"{self.code}: version must be 1 or greater (18.1)")
        if self.rounding not in ("exact", "ctx"):
            raise RegistryError(
                f"{self.code}: rounding must be 'exact' or 'ctx', got "
                f"{self.rounding!r} (formula-catalog.md)"
            )
        if not self.definition.strip():
            raise RegistryError(
                f"{self.code}: a formula needs a written definition. A catalogue "
                "row nobody can read is a row nobody can check (18.1, 11.3)."
            )
        unit_for(self.output_unit)  # raises if it is not a declared unit
        object.__setattr__(self, "_tree", parse(self.expression))
        if self.target in self.tree.references():
            raise RegistryError(
                f"{self.code}: {self.target!r} refers to itself. A self-reference "
                "is a cycle of length one, and 18.6 requires cycles be detected "
                "before evaluation, not during it."
            )

    @property
    def tree(self) -> Node:
        """The parsed expression. Parsed in `__post_init__`, so never None here.

        The check is not redundant: `_tree` is declared optional because its
        default is, and a property that returned None to a caller expecting a
        `Node` would fail somewhere else entirely.
        """
        if self._tree is None:  # pragma: no cover - __post_init__ always sets it
            raise RuntimeError(
                f"{self.code}: the expression was never parsed. That is a broken "
                "invariant in this class, not a problem with the formula -- so "
                "it is not a FormulaSyntaxError."
            )
        return self._tree

    @property
    def unit(self) -> Unit:
        return unit_for(self.output_unit)

    @property
    def inputs(self) -> frozenset[str]:
        return self.tree.references()

    @property
    def fingerprint(self) -> str:
        """18.7's formula half: code, version, expression and declared unit.

        Deliberately not over the definition text or the rule reference.
        Rewording a definition is an editorial change and must not make a
        stored calculation look stale; changing the expression must.
        """
        return _digest(self.code, str(self.version), self.tree.text(), self.output_unit)

    def describe(self) -> str:
        return (
            f"{self.code} v{self.version}: {self.target} = {self.expression} "
            f"[{self.output_unit}, {self.rounding}]"
        )


@dataclass(frozen=True)
class FormulaSet:
    """An immutable, versioned set of definitions.

    Immutable for the reason `mapping/sets.py` is: a calculation carries the
    version of the formula set that produced it, and a set that can be edited
    in place makes that reference meaningless.
    """

    definitions: tuple[FormulaDefinition, ...]
    version: int = 1
    note: str = ""

    def __post_init__(self) -> None:
        by_target: dict[str, str] = {}
        by_code: dict[str, str] = {}
        for definition in self.definitions:
            if definition.target in by_target:
                raise RegistryError(
                    f"two formulas compute {definition.target!r}: "
                    f"{by_target[definition.target]} and {definition.code}. "
                    "A cell with two definitions has no definition."
                )
            if definition.code in by_code:
                raise RegistryError(
                    f"{definition.code} is used twice. Codes are the stable "
                    "identity a stored calculation refers back to (18.1)."
                )
            by_target[definition.target] = definition.code
            by_code[definition.code] = definition.target

    def __iter__(self):
        return iter(self.definitions)

    def __len__(self) -> int:
        return len(self.definitions)

    @property
    def targets(self) -> tuple[str, ...]:
        return tuple(d.target for d in self.definitions)

    def for_target(self, target: str) -> FormulaDefinition | None:
        for definition in self.definitions:
            if definition.target == target:
                return definition
        return None

    def by_code(self, code: str) -> FormulaDefinition:
        for definition in self.definitions:
            if definition.code == code:
                return definition
        raise KeyError(f"no formula {code!r} in this set")

    def subset(self, targets: frozenset[str]) -> FormulaSet:
        return FormulaSet(
            tuple(d for d in self.definitions if d.target in targets),
            version=self.version,
            note=self.note,
        )

    @property
    def fingerprint(self) -> str:
        """18.7. The set's own identity: every formula's fingerprint, ordered."""
        return _digest(
            str(self.version),
            *sorted(d.fingerprint for d in self.definitions),
        )


def calculation_fingerprint(formulas: FormulaSet, inputs: dict[str, Decimal]) -> str:
    """18.7: "Hash inputs and formula version for reproducibility."

    The same formulas over the same inputs hash the same; one changed digit
    anywhere changes it. Values go in as their exact decimal strings, so
    `1.0` and `1` are distinguished -- see the module docstring on 4.14.
    """
    parts = [formulas.fingerprint]
    for path in sorted(inputs):
        parts.append(path)
        parts.append(str(inputs[path]))
    return _digest(*parts)
