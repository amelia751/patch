"""A project holds many repositories, and a repository belongs to many projects.

`repo-indexer.md` §3.1: the indexing unit is `(repository, branch)`, never the
project. These tests pin the two ways that can go quietly wrong — one repository
producing two sets of findings, and one repository being indexed twice.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import asyncpg
import pytest
from patchapi_repo_indexer import store
from patchapi_repo_indexer.config import IMAGEN_4_IDENTIFIERS, SCOPE_FULL_TREE
from patchapi_repo_indexer.models import ApiUsageInventory, ApiUsageRecord

from packages.repo_scan.classify import UsageKind

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the store tests need Postgres with migration 0007 applied",
)

SHA_A = "a" * 40
WATCHED = IMAGEN_4_IDENTIFIERS[0]


@pytest.fixture
async def conn():
    connection = await asyncpg.connect(DSN)
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


def repo_name() -> str:
    return f"patchapi-test/{uuid4().hex}"


async def make_project(conn, name: str = "multi repo") -> UUID:
    owner_id = await conn.fetchval(
        "INSERT INTO users (email, display_name) VALUES ($1, $2) RETURNING id",
        f"{uuid4().hex}@store.test",
        "Store Test",
    )
    return await conn.fetchval(
        "INSERT INTO projects (owner_id, name) VALUES ($1, $2) RETURNING id", owner_id, name
    )


async def import_repo(
    conn, project_id: UUID, full_name: str, *, branch: str = "main", kind: str = "backend"
) -> UUID:
    return await conn.fetchval(
        """
        INSERT INTO project_repositories (project_id, name, full_name, default_branch, kind)
        VALUES ($1, $2, $3, $4, $5::repository_kind)
        RETURNING id
        """,
        project_id,
        full_name.split("/")[-1],
        full_name,
        branch,
        kind,
    )


async def import_workspace(
    conn,
    project_id: UUID,
    repository_id: UUID,
    full_name: str,
    *,
    branch: str = "main",
    path: str | None = None,
) -> UUID:
    return await conn.fetchval(
        """
        INSERT INTO workspaces (project_id, repository_id, name, repo_url, repo_branch,
                                workspace_path)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        project_id,
        repository_id,
        full_name.split("/")[-1],
        f"https://github.com/{full_name}",
        branch,
        path,
    )


def inventory(repository: str, path: str, line: int, *, branch: str = "main") -> ApiUsageInventory:
    return ApiUsageInventory(
        repository=repository,
        branch=branch,
        observed_sha=SHA_A,
        provider="google",
        watched_identifiers=IMAGEN_4_IDENTIFIERS,
        scope=SCOPE_FULL_TREE,
        files_scanned=1,
        usages=(
            ApiUsageRecord(
                provider="google",
                identifier=WATCHED,
                file_path=path,
                line_start=line,
                usage_kind=UsageKind.RUNTIME_SOURCE,
                confidence=1.0,
                excerpt=f'const MODEL = "{WATCHED}";',
            ),
        ),
    )


async def test_two_repositories_in_one_project_both_surface(conn):
    project_id = await make_project(conn)
    backend, frontend = repo_name(), repo_name()
    await import_repo(conn, project_id, backend, kind="backend")
    await import_repo(conn, project_id, frontend, kind="frontend")
    await store.persist_inventory(conn, inventory(backend, "server/gen.ts", 9))
    await store.persist_inventory(conn, inventory(frontend, "app/gen.ts", 4))

    usages = await store.usages_for_project(conn, project_id, [WATCHED])

    assert {usage.repository for usage in usages} == {backend, frontend}
    # `kind` selects the verification plan, so it has to survive the read: a
    # frontend and a backend repository do not share build or test commands.
    assert {usage.repository: usage.kind for usage in usages} == {
        backend: "backend",
        frontend: "frontend",
    }


async def test_a_repository_in_two_projects_is_one_set_of_rows(conn):
    shared = repo_name()
    project_a = await make_project(conn, "project a")
    project_b = await make_project(conn, "project b")
    await import_repo(conn, project_a, shared)
    await import_repo(conn, project_b, shared)

    await store.persist_inventory(conn, inventory(shared, "src/gen.ts", 12))

    assert (
        await conn.fetchval("SELECT count(*) FROM provider_usages WHERE repository = $1", shared)
        == 1
    )
    # One row, two readers. Both projects see the finding; neither owns it.
    for project_id in (project_a, project_b):
        usages = await store.usages_for_project(conn, project_id, [WATCHED])
        assert [usage.record.file_path for usage in usages] == ["src/gen.ts"]


async def test_indexable_targets_deduplicates_a_shared_repository(conn):
    shared = repo_name()
    project_a = await make_project(conn, "project a")
    project_b = await make_project(conn, "project b")
    repo_a = await import_repo(conn, project_a, shared)
    await import_repo(conn, project_b, shared)
    # A workspace pinned to the same branch is the same indexing target.
    await import_workspace(conn, project_a, repo_a, shared, branch="main", path="packages/api")

    targets = await store.indexable_targets(conn)

    assert [target for target in targets if target.repository == shared] == [
        store.IndexTarget(repository=shared, branch="main")
    ]


async def test_indexable_targets_includes_every_imported_branch(conn):
    repository = repo_name()
    project_id = await make_project(conn)
    repo_id = await import_repo(conn, project_id, repository, branch="main")
    await import_workspace(conn, project_id, repo_id, repository, branch="release")

    targets = await store.indexable_targets(conn)

    assert [target.branch for target in targets if target.repository == repository] == [
        "main",
        "release",
    ]


async def test_projects_for_fans_a_push_out_to_every_importer(conn):
    shared = repo_name()
    project_a = await make_project(conn, "project a")
    project_b = await make_project(conn, "project b")
    await import_repo(conn, project_a, shared, kind="backend")
    await import_repo(conn, project_b, shared, kind="frontend")

    scopes = await store.projects_for(conn, shared, "main")

    assert {scope.project_id for scope in scopes} == {project_a, project_b}
    assert {scope.kind for scope in scopes} == {"backend", "frontend"}
    assert all(scope.path_prefix is None for scope in scopes)


async def test_a_push_to_an_unimported_branch_reaches_no_project(conn):
    repository = repo_name()
    project_id = await make_project(conn)
    await import_repo(conn, project_id, repository, branch="main")

    assert await store.projects_for(conn, repository, "dependabot/npm/left-pad") == []


async def test_findings_on_an_unimported_branch_are_invisible(conn):
    repository = repo_name()
    project_id = await make_project(conn)
    await import_repo(conn, project_id, repository, branch="main")

    await store.persist_inventory(conn, inventory(repository, "src/gen.ts", 12, branch="wip"))

    assert await store.usages_for_project(conn, project_id, [WATCHED]) == []


async def test_an_unwatched_identifier_returns_nothing(conn):
    repository = repo_name()
    project_id = await make_project(conn)
    await import_repo(conn, project_id, repository)
    await store.persist_inventory(conn, inventory(repository, "src/gen.ts", 12))

    assert await store.usages_for_project(conn, project_id, ["gemini-3.1-flash-image"]) == []
    # An empty watchlist is not "every finding": widening it would leak the
    # whole inventory into a run that watches nothing.
    assert await store.usages_for_project(conn, project_id, []) == []
