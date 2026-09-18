"""Item 168: the release-readiness report, with PASS/FAIL evidence.

Every row is produced by running something. Nothing here is a claim somebody
typed, because a typed row is a claim about the code and a measured row is
evidence about it — and a release report is read by whoever has to decide, six
months later, whether to trust a number.

**4.20's claim is made here and nowhere else.** "Never claim 'less than
0.0001% error' until the benchmark suite passes AND the test report identifies
the exact dataset and formulas tested." The in-app panel
(`diagnostics/benchmark.py`) cannot satisfy the first half: a web process does
not observe the test suite, so it reports coverage and says the result is not
observed. This *runs* the suite. So it can satisfy both halves, and it names
the dataset and every formula, or it reports the contract as **UNPROVEN** —
never as passing on the strength of a run nobody in this process saw.

    python3 -m apps.api.app.verification.report            # run and print
    python3 -m apps.api.app.verification.report --out FILE # and write it
    python3 -m apps.api.app.verification.report --fast     # skip the browser

The exit code is 0 only when every gate passed. A report that prints failures
and exits 0 is a report that gets wired into CI and ignored.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

#: Items 156-162, each as the pytest selection that runs it. Selected by path
#: and by keyword rather than by marker, because a marker somebody forgot to
#: apply silently shrinks the suite it names.
SUITES = (
    ("156", "Unit tests", ["apps/api/tests/unit", "tests/test_model.py"]),
    ("157", "Property-based tests", ["tests/test_precision.py"]),
    (
        "158",
        "Golden extraction tests",
        [
            "apps/api/tests/integration/test_fixtures.py",
            "apps/api/tests/integration/test_pipeline.py",
        ],
    ),
    (
        "159",
        "Integration tests",
        [
            "apps/api/tests/integration",
            "--ignore",
            "apps/api/tests/integration/test_accessibility.py",
        ],
    ),
    (
        "160",
        "End-to-end tests",
        ["apps/api/tests/integration/test_end_to_end.py", "tests/test_end_to_end.py"],
    ),
    (
        "161",
        "Accessibility tests",
        [
            "apps/api/tests/integration/test_accessibility.py",
            "-k",
            "keyboard or accessible_name or landmark or focus or wcag or "
            "200_percent or reduced_motion or announce",
        ],
    ),
    (
        "162",
        "Visual regression tests",
        [
            "apps/api/tests/integration/test_accessibility.py",
            "-k",
            "sideways or long_company or large_and_very or empty_state or "
            "error_state or rail or mobile or frozen or tabular or fonts",
        ],
    ),
    (
        "164",
        "Independent arithmetic benchmark",
        [
            "tests/test_precision.py",
            "apps/api/tests/integration/test_valuation.py",
            "-k",
            "benchmark or independent or longhand or exact or precision or sweep",
        ],
    ),
)

#: Which suites need a browser. Skipped by `--fast`, and a skipped suite is
#: reported as NOT RUN rather than as passing.
NEEDS_BROWSER = {"161", "162"}

#: Items that are not a test run. Each names the command that evidences it.
CHECKS = (
    ("154", "Formatting and linting", [sys.executable, "-m", "ruff", "check", "."]),
    ("154", "Formatting", [sys.executable, "-m", "ruff", "format", "--check", "."]),
    ("155", "Strict type checks", [sys.executable, "-m", "mypy"]),
    (
        "163",
        "Production build",
        # A build check has to check something. `len(app.routes)` does not:
        # this FastAPI version wraps an included router as ONE entry, so the
        # count is 4 for any application and `assert app.routes` is true for an
        # empty one. So this counts the router's own declared routes, serves a
        # request, and asserts the static mounts resolve -- which is what
        # "it builds" has to mean for a server that renders its own HTML.
        [
            sys.executable,
            "-c",
            "import apps.api.app.api.main as m; "
            "from apps.api.app.api.routes import router; "
            "from fastapi.testclient import TestClient; "
            "app = m.create_app('var/verification-build'); "
            "paths = {r.path for r in router.routes}; "
            "assert len(paths) >= 30, f'only {len(paths)} routes declared'; "
            "c = TestClient(app); "
            "assert c.get('/health').status_code == 200, 'health is not 200'; "
            "assert c.get('/static/app.css').status_code == 200, 'no stylesheet'; "
            "assert c.get('/tokens/tokens.css').status_code == 200, 'no tokens'; "
            "print(f'{len(paths)} routes, health 200, static and tokens served')",
        ],
    ),
    (
        "166",
        "No source PDF or secret in Git",
        [sys.executable, "-m", "apps.api.app.security.repository_scan"],
    ),
)

PASS = "PASS"
FAIL = "FAIL"
NOT_RUN = "NOT RUN"


@dataclass
class Outcome:
    """One row: what was run, what it returned, and how long it took."""

    item: str
    what: str
    status: str
    evidence: str
    seconds: float = 0.0
    command: str = ""

    @property
    def is_pass(self) -> bool:
        return self.status == PASS


def _run(command: list[str], timeout: int = 1800) -> tuple[int, str, float]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s", time.monotonic() - started
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode, output, time.monotonic() - started


def _last_meaningful_line(output: str) -> str:
    """The last line that is a result rather than a warning.

    A DeprecationWarning from a dependency is usually the final line of
    output, and reporting it as the evidence for a passing gate makes the row
    read like a failure.
    """
    noise = ("warning", "deprecat", "from starlette", "  ")
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if stripped and not any(word in stripped.lower() for word in noise):
            return stripped
    return output.splitlines()[-1].strip() if output else "no output"


def _pytest_summary(output: str) -> str:
    """The one line of pytest output a reader wants."""
    for line in reversed(output.splitlines()):
        if re.search(r"\d+ (passed|failed|error)", line):
            return line.strip().strip("= ")
    return output.splitlines()[-1].strip() if output else "no output"


def run_suites(fast: bool = False) -> list[Outcome]:
    outcomes = []
    for item, what, selection in SUITES:
        if fast and item in NEEDS_BROWSER:
            outcomes.append(
                Outcome(
                    item,
                    what,
                    NOT_RUN,
                    "skipped by --fast; this suite needs a browser",
                    command="(skipped)",
                )
            )
            continue
        command = [sys.executable, "-m", "pytest", "-q", *selection]
        code, output, seconds = _run(command)
        outcomes.append(
            Outcome(
                item,
                what,
                PASS if code == 0 else FAIL,
                _pytest_summary(output),
                seconds,
                " ".join(command[2:]),
            )
        )
    return outcomes


def run_checks() -> list[Outcome]:
    outcomes = []
    for item, what, command in CHECKS:
        code, output, seconds = _run(command)
        evidence = _last_meaningful_line(output)
        outcomes.append(
            Outcome(
                item,
                what,
                PASS if code == 0 else FAIL,
                evidence,
                seconds,
                " ".join(command[1:] if command[0] == sys.executable else command),
            )
        )
    return outcomes


# --- item 165: the Section 4 accuracy contract ------------------------------


def accuracy_contract(benchmark: Outcome) -> Outcome:
    """4.20's claim, made only if it can be.

    Two conditions, and both have to hold: the benchmark suite passed, and this
    report identifies the dataset and the formulas. When the first fails, or
    when the suite was not run at all, the contract is **UNPROVEN** — which is
    the only honest third state and is why this is not a boolean.
    """
    from ..diagnostics.benchmark import COVERAGE

    compared = [row for row in COVERAGE if row.compared]
    if benchmark.status != PASS:
        return Outcome(
            "165",
            "Section 4 accuracy contract",
            FAIL,
            f"UNPROVEN: 4.20 permits the 0.0001% claim only once the benchmark "
            f"suite passes, and it reported {benchmark.status} "
            f"({benchmark.evidence}).",
        )
    return Outcome(
        "165",
        "Section 4 accuracy contract",
        PASS,
        f"{len(compared)} of {len(COVERAGE)} outputs 4.16 names are compared "
        f"against an implementation sharing no helper with the engine (4.15), "
        f"on the dataset named below, and every comparison asserts EXACT "
        f"equality rather than a tolerance.",
        seconds=benchmark.seconds,
    )


# --- item 167: does the documentation describe what the code does? ----------


#: Each is a claim a document makes that a program can check. Not a spell
#: check: these are the claims that go stale when code changes, and each one
#: went stale at least once in this repository's history.
def documentation_claims() -> list[Outcome]:
    from ..diagnostics.registry import FORCED, PROPOSED, REGISTRY
    from ..exports.gather import TAB_ORDER
    from . import acceptance
    from .plan import PLAN, missing_tests

    outcomes: list[Outcome] = []

    def row(what: str, ok: bool, evidence: str) -> None:
        outcomes.append(Outcome("167", what, PASS if ok else FAIL, evidence))

    readme = (ROOT / "README.md").read_text()
    ledger = (ROOT / "docs" / "decision-ledger.md").read_text()
    policy = (ROOT / "docs" / "validation-policy.md").read_text()

    # The test count in README.md. It has been wrong before, and a reader uses
    # it to judge whether the rest of the file is maintained.
    claimed = re.search(r"([\d,]+) tests pass on Python", readme)
    actual = _collected_tests()
    row(
        "README's test count matches the suite",
        claimed is not None and int(claimed.group(1).replace(",", "")) == actual,
        f"README says {claimed.group(1) if claimed else '(nothing)'}, pytest collects {actual}",
    )

    # The phase range. The comment here read "every phase updates it and one
    # phase will forget" -- and one did: the README said "Phases 2-16 of 17"
    # after Phase 17 shipped. The check passed anyway, because it asserted the
    # range was STATED rather than that it was right. That is the same shape as
    # F-38 one level milder: a claim verified for presence instead of truth.
    #
    # Every phase of the specification is now built, so the end of the range is
    # 17. A later specification revision that adds a phase will fail this row,
    # which is the correct outcome: the README would then be wrong.
    phases = re.search(r"\*\*Phases 2.(\d+) of (\d+)\*\*", readme)
    row(
        "README's phase range matches what is built",
        phases is not None and phases.group(1) == "17" and phases.group(2) == "17",
        f"README says phases 2-{phases.group(1)} of {phases.group(2)}"
        if phases
        else "no phase range found",
    )

    # F-4's count, which moved in Phase 13 and is cited in three documents.
    row(
        "The forced/proposed severity split agrees across the documents",
        len(FORCED) == 5
        and len(PROPOSED) == 25
        and "Only five are forced" in policy
        and "twenty-five" in ledger,
        f"registry: {len(FORCED)} forced, {len(PROPOSED)} proposed; "
        f"validation-policy.md and decision-ledger.md agree",
    )

    row(
        "Section 17's thirty checks are all in the registry",
        len(REGISTRY) == 30,
        f"{len(REGISTRY)} checks registered",
    )

    row(
        "21.1's sixteen export tabs are all built",
        len(TAB_ORDER) == 16,
        f"{len(TAB_ORDER)} tabs",
    )

    missing = missing_tests()
    row(
        "Every test the Section 22 plan names exists",
        not missing,
        "every named test resolves"
        if not missing
        else f"{len(missing)} named test(s) do not exist: {missing[:3]}",
    )

    row(
        "Every Section 22 clause is either covered or says why not",
        all(bool(item.tests) or bool(item.uncovered_because) for item in PLAN),
        f"{len(PLAN)} clauses, "
        f"{sum(1 for item in PLAN if item.covered)} covered, "
        f"{sum(1 for item in PLAN if not item.covered)} with a stated reason",
    )

    # Criterion 24.22 itself. Reported as a gate rather than left to the table
    # below, because a section of a document is not a check: a criterion added
    # to Section 24 with nothing behind it has to fail something.
    unevidenced = acceptance.unevidenced()
    outcomes.append(
        Outcome(
            "24.22",
            "Every Section 24 criterion has recorded evidence",
            PASS if acceptance.every_criterion_is_evidenced() else FAIL,
            f"{len(acceptance.CRITERIA)} criteria, "
            f"{len(acceptance.CRITERIA) - len(unevidenced)} evidenced"
            + ("" if not unevidenced else f"; unevidenced: {[c.clause for c in unevidenced]}"),
        )
    )

    missing_24 = acceptance.missing_tests()
    outcomes.append(
        Outcome(
            "24.22",
            "Every test the Section 24 table names exists",
            PASS if not missing_24 else FAIL,
            "every named test resolves"
            if not missing_24
            else f"{len(missing_24)} named test(s) do not exist: {missing_24[:3]}",
        )
    )

    return outcomes


def _collected_tests() -> int:
    _code, output, _ = _run([sys.executable, "-m", "pytest", "-q", "--collect-only"], timeout=300)
    match = re.search(r"(\d+) tests collected", output)
    return int(match.group(1)) if match else -1


# --- the report --------------------------------------------------------------


@dataclass
class Report:
    """Every row, and the one verdict that follows from them."""

    generated_at: str
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def failures(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.status == FAIL]

    @property
    def not_run(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.status == NOT_RUN]

    @property
    def may_release(self) -> bool:
        """Every gate passed, and none was skipped.

        A skipped gate blocks, for rule 1.14's reason: a check that did not run
        has not passed, and a release report whose worst row is NOT RUN is one
        somebody will read as a green one.
        """
        return not self.failures and not self.not_run

    def markdown(self) -> str:
        from .plan import PLAN, uncovered

        lines = [
            "# Release-readiness report",
            "",
            "Required by [`website-build-spec.md`](website-build-spec.md) Phase 16 "
            "item 168. **Generated, not written** — every row below is the result "
            "of running something, and the command is printed beside it so a "
            "reader can run it again.",
            "",
            f"Generated at: `{self.generated_at}`",
            "",
            f"## Verdict: {'READY' if self.may_release else 'NOT READY'}",
            "",
        ]
        if self.may_release:
            lines += [
                "Every gate below passed and none was skipped.",
                "",
                "This is a statement about the gates, not a recommendation to "
                "deploy. Phase 17 item 169 is explicit: do not deploy until the "
                "target, the access level and the data policy are confirmed.",
            ]
        else:
            lines.append(
                f"{len(self.failures)} gate(s) failed and "
                f"{len(self.not_run)} were not run. A gate that did not run has "
                f"not passed (rule 1.14)."
            )
            for outcome in self.failures + self.not_run:
                lines.append(f"- **{outcome.item} {outcome.what}** — {outcome.evidence}")
        lines += [
            "",
            "## Evidence, item by item",
            "",
            "| Item | What | Result | Evidence | Seconds |",
            "|---|---|---|---|---|",
        ]
        for outcome in self.outcomes:
            evidence = outcome.evidence.replace("|", "\\|")[:200]
            lines.append(
                f"| {outcome.item} | {outcome.what} | **{outcome.status}** | "
                f"{evidence} | {outcome.seconds:.1f} |"
            )

        lines += [
            "",
            "## Section 22, clause by clause",
            "",
            f"{sum(1 for item in PLAN if item.covered)} of {len(PLAN)} clauses are "
            f"covered by a named test. The rest are listed below with the reason, "
            f"because a plan where an uncovered clause looks like a covered one "
            f"tells a reader that everything is covered.",
            "",
            "| Clause | What | Covered by |",
            "|---|---|---|",
        ]
        for item in PLAN:
            covered = ", ".join(f"`{name}`" for name in item.tests) or "—"
            lines.append(f"| {item.clause} | {item.what} | {covered} |")

        lines += ["", "### Clauses with no test, and why", ""]
        for item in uncovered():
            lines.append(f"**{item.clause} — {item.what}**")
            lines.append("")
            lines.append(item.uncovered_because)
            lines.append("")

        lines += self._acceptance_section()
        lines += self._benchmark_section()
        lines += ["", "---", "", _disclaimer(), ""]
        return "\n".join(lines)

    def _acceptance_section(self) -> list[str]:
        """Criterion 24.22: evidence for every one of Section 24's twenty-two.

        This section is here because it was missing. The report recorded
        evidence for items 154-168 and for Section 22's clauses, and said
        nothing about Section 24 -- the section that defines what release
        means -- while printing READY. Finding F-37.
        """
        from .acceptance import CRITERIA, assess, not_applicable, unevidenced

        assessments = assess(self._worst_status_per_item())
        clear = sum(1 for a in assessments if a.is_pass)

        lines = [
            "",
            "## Section 24, criterion by criterion",
            "",
            f"{clear} of {len(CRITERIA)} acceptance criteria are clear. "
            f"Criterion 24.22 asks that this report record evidence for every "
            f"criterion, so this table is that record.",
            "",
            "A criterion that defers to a gate above takes **that gate's "
            "result** rather than asserting its own, so a criterion cannot "
            "read PASS while the gate under it is red. A criterion whose gate "
            "is absent from this run reads NOT RUN, never PASS.",
            "",
            "| Criterion | What Section 24 requires | Result | Evidence |",
            "|---|---|---|---|",
        ]
        for a in assessments:
            parts = []
            if a.criterion.gate:
                parts.append(f"item {a.criterion.gate}")
            parts += [f"`{name}`" for name in a.criterion.tests]
            if a.criterion.document:
                parts.append(f"[`{a.criterion.document}`]({a.criterion.document})")
            evidence = ", ".join(parts) or a.evidence
            lines.append(
                f"| {a.criterion.clause} | {a.criterion.what} | **{a.status}** | {evidence} |"
            )

        noted = [c for c in CRITERIA if c.note]
        if noted:
            lines += ["", "### What the evidence does and does not establish", ""]
            for criterion in noted:
                lines.append(f"**{criterion.clause} — {criterion.what}**")
                lines.append("")
                lines.append(criterion.note)
                lines.append("")

        for heading, rows in (
            ("### Criteria with no evidence", unevidenced()),
            ("### Criteria that do not apply, and why", not_applicable()),
        ):
            if rows:
                lines += ["", heading, ""]
                for criterion in rows:
                    lines.append(f"- **{criterion.clause} {criterion.what}** — {criterion.because}")
        return lines

    def _worst_status_per_item(self) -> dict[str, str]:
        """Each item's worst row, not its last.

        Several rows share an item -- `documentation_claims` emits seven under
        167 -- so a plain `{o.item: o.status}` keeps whichever came last. That
        is the wrong one exactly when it matters: a failing 167 row followed by
        a passing one would leave criterion 24.21 reading PASS with a red gate
        under it, which is the thing deriving the status was supposed to
        prevent.
        """
        order = {FAIL: 0, NOT_RUN: 1, PASS: 2}
        worst: dict[str, str] = {}
        for outcome in self.outcomes:
            current = worst.get(outcome.item)
            if current is None or order.get(outcome.status, 0) < order.get(current, 0):
                worst[outcome.item] = outcome.status
        return worst

    def _benchmark_section(self) -> list[str]:
        from ..diagnostics.benchmark import COVERAGE, EXTREMES

        lines = [
            "",
            "## The dataset and the formulas 4.20 requires be identified",
            "",
            "4.20 permits the 0.0001% claim only once the benchmark suite passes "
            "**and** the report names the exact dataset and formulas tested. The "
            "suite's result is the item 164 row above; this is the other half.",
            "",
            "**Dataset:** the committed golden fixtures — "
            "`apps/api/tests/fixtures/*.pdf`, each pinned by SHA-256 in "
            "`test_fixtures.py` and generated by `build_fixtures.py`; and "
            f"`tests/fixtures/` for the engine. Plus {len(EXTREMES)} extreme-input "
            "cases and a randomized sweep across nine orders of magnitude.",
            "",
            "**Formulas, one row per 4.16 output:**",
            "",
            "| Output | Compared | Where | How |",
            "|---|---|---|---|",
        ]
        for row in COVERAGE:
            if row.compared:
                lines.append(f"| {row.output} | yes | `{row.where}` | {row.method} |")
            else:
                lines.append(f"| {row.output} | **no** | — | {row.reason} |")
        return lines


def _disclaimer() -> str:
    from model.disclaimer import DISCLAIMER

    return DISCLAIMER


def _item_order(outcome: Outcome) -> tuple[int, int, str]:
    """Phase-16 items numerically, then Section 24's clauses.

    The first version sorted on `int(o.item)`, which was fine while every item
    was a phase number and raised `ValueError` the moment criterion 24.22 was
    reported as a row. Sorting is not the place to discover that an item
    string is not always a number.
    """
    head, _, tail = outcome.item.partition(".")
    if not tail:
        return (0, int(head), outcome.what)
    return (1, int(tail), outcome.what)


def build(fast: bool = False) -> Report:
    """Run everything and assemble the report."""
    outcomes: list[Outcome] = []
    outcomes += run_checks()
    suites = run_suites(fast=fast)
    outcomes += suites

    benchmark = next(o for o in suites if o.item == "164")
    outcomes.append(accuracy_contract(benchmark))
    outcomes += documentation_claims()

    outcomes.sort(key=_item_order)
    return Report(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        outcomes=outcomes,
    )


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Item 168: produce the release-readiness report with "
        "PASS/FAIL evidence. Exits non-zero unless every gate "
        "passed and none was skipped.",
    )
    parser.add_argument("--out", type=Path, help="also write the report here")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="skip the suites that need a browser. They are "
        "then reported NOT RUN, which blocks the verdict",
    )
    args = parser.parse_args(argv)

    report = build(fast=args.fast)
    body = report.markdown()
    if args.out:
        args.out.write_text(body)
        print(f"Wrote {args.out}")

    print()
    for outcome in report.outcomes:
        print(f"  {outcome.status:8} {outcome.item:4} {outcome.what}")
        if not outcome.is_pass:
            print(f"           {outcome.evidence[:160]}")
    print()
    print("READY" if report.may_release else "NOT READY")
    return 0 if report.may_release else 1


if __name__ == "__main__":
    raise SystemExit(_main())
