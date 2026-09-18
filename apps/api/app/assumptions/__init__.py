"""Phase 9 (items 89-96): assumptions and scenarios, specification Section 14.

The engine's `model/assumptions.py` is the gate every forecast driver already
passes through. This is the fuller record Section 14.4 asks for -- ten fields
rather than four, with evidence rules per source type -- plus the Scenario
entity Section 9 references and never defines (finding F-5), the approval
workflow of 14.2, and the before-saving impact preview of 14.8.
"""

from .drivers import DRIVERS, REQUIRED, Driver, driver
from .gate import evaluate
from .impact import Impact, MovedValue, preview, reaches, unread_assumptions
from .proposals import Proposal, propose_from_schedules, unproposable
from .scenarios import (
    BASE,
    Probability,
    Resolved,
    Scenario,
    ScenarioError,
    ScenarioSet,
    base_scenario,
)
from .schema import (
    Assumption,
    AssumptionError,
    Evidence,
    SourceType,
    Status,
)
from .store import ScenarioStore
from .workflow import GateResult, StatusChange, WorkflowError, transition

__all__ = [
    "BASE",
    "DRIVERS",
    "REQUIRED",
    "Assumption",
    "AssumptionError",
    "Driver",
    "Evidence",
    "GateResult",
    "Impact",
    "MovedValue",
    "Probability",
    "Proposal",
    "Resolved",
    "Scenario",
    "ScenarioError",
    "ScenarioSet",
    "ScenarioStore",
    "SourceType",
    "Status",
    "StatusChange",
    "WorkflowError",
    "base_scenario",
    "driver",
    "evaluate",
    "preview",
    "propose_from_schedules",
    "reaches",
    "transition",
    "unproposable",
    "unread_assumptions",
]
