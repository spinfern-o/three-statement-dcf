"""Item 78's tests: the parser, and the refusals that make 18.3 true.

18.3 says "do not evaluate arbitrary user code". A test suite cannot prove
that a program never runs code, but it can do two things that together come
close: assert that every construct a person would reach for to run code is
refused with a message naming why, and assert that the module source contains
no call to anything that could.

The second is the one that would survive a refactor. Grammar tests pass if
someone adds an `eval` fast path beside the parser; the source check does not.
"""

from __future__ import annotations

import pathlib
import re
from decimal import Decimal

import pytest

from apps.api.app.formula.parse import (
    FUNCTIONS,
    OPERATORS,
    Binary,
    Call,
    FormulaSyntaxError,
    Literal,
    Reference,
    Unary,
    parse,
    tokenize,
)

D = Decimal
PACKAGE = pathlib.Path(__file__).resolve().parents[3] / "api" / "app" / "formula"


# --- 18.3: nothing in this package can run code ----------------------------

DANGEROUS = ("eval", "exec", "compile", "literal_eval", "__import__", "getattr")


@pytest.mark.parametrize("name", DANGEROUS)
def test_the_package_never_calls_anything_that_runs_code(name):
    """The check that survives a refactor the grammar tests would not."""
    pattern = re.compile(rf"(?<![A-Za-z_.]){re.escape(name)}\s*\(")
    offenders = []
    for path in sorted(PACKAGE.glob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("#", '"')):
                continue
            if pattern.search(line):
                offenders.append(f"{path.name}:{number}: {stripped}")
    assert not offenders, f"{name}( appears in the formula package: {offenders}"


@pytest.mark.parametrize(
    "attack",
    [
        '__import__("os").system("id")',
        "revenue.__class__",
        "(lambda: 1)()",
        "revenue if True else 0",
        "[x for x in range(3)]",
        "revenue; import os",
        "revenue\\nimport os",
        "0x41",
        "1e300",
    ],
)
def test_every_way_in_is_refused_at_the_character_or_grammar_level(attack):
    with pytest.raises(FormulaSyntaxError):
        parse(attack)


def test_the_refusal_says_where_it_stopped():
    """A formula is something a person typed; "invalid syntax" is not a repair."""
    with pytest.raises(FormulaSyntaxError) as caught:
        parse("revenue + $cogs")
    message = str(caught.value)
    assert "'$' is not allowed" in message
    assert "position 10" in message
    assert "^" in message, "the caret points at the offending character"


# --- the grammar ------------------------------------------------------------


@pytest.mark.parametrize(
    "formula,text",
    [
        ("revenue - cogs", "(revenue - cogs)"),
        ("a + b + c", "((a + b) + c)"),
        ("a - b - c", "((a - b) - c)"),
        ("a + b * c", "(a + (b * c))"),
        ("(a + b) * c", "((a + b) * c)"),
        ("a / b / c", "((a / b) / c)"),
        ("2 ^ 3 ^ 2", "(2 ^ (3 ^ 2))"),
        ("-a", "-a"),
        ("+a", "a"),
        ("- -a", "--a"),
        ("min(a, b)", "min(a, b)"),
        ("abs(a - b)", "abs((a - b))"),
        ("assumptions.tax_rate * 2", "(assumptions.tax_rate * 2)"),
    ],
)
def test_precedence_and_associativity(formula, text):
    assert parse(formula).text() == text


def test_subtraction_is_left_associative_and_it_matters():
    """`a - b - c` read right-associatively is `a - b + c`."""
    assert parse("10 - 3 - 2").text() == "((10 - 3) - 2)"


def test_a_literal_keeps_the_digits_the_author_typed():
    """4.14: the precision a figure was written to is a fact about it."""
    node = parse("1.50")
    assert isinstance(node, Literal)
    assert node.value == D("1.50")
    assert node.text() == "1.50", "1.50 must not be redisplayed as 1.5"


def test_a_dotted_reference_is_one_token():
    tokens = tokenize("a.b.c + 1")
    assert tokens[0].text == "a.b.c"
    assert parse("a.b.c").references() == frozenset({"a.b.c"})


def test_references_are_collected_from_everywhere_in_the_tree():
    node = parse("min(a, b * (c - d)) / abs(e)")
    assert node.references() == frozenset({"a", "b", "c", "d", "e"})


@pytest.mark.parametrize(
    "formula,fragment",
    [
        ("", "the formula is empty"),
        ("a +", "ends where a value was expected"),
        ("a b", "unexpected 'b'"),
        ("(a + b", "expected a closing parenthesis"),
        ("a.", "ends with a dot"),
        ("sqrt(a)", "not an approved function"),
        ("abs(1, 2)", "exactly one argument"),
        ("min(1)", "at least two arguments"),
        ("abs", "is a function and needs arguments"),
        (")", "is not a value"),
    ],
)
def test_the_grammar_refuses_and_says_why(formula, fragment):
    with pytest.raises(FormulaSyntaxError, match=re.escape(fragment)):
        parse(formula)


def test_the_approved_sets_are_short_and_explicit():
    """18.2. A growing operator set is a growing attack surface."""
    assert OPERATORS == ("+", "-", "*", "/", "^")
    assert FUNCTIONS == ("min", "max", "abs")


def test_the_tree_is_made_of_exactly_the_five_node_kinds():
    node = parse("-min(a, 2) + b / 3")
    kinds = set()

    def walk(n):
        kinds.add(type(n).__name__)
        for child in ("operand", "left", "right"):
            if hasattr(n, child):
                walk(getattr(n, child))
        for argument in getattr(n, "arguments", ()):
            walk(argument)

    walk(node)
    assert kinds <= {"Literal", "Reference", "Unary", "Binary", "Call"}
    assert {Binary, Call, Literal, Reference, Unary}
