"""Item 29: the extraction job state machine and its legal transitions."""

from __future__ import annotations

import pytest

from apps.api.app.core.errors import IllegalTransition
from apps.api.app.extraction.jobs import (
    LEGAL_TRANSITIONS,
    TERMINAL,
    ExtractionJob,
    JobState,
)


def test_every_state_has_a_transition_row():
    assert set(LEGAL_TRANSITIONS) == set(JobState)


def test_terminal_states_have_no_exits():
    for state in TERMINAL:
        assert LEGAL_TRANSITIONS[state] == frozenset()


def test_every_non_terminal_state_can_refuse_and_fail():
    """A rule can say no at any point, and a parser can raise at any point."""
    for state, allowed in LEGAL_TRANSITIONS.items():
        if state in TERMINAL:
            continue
        assert JobState.REFUSED in allowed and JobState.FAILED in allowed


def test_the_happy_path_runs_end_to_end():
    job = ExtractionJob.start(job_id="job-x")
    for state in (
        JobState.VALIDATING,
        JobState.STORED,
        JobState.CLASSIFYING,
        JobState.EXTRACTING,
        JobState.EXTRACTED,
    ):
        job = job.advance(state, f"moving to {state.value}")
    assert job.is_terminal
    assert len(job.history) == 5


def test_skipping_a_state_is_refused():
    job = ExtractionJob.start().advance(JobState.VALIDATING, "checking")
    with pytest.raises(IllegalTransition) as exc:
        job.advance(JobState.EXTRACTED, "skip ahead")
    assert "legal next states" in str(exc.value)


def test_a_terminal_job_cannot_be_rewound():
    job = ExtractionJob.start().advance(JobState.REFUSED, "not a PDF")
    with pytest.raises(IllegalTransition) as exc:
        job.advance(JobState.VALIDATING, "try again")
    assert "new job" in str(exc.value)


def test_a_transition_without_a_reason_is_refused():
    """10.33. A state change with no stated reason is the audit gap itself."""
    job = ExtractionJob.start()
    with pytest.raises(ValueError):
        job.advance(JobState.VALIDATING, "   ")


def test_history_is_append_only():
    first = ExtractionJob.start()
    second = first.advance(JobState.VALIDATING, "checking")
    assert first.history == ()
    assert len(second.history) == 1
