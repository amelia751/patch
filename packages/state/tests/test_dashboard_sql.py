"""Every dashboard query, executed against the schema that actually exists.

The run projections were written against a `repositories` table that was
specified in `schema.md` and never migrated, and against `provider_usages`
columns that were renamed before the table shipped. Nothing caught it, because
the only tests of these reads used fakes: a recorder agrees with any SQL, valid
or not, and the failure surfaced as a 503 on a page.

So this asserts the one property a fake cannot — that Postgres accepts the
query. Results are irrelevant; an empty database is a perfectly good answer.
"""

from __future__ import annotations

import os
from typing import Any, Final

import asyncpg
import pytest

from packages.state import dashboard, runs
from packages.state.pool import configure_connection

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN, reason="DATABASE_URL is unset; the dashboard SQL tests need Postgres"
)

ABSENT: Final[str] = "00000000-0000-0000-0000-000000000000"

# Name, query, arguments. A uuid that matches nothing exercises the joins and
# the casts without needing a fixture.
QUERIES: Final[tuple[tuple[str, str, tuple[Any, ...]], ...]] = (
    ("list_changes", dashboard._LIST_CHANGES, (5,)),
    ("read_change", dashboard._READ_CHANGE, ("no-such-change",)),
    ("change_for_run", dashboard._CHANGE_FOR_RUN, (ABSENT,)),
    ("list_repositories", dashboard._LIST_REPOSITORIES, (None,)),
    ("list_repositories_scoped", dashboard._LIST_REPOSITORIES, (["gemini-2.0-flash"],)),
    ("list_usages", dashboard._LIST_USAGES, (None,)),
    ("latest_run_per_repository", dashboard._LATEST_RUN_PER_REPOSITORY, (None,)),
    ("list_runs", dashboard._LIST_RUNS, (None, None, 5)),
    ("list_runs_filtered", dashboard._LIST_RUNS, ("chg", "owner/repo", 5)),
    ("read_run_summary", dashboard._READ_RUN_SUMMARY, (ABSENT,)),
    ("read_transitions", dashboard._READ_TRANSITIONS, (ABSENT,)),
    ("read_policy", dashboard._READ_POLICY, (ABSENT,)),
    ("read_attempts", dashboard._READ_ATTEMPTS, (ABSENT,)),
    ("read_verification", dashboard._READ_VERIFICATION, (ABSENT,)),
    ("read_artifacts", dashboard._READ_ARTIFACTS, (ABSENT,)),
    ("read_pull_request", dashboard._READ_PULL_REQUEST, (ABSENT,)),
    ("read_run_usages", dashboard._READ_RUN_USAGES, (ABSENT,)),
    ("fleet_actors", dashboard._FLEET_ACTORS, ()),
    ("fleet_models", dashboard._FLEET_MODELS, ()),
    ("fleet_denials", dashboard._FLEET_DENIALS, (5,)),
    ("policy_versions", dashboard._POLICY_VERSIONS, ()),
    ("read_run", runs._READ_RUN, (ABSENT,)),
)


@pytest.fixture
async def conn() -> Any:
    connection = await asyncpg.connect(DSN)
    await configure_connection(connection)
    try:
        yield connection
    finally:
        await connection.close()


@pytest.mark.parametrize("name,query,args", QUERIES, ids=[case[0] for case in QUERIES])
async def test_the_query_runs(conn: Any, name: str, query: str, args: tuple[Any, ...]) -> None:
    await conn.fetch(query, *args)
