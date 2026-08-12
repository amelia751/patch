"""The run state machine matches roadmap §9 and has no path past the PR."""

from itertools import pairwise

import pytest

from packages.schemas import (
    ALLOWED_RUN_STATE_TRANSITIONS,
    TERMINAL_RUN_STATES,
    IllegalRunStateTransitionError,
    RunState,
    assert_transition,
    can_transition,
    is_terminal,
)


def test_every_state_has_a_transition_entry():
    assert set(ALLOWED_RUN_STATE_TRANSITIONS) == set(RunState)


def test_terminal_states_have_no_successor():
    for state in TERMINAL_RUN_STATES:
        assert ALLOWED_RUN_STATE_TRANSITIONS[state] == frozenset()
        assert is_terminal(state)


def test_non_terminal_states_can_always_move():
    for state in set(RunState) - TERMINAL_RUN_STATES:
        assert ALLOWED_RUN_STATE_TRANSITIONS[state], state


def test_nothing_follows_a_created_pull_request():
    """PatchAPI stops at the pull request; there is no merge or deploy state."""
    assert is_terminal(RunState.PR_CREATED)
    assert not any(
        RunState.PR_CREATED in targets and source is not RunState.PR_CREATING
        for source, targets in ALLOWED_RUN_STATE_TRANSITIONS.items()
    )


def test_the_happy_path_is_walkable():
    path = [
        RunState.RECEIVED,
        RunState.SANITIZED,
        RunState.NORMALIZED,
        RunState.IMPACT_SCANNING,
        RunState.POLICY_EVALUATION,
        RunState.PATCHING,
        RunState.BUILDING,
        RunState.TESTING,
        RunState.VERIFYING,
        RunState.PR_CREATING,
        RunState.PR_CREATED,
    ]

    for source, target in pairwise(path):
        assert_transition(source, target)


def test_verification_cannot_be_skipped():
    assert not can_transition(RunState.TESTING, RunState.PR_CREATING)
    assert not can_transition(RunState.BUILDING, RunState.PR_CREATING)
    assert not can_transition(RunState.PATCHING, RunState.PR_CREATED)


def test_retry_returns_to_patching_only():
    assert ALLOWED_RUN_STATE_TRANSITIONS[RunState.RETRY_PATCH] == frozenset(
        {RunState.PATCHING, RunState.FAILED}
    )


def test_an_illegal_transition_raises():
    with pytest.raises(IllegalRunStateTransitionError, match="not a legal run transition"):
        assert_transition(RunState.RECEIVED, RunState.PR_CREATED)


def test_serialized_states_stay_readable():
    assert RunState.PR_CREATED.value == "PR_CREATED"
    assert f"{RunState.TESTING}" == "TESTING"
