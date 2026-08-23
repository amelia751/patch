"""The deterministic run state machine from roadmap §9.

Orchestration is a table, not a supervisor agent's opinion. The transition map
here is the single definition of which moves are legal; Postgres persists each
transition and this module says whether the transition was allowed.
"""

from enum import StrEnum
from types import MappingProxyType
from typing import Final


class RunState(StrEnum):
    RECEIVED = "RECEIVED"
    SANITIZED = "SANITIZED"
    NORMALIZED = "NORMALIZED"
    IMPACT_SCANNING = "IMPACT_SCANNING"
    UNAFFECTED = "UNAFFECTED"
    POLICY_EVALUATION = "POLICY_EVALUATION"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    WAITING_ON_OPERATOR = "WAITING_ON_OPERATOR"
    BLOCKED = "BLOCKED"
    PATCHING = "PATCHING"
    BUILDING = "BUILDING"
    RETRY_PATCH = "RETRY_PATCH"
    TESTING = "TESTING"
    VERIFYING = "VERIFYING"
    FAILED = "FAILED"
    PR_CREATING = "PR_CREATING"
    PR_CREATED = "PR_CREATED"


# States a run may end in. There is no state after `PR_CREATED`: PatchAPI stops
# at the pull request and hands control back to normal human review.
TERMINAL_RUN_STATES: Final[frozenset[RunState]] = frozenset(
    {
        RunState.UNAFFECTED,
        RunState.HUMAN_REQUIRED,
        RunState.BLOCKED,
        RunState.FAILED,
        RunState.PR_CREATED,
    }
)

# States in which a run has stopped but has not ended: nothing is executing it,
# and what it is waiting for arrives from outside the run. Distinct from
# terminal, because the run can still reach a pull request, and distinct from
# in-flight, because no execution will pick it up on its own. Only the console
# saying "continue" moves it, which is why the set exists at all — treating
# these as in-flight is what leaves a run paused for a secret paused forever
# after the secret is supplied.
RESUMABLE_RUN_STATES: Final[frozenset[RunState]] = frozenset({RunState.WAITING_ON_OPERATOR})

ALLOWED_RUN_STATE_TRANSITIONS: Final[MappingProxyType[RunState, frozenset[RunState]]] = (
    MappingProxyType(
        {
            RunState.RECEIVED: frozenset({RunState.SANITIZED, RunState.FAILED}),
            RunState.SANITIZED: frozenset({RunState.NORMALIZED, RunState.FAILED}),
            RunState.NORMALIZED: frozenset({RunState.IMPACT_SCANNING, RunState.FAILED}),
            RunState.IMPACT_SCANNING: frozenset(
                {RunState.UNAFFECTED, RunState.POLICY_EVALUATION, RunState.FAILED}
            ),
            RunState.POLICY_EVALUATION: frozenset(
                {RunState.PATCHING, RunState.HUMAN_REQUIRED, RunState.BLOCKED, RunState.FAILED}
            ),
            RunState.PATCHING: frozenset(
                {RunState.BUILDING, RunState.WAITING_ON_OPERATOR, RunState.FAILED}
            ),
            RunState.BUILDING: frozenset({RunState.TESTING, RunState.RETRY_PATCH, RunState.FAILED}),
            RunState.RETRY_PATCH: frozenset({RunState.PATCHING, RunState.FAILED}),
            RunState.TESTING: frozenset(
                {RunState.VERIFYING, RunState.RETRY_PATCH, RunState.FAILED}
            ),
            RunState.VERIFYING: frozenset(
                {
                    RunState.PR_CREATING,
                    RunState.HUMAN_REQUIRED,
                    RunState.WAITING_ON_OPERATOR,
                    RunState.FAILED,
                }
            ),
            RunState.PR_CREATING: frozenset({RunState.PR_CREATED, RunState.FAILED}),
            RunState.WAITING_ON_OPERATOR: frozenset(
                {
                    RunState.PATCHING,
                    RunState.VERIFYING,
                    RunState.FAILED,
                }
            ),
            RunState.UNAFFECTED: frozenset(),
            RunState.HUMAN_REQUIRED: frozenset(),
            RunState.BLOCKED: frozenset(),
            RunState.FAILED: frozenset(),
            RunState.PR_CREATED: frozenset(),
        }
    )
)


def is_terminal(state: RunState) -> bool:
    """Return whether `state` ends the run."""
    return state in TERMINAL_RUN_STATES


def is_resumable(state: RunState) -> bool:
    """Return whether `state` is stopped waiting for something outside the run."""
    return state in RESUMABLE_RUN_STATES


def can_transition(source: RunState, target: RunState) -> bool:
    """Return whether moving from `source` to `target` is legal."""
    return target in ALLOWED_RUN_STATE_TRANSITIONS[source]


class IllegalRunStateTransitionError(ValueError):
    """Raised when a caller attempts a transition the state machine forbids."""


def assert_transition(source: RunState, target: RunState) -> None:
    """Raise `IllegalRunStateTransitionError` unless the transition is legal."""
    if not can_transition(source, target):
        allowed = ", ".join(sorted(ALLOWED_RUN_STATE_TRANSITIONS[source])) or "<terminal>"
        raise IllegalRunStateTransitionError(
            f"{source} -> {target} is not a legal run transition; allowed: {allowed}"
        )
