"""Item 147's first half: 20.9, and the claim it must not make.

20.9: "Scan uploads before processing." `security-model.md` fixed two things
about it in Phase 2 and left the mechanism to the deployment:

  - scanning happens **before** extraction, not alongside it;
  - a file that fails is **quarantined, not deleted**, so the rejection is
    auditable.

**There is no scanner in this repository, and this module does not pretend
otherwise.** Bundling one would mean either shipping a signature database that
is stale the day it is committed, or calling a service, which sends a
confidential filing to a third party -- the thing 20.1 forbids without an
explicit recorded decision. So this is a hook: a command named in the
environment, run before anything parses the bytes.

**The honest part is `NOT_SCANNED`.** When no command is configured, the
result is not "clean" -- it is a recorded fact that nothing scanned this file,
carried on the document and visible on the diagnostics screen. A field that
reads "clean" because nobody looked is worse than no field at all: it answers
the question a reviewer was about to ask, wrongly.

The command's contract is the one every scanner already implements: exit 0 for
clean, non-zero for a finding, and the file path as the single argument.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

#: The command to run. Named, never a default: a default would be a scanner
#: this repository chose on the deployment's behalf.
SCAN_COMMAND_ENV = "INGEST_SCAN_COMMAND"

#: How long a scan may take before it is treated as a failure. A scanner that
#: hangs must not hold an upload open indefinitely.
SCAN_TIMEOUT_SECONDS = 120

#: Where a file that failed goes. Under the storage root, beside the store, so
#: a rejection is as durable as an acceptance.
QUARANTINE_DIRNAME = "quarantine"


class ScanOutcome(str, Enum):
    """What is known about this file, including "nothing"."""

    CLEAN = "clean"
    INFECTED = "infected"
    #: The scanner ran and could not decide, or failed to run.
    ERRORED = "errored"
    #: No scanner is configured. Not the same as clean, and never shown as it.
    NOT_SCANNED = "not scanned"

    @property
    def may_process(self) -> bool:
        """Whether extraction may proceed.

        NOT_SCANNED proceeds, deliberately: 2.2.b's single user processing
        their own filings on a private deployment is the case the specification
        describes, and refusing every upload until a scanner exists would stop
        the application working for the only person using it. What it must not
        do is call that state clean -- and it does not.
        """
        return self in (ScanOutcome.CLEAN, ScanOutcome.NOT_SCANNED)

    @property
    def is_known(self) -> bool:
        return self is not ScanOutcome.NOT_SCANNED


@dataclass(frozen=True)
class ScanResult:
    """One scan, and what it is allowed to be reported as."""

    outcome: ScanOutcome
    detail: str = ""
    command: str = ""
    quarantined_at: str = ""

    @property
    def may_process(self) -> bool:
        return self.outcome.may_process

    def describe(self) -> str:
        if self.outcome is ScanOutcome.NOT_SCANNED:
            return (
                f"No upload scanner is configured ({SCAN_COMMAND_ENV} is unset), "
                "so nothing has scanned this file. That is not the same as a "
                "clean result and is not reported as one (20.9)."
            )
        return f"{self.outcome.value}: {self.detail}" if self.detail else self.outcome.value


def configured_command(environ=None) -> str:
    return ((environ or os.environ).get(SCAN_COMMAND_ENV) or "").strip()


def scan(path: "str | Path", *, environ=None, timeout: int = SCAN_TIMEOUT_SECONDS) -> ScanResult:
    """Run the configured scanner over one file, before anything parses it."""
    command = configured_command(environ)
    if not command:
        return ScanResult(ScanOutcome.NOT_SCANNED)

    argv = command.split() + [str(path)]
    try:
        completed = subprocess.run(
            argv, capture_output=True, timeout=timeout, check=False,
        )
    except FileNotFoundError:
        return ScanResult(
            ScanOutcome.ERRORED,
            detail=f"{argv[0]!r} is not on the path",
            command=command,
        )
    except subprocess.TimeoutExpired:
        return ScanResult(
            ScanOutcome.ERRORED,
            detail=f"the scanner did not finish within {timeout}s",
            command=command,
        )

    if completed.returncode == 0:
        return ScanResult(ScanOutcome.CLEAN, command=command)
    # The scanner's own words, truncated. They describe the file, not its
    # contents, so they are safe to carry -- and a finding with no detail is
    # one nobody can act on.
    detail = (completed.stdout or completed.stderr or b"").decode(
        "utf-8", "replace"
    ).strip()[:500]
    return ScanResult(
        ScanOutcome.INFECTED,
        detail=detail or f"the scanner exited {completed.returncode}",
        command=command,
    )


def quarantine(path: "str | Path", storage_root: "str | Path", result: ScanResult) -> ScanResult:
    """Move a failed file aside and record where, rather than deleting it.

    Deleting destroys the evidence of why an upload was refused, and the
    question asked afterwards is always "what was in it".
    """
    source = Path(path)
    target_dir = Path(storage_root) / QUARANTINE_DIRNAME
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    counter = 1
    while target.exists():
        target = target_dir / f"{source.stem}-{counter}{source.suffix}"
        counter += 1
    shutil.move(str(source), str(target))
    return ScanResult(
        outcome=result.outcome,
        detail=result.detail,
        command=result.command,
        quarantined_at=str(target),
    )


def scan_state(storage_root: "str | Path", result=None) -> ScanResult:
    """What is known about scanning on this deployment, for the settings page.

    Reported per deployment rather than per document, because that is what is
    actually true: the scanner is a command in the environment, and whether it
    ran on a given upload is recorded in that upload's own job history. A
    per-document "clean" badge derived from a deployment-wide setting would be
    the exact claim this module exists not to make.
    """
    command = configured_command()
    if not command:
        return ScanResult(ScanOutcome.NOT_SCANNED)
    return ScanResult(
        ScanOutcome.CLEAN,
        detail=f"uploads are scanned by {command!r} before extraction (20.9)",
        command=command,
    )
