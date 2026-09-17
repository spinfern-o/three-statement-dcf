"""Phase 10 (items 97-108): the forecast statements of specification Section 15.

Nothing here forecasts anything. `model/forecast.py` implements all twenty-one
of Section 15's steps and has an independent benchmark behind it. This package
turns a *scenario* -- Section 14's reviewed assumption register, with lineage
and statuses -- into the engine's inputs, runs it, and reports the checks per
scenario and per period as 15.20 requires.
"""

from .build import (
    ForecastError,
    ScenarioForecast,
    build_scenario_forecast,
    forecast_ledger,
    forecast_periods,
)
from .checks import (
    VALUATION_CHECKS,
    ForecastReadiness,
    ScenarioChecks,
    check_every_scenario,
    check_scenario,
)

__all__ = [
    "VALUATION_CHECKS",
    "ForecastError",
    "ForecastReadiness",
    "ScenarioChecks",
    "ScenarioForecast",
    "build_scenario_forecast",
    "check_every_scenario",
    "check_scenario",
    "forecast_ledger",
    "forecast_periods",
]
