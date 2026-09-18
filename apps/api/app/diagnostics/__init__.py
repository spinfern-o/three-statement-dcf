"""Phase 13 (items 131-137): diagnostics, lineage and audit, from Section 17.

All thirty of Section 17's checks in one panel, the chain from a page of the
filing to a valuation output, the audit log made searchable, the benchmark's
coverage reported without claiming a result it has not seen, and the release
gate -- which blocks on every outstanding check because Section 17 assigns a
severity to none of them (F-4), and says so.
"""

from .audit import Filters, Log, choices, filter_events
from .benchmark import COVERAGE, Report
from .lineage import Step, Trace, trace, traceable_lines
from .registry import BY_CLAUSE, FORCED, PROPOSED, REGISTRY, Check, Severity
from .release import Readiness, checklist, readiness
from .run import Diagnostics, Outcome, evaluate

__all__ = [
    "BY_CLAUSE",
    "COVERAGE",
    "FORCED",
    "PROPOSED",
    "REGISTRY",
    "Check",
    "Diagnostics",
    "Filters",
    "Log",
    "Outcome",
    "Readiness",
    "Report",
    "Severity",
    "Step",
    "Trace",
    "checklist",
    "choices",
    "evaluate",
    "filter_events",
    "readiness",
    "trace",
    "traceable_lines",
]
