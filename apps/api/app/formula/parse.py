"""Item 78: the safe formula parser (18.2, 18.3).

18.3 says "do not evaluate arbitrary user code", and the only way to mean that
is to never hand a formula to anything that can run code. So there is no
`eval`, no `exec`, no `compile`, and no `ast.literal_eval` anywhere in this
package -- not even on the numeric literals, which are built straight from
their matched text with `Decimal`.

What is here instead is a tokenizer over an explicitly approved character set
and a recursive-descent parser over a grammar small enough to read:

    expression := term (('+' | '-') term)*
    term       := factor (('*' | '/') factor)*
    factor     := unary ('^' factor)?            # right-associative
    unary      := ('-' | '+') unary | primary
    primary    := NUMBER
                | NAME '(' expression (',' expression)* ')'
                | REFERENCE
                | '(' expression ')'
    REFERENCE  := NAME ('.' NAME)*

A reference is a dotted path -- `revenue`, `revenue.prior`,
`assumptions.tax_rate` -- resolved by the evaluator against a supplied
environment. It is deliberately not an attribute lookup on a Python object:
resolution is a dictionary get, so a formula cannot reach a method, a dunder,
or anything else that is not a value someone put in the environment.

Every refusal names the position it happened at, because a formula is a thing
a person typed and "invalid syntax" is not a repair instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

#: 18.2. The complete approved set. `^` is integer exponentiation; there is no
#: `**`, because two spellings of one operator is two things to keep correct.
OPERATORS = ("+", "-", "*", "/", "^")

#: 18.2. Deliberately short. `sqrt`, `log` and `exp` are absent because none is
#: exact in decimal arithmetic, and 4.4 makes the authoritative engine exact.
#: A formula that needs one needs a decision about its precision first.
FUNCTIONS = ("min", "max", "abs")

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
#: A decimal literal. No exponent notation: `1e3` is a float's spelling, and
#: a formula written by a person should say 1000.
_NUMBER = re.compile(r"\d+(?:\.\d+)?|\.\d+")


class FormulaSyntaxError(ValueError):
    """The formula could not be parsed, and this says where."""

    def __init__(self, message: str, formula: str, position: int):
        self.formula = formula
        self.position = position
        caret = " " * position + "^"
        super().__init__(f"{message}\n    {formula}\n    {caret}  (position {position})")


# --- the syntax tree --------------------------------------------------------

@dataclass(frozen=True)
class Node:
    """Base for every node. `text()` re-renders the formula a person reads."""

    def text(self) -> str:  # pragma: no cover - overridden everywhere
        raise NotImplementedError

    def references(self) -> "frozenset[str]":
        return frozenset()


@dataclass(frozen=True)
class Literal(Node):
    value: Decimal
    #: The characters the author typed, so `1.50` does not become `1.5`.
    raw: str

    def text(self) -> str:
        return self.raw


@dataclass(frozen=True)
class Reference(Node):
    path: str

    def text(self) -> str:
        return self.path

    def references(self) -> "frozenset[str]":
        return frozenset({self.path})


@dataclass(frozen=True)
class Unary(Node):
    op: str
    operand: Node

    def text(self) -> str:
        return f"-{self.operand.text()}" if self.op == "-" else self.operand.text()

    def references(self) -> "frozenset[str]":
        return self.operand.references()


@dataclass(frozen=True)
class Binary(Node):
    op: str
    left: Node
    right: Node

    def text(self) -> str:
        return f"({self.left.text()} {self.op} {self.right.text()})"

    def references(self) -> "frozenset[str]":
        return self.left.references() | self.right.references()


@dataclass(frozen=True)
class Call(Node):
    function: str
    arguments: tuple[Node, ...]

    def text(self) -> str:
        return f"{self.function}({', '.join(a.text() for a in self.arguments)})"

    def references(self) -> "frozenset[str]":
        out: frozenset[str] = frozenset()
        for argument in self.arguments:
            out |= argument.references()
        return out


# --- tokenizer --------------------------------------------------------------

@dataclass(frozen=True)
class Token:
    kind: str  # "number" | "name" | "op" | "(" | ")" | "," | "end"
    text: str
    position: int


def tokenize(formula: str) -> "tuple[Token, ...]":
    """Characters to tokens, refusing anything outside the approved set."""
    tokens: list[Token] = []
    index = 0
    while index < len(formula):
        character = formula[index]
        if character.isspace():
            index += 1
            continue
        if character in OPERATORS:
            tokens.append(Token("op", character, index))
            index += 1
            continue
        if character in "(),":
            tokens.append(Token(character, character, index))
            index += 1
            continue
        number = _NUMBER.match(formula, index)
        if number:
            tokens.append(Token("number", number.group(), index))
            index = number.end()
            continue
        name = _NAME.match(formula, index)
        if name:
            # A dotted reference is one token, so `a.b` cannot be read as
            # `a` applied to `b` by anything downstream.
            end = name.end()
            while end < len(formula) and formula[end] == ".":
                following = _NAME.match(formula, end + 1)
                if not following:
                    raise FormulaSyntaxError(
                        "a reference ends with a dot and no name after it",
                        formula, end,
                    )
                end = following.end()
            path = formula[index:end]
            # A dunder segment is never a model path, and refusing it here
            # removes the question of whether resolution is safe rather than
            # answering it. Resolution IS safe -- `Environment.get` is a
            # dictionary lookup and never an attribute access -- but a rule
            # that depends on a reader checking that is a weaker rule.
            for segment in path.split("."):
                if segment.startswith("__") and segment.endswith("__"):
                    raise FormulaSyntaxError(
                        f"{segment!r} is not a name a formula may use. A "
                        "reference is a path into the model's own values, and "
                        "no value is named like a Python special attribute "
                        "(18.3)",
                        formula, index,
                    )
            tokens.append(Token("name", path, index))
            index = end
            continue
        raise FormulaSyntaxError(
            f"{character!r} is not allowed in a formula. Permitted: names, "
            f"decimal numbers, {' '.join(OPERATORS)}, parentheses and commas "
            "(18.2)",
            formula, index,
        )
    tokens.append(Token("end", "", len(formula)))
    return tuple(tokens)


# --- parser -----------------------------------------------------------------

class _Parser:
    def __init__(self, formula: str):
        self.formula = formula
        self.tokens = tokenize(formula)
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def advance(self) -> Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def expect(self, kind: str, what: str) -> Token:
        if self.current.kind != kind:
            raise FormulaSyntaxError(
                f"expected {what}, found "
                + (f"{self.current.text!r}" if self.current.kind != "end" else "the end of the formula"),
                self.formula, self.current.position,
            )
        return self.advance()

    def parse(self) -> Node:
        if self.current.kind == "end":
            raise FormulaSyntaxError("the formula is empty", self.formula, 0)
        node = self.expression()
        if self.current.kind != "end":
            raise FormulaSyntaxError(
                f"unexpected {self.current.text!r} after a complete expression",
                self.formula, self.current.position,
            )
        return node

    def expression(self) -> Node:
        node = self.term()
        while self.current.kind == "op" and self.current.text in "+-":
            op = self.advance().text
            node = Binary(op, node, self.term())
        return node

    def term(self) -> Node:
        node = self.factor()
        while self.current.kind == "op" and self.current.text in "*/":
            op = self.advance().text
            node = Binary(op, node, self.factor())
        return node

    def factor(self) -> Node:
        node = self.unary()
        if self.current.kind == "op" and self.current.text == "^":
            self.advance()
            # Right-associative, so 2^3^2 is 2^(3^2) as in ordinary notation.
            return Binary("^", node, self.factor())
        return node

    def unary(self) -> Node:
        if self.current.kind == "op" and self.current.text in "+-":
            op = self.advance().text
            operand = self.unary()
            return operand if op == "+" else Unary("-", operand)
        return self.primary()

    def primary(self) -> Node:
        token = self.current
        if token.kind == "number":
            self.advance()
            try:
                # Built from the matched text directly. No eval, and no float
                # anywhere between the characters and the Decimal (4.4).
                return Literal(Decimal(token.text), token.text)
            except InvalidOperation:  # pragma: no cover - the regex prevents it
                raise FormulaSyntaxError(
                    f"{token.text!r} is not a decimal number", self.formula, token.position
                ) from None
        if token.kind == "name":
            self.advance()
            if self.current.kind == "(":
                if token.text not in FUNCTIONS:
                    raise FormulaSyntaxError(
                        f"{token.text!r} is not an approved function. Permitted: "
                        f"{', '.join(FUNCTIONS)} (18.2)",
                        self.formula, token.position,
                    )
                self.advance()
                arguments = [self.expression()]
                while self.current.kind == ",":
                    self.advance()
                    arguments.append(self.expression())
                self.expect(")", "a closing parenthesis")
                if token.text == "abs" and len(arguments) != 1:
                    raise FormulaSyntaxError(
                        f"abs takes exactly one argument, {len(arguments)} given",
                        self.formula, token.position,
                    )
                if token.text in ("min", "max") and len(arguments) < 2:
                    raise FormulaSyntaxError(
                        f"{token.text} takes at least two arguments, "
                        f"{len(arguments)} given",
                        self.formula, token.position,
                    )
                return Call(token.text, tuple(arguments))
            if token.text in FUNCTIONS:
                raise FormulaSyntaxError(
                    f"{token.text!r} is a function and needs arguments",
                    self.formula, token.position,
                )
            return Reference(token.text)
        if token.kind == "(":
            self.advance()
            node = self.expression()
            self.expect(")", "a closing parenthesis")
            return node
        if token.kind == "end":
            raise FormulaSyntaxError(
                "the formula ends where a value was expected", self.formula, token.position
            )
        raise FormulaSyntaxError(
            f"{token.text!r} is not a value", self.formula, token.position
        )


def parse(formula: str) -> Node:
    """Text to a syntax tree, or `FormulaSyntaxError` saying where it stopped."""
    return _Parser(formula).parse()
