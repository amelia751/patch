"""Every run reaches an ending, including the ones a specialist cuts short.

Observed on a real Imagen run: the Patch agent landed the rewrite, both sandbox
checks exited 0, and then — having spent its tool-call budget — it called
`record_human_required`. The patch stage returned success, `keep` saw a context
that had stopped for a human and returned False, and `run_vertical_slice`
returned with the run resting in TESTING.

TESTING is not terminal. No process was executing the run, the console rendered
it as still working, and no operator was asked for anything: the run hung there
until somebody read the database. A stage succeeding and an agent asking for a
human are both true at once, and the ending belongs to the agent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.config import AgentId
from agents.context import RunContext
from agents.orchestrator import Orchestrator, StageResult
from agents.trace import ToolTrace
from packages.schemas.run_state import RunState, is_terminal

RUN_ID = "run-always-ends"


@pytest.fixture
def orchestrator() -> Orchestrator:
    context = RunContext(run_id=RUN_ID, repo_root=Path("/tmp"), feed_dir=Path("/tmp"))
    return Orchestrator(context, ToolTrace(run_id=RUN_ID))


def _mid_patch_loop(orchestrator: Orchestrator) -> None:
    """Walk the machine to TESTING the way a green patch run gets there."""
    for state in (
        RunState.SANITIZED,
        RunState.NORMALIZED,
        RunState.IMPACT_SCANNING,
        RunState.POLICY_EVALUATION,
        RunState.PATCHING,
        RunState.BUILDING,
        RunState.TESTING,
    ):
        orchestrator._advance(state)


def _succeeded(orchestrator: Orchestrator, detail: str) -> StageResult:
    return StageResult(
        agent=AgentId.PATCH,
        state=orchestrator._state,
        turn=None,
        output=None,
        human_required=tuple(orchestrator._context.human_required),
        detail=detail,
    )


def test_a_green_stage_and_a_fail_closed_agent_still_ends_the_run(
    orchestrator: Orchestrator,
) -> None:
    _mid_patch_loop(orchestrator)
    orchestrator._context.human_required.append(
        {"agent": str(AgentId.PATCH), "reason": "the tool-call budget ran out mid-migration"}
    )

    keep, _ = orchestrator._slice_keeper()
    going_on = keep(_succeeded(orchestrator, "IMAGE_MODEL now binds the replacement; checks pass"))

    assert not going_on
    assert orchestrator._state is RunState.HUMAN_REQUIRED
    assert is_terminal(orchestrator._state)


def test_the_reason_is_the_agents_rather_than_the_stages(orchestrator: Orchestrator) -> None:
    """A success line under a HUMAN_REQUIRED heading tells the operator nothing."""
    _mid_patch_loop(orchestrator)
    orchestrator._context.human_required.append(
        {"agent": str(AgentId.PATCH), "reason": "the tool-call budget ran out mid-migration"}
    )

    keep, result = orchestrator._slice_keeper()
    keep(_succeeded(orchestrator, "both checks exited 0"))

    assert result.detail == "the tool-call budget ran out mid-migration"
    assert result.state is RunState.HUMAN_REQUIRED


def test_an_operator_hold_is_left_alone(orchestrator: Orchestrator) -> None:
    """WAITING_ON_OPERATOR is not terminal on purpose — Continue moves it."""
    _mid_patch_loop(orchestrator)
    orchestrator._advance(RunState.VERIFYING)
    orchestrator._advance(RunState.WAITING_ON_OPERATOR)
    orchestrator._context.operator_requests.append({"message": "connect GCP"})

    keep, _ = orchestrator._slice_keeper()

    assert not keep(_succeeded(orchestrator, "waiting on you"))
    assert orchestrator._state is RunState.WAITING_ON_OPERATOR


def test_a_stage_that_is_going_fine_is_not_ended(orchestrator: Orchestrator) -> None:
    _mid_patch_loop(orchestrator)

    keep, result = orchestrator._slice_keeper()

    assert keep(_succeeded(orchestrator, "both checks exited 0"))
    assert result.state is RunState.TESTING
