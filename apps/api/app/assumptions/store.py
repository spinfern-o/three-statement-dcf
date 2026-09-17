"""Persisting a scenario set beside the document it belongs to.

Specification item 20 -- the database schema and its migrations -- is still
outstanding, and Section 9's rows are written to JSON files meanwhile, exactly
as `persistence/json_store.py` does for extractions. This is the same
arrangement for Section 14's rows, and it is deliberately the same shape so
that replacing both with PostgreSQL is one piece of work rather than two.

Serialisation keeps `Decimal` as a **string**, never a float. 4.2 asks for
decimal strings at API boundaries, and JSON has no decimal type, so a number
round-tripped through a float would lose precision silently at rest. `D`
refuses a float on the way back in, so a regression here fails loudly.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from .scenarios import Probability, Scenario, ScenarioSet, base_scenario
from .schema import Assumption, Evidence, SourceType, Status


def _assumption_json(assumption: Assumption) -> dict:
    return {
        "code": assumption.code,
        "name": assumption.name,
        "value": str(assumption.value),
        "unit": assumption.unit,
        "periods": list(assumption.periods),
        "scenario_id": assumption.scenario_id,
        "source_type": assumption.source_type.value,
        "evidence": {
            "document_id": assumption.evidence.document_id,
            "page": assumption.evidence.page,
            "url": assumption.evidence.url,
            "date": assumption.evidence.date,
            "measured_over": list(assumption.evidence.measured_over),
        },
        "rationale": assumption.rationale,
        "owner": assumption.owner,
        "reviewer": assumption.reviewer,
        "status": assumption.status.value,
        "created_at": assumption.created_at,
        "updated_at": assumption.updated_at,
        "inherited_from": assumption.inherited_from,
        "overrides": assumption.overrides,
    }


def _assumption_from(row: dict) -> Assumption:
    evidence = row.get("evidence", {})
    return Assumption(
        code=row["code"],
        name=row["name"],
        # A string, so `D` builds an exact Decimal. A float here would raise,
        # which is the behaviour we want if this file was ever rewritten badly.
        value=row["value"],
        unit=row["unit"],
        periods=tuple(row.get("periods", ())),
        scenario_id=row.get("scenario_id", "base"),
        source_type=SourceType(row["source_type"]),
        evidence=Evidence(
            document_id=evidence.get("document_id", ""),
            page=evidence.get("page"),
            url=evidence.get("url", ""),
            date=evidence.get("date", ""),
            measured_over=tuple(evidence.get("measured_over", ())),
        ),
        rationale=row["rationale"],
        owner=row["owner"],
        reviewer=row.get("reviewer", ""),
        status=Status(row.get("status", "Draft")),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        inherited_from=row.get("inherited_from", ""),
        overrides=row.get("overrides", ""),
    )


def _scenario_json(scenario: Scenario) -> dict:
    return {
        "id": scenario.id,
        "name": scenario.name,
        "parent_id": scenario.parent_id,
        "description": scenario.description,
        "created_by": scenario.created_by,
        "created_at": scenario.created_at,
        "probability": (
            None
            if scenario.probability is None
            else {
                "value": str(scenario.probability.value),
                "source": scenario.probability.source,
                "date": scenario.probability.date,
            }
        ),
    }


def _scenario_from(row: dict) -> Scenario:
    probability = row.get("probability")
    return Scenario(
        id=row["id"],
        name=row["name"],
        parent_id=row.get("parent_id"),
        description=row.get("description", ""),
        created_by=row.get("created_by", ""),
        created_at=row["created_at"],
        probability=(
            None
            if probability is None
            else Probability(probability["value"], probability["source"], probability["date"])
        ),
    )


def to_json(scenarios: ScenarioSet) -> dict:
    return {
        "version": scenarios.version,
        "scenarios": [_scenario_json(s) for s in scenarios.scenarios],
        "assumptions": [_assumption_json(a) for a in scenarios.assumptions],
    }


def from_json(payload: dict) -> ScenarioSet:
    return ScenarioSet(
        scenarios=tuple(_scenario_from(row) for row in payload["scenarios"]),
        assumptions=tuple(_assumption_from(row) for row in payload["assumptions"]),
        version=payload.get("version", 1),
    )


class ScenarioStore:
    """One scenario set per document, in a JSON file beside the extraction."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path_for(self, document_id: str) -> Path:
        return self.root / "assumptions" / f"{document_id}.json"

    def load(self, document_id: str, owner: str = "") -> ScenarioSet:
        """The stored set, or a fresh one holding only the base scenario."""
        path = self.path_for(document_id)
        if not path.exists():
            return ScenarioSet((base_scenario(owner),))
        return from_json(json.loads(path.read_text()))

    def save(self, document_id: str, scenarios: ScenarioSet) -> Path:
        path = self.path_for(document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Written whole and renamed, so a crash mid-write cannot leave a file
        # that parses into a half-set.
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(to_json(scenarios), indent=2, sort_keys=False))
        temporary.replace(path)
        return path


def _decimal_guard(value) -> Decimal:  # pragma: no cover - documentation
    """Never used. Present to state that no float path exists here."""
    raise AssertionError("values are stored and read as decimal strings (4.2)")
