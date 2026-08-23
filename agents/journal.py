"""Where the run has been, recorded as it moves.

The orchestrator holds its state in memory and asserts every transition against
the shared table. That is enough to run a slice from a script, and not enough to
run one as a product: when the process ends the history ends with it, so a
console cannot follow a run it did not start and a run that dies leaves no trace
of how far it got.

A journal is the smallest thing that fixes it. `_advance` appends a record and
returns; nothing here touches a database, opens a socket, or blocks. Persisting
is somebody else's job, done from a different task, which is what keeps a slow
write from stalling the state machine — and keeps `agents` free of a dependency
on `packages.state`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from packages.schemas.run_state import RunState


@dataclass(frozen=True, slots=True)
class StateChange:
    """One move of the run state machine."""

    sequence: int
    from_state: RunState | None
    to_state: RunState
    occurred_at: datetime


@dataclass(slots=True)
class RunJournal:
    """An ordered, append-only record of one run's transitions.

    `sequence` is dense and monotonic so a reader can ask for everything after
    what it already holds, which is exact where a timestamp comparison is only
    nearly exact.
    """

    run_id: str = ""
    changes: list[StateChange] = field(default_factory=list)

    def record(self, source: RunState | None, target: RunState) -> StateChange:
        change = StateChange(
            sequence=len(self.changes) + 1,
            from_state=source,
            to_state=target,
            occurred_at=datetime.now(UTC),
        )
        self.changes.append(change)
        return change

    def since(self, sequence: int) -> list[StateChange]:
        """Every change after `sequence`."""
        return [change for change in self.changes if change.sequence > sequence]

    def state_at(self, when: datetime) -> RunState:
        """The state the run was in at `when`.

        A worklog line is written by whoever drains the journal, which happens
        some time after the tool ran — often a stage or two later. Labelling the
        line with the state at drain time puts an impact scan under PATCHING and
        makes the console's grouping wrong. The journal knows when each move
        happened, so the honest label is the one in effect when the tool ran.
        """
        state = RunState.RECEIVED
        for change in self.changes:
            if change.occurred_at > when:
                break
            state = change.to_state
        return state

    def __len__(self) -> int:
        return len(self.changes)


__all__ = ["RunJournal", "StateChange"]
