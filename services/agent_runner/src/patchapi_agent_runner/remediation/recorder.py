"""Publishing a run's progress while the run is still happening.

The console polls a table; the orchestrator advances a machine in memory. This
is the pump between them, and it runs as its own task for one reason: a state
transition must not wait on a database write. If it did, a slow connection would
show up as a stalled agent, and a failed write would abort a migration that was
going fine.

So the orchestrator appends to a journal and returns. This drains the journal
and the tool trace on a tick, and again at the end. Losing the last tick of
worklog to a crashed job is acceptable; losing the patch because Postgres was
briefly slow is not.

Transitions are replayed through the same `advance` every other writer uses, so
the persisted history is checked against the state machine a second time. An
orchestrator bug that produced an illegal move would be caught here rather than
written down as though it were legal.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from agents.journal import RunJournal
from agents.trace import ToolStatus, ToolTrace
from packages.schemas.run_state import IllegalRunStateTransitionError, RunState
from packages.state import remediation

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

log = logging.getLogger(__name__)

FLUSH_INTERVAL_SECONDS: Final[float] = 1.0
ACTOR: Final[str] = "orchestrator"

# How a tool call reads in the console worklog. `denied` is loud on purpose: a
# refused call is the control surface doing its job and is the single most
# interesting line a reviewer can see.
_KIND_BY_STATUS: Final[dict[ToolStatus, str]] = {
    ToolStatus.OK: "action",
    ToolStatus.REFUSED: "result",
    ToolStatus.DENIED: "narration",
    ToolStatus.ERROR: "narration",
}


@dataclass(slots=True)
class RunRecorder:
    """Drains one run's journal and trace into Postgres."""

    pool: asyncpg.Pool
    run_id: str
    journal: RunJournal
    trace: ToolTrace

    _states_flushed: int = 0
    _events_flushed: int = 0
    _narration: list[tuple[RunState, str]] = field(default_factory=list)
    _task: asyncio.Task[None] | None = None
    _stop: asyncio.Event = field(default_factory=asyncio.Event)

    def narrate(self, state: RunState, line: str) -> None:
        """Add a sentence the console should show that no tool call produced."""
        self._narration.append((state, line))

    @property
    def state(self) -> RunState:
        """The last state the journal recorded, or where a run begins."""
        if not self.journal.changes:
            return RunState.RECEIVED
        return self.journal.changes[-1].to_state

    async def flush(self) -> None:
        """Write everything recorded since the last call."""
        async with self.pool.acquire() as connection:
            await self._flush_states(connection)
            await self._flush_trace(connection)
            await self._flush_narration(connection)

    async def _flush_states(self, connection: asyncpg.Connection) -> None:
        pending = self.journal.since(self._states_flushed)
        for change in pending:
            try:
                await remediation.advance(
                    connection,
                    self.run_id,
                    change.to_state,
                    actor=ACTOR,
                    reason="",
                )
            except IllegalRunStateTransitionError as exc:
                # The in-memory machine already allowed this, so disagreement
                # means the stored state drifted — a second execution of the
                # same run, most likely. Recording is abandoned rather than
                # forced; the run in the database is somebody else's.
                log.error("run %s: refusing to persist %s: %s", self.run_id, change.to_state, exc)
            except LookupError:
                log.error("run %s vanished while it was being recorded", self.run_id)
                return
            self._states_flushed = change.sequence

    async def _flush_trace(self, connection: asyncpg.Connection) -> None:
        events = self.trace.events[self._events_flushed :]
        for event in events:
            await remediation.append_trace(
                connection,
                self.run_id,
                state=self._state_when(event.started_at),
                kind=_KIND_BY_STATUS.get(event.status, "narration"),
                verb=event.tool,
                body=_body(event),
                tool_type=str(event.agent),
                tool_use_id=f"{self.run_id}-{event.sequence}",
                file_path=str(event.arguments.get("path") or ""),
            )
        self._events_flushed += len(events)

    def _state_when(self, started_at: str) -> RunState:
        """The run state in effect when a tool call began."""
        try:
            when = datetime.fromisoformat(started_at)
        except (TypeError, ValueError):
            return self.state
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        return self.journal.state_at(when)

    async def _flush_narration(self, connection: asyncpg.Connection) -> None:
        pending, self._narration = self._narration, []
        for state, line in pending:
            await remediation.append_trace(
                connection, self.run_id, state=state, kind="narration", body=line
            )

    async def _pump(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=FLUSH_INTERVAL_SECONDS)
            except TimeoutError:
                pass
            try:
                await self.flush()
            except Exception as exc:  # a recorder must never end a run
                log.warning("run %s: flush failed (%s); retrying", self.run_id, exc)

    async def __aenter__(self) -> RunRecorder:
        self._task = asyncio.create_task(self._pump())
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
        # The pump may have exited on a failed flush. The final one is the write
        # that decides whether the console sees how the run ended.
        try:
            await self.flush()
        except Exception as exc:
            log.error("run %s: final flush failed: %s", self.run_id, exc)


def _body(event: object) -> str:
    """One readable line for a tool call, arguments included."""
    tool = getattr(event, "tool", "")
    arguments = getattr(event, "arguments", {}) or {}
    summary = getattr(event, "result_summary", "")
    detail = getattr(event, "detail", "") or ""
    shown = ", ".join(f"{name}={value}" for name, value in arguments.items())
    line = f"{tool}({shown})"
    if summary:
        line += f" → {summary}"
    if getattr(event, "status", None) is ToolStatus.DENIED:
        line = f"DENIED {line}"
        if detail:
            line += f" — {detail}"
    return line


__all__ = ["ACTOR", "FLUSH_INTERVAL_SECONDS", "RunRecorder"]
