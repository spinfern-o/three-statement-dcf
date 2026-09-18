"""Item 180: the deployed commit, the schema version, and the formula version.

180 asks that a deployment record three things. The reason is the question
somebody asks six months later, holding an export and a screenshot that
disagree: **which code produced this?** An export already carries its model
version (21.7), which identifies the *data*. This identifies the *code*.

Three separate versions, because they move independently and the interesting
answer is usually "one of them moved":

  `commit`          the git revision, read at runtime. Not baked in at build
                    time by a script somebody has to remember to run.
  `schema_version`  the JSON export schema (21.5). A consumer that broke has
                    to know whether this changed.
  `formula_version` the fingerprint over every formula definition (18.7). A
                    figure that moved with no change to the data and no change
                    to the schema moved because a formula did, and this is the
                    only thing that says so.

**The commit is read from git, and says so when it cannot be.** A deployment
from a tarball has no `.git`, and the honest answer there is `unknown` with the
reason, not a hardcoded string from whenever somebody last edited this file.
Item 180 says *record* the deployed commit; a recorded value that is wrong is
worse than one that is absent, because the whole point is to be able to trust
it in an argument.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

UNKNOWN = "unknown"


@dataclass(frozen=True)
class BuildInfo:
    """What 180 requires recorded, plus how each value was obtained."""

    commit: str
    commit_source: str
    schema_version: str
    formula_version: str
    started_at: str

    @property
    def is_identified(self) -> bool:
        """Whether this deployment can answer "which code produced this"."""
        return self.commit != UNKNOWN

    def describe(self) -> str:
        if not self.is_identified:
            return (
                f"This deployment cannot identify its own commit "
                f"({self.commit_source}). Item 180 requires it recorded, and a "
                f"figure nobody can trace to a revision is one nobody can "
                f"reproduce."
            )
        return (
            f"commit {self.commit[:12]}, export schema {self.schema_version}, "
            f"formulas {self.formula_version[:12]}"
        )

    def as_dict(self) -> dict[str, str | bool]:
        body: dict[str, str | bool] = dict(asdict(self))
        body["identified"] = self.is_identified
        return body


def _commit() -> tuple[str, str]:
    """The git revision, or `unknown` and why."""
    if not (ROOT / ".git").exists():
        return UNKNOWN, "no .git directory; deployed from an archive rather than a clone"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return UNKNOWN, f"git could not be run: {exc}"
    if result.returncode != 0:
        return UNKNOWN, f"git rev-parse failed: {result.stderr.strip()[:120]}"

    revision = result.stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if dirty.returncode == 0 and dirty.stdout.strip():
        # A deployment from a dirty tree is not the tested version, which is
        # item 178's whole requirement. Said in the value itself, because a
        # reader comparing two exports will read the value and not this file.
        return f"{revision}-dirty", "git, with uncommitted changes in the tree"
    return revision, "git rev-parse HEAD"


def collect() -> BuildInfo:
    """Read the three versions. Called once at startup, not per request."""
    from ..exports.schema import SCHEMA_VERSION
    from ..formula.catalog import derivation_formulas

    commit, source = _commit()
    return BuildInfo(
        commit=commit,
        commit_source=source,
        schema_version=SCHEMA_VERSION,
        formula_version=derivation_formulas().fingerprint,
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
