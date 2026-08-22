"""Hand the repo index to an agent run.

`RunContext.index_usages` existed and `lookup_index_usages` read it, but nothing
in a real run ever filled it — the rows sat in `project_provider_usages` while
every agent saw an empty list. The index tools were a no-op, so an agent that
needed to know where a model is called had to fall back on scanning a checkout.

This is the join. The caller that owns a database connection loads the rows and
puts them on the context; `agents/` stays free of a Postgres dependency, which
is why the field is a list of plain dicts rather than a typed row.

Reading the index is navigation, not evidence. It says where an identifier was
seen at the last indexed SHA. A remediation still scans the sandbox, because
the tree an agent patches is the one that has to be correct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

if TYPE_CHECKING:
    import asyncpg

# A project with a large monorepo can hold tens of thousands of rows. The index
# is a lookup surface for an agent turn, not a bulk export, and an unbounded
# read would blow the context window it is meant to save.
MAX_ROWS: Final[int] = 2000

_COLUMNS: Final[str] = """
    repository, branch, provider, identifier, surface, file_path,
    line_start, line_end, usage_kind::text AS usage_kind,
    detection_layer::text AS detection_layer, confidence, excerpt, observed_sha
"""

_ALL_SQL: Final[str] = f"""
SELECT {_COLUMNS}
FROM project_provider_usages
WHERE project_id = $1 AND provider = $2
ORDER BY repository, file_path, line_start, identifier
LIMIT $3
"""

_FILTERED_SQL: Final[str] = f"""
SELECT {_COLUMNS}
FROM project_provider_usages
WHERE project_id = $1 AND provider = $2 AND identifier = ANY($3::text[])
ORDER BY repository, file_path, line_start, identifier
LIMIT $4
"""


async def load_index_usages(
    connection: asyncpg.Connection,
    project_id: UUID,
    *,
    provider: str = "google",
    identifiers: list[str] | None = None,
    limit: int = MAX_ROWS,
) -> list[dict[str, Any]]:
    """Inventory rows for one project, shaped for `RunContext.index_usages`.

    Pass `identifiers` to scope the read to a manifest's models. Omit it for
    the whole provider inventory, which is what a Change Intelligence turn
    wants: it is looking for which models this project uses at all.
    """
    if identifiers is not None:
        if not identifiers:
            return []
        rows = await connection.fetch(_FILTERED_SQL, project_id, provider, list(identifiers), limit)
    else:
        rows = await connection.fetch(_ALL_SQL, project_id, provider, limit)
    return [dict(row) for row in rows]


async def index_summary(
    connection: asyncpg.Connection, project_id: UUID, *, provider: str = "google"
) -> dict[str, Any]:
    """Row and repository counts, so a caller can say what it loaded."""
    row = await connection.fetchrow(
        """
        SELECT count(*) AS rows,
               count(DISTINCT repository) AS repositories,
               count(DISTINCT identifier) AS identifiers
        FROM project_provider_usages
        WHERE project_id = $1 AND provider = $2
        """,
        project_id,
        provider,
    )
    if row is None:
        return {"rows": 0, "repositories": 0, "identifiers": 0}
    return dict(row)


__all__ = ["MAX_ROWS", "index_summary", "load_index_usages"]
