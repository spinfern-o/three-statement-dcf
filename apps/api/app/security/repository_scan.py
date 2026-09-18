"""Item 152's second half, and item 166's precondition: what must not be in Git.

20.4: "Never commit secrets, source PDFs, or production financial data to Git."
Item 166 asks that it be *confirmed* before release. A confirmation somebody
performs by looking is a confirmation that degrades, so this is a check that
runs in CI on every commit.

**The hard part is telling a fixture from a filing**, and the answer is not a
filename pattern. Every fixture PDF here is *pinned by hash* in
`test_fixtures.py` and *built by* `build_fixtures.py`, and this check requires
both -- a hash says what a file is, and only the generator says where it came
from. A PDF that is not both is one nobody can account for, and it is refused.
That is the right direction to err in: the cost of a false positive is a line
in a manifest, and the cost of a false negative is a company's unreleased
accounts on GitHub.

**Secrets are matched on shape, not on name.** A variable called
`REVIEW_PASSWORD_HASH` in `.env.example` is a name and is fine; a 64-character
scrypt hash next to it is a value and is not. The patterns are the ones from
`security/logging.py`, reused deliberately: a shape worth redacting from a log
is a shape worth refusing from a commit.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

#: Where fixture PDFs are allowed to live. Anywhere else is a finding.
FIXTURE_DIRS = ("apps/api/tests/fixtures",)

#: The generator that produces every fixture PDF. A fixture it does not build
#: is a document that came from somewhere else.
GENERATOR = "apps/api/tests/fixtures/build_fixtures.py"

#: Where the fixtures are pinned by hash, and where the one that cannot be
#: pinned is excused by name.
MANIFEST = "apps/api/tests/integration/test_fixtures.py"

#: File suffixes that could carry a filing.
DOCUMENT_SUFFIXES = (".pdf",)

#: Shapes that are values rather than names. `.env.example` may carry the
#: names; it may not carry any of these.
SECRET_SHAPES = (
    (re.compile(r"scrypt\$\d+\$\d+\$\d+\$[A-Za-z0-9+/=]+\$[A-Za-z0-9+/=]{20,}"),
     "a stored password hash"),
    (re.compile(r"(?i)\b(?:aws|api|secret|private)[_-]?key\b\s*[:=]\s*['\"]?[A-Za-z0-9/+=_-]{16,}"),
     "an API or private key"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
     "a private key block"),
    (re.compile(r"(?i)\bpassword\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
     "a literal password"),
)

#: Files this check reads but does not scan for secret shapes, because their
#: subject IS the shape. Each is listed with the reason.
SHAPE_EXEMPT = {
    "apps/api/app/security/repository_scan.py": "this file defines the shapes",
    "apps/api/app/security/logging.py": "the redaction patterns",
    "apps/api/app/security/credentials.py": "the hash format's own definition",
    "apps/api/tests/integration/test_security.py": "exercises them",
}


@dataclass(frozen=True)
class Finding:
    path: str
    what: str
    detail: str = ""

    def describe(self) -> str:
        return f"{self.path}: {self.what}" + (f" -- {self.detail}" if self.detail else "")


def tracked_files(root: Path = ROOT) -> list[str]:
    """Every file Git tracks. The working tree is not the question; the repository is."""
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True,
    )
    return [name for name in result.stdout.decode().split("\0") if name]


def _is_fixture(path: str) -> bool:
    return any(path.startswith(f"{directory}/") for directory in FIXTURE_DIRS)


def _accounted_for(root: Path) -> set[str]:
    """Every fixture the repository can vouch for.

    Two conditions, both from files already in the tree, so this check cannot
    drift from what the tests enforce:

      pinned by hash in `test_fixtures.py` (or listed there as deliberately
      not reproducible -- `encrypted.pdf`, because AES-256 salts every write),
      **and** built by `build_fixtures.py`.

    The second is the one that matters here. A hash pins a file to what it was;
    only the generator says where it came from. A PDF nobody generated is a PDF
    somebody added, and 20.4 is about exactly that.
    """
    manifest = root / MANIFEST
    generator = root / GENERATOR
    if not manifest.exists() or not generator.exists():
        return set()
    text = manifest.read_text()
    pinned = set(re.findall(r'"([\w.-]+\.pdf)":\s*"[0-9a-f]{64}"', text))
    excused = set(re.findall(r'NOT_REPRODUCIBLE = \{([^}]*)\}', text))
    for group in excused:
        pinned |= set(re.findall(r'"([\w.-]+\.pdf)"', group))
    built = set(re.findall(r'"([\w.-]+\.pdf)"', generator.read_text()))
    return pinned & built


def scan_documents(root: Path = ROOT) -> list[Finding]:
    """20.4: no source PDF in the repository that is not an accounted-for fixture."""
    accounted = _accounted_for(root)
    findings: list[Finding] = []
    for name in tracked_files(root):
        if not name.lower().endswith(DOCUMENT_SUFFIXES):
            continue
        if not _is_fixture(name):
            findings.append(
                Finding(name, "a PDF outside the fixture directory", "20.4")
            )
            continue
        if Path(name).name not in accounted:
            findings.append(
                Finding(
                    name,
                    "is not an accounted-for fixture",
                    f"every fixture is pinned in {MANIFEST} and built by "
                    f"{GENERATOR}; this one is not both",
                )
            )
    return findings


def scan_secrets(root: Path = ROOT) -> list[Finding]:
    """20.4: no secret *value* in the repository. Names are fine."""
    findings: list[Finding] = []
    for name in tracked_files(root):
        if name in SHAPE_EXEMPT:
            continue
        path = root / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern, what in SECRET_SHAPES:
            if pattern.search(body):
                findings.append(Finding(name, f"looks like {what}", "20.4"))
                break
    return findings


def run(root: Path = ROOT) -> list[Finding]:
    return scan_documents(root) + scan_secrets(root)


def _main() -> int:
    findings = run()
    if not findings:
        print(
            f"No source PDF and no secret value in the tree "
            f"({len(tracked_files())} tracked file(s) checked). 20.4 holds."
        )
        return 0
    print("REFUSED -- 20.4: never commit secrets, source PDFs, or production data.\n")
    for finding in findings:
        print(f"  {finding.describe()}")
    return 1


if __name__ == "__main__":
    sys.exit(_main())
