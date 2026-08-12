"""The narrow run-state read.

Kept apart from `dashboard.py` because it is on a different path: an
orchestrator polls this to find out where a run is, and it has to stay one
indexed lookup. The dashboard's richer projections may cost more because a
human is waiting on a page, not a state machine on a decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from patchapi_control_api.ports import RunRecord

from packages.state.pool import StateUnavailableError

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

# `reason` is the failure reason when the run has one, and otherwise the reason
# recorded on the transition that put the run in its current state — which is
# what an operator means by "why is it here".
_READ_RUN = """
SELECT
    r.id::text                              AS run_id,
    r.state::text                           AS state,
    repo.owner || '/' || repo.name          AS repository,
    r.base_sha                              AS base_sha,
    r.updated_at                            AS updated_at,
    COALESCE(r.failure_reason, t.reason)    AS reason
FROM remediation_runs r
JOIN repositories repo ON repo.id = r.repository_id
LEFT JOIN LATERAL (
    SELECT reason
    FROM run_state_transitions
    WHERE run_id = r.id AND to_state = r.state
    ORDER BY sequence DESC
    LIMIT 1
) t ON TRUE
WHERE r.id = $1::uuid
"""


def _is_uuid(value: str) -> bool:
    """Return whether `value` can be cast to uuid without erroring in Postgres."""
    from uuid import UUID

    try:
        UUID(value)
    except ValueError:
        return False
    return True


class PostgresRunStateReader:
    """Reads deterministic run state from Cloud SQL / local Postgres."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def read(self, run_id: str) -> RunRecord | None:
        """Return the run, or `None` if no such run exists.

        A run id that is not a uuid cannot identify a row, so it is reported as
        not found rather than as a database error: the caller asked about a run
        that does not exist either way.
        """
        if not _is_uuid(run_id):
            return None
        row = await _fetchrow(self._pool, _READ_RUN, run_id)
        if row is None:
            return None
        return RunRecord(**dict(row))


async def _fetchrow(pool: asyncpg.Pool, query: str, *args: Any) -> Any:
    try:
        return await pool.fetchrow(query, *args)
    except Exception as exc:
        raise StateUnavailableError(f"run-state read failed: {type(exc).__name__}") from exc
