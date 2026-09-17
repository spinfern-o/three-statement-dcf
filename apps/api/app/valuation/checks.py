"""Items 115, 119, and 16.21-16.25: what a valuation must say about itself.

Four requirements, and three of them are about not overstating what a DCF
knows.

**16.21 -- show terminal value as a percentage of enterprise value.** Not
optional, and not buried. In most DCFs the terminal value is the majority of
the answer, which means most of the answer rests on a perpetual growth rate
somebody chose rather than on the five years of forecasting that took the work.

**16.22 -- warn above a configurable threshold, and DO NOT automatically fail
solely because it is high.** The specification is unusually explicit, and it is
right: a high terminal share is normal for a growing company and is a red flag
for a declining one, and no threshold can tell the two apart. So this warns and
says what a reader should go and check.

**16.25 -- never average terminal methods unless the user explicitly approves a
policy.** There is one method here, Gordon Growth, so there is nothing to
average -- and `exit_multiple_status` says so rather than leaving a reader to
assume a second method was considered.

**16.16 / item 115 -- WACC > g.** Enforced by `model/dcf.py`, which raises
rather than returning a negative or infinite terminal value. Checked here as
well, because the sensitivity grid walks WACC values downward and has to know
which corners are unreachable rather than merely empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from model.numeric import ZERO, quantize_for_display

from .build import ScenarioValuation

#: 16.22's "configurable review threshold". 75% is a starting point, not a
#: finding: it is high enough that most healthy DCFs sit below it and low
#: enough to catch one where the explicit forecast has stopped doing any work.
DEFAULT_TERMINAL_THRESHOLD = Decimal("0.75")

PERCENT_PLACES = 1


@dataclass(frozen=True)
class TerminalShare:
    """16.21 and 16.22, together, because one without the other misleads."""

    share: Decimal | None
    threshold: Decimal
    reason: str = ""

    @property
    def percent(self) -> Decimal | None:
        if self.share is None:
            return None
        return quantize_for_display(self.share * 100, PERCENT_PLACES)

    @property
    def is_above_threshold(self) -> bool:
        return self.share is not None and self.share > self.threshold

    def describe(self) -> str:
        if self.share is None:
            return self.reason or "the terminal share could not be computed"
        text = (
            f"The terminal value is {self.percent}% of enterprise value "
            f"(16.21)."
        )
        if not self.is_above_threshold:
            return text
        return text + (
            f" That is above the {quantize_for_display(self.threshold * 100, 0)}% "
            "review threshold (16.22). This is a WARNING and not a failure: a "
            "high terminal share is ordinary for a company still growing and a "
            "red flag for one that is not, and no threshold tells the two "
            "apart. What it means is that most of this answer rests on the "
            "perpetual growth rate rather than on the explicit forecast, so "
            "the growth rate is where a reviewer's attention belongs."
        )


def terminal_share(
    valuation: ScenarioValuation, threshold: Decimal = DEFAULT_TERMINAL_THRESHOLD
) -> TerminalShare:
    """16.21, with 16.22's threshold attached."""
    share = valuation.valuation.tv_share_of_ev
    if share is None:
        return TerminalShare(
            None, threshold,
            "enterprise value is zero, so the terminal share is undefined "
            "rather than infinite (4.12, 17.27)",
        )
    return TerminalShare(share, threshold)


#: 16.24. Recorded rather than silently absent.
EXIT_MULTIPLE_STATUS = (
    "Not implemented. 16.24 permits an exit-multiple terminal value if it is "
    "kept separate and its metric, multiple, date and comparable set are all "
    "sourced. None of those exists here, and the chart has no EBITDA line to "
    "apply a multiple to (F-17). So this valuation uses Gordon Growth alone -- "
    "which also means 16.25's rule against averaging terminal methods has "
    "nothing to bind: there is one method, and its result is its result."
)


@dataclass(frozen=True)
class Headroom:
    """Item 115 / 16.16: how far the WACC is above the growth rate."""

    wacc: Decimal
    growth: Decimal

    @property
    def spread(self) -> Decimal:
        return self.wacc - self.growth

    @property
    def is_blocked(self) -> bool:
        return self.spread <= ZERO

    def describe(self) -> str:
        if self.is_blocked:
            return (
                f"WACC {self.wacc} does not exceed the terminal growth rate "
                f"{self.growth}, and 16.16 blocks the calculation there: the "
                "perpetual-growth formula returns a negative or infinite value."
            )
        narrow = self.spread < Decimal("0.02")
        text = (
            f"WACC {self.wacc} exceeds terminal growth {self.growth} by "
            f"{self.spread} (16.16)."
        )
        if narrow:
            text += (
                " The spread is under two points, and the terminal value is "
                "that spread in the denominator -- so a small change in either "
                "input moves the answer a great deal. Worth showing the "
                "sensitivity grid beside it."
            )
        return text


def headroom(valuation: ScenarioValuation) -> Headroom:
    return Headroom(
        wacc=valuation.valuation.wacc,
        growth=valuation.valuation.terminal_growth,
    )
