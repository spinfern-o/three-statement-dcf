"""Persisting a scenario set: values must survive as exact decimals.

JSON has no decimal type. A value round-tripped through a float loses
precision silently at rest, and the loss shows up much later as a valuation
that does not reproduce. So values are written as strings, read back as
strings, and `model/numeric.py:D` refuses a float on the way in -- which makes
a regression here fail loudly rather than quietly.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from apps.api.app.assumptions.scenarios import (
    BASE,
    Probability,
    Scenario,
    ScenarioSet,
    base_scenario,
)
from apps.api.app.assumptions.schema import Assumption, Evidence, SourceType, Status
from apps.api.app.assumptions.store import ScenarioStore, from_json, to_json

D = Decimal


def assumption(code="dso", value="59.9", unit="days", **kwargs):
    defaults = dict(
        code=code, name=code.upper(), value=D(value), unit=unit,
        source_type=SourceType.HISTORICAL_DRIVER,
        evidence=Evidence(measured_over=("2024A", "2025A")),
        rationale="measured from the 13.1 working-capital schedule",
        owner="larry",
    )
    defaults.update(kwargs)
    return Assumption(**defaults)


@pytest.fixture
def populated():
    return (
        ScenarioSet((base_scenario("larry"),), (assumption(),))
        .with_scenario(
            Scenario(id="upside", name="Upside", parent_id=BASE, created_by="larry")
        )
        .override("upside", "dso", D("45"), owner="larry", rationale="collection programme")
    )


def test_a_set_round_trips_exactly(populated):
    restored = from_json(to_json(populated))
    assert restored.version == populated.version
    assert [s.id for s in restored.scenarios] == [s.id for s in populated.scenarios]
    assert restored.resolve("upside")["dso"].assumption.value == D("45")
    assert restored.resolve(BASE)["dso"].assumption.value == D("59.9")


def test_values_are_stored_as_decimal_strings_not_floats(populated):
    """4.2, and the reason: JSON has no decimal type."""
    payload = json.loads(json.dumps(to_json(populated)))
    for row in payload["assumptions"]:
        assert isinstance(row["value"], str), f"{row['code']} was stored as {row['value']!r}"


def test_trailing_zeros_survive_the_round_trip():
    """4.14: the precision a figure was written to is a fact about it."""
    original = ScenarioSet((base_scenario(),), (assumption(value="59.900"),))
    restored = from_json(to_json(original))
    assert str(restored.assumptions[0].value) == "59.900"


def test_lineage_survives_the_round_trip(populated):
    """14.7: an override that loses its lineage has thrown the requirement away."""
    restored = from_json(to_json(populated))
    override = restored.resolve("upside")["dso"].assumption
    assert override.inherited_from == BASE
    assert override.overrides == "base:dso"
    assert override.source_type is SourceType.SCENARIO_OVERRIDE


def test_a_sourced_probability_survives_the_round_trip():
    original = ScenarioSet((
        base_scenario(),
        Scenario(
            id="likely", name="Likely case", parent_id=BASE,
            probability=Probability(D("0.6"), "internal forecast poll", "2026-09-01"),
        ),
    ))
    restored = from_json(to_json(original))
    probability = restored.scenario("likely").probability
    assert probability.value == D("0.6")
    assert probability.source == "internal forecast poll"


def test_statuses_and_timestamps_survive(populated):
    approved = assumption(status=Status.REVIEWED, reviewer="larry")
    restored = from_json(to_json(ScenarioSet((base_scenario(),), (approved,))))
    stored = restored.assumptions[0]
    assert stored.status is Status.REVIEWED
    assert stored.reviewer == "larry"
    assert stored.created_at == approved.created_at
    assert stored.updated_at == approved.updated_at


def test_an_absent_file_gives_a_fresh_base_scenario(tmp_path):
    store = ScenarioStore(tmp_path)
    fresh = store.load("doc-1", owner="larry")
    assert [s.id for s in fresh.scenarios] == [BASE]
    assert fresh.assumptions == ()


def test_saving_then_loading_gives_back_what_was_saved(tmp_path, populated):
    store = ScenarioStore(tmp_path)
    store.save("doc-1", populated)
    restored = store.load("doc-1")
    assert restored.resolve("upside")["dso"].assumption.value == D("45")


def test_saving_leaves_no_partial_file_behind(tmp_path, populated):
    """Written whole and renamed, so a crash cannot leave a half-set."""
    store = ScenarioStore(tmp_path)
    store.save("doc-1", populated)
    directory = store.path_for("doc-1").parent
    assert not list(directory.glob("*.tmp"))
    assert json.loads(store.path_for("doc-1").read_text())["scenarios"]


def test_a_float_written_into_the_file_by_hand_is_refused_on_load(tmp_path, populated):
    """The regression this arrangement is designed to make loud."""
    from model.numeric import PrecisionError

    store = ScenarioStore(tmp_path)
    path = store.save("doc-1", populated)
    payload = json.loads(path.read_text())
    payload["assumptions"][0]["value"] = 59.9  # a float, not a string
    path.write_text(json.dumps(payload))

    with pytest.raises(PrecisionError, match="arrived as a float"):
        store.load("doc-1")
