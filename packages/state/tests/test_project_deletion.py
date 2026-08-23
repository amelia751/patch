"""Deleting a project has to tell the indexer, not just the cascade.

Every table keyed by `project_id` goes with the row. `repo_index_state` is not
one of them: it is keyed by repository and shared with whoever else imported it,
so it is freed by reference count. Nothing decrements that count except a
`project-repo-removed` event, which means a delete that stays silent leaks the
shard and leaves the inventory attributed to nobody.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest

from packages.state import projects
from packages.state.pool import configure_connection

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the deletion tests need Postgres",
)


class OnePool:
    """A pool over a single transaction, so the test can roll everything back."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def acquire(self) -> Any:
        connection = self._connection

        class _Ctx:
            async def __aenter__(self) -> Any:
                return connection

            async def __aexit__(self, *_exc: Any) -> None:
                return None

        return _Ctx()


@pytest.fixture
async def conn() -> Any:
    connection = await asyncpg.connect(DSN)
    await configure_connection(connection)
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


async def seed(conn: Any, *, repositories: list[str]) -> tuple[UUID, UUID]:
    owner = await conn.fetchval(
        "INSERT INTO users (email, display_name) VALUES ($1, 'Delete Test') RETURNING id",
        f"delete-{uuid4().hex}@example.test",
    )
    project = await conn.fetchval(
        "INSERT INTO projects (owner_id, name) VALUES ($1, $2) RETURNING id",
        owner,
        f"delete-{uuid4().hex[:8]}",
    )
    for full_name in repositories:
        await conn.execute(
            "INSERT INTO project_repositories (project_id, name, full_name, default_branch) "
            "VALUES ($1, $2, $3, 'main')",
            project,
            full_name.split("/")[-1],
            full_name,
        )
    return UUID(str(owner)), UUID(str(project))


async def test_every_imported_repository_is_announced(
    conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, project = await seed(
        conn, repositories=["patchapi-test/one", "patchapi-test/two"]
    )
    announced: list[tuple[str, str]] = []

    async def record(project_id: UUID, repository: str, branch: str) -> bool:
        announced.append((repository, branch))
        return True

    monkeypatch.setattr(projects, "announce_repository_removed", record)

    assert await projects.delete_project(OnePool(conn), project, owner) is True
    assert sorted(announced) == [
        ("patchapi-test/one", "main"),
        ("patchapi-test/two", "main"),
    ]


async def test_a_project_that_is_not_yours_is_neither_deleted_nor_announced(
    conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _owner, project = await seed(conn, repositories=["patchapi-test/one"])
    announced: list[str] = []

    async def record(project_id: UUID, repository: str, branch: str) -> bool:
        announced.append(repository)
        return True

    monkeypatch.setattr(projects, "announce_repository_removed", record)

    assert await projects.delete_project(OnePool(conn), project, uuid4()) is False
    assert announced == []
    assert await conn.fetchval("SELECT count(*) FROM projects WHERE id = $1", project) == 1


async def test_the_announcement_happens_after_the_row_is_gone(
    conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository the indexer is told to release must actually be released."""
    owner, project = await seed(conn, repositories=["patchapi-test/one"])
    still_there: list[int] = []

    async def record(project_id: UUID, repository: str, branch: str) -> bool:
        still_there.append(
            await conn.fetchval("SELECT count(*) FROM projects WHERE id = $1", project)
        )
        return True

    monkeypatch.setattr(projects, "announce_repository_removed", record)

    await projects.delete_project(OnePool(conn), project, owner)
    assert still_there == [0]


async def test_a_project_with_no_repositories_announces_nothing(
    conn: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, project = await seed(conn, repositories=[])
    announced: list[str] = []

    async def record(project_id: UUID, repository: str, branch: str) -> bool:
        announced.append(repository)
        return True

    monkeypatch.setattr(projects, "announce_repository_removed", record)

    assert await projects.delete_project(OnePool(conn), project, owner) is True
    assert announced == []
