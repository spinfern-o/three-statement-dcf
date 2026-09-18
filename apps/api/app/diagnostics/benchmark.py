"""Item 135: the benchmark-accuracy report, and what 4.20 forbids it saying.

4.20: "Never claim 'less than 0.0001% error' until the benchmark suite passes
and the test report identifies the exact dataset and formulas tested."

A running application cannot honour the first half. The benchmark lives in the
test suite and runs in CI; this process does not observe its result, and a
screen that printed "0.0001% accuracy" because somebody once ran the tests
would be making exactly the claim 4.20 exists to prevent.

So this reports the second half, which it CAN establish: what the benchmark
suite covers, formula by formula, where each comparison lives, and which of
4.16's required outputs are compared against an implementation that shares no
helper with the engine. The verdict line says plainly that the result is not
observed here and where to look for it.

That is a weaker claim than a green tick, and it is the true one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Coverage:
    """One 4.16 output, and the benchmark that compares it."""

    output: str
    #: The test file and function that compares it.
    where: str
    #: How the benchmark computes it independently.
    method: str
    compared: bool = True
    #: When not compared, why.
    reason: str = ""


#: 4.16's list, verbatim, with what compares each one.
PRECISION = "tests/test_precision.py::test_independent_recomputation"
VALUATION = "apps/api/tests/integration/test_valuation.py::test_the_benchmark_agrees_with_the_engine_exactly"
CATALOG = "apps/api/tests/integration/test_formula_catalog.py"
TIMING = "tests/test_timing.py"

COVERAGE = (
    Coverage("revenue", PRECISION, "recomputed from the YAML with its own Decimal loader"),
    Coverage(
        "gross profit", CATALOG, "the formula engine's tree evaluation against Ledger._try_derive"
    ),
    Coverage(
        "EBITDA",
        "",
        "",
        compared=False,
        reason="the chart has no `ebitda` line (F-17), so there is nothing to compare",
    ),
    Coverage("EBIT", CATALOG, "the formula engine against the engine's derivation table"),
    Coverage(
        "EBT (pretax income)", CATALOG, "the formula engine against the engine's derivation table"
    ),
    Coverage("taxes", PRECISION, "rate x pretax, recomputed longhand"),
    Coverage("net income", CATALOG, "the formula engine against the engine's derivation table"),
    Coverage("total assets", CATALOG, "the formula engine against the engine's derivation table"),
    Coverage(
        "total liabilities", CATALOG, "the formula engine against the engine's derivation table"
    ),
    Coverage("equity", CATALOG, "the formula engine against the engine's derivation table"),
    Coverage("CFO", CATALOG, "the formula engine against the engine's derivation table"),
    Coverage("CFI", CATALOG, "the formula engine against the engine's derivation table"),
    Coverage("CFF", CATALOG, "the formula engine against the engine's derivation table"),
    Coverage("ending cash", PRECISION, "the cash roll-forward, recomputed longhand"),
    Coverage("NOPAT", VALUATION, "EBIT x (1 - tax), written out with built-in operators"),
    Coverage("change in NWC", VALUATION, "working capital read off the ledgers and differenced"),
    Coverage("FCFF", VALUATION, "NOPAT + D&A - CapEx - change in NWC, longhand"),
    Coverage(
        "discount factors", VALUATION, "1 / (1 + WACC)^t, with `**` rather than the engine's helper"
    ),
    Coverage("terminal value", VALUATION, "terminal FCFF / (WACC - g), longhand"),
    Coverage(
        "enterprise value",
        VALUATION,
        "the sum of present values plus the discounted terminal value",
    ),
    Coverage("equity value", VALUATION, "enterprise value plus cash less debt"),
    Coverage(
        "implied value per share",
        "",
        "",
        compared=False,
        reason="no verified diluted share count exists, so 16.20 withholds the "
        "figure and there is nothing to compare",
    ),
)

#: 4.17's input families, and where each is exercised.
EXTREMES = (
    ("negatives and zeros", CATALOG),
    ("very small decimals (1e-8)", CATALOG),
    ("very large values (1e30)", CATALOG),
    ("mixed source scales", CATALOG),
    ("repeating-decimal rates", TIMING),
    ("nine orders of reporting magnitude", PRECISION),
)


@dataclass(frozen=True)
class Report:
    coverage: tuple[Coverage, ...] = COVERAGE
    extremes: tuple[tuple[str, str], ...] = EXTREMES

    @property
    def compared(self) -> tuple[Coverage, ...]:
        return tuple(c for c in self.coverage if c.compared)

    @property
    def not_compared(self) -> tuple[Coverage, ...]:
        return tuple(c for c in self.coverage if not c.compared)

    @property
    def verdict(self) -> str:
        """4.20, stated as the limit it is."""
        return (
            f"{len(self.compared)} of {len(self.coverage)} outputs 4.16 requires "
            "are compared against an implementation that shares no helper with "
            "the engine (4.15), and every comparison asserts EXACT equality "
            "rather than a tolerance, because each is composed only of decimal "
            "addition, subtraction, multiplication and terminating division "
            "(4.12). **This page does not assert that the suite passed.** 4.20 "
            "permits the 0.0001% claim only once the report identifies the "
            "dataset and formulas tested and the suite has run; the suite runs "
            "in CI and this process does not observe its result."
        )
