"""The indexing banner one project shows, read from `repo_index_state`.

`repo-indexer.md` §7.6 and `schema.md` §13: the Codebase tab reads this on the
console SSE stream (and polls it only if that stream drops). The SQL is one
round trip — ownership and rollup on a single connection — and it answers with
the four-value status the banner branches on.

The SQL is duplicated from `patchapi_repo_indexer.store.indexing_for_project`
rather than imported. The control plane's image
(`services/control_api/Dockerfile`) ships schemas, auth, state, and the API and
nothing else; importing a service package from `packages/` would also invert the
workspace's dependency direction, and would put the indexer's Pydantic models and
its scanner configuration in the request path of a read that returns four columns.
`packages/state/tests/test_indexing_route.py` asserts this rollup agrees with the
indexer's for every combination, so the duplication cannot drift silently.

A project that imported nothing, or whose repositories have never been indexed,
reads `idle` at 0%. That is neither an error nor readiness, and the banner stays
hidden for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from packages.state.pool import StateUnavailableError

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    from collections.abc import Sequence

    import asyncpg

IndexStatus = Literal["idle", "indexing", "ready", "error"]

MAX_PROGRESS: Final[int] = 100

# Postgres `undefined_table`. The indexer's migration (0007) may not have been
# applied yet in an environment where the console is already serving; that is a
# missing dependency, not an empty result.
_UNDEFINED_TABLE: Final[str] = "42P01"

# Every `(repository, branch)` the project imported: each repository's default
# branch, plus every branch one of its workspaces pinned. Both are indexable
# targets, so both belong in the rollup the banner averages over.
_TARGETS_SQL: Final[str] = """
SELECT pr.full_name AS repository, pr.default_branch AS branch
FROM project_repositories pr
WHERE pr.project_id = $1::uuid
UNION
SELECT pr.full_name AS repository, w.repo_branch AS branch
FROM workspaces w
JOIN project_repositories pr ON pr.id = w.repository_id
WHERE pr.project_id = $1::uuid
"""

_INDEXING_SQL: Final[str] = f"""
SELECT t.repository,
       t.branch,
       COALESCE(s.status::text, 'idle') AS status,
       COALESCE(s.progress_percent, 0) AS progress_percent
FROM ({_TARGETS_SQL}) t
LEFT JOIN repo_index_state s
       ON s.repository = t.repository AND s.branch = t.branch
ORDER BY t.repository, t.branch
"""


def rollup(repositories: Sequence[dict[str, Any]]) -> tuple[IndexStatus, int]:
    """Reduce per-repository state to the single banner a project shows.

    `repo-indexer.md` §7.6: anything still indexing wins, an error shows only
    once nothing is running, and the bar is the average over the targets that
    are actually indexing — two repositories at 20% and 80% read 50%.
    """
    if not repositories:
        return "idle", 0
    indexing = [
        int(repo["progress_percent"]) for repo in repositories if repo["status"] == "indexing"
    ]
    if indexing:
        # Half-up, so a project is never shown less progress than its average.
        return "indexing", int(sum(indexing) / len(indexing) + 0.5)
    if any(repo["status"] == "error" for repo in repositories):
        return "error", 0
    if all(repo["status"] == "ready" for repo in repositories):
        return "ready", MAX_PROGRESS
    return "idle", 0


def _payload(rows: Sequence[Any]) -> dict[str, Any]:
    repositories = [
        {
            "full_name": row["repository"],
            "branch": row["branch"],
            "status": row["status"],
            "progress_percent": int(row["progress_percent"]),
        }
        for row in rows
    ]
    status, progress_percent = rollup(repositories)
    return {
        "status": status,
        "progress_percent": progress_percent,
        "repositories": repositories,
    }


async def indexing_for_project(
    pool: asyncpg.Pool, project_id: UUID, owner_id: UUID
) -> dict[str, Any] | None:
    """Return the indexing payload for a project the user owns, or `None`.

    `None` covers both "no such project" and "not yours": the console must not
    let a caller distinguish the two, because the difference is itself a fact
    about another tenant's data.
    """
    try:
        async with pool.acquire() as connection:
            owned = await connection.fetchval(
                "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
                project_id,
                owner_id,
            )
            if owned is None:
                return None
            rows = await connection.fetch(_INDEXING_SQL, project_id)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == _UNDEFINED_TABLE:
            raise StateUnavailableError(
                "repo_index_state is missing; migration 0007_provider_usages.sql "
                "has not been applied to this database"
            ) from exc
        raise StateUnavailableError(
            f"could not read indexing status: {type(exc).__name__}"
        ) from exc

    return _payload(rows)


async def indexing_snapshot(pool: asyncpg.Pool, project_id: UUID) -> dict[str, Any]:
    """Indexing payload for an already-authorized project (SSE fan-out).

    Tenancy was checked when the EventSource subscribed. A missing project
    reads as idle rather than as an error: the tab hides the banner either way.
    """
    try:
        async with pool.acquire() as connection:
            rows = await connection.fetch(_INDEXING_SQL, project_id)
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == _UNDEFINED_TABLE:
            raise StateUnavailableError(
                "repo_index_state is missing; migration 0007_provider_usages.sql "
                "has not been applied to this database"
            ) from exc
        raise StateUnavailableError(
            f"could not read indexing status: {type(exc).__name__}"
        ) from exc
    return _payload(rows)


__all__ = [
    "MAX_PROGRESS",
    "IndexStatus",
    "indexing_for_project",
    "indexing_snapshot",
    "rollup",
]
