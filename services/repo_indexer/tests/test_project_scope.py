"""Tenancy: a project sees only the subtree it imported.

`repo-indexer.md` §3.1 — two projects can import one repository at different
`workspaces.workspace_path` prefixes. Leaking across that boundary puts another
team's file in front of a reviewer, so a failure here is a security bug and not
a display defect.
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

API_FILE = "packages/api/src/gen.ts"
WEB_FILE = "packages/web/src/gen.ts"
ROOT_FILE = "scripts/seed.ts"


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


async def make_project(conn, name: str) -> UUID:
    owner_id = await conn.fetchval(
        "INSERT INTO users (email, display_name) VALUES ($1, $2) RETURNING id",
        f"{uuid4().hex}@store.test",
        "Store Test",
    )
    return await conn.fetchval(
        "INSERT INTO projects (owner_id, name) VALUES ($1, $2) RETURNING id", owner_id, name
    )


async def import_repo(conn, project_id: UUID, full_name: str, *, branch: str = "main") -> UUID:
    return await conn.fetchval(
        """
        INSERT INTO project_repositories (project_id, name, full_name, default_branch)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        project_id,
        full_name.split("/")[-1],
        full_name,
        branch,
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


def record(path: str) -> ApiUsageRecord:
    return ApiUsageRecord(
        provider="google",
        identifier=WATCHED,
        file_path=path,
        line_start=7,
        usage_kind=UsageKind.RUNTIME_SOURCE,
        confidence=1.0,
        excerpt=f'const MODEL = "{WATCHED}";',
    )


def inventory(repository: str, *paths: str) -> ApiUsageInventory:
    return ApiUsageInventory(
        repository=repository,
        branch="main",
        observed_sha=SHA_A,
        provider="google",
        watched_identifiers=IMAGEN_4_IDENTIFIERS,
        scope=SCOPE_FULL_TREE,
        files_scanned=len(paths),
        usages=tuple(record(path) for path in paths),
    )


async def scoped_repo(conn, name: str, full_name: str, path: str | None) -> UUID:
    """Import `full_name` into a fresh project, optionally scoped to `path`."""
    project_id = await make_project(conn, name)
    repository_id = await import_repo(conn, project_id, full_name)
    await import_workspace(conn, project_id, repository_id, full_name, path=path)
    return project_id


def paths_seen(usages: list[store.ProjectUsage]) -> set[str]:
    return {usage.record.file_path for usage in usages}


async def test_a_workspace_path_hides_the_rest_of_the_repository(conn):
    shared = repo_name()
    api_project = await scoped_repo(conn, "api team", shared, "packages/api")
    web_project = await scoped_repo(conn, "web team", shared, "packages/web")
    await store.persist_inventory(conn, inventory(shared, API_FILE, WEB_FILE, ROOT_FILE))

    api_usages = await store.usages_for_project(conn, api_project, [WATCHED])
    web_usages = await store.usages_for_project(conn, web_project, [WATCHED])

    assert paths_seen(api_usages) == {API_FILE}
    assert paths_seen(web_usages) == {WEB_FILE}


async def test_a_null_workspace_path_sees_the_whole_repository(conn):
    shared = repo_name()
    whole = await scoped_repo(conn, "platform team", shared, None)
    await store.persist_inventory(conn, inventory(shared, API_FILE, WEB_FILE, ROOT_FILE))

    assert paths_seen(await store.usages_for_project(conn, whole, [WATCHED])) == {
        API_FILE,
        WEB_FILE,
        ROOT_FILE,
    }


async def test_a_repository_imported_without_a_workspace_sees_the_whole_repository(conn):
    repository = repo_name()
    project_id = await make_project(conn, "no workspace")
    await import_repo(conn, project_id, repository)
    await store.persist_inventory(conn, inventory(repository, API_FILE, ROOT_FILE))

    assert paths_seen(await store.usages_for_project(conn, project_id, [WATCHED])) == {
        API_FILE,
        ROOT_FILE,
    }


async def test_a_prefix_does_not_match_a_sibling_that_merely_starts_with_it(conn):
    shared = repo_name()
    api_project = await scoped_repo(conn, "api team", shared, "packages/api")
    await store.persist_inventory(conn, inventory(shared, "packages/api-internal/src/gen.ts"))

    # `packages/api-internal` is a different package, not a child of
    # `packages/api`. A prefix match without the separator would leak it.
    assert await store.usages_for_project(conn, api_project, [WATCHED]) == []


async def test_a_project_never_reads_another_projects_repository(conn):
    theirs = repo_name()
    ours = repo_name()
    their_project = await scoped_repo(conn, "them", theirs, None)
    our_project = await scoped_repo(conn, "us", ours, None)
    await store.persist_inventory(conn, inventory(theirs, ROOT_FILE))
    await store.persist_inventory(conn, inventory(ours, API_FILE))

    assert paths_seen(await store.usages_for_project(conn, our_project, [WATCHED])) == {API_FILE}
    assert paths_seen(await store.usages_for_project(conn, their_project, [WATCHED])) == {ROOT_FILE}


async def test_retired_findings_leave_the_project_view(conn):
    shared = repo_name()
    project_id = await scoped_repo(conn, "api team", shared, "packages/api")
    await store.persist_inventory(conn, inventory(shared, API_FILE))

    await store.retire_paths(conn, shared, "main", [API_FILE], "b" * 40)

    assert await store.usages_for_project(conn, project_id, [WATCHED]) == []


async def test_projects_for_reports_the_prefix_the_fan_out_must_apply(conn):
    shared = repo_name()
    api_project = await scoped_repo(conn, "api team", shared, "packages/api")
    web_project = await scoped_repo(conn, "web team", shared, "packages/web")

    scopes = await store.projects_for(conn, shared, "main")

    assert {scope.project_id: scope.path_prefix for scope in scopes} == {
        api_project: "packages/api",
        web_project: "packages/web",
    }
