"""Which run a warm worker should perform next.

There is no separate queue. `open_run` drives a new run, a restart and an
operator resume all to `RECEIVED`, so `state = 'RECEIVED'` already means "no
worker is performing this and one should". Adding Pub/Sub beside that would give
two sources of truth about what is pending, and Postgres is the authoritative one
(roadmap §7).

What the job model did not need, and a pool of always-on instances does, is a
lease: several instances poll the same rows, and a run must be performed once.
The claim is a single `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP
LOCKED)`, which is the one shape that cannot hand the same row to two callers —
the subquery locks the row it returns, and a concurrent caller skips it rather
than blocking on it and then claiming an already-claimed run.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    import asyncpg

# How long a lease on a run that has not left RECEIVED stays believable. A
# claimed run gets its first transition within seconds, so a RECEIVED row under
# an older lease than this is one whose worker went away before doing anything.
# Deliberately not a heartbeat on a running remediation: a run that got as far as
# PATCHING and lost its worker is not resumable from another instance, and
# handing it over would replay work whose evidence is already written down.
LEASE_SECONDS: Final[float] = 120.0

_CLAIM_SQL: Final[str] = """
UPDATE remediation_runs
SET leased_by = $1, leased_at = now(), updated_at = now()
WHERE id = (
    SELECT id
    FROM remediation_runs
    WHERE state = 'RECEIVED'
      AND (leased_by = '' OR leased_at IS NULL OR leased_at < now() - $2::interval)
    ORDER BY started_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id::text
"""

_RELEASE_SQL: Final[str] = """
UPDATE remediation_runs
SET leased_by = '', leased_at = NULL, updated_at = now()
WHERE id = $1::uuid AND leased_by = $2
"""


async def claim(
    connection: asyncpg.Connection,
    worker: str,
    *,
    lease_seconds: float = LEASE_SECONDS,
) -> str | None:
    """Take one run for this worker, or return None if there is nothing to do.

    The returned run is this worker's until it releases it. A caller that gets a
    run and then dies leaves the row at `RECEIVED` under a stale lease, which the
    next poll of any instance reclaims.
    """
    row = await connection.fetchrow(_CLAIM_SQL, worker, timedelta(seconds=lease_seconds))
    return None if row is None else str(row["id"])


async def release(connection: asyncpg.Connection, run_id: str, worker: str) -> None:
    """Give up this worker's lease on a run it has finished performing.

    Scoped to the holder so a worker that overran its lease and was reclaimed
    cannot clear the lease of whichever instance took the run over.
    """
    await connection.execute(_RELEASE_SQL, run_id, worker)


__all__ = ["LEASE_SECONDS", "claim", "release"]
