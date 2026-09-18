"""Item 148: 20.14's limits, and an honest account of what they protect.

20.14 names four endpoint classes -- upload, extraction, authentication and
export. `security-model.md` added the part the clause leaves out: **extraction
and export are limited by concurrent work, not only by request rate**, because
the resource risk here is one expensive job rather than many cheap requests. A
DCF export rebuilds the statements, the schedules, the forecast and the
valuation; ten of those at once is a problem and ten page loads is not.

So there are two limiters and they answer different questions:

  `RateLimit`     how many times in a window -- the right shape for a login,
                  where the attack is repetition.
  `Concurrency`   how many at once -- the right shape for an export, where the
                  attack, or the accident, is simultaneity.

**Authentication gets both a window and a delay.** A fixed window alone lets an
attacker use the whole budget instantly and wait; a lockout alone lets them
lock the one real user out. The limit here is per-window with the window
counted from the first failure, and a successful login clears it -- so the
person who knows the password is never locked out by somebody else's guessing
from a different address, while the guessing itself is bounded.

**This is in-process state.** With one user (2.2.b) and one worker that is the
whole system, and it is written down rather than assumed: a deployment running
two workers has two independent limiters, which halves every limit's strength.
`is_shared` returns False and the security documentation says what to do about
it before that deployment exists, rather than after.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

#: 20.14's four classes, with the limit each one gets and why.
LIMITS = {
    "authentication": (5, 300),  # 5 attempts per 5 minutes: a person who has
    # typed it wrong five times is not typing.
    "upload": (20, 3600),  # 20 filings an hour, for one reviewer.
    "extraction": (20, 3600),  # extraction follows upload one-for-one.
    "export": (60, 3600),  # a reader may reasonably re-download often.
}

#: How many of the expensive operations may run at once. One, deliberately:
#: there is one user, and a second simultaneous export is either a double
#: click or a tab left reloading.
CONCURRENT_JOBS = 1


class RateLimited(Exception):
    """The caller has used its budget, and this says when it refills."""

    def __init__(self, retry_after: int, name: str) -> None:
        super().__init__(f"too many {name} requests; try again in {retry_after} second(s)")
        self.retry_after = retry_after
        self.name = name


@dataclass
class RateLimit:
    """A fixed window per key, counted from the first request in it."""

    allowed: int
    window: int
    name: str = "request"
    _events: dict[str, deque] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, key: str, *, now: float | None = None) -> None:
        """Record one request, or raise `RateLimited`."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= moment - self.window:
                events.popleft()
            if len(events) >= self.allowed:
                retry = int(events[0] + self.window - moment) + 1
                raise RateLimited(retry, self.name)
            events.append(moment)

    def clear(self, key: str) -> None:
        """Forget one key's history. Called when a login succeeds."""
        with self._lock:
            self._events.pop(key, None)

    def remaining(self, key: str, *, now: float | None = None) -> int:
        moment = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.get(key, deque())
            live = sum(1 for event in events if event > moment - self.window)
            return max(0, self.allowed - live)


class Concurrency:
    """At most `limit` of something at once, refused rather than queued.

    Refused, because a queue on a synchronous request just moves the wait to a
    connection the reader is holding open, and a reader who double-clicked
    would rather be told than wait twice as long.
    """

    def __init__(self, limit: int = CONCURRENT_JOBS, name: str = "job") -> None:
        self.limit = limit
        self.name = name
        self._running = 0
        self._lock = threading.Lock()

    @property
    def running(self) -> int:
        with self._lock:
            return self._running

    def __enter__(self) -> Concurrency:
        with self._lock:
            if self._running >= self.limit:
                raise RateLimited(1, f"concurrent {self.name}")
            self._running += 1
        return self

    def __exit__(self, *exc) -> None:
        with self._lock:
            self._running -= 1


@dataclass
class Limiters:
    """Every limiter one application instance holds."""

    authentication: RateLimit
    upload: RateLimit
    extraction: RateLimit
    export: RateLimit
    jobs: Concurrency

    @classmethod
    def build(cls) -> Limiters:
        return cls(
            **{
                name: RateLimit(allowed, window, name) for name, (allowed, window) in LIMITS.items()
            },
            jobs=Concurrency(name="export"),
        )

    @property
    def is_shared(self) -> bool:
        """False, and saying so is the point.

        These counters live in one process. A deployment running N workers has
        N independent limiters and every limit above is N times weaker. That is
        acceptable for 2.2.b's single user on one worker and must be revisited
        before it is not -- which is why this is a property that reads False
        rather than a comment nobody greps for.
        """
        return False
