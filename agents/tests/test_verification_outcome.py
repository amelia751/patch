"""How the run ends when the verifier does not answer.

Constraint 6 says an independent verification must pass before a pull request is
opened, and the interesting case is not a failing verdict — it is no verdict at
all. Observed on a real run: the verifier listed and read every piece of
evidence, called `list_runtime_credentials`, found nothing bound, and ended its
turn without either requesting credentials or recording a skip.

The run was marked FAILED with "no VerificationReport was recorded". No pull
request, which is right, and otherwise wrong in both directions: it told the
operator a migration had failed when the tests in its own worklog were green,
and it left a terminal row with nothing to act on.

These pin the ending down: no pull request, HUMAN_REQUIRED, and a reason that
says the verifier is what is missing.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agents.config import AgentId
from agents.context import RunContext
from agents.orchestrator import STAGE_CONTRACTS, Orchestrator
from agents.trace import ToolTrace
from packages.schemas.run_state import RunState
from packages.schemas.verification_report import VerificationReport

RUN_ID = "run-verification-outcome"


class _Slice:
    change_id = "gemini20-flash-shutdown-2026-06-01"
    repo = "amelia751/storygen"


@pytest.fixture
def orchestrator() -> Orchestrator:
    context = RunContext(run_id=RUN_ID, repo_root=Path("/tmp"), feed_dir=Path("/tmp"))
    # `run_verification` refuses before reaching a verdict without these two, and
    # neither is what these tests are about.
    context.evidence_root = Path("/tmp")
    return Orchestrator(context, ToolTrace(run_id=RUN_ID))


def _up_to_verification(orchestrator: Orchestrator) -> None:
    """Walk the state machine to where a verdict is next.

    Through `_advance` rather than by assignment, so the test cannot ask for an
    ending the machine would refuse to reach in a real run.
    """
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


def _with_manifest(orchestrator: Orchestrator) -> None:
    from packages.schemas.change_manifest import ChangeManifest

    manifest = ChangeManifest(
        provider="google",
        change_id=_Slice.change_id,
        change_type="model_retirement",
        severity="high",
        effective_at=date(2026, 6, 1),
        affected_identifiers=["gemini-2.0-flash"],
        recommended_replacement="gemini-3.5-flash",
        semantic_migration_required=False,
        source_urls=["https://ai.google.dev/gemini-api/docs/changelog"],
    )
    orchestrator._context.record(
        STAGE_CONTRACTS[AgentId.CHANGE_INTELLIGENCE], AgentId.CHANGE_INTELLIGENCE, manifest
    )


@pytest.mark.asyncio
async def test_a_verifier_that_records_nothing_asks_for_a_human(
    orchestrator: Orchestrator,
) -> None:
    _with_manifest(orchestrator)
    _up_to_verification(orchestrator)

    result = await orchestrator.run_verification(_Slice(), deterministic=True)

    assert orchestrator._state is RunState.HUMAN_REQUIRED
    assert "without recording a report" in result.detail
    assert result.output is None


@pytest.mark.asyncio
async def test_that_ending_is_terminal_so_no_pull_request_is_attempted(
    orchestrator: Orchestrator,
) -> None:
    """The guard `run_pr` has of its own is a second line, not the first."""
    from packages.schemas.run_state import is_terminal

    _with_manifest(orchestrator)
    _up_to_verification(orchestrator)

    await orchestrator.run_verification(_Slice(), deterministic=True)

    assert is_terminal(orchestrator._state)
    recorded = orchestrator._context.output(STAGE_CONTRACTS[AgentId.VERIFICATION])
    assert not isinstance(recorded, VerificationReport)


@pytest.mark.asyncio
async def test_the_ending_names_the_verifier_rather_than_the_patch(
    orchestrator: Orchestrator,
) -> None:
    """The operator's next question is what to do, and the answer is 'grade this'."""
    _with_manifest(orchestrator)
    _up_to_verification(orchestrator)

    result = await orchestrator.run_verification(_Slice(), deterministic=True)

    assert "verifier" in result.detail
    assert "review" in result.detail
    # The old wording was an internal contract name, which told an operator
    # nothing and read as a crash.
    assert "no VerificationReport was recorded" not in result.detail
