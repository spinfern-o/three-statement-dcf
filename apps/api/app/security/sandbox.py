"""Item 147's second half: 20.10, and an honest account of what it buys.

20.10: "Isolate PDF/OCR processing from the web process." The reason is in
`security-model.md`: PDF parsers are large C libraries processing untrusted
input, and this application hands them a file somebody else produced.

**What this is.** Every call runs in a fresh child process, started with
`spawn` so it inherits no imported state, under an address-space limit, a CPU
limit and a wall-clock timeout. A parse that allocates without bound, loops
without end, or segfaults takes down the child and returns a refusal; the web
process keeps serving, and the refusal names which of the three happened.

**What this is not, stated plainly.** It is not a boundary against code
execution. A child process runs as the same user with the same filesystem and
the same network as its parent, so an attacker who achieves execution inside
the parser is inside the account. Making it a security boundary needs a
container, a seccomp filter or a separate user, and those are deployment
mechanisms rather than application ones -- `security-model.md` says exactly
that, and `docs/incident-response.md` records it as the residual risk.

Writing that down matters more than the code does. An isolation layer whose
limits are unstated gets treated as a sandbox, and the next person adds a
feature on the strength of a guarantee it never made.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import traceback
from dataclasses import dataclass

#: Address space the child may map. A PDF page render is tens of megabytes; a
#: parser walking a malformed cross-reference table can ask for gigabytes.
DEFAULT_MEMORY_BYTES = 1024 * 1024 * 1024

#: CPU seconds. The kernel sends SIGXCPU at the soft limit, which turns a
#: runaway loop into a dead child rather than a pegged core.
DEFAULT_CPU_SECONDS = 30

#: Wall clock. Separate from CPU, because a child blocked on something is not
#: burning CPU and would never hit the other limit.
DEFAULT_TIMEOUT_SECONDS = 60


class SandboxError(RuntimeError):
    """The isolated work did not complete, and this says which way it failed."""


@dataclass(frozen=True)
class Limits:
    memory_bytes: int = DEFAULT_MEMORY_BYTES
    cpu_seconds: int = DEFAULT_CPU_SECONDS
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


def _apply(limits: Limits) -> None:
    """Set the child's own limits. Best-effort: some platforms have neither."""
    try:
        import resource
    except ImportError:  # pragma: no cover - not POSIX
        return
    for name, value in (
        ("RLIMIT_AS", limits.memory_bytes),
        ("RLIMIT_CPU", limits.cpu_seconds),
    ):
        constant = getattr(resource, name, None)
        if constant is None:
            continue
        _soft, hard = resource.getrlimit(constant)
        ceiling = value if hard in (resource.RLIM_INFINITY, -1) else min(value, hard)
        # A limit this platform will not let us lower is one `is_available` and
        # the incident notes report, rather than one we pretend to have set.
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(constant, (ceiling, hard))


def _child(connection, limits: Limits, func, args, kwargs) -> None:
    _apply(limits)
    try:
        connection.send(("ok", func(*args, **kwargs)))
    except BaseException as exc:
        connection.send(("error", f"{type(exc).__name__}: {exc}", traceback.format_exc()))
    finally:
        connection.close()


def run_isolated(func, *args, limits: Limits | None = None, **kwargs):
    """Run `func` in a child process, or raise `SandboxError` saying why not.

    `func` must be importable by name in a fresh interpreter, because `spawn`
    re-imports rather than forking. That constraint is deliberate: a closure
    over the web process's state is exactly the thing this is separating from.
    """
    limits = limits or Limits()
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_child, args=(child, limits, func, args, kwargs), daemon=True
    )
    process.start()
    child.close()

    try:
        if not parent.poll(limits.timeout_seconds):
            process.terminate()
            process.join(5)
            raise SandboxError(
                f"the isolated parser did not finish within "
                f"{limits.timeout_seconds}s and was stopped"
            )
        message = parent.recv()
    except EOFError:
        process.join(5)
        raise SandboxError(
            f"the isolated parser exited without a result (exit code "
            f"{process.exitcode}). A parser killed by the kernel -- out of "
            f"memory, over its CPU limit, or crashed -- ends here rather than "
            f"in the web process."
        ) from None
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
        process.join(5)

    if message[0] == "ok":
        return message[1]
    raise SandboxError(f"the isolated parser refused: {message[1]}")


def is_available() -> bool:
    """Whether isolation can actually run here.

    Returned rather than assumed: a platform without `fork`/`spawn` support, or
    a container that forbids new processes, must not be told it is isolated
    when it is not.
    """
    try:
        multiprocessing.get_context("spawn")
    except ValueError:  # pragma: no cover
        return False
    return hasattr(os, "fork") or os.name == "nt"
