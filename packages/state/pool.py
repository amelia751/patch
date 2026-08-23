"""Connection pool lifecycle for the read model.

The pool is created once per process and closed on shutdown. Codecs are
registered at connection setup rather than at each call site, so a `jsonb`
column arrives as a Python object and a `numeric` confidence arrives as a float
everywhere, instead of as a string that one caller remembers to parse and
another does not.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from packages.state.config import (
    COMMAND_TIMEOUT_SECONDS,
    MAX_POOL_SIZE,
    MIN_POOL_SIZE,
    database_url,
)

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    import asyncpg


class StateUnavailableError(RuntimeError):
    """The authoritative store could not be reached or answered.

    Raised instead of returning an empty result. A caller that cannot reach
    Postgres knows nothing about the workflow, and must not report that as a
    run having no transitions or an organization having no affected
    repositories.
    """


async def configure_connection(connection: Any) -> None:
    """Register the codecs every query in this package assumes.

    Public because the pool is not the only way in. A batch job that opens a
    single `asyncpg.connect` runs the same SQL, and a `jsonb` argument passed to
    an unconfigured connection fails with "expected str, got list" — at the
    moment the job writes, having already done the work.
    """
    await connection.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await connection.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    # `confidence` is numeric(3,2). Decimal would serialize to a JSON string and
    # make a numeric column read as text in the dashboard.
    await connection.set_type_codec(
        "numeric", encoder=str, decoder=float, schema="pg_catalog", format="text"
    )


async def create_pool(dsn: str | None = None) -> asyncpg.Pool:
    """Open the connection pool. Raises if the database cannot be reached."""
    import asyncpg

    target = dsn if dsn is not None else database_url()
    try:
        pool = await asyncpg.create_pool(
            target,
            min_size=MIN_POOL_SIZE,
            max_size=MAX_POOL_SIZE,
            command_timeout=COMMAND_TIMEOUT_SECONDS,
            init=configure_connection,
        )
    except OSError as exc:
        # The DSN may carry a password, so the message names the failure, never
        # the target.
        raise StateUnavailableError(f"could not connect to Postgres: {type(exc).__name__}") from exc
    if pool is None:  # pragma: no cover - asyncpg returns None only on misuse
        raise StateUnavailableError("asyncpg returned no pool")
    return pool


async def ping(pool: asyncpg.Pool) -> None:
    """Raise `StateUnavailableError` unless the database answers a trivial query."""
    try:
        await pool.fetchval("SELECT 1")
    except Exception as exc:
        raise StateUnavailableError(f"Postgres did not answer: {type(exc).__name__}") from exc
