"""Continuing a parked agent turn rather than starting it over.

A remediation that asks the operator for a credential ends its Cloud Run job.
Continue starts a new execution, and the only way that execution can rejoin the
turn — instead of re-reading every file the model already read — is the pointer
recorded when the turn parked. These cover the pointer: what it must contain to
be usable, and the cases where using it would be wrong.

The live proof that ADK honours it across a process boundary is
`scripts/smoke_adk_resume.py`, which needs Vertex and Postgres.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.adk import TurnResult, session_id_for
from agents.config import AgentId
from agents.context import RunContext
from agents.orchestrator import Orchestrator, SliceResult, StageResult
from agents.sessions import (
    ASYNC_SCHEME,
    ENV_DATABASE_URL,
    missing_driver,
    session_dsn,
    undurable_reason,
)
from agents.trace import ToolTrace
from packages.schemas.run_state import RunState

RUN_ID = "run-operator-resume"


def _turn(**overrides: object) -> TurnResult:
    fields: dict[str, object] = {
        "agent": str(AgentId.PATCH),
        "final_text": "",
        "model_versions": ("gemini-3.5-flash",),
        "event_count": 4,
        "trace": ToolTrace(run_id=RUN_ID),
        "paused": True,
        "long_running_tool": "request_runtime_credentials",
        "session_id": session_id_for(RUN_ID, str(AgentId.PATCH)),
        "pending_call_id": "call_1",
    }
    fields.update(overrides)
    return TurnResult(**fields)  # type: ignore[arg-type]


def _context(**overrides: object) -> RunContext:
    fields: dict[str, object] = {
        "run_id": RUN_ID,
        "repo_root": Path("/tmp"),
        "feed_dir": Path("/tmp"),
    }
    fields.update(overrides)
    return RunContext(**fields)  # type: ignore[arg-type]


def _orchestrator(context: RunContext) -> Orchestrator:
    return Orchestrator(context, ToolTrace(run_id=RUN_ID))


# -- what makes a pause answerable ---------------------------------------


def test_a_pause_with_a_session_and_a_call_id_can_be_answered():
    assert _turn().resumable is True


def test_a_pause_that_kept_no_call_id_cannot_be_answered():
    """Without the id there is nothing to send a function response for."""
    assert _turn(pending_call_id="").resumable is False


def test_a_turn_that_did_not_pause_is_never_resumable():
    assert _turn(paused=False).resumable is False


# -- which stage the caller should write down ----------------------------


def test_the_parked_turn_is_the_one_the_run_stopped_inside():
    parked = _turn()
    result = SliceResult(
        state=RunState.WAITING_ON_OPERATOR,
        detail="waiting on the operator",
        stages=[
            StageResult(
                agent=AgentId.IMPACT,
                state=RunState.IMPACT_SCANNING,
                turn=None,
                output={},
                human_required=(),
            ),
            StageResult(
                agent=AgentId.PATCH,
                state=RunState.WAITING_ON_OPERATOR,
                turn=parked,
                output=None,
                human_required=(),
            ),
        ],
    )
    assert result.parked_turn is parked


def test_a_hold_decided_before_any_model_ran_has_no_turn_to_resume():
    """The live-credential park happens before the Patch turn starts.

    Nothing was read and nothing was said, so there is no conversation to
    rejoin — and recording a pointer would send the next execution to answer a
    call that was never made.
    """
    result = SliceResult(
        state=RunState.WAITING_ON_OPERATOR,
        detail="connect GCP",
        stages=[
            StageResult(
                agent=AgentId.PATCH,
                state=RunState.WAITING_ON_OPERATOR,
                turn=None,
                output=None,
                human_required=(),
            )
        ],
    )
    assert result.parked_turn is None


def test_a_turn_that_paused_without_a_pointer_is_reported_not_hidden():
    """The replay is about to happen; the operator should hear why."""
    result = SliceResult(
        state=RunState.WAITING_ON_OPERATOR,
        detail="waiting on the operator",
        stages=[
            StageResult(
                agent=AgentId.PATCH,
                state=RunState.WAITING_ON_OPERATOR,
                turn=_turn(session_id=""),
                output=None,
                human_required=(),
            )
        ],
    )
    assert result.parked_turn is None
    assert result.parked_mid_turn_without_a_pointer is True


def test_a_hold_before_the_model_ran_is_not_reported_as_a_lost_pointer():
    """Nothing was said, so nothing is replayed and there is nothing to warn about."""
    result = SliceResult(
        state=RunState.WAITING_ON_OPERATOR,
        detail="connect GCP",
        stages=[
            StageResult(
                agent=AgentId.PATCH,
                state=RunState.WAITING_ON_OPERATOR,
                turn=None,
                output=None,
                human_required=(),
            )
        ],
    )
    assert result.parked_mid_turn_without_a_pointer is False


def test_a_run_that_moved_past_its_hold_reports_no_parked_turn():
    """So the caller clears the pointer instead of leaving a stale one."""
    result = SliceResult(
        state=RunState.PR_CREATED,
        detail="pull request opened",
        stages=[
            StageResult(
                agent=AgentId.PATCH,
                state=RunState.WAITING_ON_OPERATOR,
                turn=_turn(),
                output=None,
                human_required=(),
            )
        ],
    )
    assert result.parked_turn is None


# -- using the pointer --------------------------------------------------


def test_the_patch_agent_resumes_the_hold_it_recorded():
    hold = {
        "agent": str(AgentId.PATCH),
        "session_id": session_id_for(RUN_ID, str(AgentId.PATCH)),
        "call_id": "call_1",
        "tool": "request_runtime_credentials",
    }
    orchestrator = _orchestrator(_context(agent_hold=hold))
    assert orchestrator._hold_for(AgentId.PATCH) == hold


def test_one_specialist_does_not_answer_another_specialists_hold():
    """Sessions are per agent so Verification cannot read the Patch turn.

    Resuming across that line would hand it over, which is the separation the
    per-agent session id exists to keep.
    """
    hold = {
        "agent": str(AgentId.PATCH),
        "session_id": session_id_for(RUN_ID, str(AgentId.PATCH)),
        "call_id": "call_1",
        "tool": "request_runtime_credentials",
    }
    orchestrator = _orchestrator(_context(agent_hold=hold))
    assert orchestrator._hold_for(AgentId.VERIFICATION) == {}


def test_a_hold_from_another_run_is_refused():
    """A pointer whose session does not belong to this run is not this run's."""
    hold = {
        "agent": str(AgentId.PATCH),
        "session_id": session_id_for("some-other-run", str(AgentId.PATCH)),
        "call_id": "call_1",
        "tool": "request_runtime_credentials",
    }
    orchestrator = _orchestrator(_context(agent_hold=hold))
    assert orchestrator._hold_for(AgentId.PATCH) == {}


def test_a_run_that_never_parked_has_nothing_to_resume():
    orchestrator = _orchestrator(_context())
    assert orchestrator._hold_for(AgentId.PATCH) == {}


# -- what the resumed tool call returns ---------------------------------


def test_the_answer_reports_the_connection_and_never_a_secret_value():
    class Inventory:
        bound = True
        gcp_connected = True
        gcp_project_id = "artful-journey-486915-a8"
        secret_names = ("GEMINI_API_KEY",)

    orchestrator = _orchestrator(_context(credentials_inventory=Inventory()))
    answer = orchestrator._credential_answer()

    assert answer["status"] == "ok"
    assert answer["gcp_connected"] is True
    assert answer["gcp_project_id"] == "artful-journey-486915-a8"
    assert answer["secret_names"] == ["GEMINI_API_KEY"]
    # Names, not values. The model asked what exists, not for the credential.
    assert "value" not in answer
    assert not any("AIza" in str(item) for item in answer.values())


def test_the_answer_says_so_when_the_operator_supplied_nothing_usable():
    class Empty:
        bound = False
        gcp_connected = False
        gcp_project_id = ""
        secret_names = ()

    orchestrator = _orchestrator(_context(credentials_inventory=Empty()))
    answer = orchestrator._credential_answer()

    assert answer["status"] == "still_missing"
    assert "record_human_required" in answer["detail"]


# -- where the conversation is stored ----------------------------------


@pytest.mark.parametrize(
    "configured",
    [
        "postgresql://u:p@host:5432/db",
        "postgres://u:p@host:5432/db",
        "postgresql+psycopg://u:p@host:5432/db",
    ],
)
def test_a_sync_dsn_is_rewritten_for_the_async_engine(configured: str):
    """ADK builds an async engine; a sync driver fails at construction."""
    dsn = session_dsn({ENV_DATABASE_URL: configured})
    assert dsn.startswith(ASYNC_SCHEME)
    assert dsn.endswith("u:p@host:5432/db")


def test_an_unrecognised_dsn_is_not_guessed_into_a_driver():
    assert session_dsn({ENV_DATABASE_URL: "mysql://u:p@host/db"}) == ""


def test_no_database_means_a_parked_turn_is_reported_as_unresumable():
    """Said out loud rather than discovered when Continue silently replays."""
    reason = undurable_reason({})
    assert reason is not None
    assert ENV_DATABASE_URL in reason


def test_a_configured_database_can_resume_a_parked_turn():
    assert undurable_reason({ENV_DATABASE_URL: "postgresql://u:p@host:5432/db"}) is None


def test_the_session_store_driver_is_installed_where_the_job_runs():
    """`agents` is copied into the remediator image as source, not installed.

    Declaring the session store's driver in `agents/pyproject.toml` alone left
    it absent from the deployed image, which resumed nothing and said nothing.
    """
    assert missing_driver() is None


def test_a_missing_driver_is_reported_rather_than_assumed_away(monkeypatch):
    """A DSN is not durability if the engine cannot be built."""
    monkeypatch.setattr("agents.sessions.missing_driver", lambda: "sqlalchemy")
    reason = undurable_reason({ENV_DATABASE_URL: "postgresql://u:p@host:5432/db"})
    assert reason is not None
    assert "sqlalchemy" in reason
