"""Who is on the air to perform remediations, for diagnosis only.

The run lease answers "which instance is performing this run". Nothing answered
"is any instance available to perform one", and the console needs both to say
anything true about a run that has not started: waiting behind work in progress
and waiting on a worker that is gone look identical from the run row alone.

Nothing here is on the claim path. A worker whose heartbeat write fails carries
on claiming and performing runs, and the reader treats a silent lane as unknown
rather than as a reason not to dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    import asyncpg

# How long after its last poll a worker is still believed to be on the air.
# Several poll intervals, so an instance mid-remediation — which polls only
# between runs — is not called dead while it is working.
ALIVE_SECONDS: Final[float] = 90.0

_BEAT_SQL: Final[str] = """
INSERT INTO remediation_workers (worker_id, lane, last_seen_at, current_run)
VALUES ($1, $2, now(), $3::uuid)
ON CONFLICT (worker_id) DO UPDATE
SET lane = EXCLUDED.lane,
    last_seen_at = now(),
    current_run = EXCLUDED.current_run
"""

_LANE_SQL: Final[str] = """
SELECT
    count(*) FILTER (WHERE last_seen_at > now() - $2::interval) AS alive,
    count(*) FILTER (
        WHERE last_seen_at > now() - $2::interval AND current_run IS NULL
    ) AS idle,
    max(last_seen_at) AS last_seen
FROM remediation_workers
WHERE lane = $1
"""

_FORGET_SQL: Final[str] = "DELETE FROM remediation_workers WHERE worker_id = $1"


@dataclass(frozen=True, slots=True)
class LaneHealth:
    """What is known about the workers serving one lane."""

    alive: int = 0
    idle: int = 0
    # Seconds since any worker in this lane last polled, or None if none ever has.
    silent_for: float | None = None

    @property
    def busy(self) -> int:
        """Workers on the air and already performing a run."""
        return max(self.alive - self.idle, 0)

    @property
    def unattended(self) -> bool:
        """Whether a run in this lane has nobody to claim it.

        A lane no worker has ever reported into is unattended too: either the
        table predates the workers or nothing is deployed. Both mean a run put
        there will not be performed, which is what the operator needs to know.
        """
        return self.alive == 0


async def beat(
    connection: asyncpg.Connection,
    worker: str,
    *,
    lane: str,
    run_id: str | None = None,
) -> None:
    """Record that `worker` is on the air, performing `run_id` or idle."""
    await connection.execute(_BEAT_SQL, worker, lane, run_id)


async def forget(connection: asyncpg.Connection, worker: str) -> None:
    """Drop this worker's row on a clean shutdown, so it is not read as wedged."""
    await connection.execute(_FORGET_SQL, worker)


async def lane_health(
    connection: asyncpg.Connection, lane: str, *, alive_seconds: float = ALIVE_SECONDS
) -> LaneHealth:
    """How many workers are serving `lane`, and how many are free."""
    row = await connection.fetchrow(_LANE_SQL, lane, timedelta(seconds=alive_seconds))
    if row is None:  # pragma: no cover - an aggregate always returns one row
        return LaneHealth()
    last_seen = row["last_seen"]
    silent_for: float | None = None
    if last_seen is not None:
        silent_for = (datetime.now(UTC) - last_seen).total_seconds()
    return LaneHealth(
        alive=int(row["alive"] or 0),
        idle=int(row["idle"] or 0),
        silent_for=silent_for,
    )


__all__ = ["ALIVE_SECONDS", "LaneHealth", "beat", "forget", "lane_health"]
