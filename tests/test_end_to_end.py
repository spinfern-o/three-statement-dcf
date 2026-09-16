"""The CLI, the blank templates, and the repo's own no-invented-data rule."""

from __future__ import annotations

import subprocess
import sys

import pytest
import yaml

from tests.conftest import FIXTURES, INPUTS, ROOT


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "run_model.py", *args],
        cwd=ROOT, capture_output=True, text=True,
    )


def test_cli_runs_the_fixture_clean():
    result = run_cli("--inputs", str(FIXTURES))
    assert result.returncode == 0, result.stderr
    assert "13 PASS   0 FAIL   0 SKIP" in result.stdout
    for step in ("STEP 1-3", "STEP 10", "STEP 23-24", "STEP 25-28", "STEP 29-35", "STEP 36", "STEP 37"):
        assert step in result.stdout, f"{step} section missing from the report"


def test_cli_halts_on_the_blank_template_with_a_useful_message():
    """A blank template must stop the model, not run it on defaults."""
    result = run_cli("--inputs", str(INPUTS))
    assert result.returncode == 2
    assert "MODEL HALTED" in result.stderr
    assert "STEP 1" in result.stderr
    assert "required" in result.stderr.lower()


def test_cli_exit_code_signals_check_failure(tmp_path):
    """Exit 1 when a STEP 37 check fails, so this is usable in CI."""
    import shutil

    broken = tmp_path / "broken"
    shutil.copytree(FIXTURES, broken)
    data = yaml.safe_load((broken / "raw_historical.yaml").read_text())
    # Corrupt one transcribed balance so the historical sheet no longer balances.
    data["balance_sheet"]["inventory"]["values"]["2025A"] += 25.0
    (broken / "raw_historical.yaml").write_text(yaml.safe_dump(data))

    result = run_cli("--inputs", str(broken))
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert "do not plug it" in result.stdout


@pytest.mark.parametrize("name", [
    "company_profile.yaml", "raw_historical.yaml", "assumptions.yaml", "valuation.yaml",
])
def test_shipped_templates_contain_no_company_data(name):
    """The repo must not ship invented figures anyone could mistake for real.

    Every value in inputs/ is blank. A number committed here would look like
    a real company's data to the next person who opens the file, which is
    exactly the failure mode the workflow's 'do not invent' rules exist to
    prevent. Fixture data lives in tests/fixtures/ and is labeled FICTIONAL.
    """
    data = yaml.safe_load((INPUTS / name).read_text())

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from walk(value, f"{path}[{i}]")
        else:
            yield path, node

    offenders = [
        (path, value) for path, value in walk(data)
        # The optional STEP 34 bridge lines are explicitly 0 so the report can
        # print them; a zero is not a company figure.
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0
    ]
    assert offenders == [], f"{name} ships non-zero data: {offenders}"


@pytest.mark.parametrize("name", [
    "company_profile.yaml", "raw_historical.yaml", "assumptions.yaml", "valuation.yaml",
])
def test_fixture_files_are_labeled_fictional(name):
    """Anyone opening a fixture should see immediately that it is not real."""
    text = (FIXTURES / name).read_text()
    assert "FICTIONAL" in text.upper(), f"{name} is not labeled as fictional test data"


def test_every_workflow_step_is_referenced_somewhere_in_the_package():
    """All 37 steps should be traceable to code that implements them."""
    import re
    from pathlib import Path

    corpus = "\n".join(
        p.read_text() for p in sorted(Path(ROOT / "model").glob("*.py"))
    ) + (ROOT / "run_model.py").read_text()

    referenced = set()
    for match in re.finditer(r"STEP\s+(\d+)(?:\s*-\s*(\d+))?", corpus):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        referenced.update(range(start, end + 1))

    missing = sorted(set(range(1, 38)) - referenced)
    assert missing == [], f"no code references these workflow steps: {missing}"
