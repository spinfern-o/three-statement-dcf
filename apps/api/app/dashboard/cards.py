"""Item 125: metric cards, each carrying period, scenario, source and status.

The four fields 125 names are the whole requirement, and the reason is 1.19
and 7.4's "show only values that have a clear period and scenario label". A
headline number on a dashboard is the figure most likely to be quoted out of
the application, so it is the figure that most needs to say which period it
belongs to, which scenario produced it, where it came from, and whether
anybody has approved it.

A card with nothing behind it yet says what is missing rather than showing a
zero. 6.5.h is about loading states and the same reasoning applies here: a
financial value that is not known must never render as a number.
"""

from __future__ import annotations

from dataclasses import dataclass

from .status import ModelStatus, Standing


@dataclass(frozen=True)
class Card:
    label: str
    value: str
    #: 125: the four labels, none optional.
    period: str
    scenario: str
    source: str
    status: str
    tone: str = "neutral"
    is_absent: bool = False


#: 7.1.b's statuses, each in a sentence.
STATUS_LEGEND = (
    (ModelStatus.DRAFT, "A model exists and no filing has been attached to it."),
    (ModelStatus.EXTRACTING, "The filing is in the pipeline and has produced no facts yet."),
    (
        ModelStatus.NEEDS_REVIEW,
        "Facts exist and something still needs a person: a decision, a confirmed "
        "metadata field, or a statement that does not build.",
    ),
    (
        ModelStatus.VALIDATED,
        "The historical statements build from verified, approved facts, and every "
        "cell cites the page it was printed on.",
    ),
    (
        ModelStatus.FORECAST_READY,
        "Every required assumption is an answer (14.1) and the forecast builds for every period.",
    ),
    (
        ModelStatus.VALUATION_READY,
        "The cost-of-capital inputs are supplied, each with the URL and date "
        "somebody observed it on.",
    ),
    (
        ModelStatus.ARCHIVED,
        "Set by a person, never inferred: a model nobody touched recently is not "
        "the same as a model somebody finished.",
    ),
)


def portfolio_cards(models: tuple[tuple[object, Standing], ...]) -> tuple[Card, ...]:
    """The four figures worth putting at the top of a portfolio."""
    total = len(models)
    ready = sum(
        1 for _, standing in models if standing.status.rank >= ModelStatus.VALUATION_READY.rank
    )
    needs_review = sum(1 for _, standing in models if standing.status is ModelStatus.NEEDS_REVIEW)
    unresolved = sum(standing.unresolved_count for _, standing in models)

    return (
        Card(
            label="Models",
            value=str(total),
            period="all",
            scenario="",
            source="counted from the documents in this store",
            status="live",
            tone="neutral",
        ),
        Card(
            label="Valuation ready",
            value=str(ready),
            period="current state",
            scenario="base",
            source="computed from each model's own contents",
            status="computed",
            tone="success" if ready else "neutral",
        ),
        Card(
            label="Needs review",
            value=str(needs_review),
            period="current state",
            scenario="",
            source="every fact decided and the metadata confirmed",
            status="computed",
            tone="warning" if needs_review else "success",
        ),
        Card(
            label="Unresolved items",
            value=str(unresolved),
            period="current state",
            scenario="",
            source="blocking reason codes, undecided facts and missing inputs",
            status="computed",
            tone="warning" if unresolved else "success",
        ),
    )
