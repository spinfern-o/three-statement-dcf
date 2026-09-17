"""Phase 12 (items 121-130): the dashboard and design system of Section 6.

7.1's portfolio, the navigation shell, the metric cards, and charts that
cannot be built without the text summary and downloadable data 6.5.f requires.

Every model's status is computed from what it contains rather than stored, and
`Archived` is never inferred: a model nobody touched recently is not the same
as a model somebody finished.
"""

from .cards import STATUS_LEGEND, Card, portfolio_cards
from .charts import LineChart, line_chart
from .navigation import NavItem, nav_items
from .standing import standing_for
from .status import ModelStatus, Standing

__all__ = [
    "STATUS_LEGEND",
    "Card",
    "LineChart",
    "ModelStatus",
    "NavItem",
    "Standing",
    "line_chart",
    "nav_items",
    "portfolio_cards",
    "standing_for",
]
