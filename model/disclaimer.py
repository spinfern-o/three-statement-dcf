"""Section 25's required language, in one place because it has three homes.

25 is explicit about where it goes: **"Do not bury this only in Terms. Show it
in the model, release flow, and exports."** Three surfaces, and a disclaimer
that differs between them is one somebody wrote twice.

Until Phase 15 this repository had a shortened version in the web footer
(`README.md` had the full one) and **nothing in the CLI report**. The short
version dropped two of the four sentences, and the two it dropped are the ones
about this system in particular: that historical figures may carry extraction
errors until reviewed, and that outputs must be verified before being relied
on. Trimming a disclaimer to the part that sounds most like boilerplate keeps
the least useful half.

`model/` rather than `apps/`, because the engine cannot import the website and
the CLI report is one of the three surfaces. A test asserts every surface
carries it.

20.19 also asks for *model limitations* beside it. Those are per-model and live
with the export that knows them (`exports/gather.py:STANDING_LIMITATIONS`); this
is the standing text that is true of every run.
"""

from __future__ import annotations

import textwrap

#: Section 25, verbatim. Not paraphrased: the clause says "the same meaning as
#: the following" and the cheapest way to have the same meaning is to use the
#: same words. Legal review before commercial use is 25's own instruction and
#: has not happened -- see `docs/decision-ledger.md`.
DISCLAIMER = (
    "This model is an analytical tool, not investment, accounting, tax, or "
    "legal advice. Historical information may contain extraction or "
    "classification errors until reviewed. Forecasts and valuations depend on "
    "assumptions and are inherently uncertain. Verify all source data, "
    "assumptions, and outputs before relying on them."
)

#: The one line a footer has room for. It is a *pointer* to the full text, not
#: a replacement for it, and every surface that uses it also shows the whole
#: thing somewhere a reader can reach.
SHORT = (
    "An analytical tool, not investment advice. Verify every figure before "
    "relying on it (Section 25)."
)

#: Four sentences, each of which a surface must not drop.
SENTENCES = tuple(
    sentence.strip() + "." for sentence in DISCLAIMER.split(". ") if sentence.strip()
)


def wrapped(width: int = 78, indent: str = "") -> str:
    """The full text, wrapped for a terminal report."""
    return textwrap.fill(
        DISCLAIMER, width=width, initial_indent=indent, subsequent_indent=indent
    )


def block(width: int = 78) -> str:
    """The disclaimer as a CLI report block, ruled off so it is not skimmed."""
    rule = "=" * width
    return "\n".join([rule, "DISCLAIMER (specification Section 25)", rule, wrapped(width)])
