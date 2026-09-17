"""Phase 11 (items 109-120): the DCF of specification Section 16.

Like Phase 10, a boundary rather than a second implementation. `model/dcf.py`
does 16.2 through 16.20; what did not exist is the path from a Section 14
assumption register into it, with every market input carrying the URL and the
observation date a valuation has to be reproducible from -- and Section 16's
timing conventions, which the engine did not offer until `model/timing.py`.
"""

from .build import (
    InputRecord,
    ScenarioValuation,
    ValuationError,
    build_scenario_valuation,
    missing_inputs,
)
from .checks import (
    DEFAULT_TERMINAL_THRESHOLD,
    EXIT_MULTIPLE_STATUS,
    Headroom,
    TerminalShare,
    headroom,
    terminal_share,
)
from .inputs import BRIDGE_INPUTS, LEASE_LIABILITIES_NOTE, MARKET_INPUTS, MarketInput
from .sensitivity import Grid, build_grid

__all__ = [
    "BRIDGE_INPUTS",
    "DEFAULT_TERMINAL_THRESHOLD",
    "EXIT_MULTIPLE_STATUS",
    "Grid",
    "Headroom",
    "InputRecord",
    "LEASE_LIABILITIES_NOTE",
    "MARKET_INPUTS",
    "MarketInput",
    "ScenarioValuation",
    "TerminalShare",
    "ValuationError",
    "build_grid",
    "build_scenario_valuation",
    "headroom",
    "missing_inputs",
    "terminal_share",
]
