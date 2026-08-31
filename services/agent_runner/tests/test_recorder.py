"""The worklog body the console draws Edit cards from, and how it is drained."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from patchapi_agent_runner.remediation.recorder import RunRecorder, _body

from agents.config import AgentId
from agents.journal import RunJournal
from agents.trace import ToolStatus, ToolTrace


def test_apply_patch_carries_the_unified_diff_after_the_summary() -> None:
    """The next 1s poll must see the hunk, not wait for the end-of-run artifact."""
    diff = "--- a/lib/gemini.ts\n+++ b/lib/gemini.ts\n@@ -1 +1 @@\n-old\n+new\n"
    body = _body(
        SimpleNamespace(
            tool="apply_patch",
            arguments={"diff": "<12 chars, sha256:abc>"},
            result_summary="applied",
            detail=diff,
            status=ToolStatus.OK,
        )
    )
    head, _, tail = body.partition("\n")
    assert head.startswith("apply_patch(")
    assert "applied" in head
    assert tail == diff


class _SlowPool:
    """A pool whose every write lands in `rows`, slowly enough to overlap."""

    def __init__(self, delay: float = 0.02) -> None:
        self.rows: list[tuple[str, str]] = []
        self._delay = delay

    @asynccontextmanager
    async def acquire(self):
        yield self

    async def execute(self, sql: str, *args: object) -> str:
        await asyncio.sleep(self._delay)
        if "run_trace_events" in sql:
            self.rows.append((str(args[4]), str(args[3])))
        return "INSERT 0 1"

    async def fetchrow(self, _sql: str, *_args: object):
        return {"state": "RECEIVED"}

    @asynccontextmanager
    async def transaction(self):
        yield


async def test_two_flushes_at_once_write_each_line_once() -> None:
    """The pump ticks while the job flushes at a stage boundary; both drain.

    The pending slice is only marked written once every row in it has been, so
    an overlapping pair used to write every line twice and collide on the
    worklog's per-run sequence — failing a healthy run over a log line.
    """
    run_id = "11111111-2222-3333-4444-555555555555"
    pool = _SlowPool()
    trace = ToolTrace(run_id=run_id)
    for tool in ("list_skills", "load_skill", "load_skill_resource"):
        trace.record(
            agent=AgentId.PATCH,
            tool=tool,
            status=ToolStatus.OK,
            arguments={},
            result={"status": "ok"},
            duration_ms=1.0,
        )
    recorder = RunRecorder(
        pool=pool, run_id=run_id, journal=RunJournal(run_id=run_id), trace=trace
    )

    await asyncio.gather(recorder.flush(), recorder.flush())

    assert [verb for _, verb in pool.rows] == ["list_skills", "load_skill", "load_skill_resource"]
