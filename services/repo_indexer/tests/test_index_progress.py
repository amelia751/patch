"""The Codebase tab banner: per-repository progress rolled up to one project.

`repo-indexer.md` §7.6 / `schema.md` §13. The banner shows while any imported
target is indexing, and its bar is the average over the targets that are
actually running — a project with one repository at 20% and one at 80% reads 50.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import asyncpg
import pytest
from patchapi_repo_indexer import store

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the store tests need Postgres with migration 0007 applied",
)


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


async def make_project(conn, name: str = "banner") -> UUID:
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


async def project_with_two_repos(conn) -> tuple[UUID, str, str]:
    project_id = await make_project(conn)
    first, second = repo_name(), repo_name()
    await import_repo(conn, project_id, first)
    await import_repo(conn, project_id, second)
    return project_id, first, second


async def test_one_repository_indexing_shows_the_banner_at_the_average(conn):
    project_id, first, second = await project_with_two_repos(conn)

    await store.set_index_progress(conn, first, "main", status="indexing", progress_percent=20)
    await store.set_index_progress(conn, second, "main", status="indexing", progress_percent=80)

    status = await store.indexing_for_project(conn, project_id)
    assert status.status == "indexing"
    assert status.progress_percent == 50


async def test_the_average_covers_only_the_targets_still_indexing(conn):
    project_id, first, second = await project_with_two_repos(conn)

    await store.set_index_progress(conn, first, "main", status="ready", progress_percent=100)
    await store.set_index_progress(conn, second, "main", status="indexing", progress_percent=30)

    status = await store.indexing_for_project(conn, project_id)
    assert status.status == "indexing"
    assert status.progress_percent == 30


async def test_all_ready_hides_the_banner(conn):
    project_id, first, second = await project_with_two_repos(conn)

    await store.set_index_progress(conn, first, "main", status="ready", progress_percent=100)
    await store.set_index_progress(conn, second, "main", status="ready", progress_percent=100)

    status = await store.indexing_for_project(conn, project_id)
    assert status.status == "ready"
    assert status.progress_percent == 100


async def test_an_error_surfaces_only_once_nothing_is_still_indexing(conn):
    project_id, first, second = await project_with_two_repos(conn)
    await store.set_index_progress(
        conn, first, "main", status="error", progress_percent=0, error_message="clone denied"
    )
    await store.set_index_progress(conn, second, "main", status="indexing", progress_percent=60)

    assert (await store.indexing_for_project(conn, project_id)).status == "indexing"

    await store.set_index_progress(conn, second, "main", status="ready", progress_percent=100)

    assert (await store.indexing_for_project(conn, project_id)).status == "error"


async def test_an_imported_but_unindexed_target_reads_idle(conn):
    project_id, first, _ = await project_with_two_repos(conn)
    await store.set_index_progress(conn, first, "main", status="ready", progress_percent=100)

    status = await store.indexing_for_project(conn, project_id)

    # Imported and not yet indexed is neither an error nor readiness.
    assert status.status == "idle"
    assert status.progress_percent == 0
    assert {repo.status for repo in status.repositories} == {"ready", "idle"}


async def test_a_project_with_no_repositories_is_idle(conn):
    project_id = await make_project(conn, "empty")

    status = await store.indexing_for_project(conn, project_id)

    assert status == store.ProjectIndexingStatus(status="idle", progress_percent=0, repositories=())


async def test_progress_is_reported_per_repository_in_the_wire_shape(conn):
    project_id = await make_project(conn)
    repository = repo_name()
    await import_repo(conn, project_id, repository)
    await store.set_index_progress(conn, repository, "main", status="indexing", progress_percent=47)

    payload = (await store.indexing_for_project(conn, project_id)).as_dict()

    assert payload == {
        "status": "indexing",
        "progress_percent": 47,
        "repositories": [
            {
                "full_name": repository,
                "branch": "main",
                "status": "indexing",
                "progress_percent": 47,
            }
        ],
    }


async def test_set_index_progress_creates_then_updates_one_row(conn):
    repository = repo_name()

    await store.set_index_progress(conn, repository, "main", status="indexing", progress_percent=0)
    await store.set_index_progress(conn, repository, "main", status="indexing", progress_percent=64)

    state = await store.load_state(conn, repository, "main")
    assert state is not None
    assert (state.status, state.progress_percent) == ("indexing", 64)
    # A progress ping must never claim an index that has not finished.
    assert state.indexed_sha is None
    assert state.shard_path is None


async def test_set_index_progress_records_and_clears_the_error(conn):
    repository = repo_name()
    await store.set_index_progress(
        conn, repository, "main", status="error", progress_percent=0, error_message="clone denied"
    )
    first = await store.load_state(conn, repository, "main")
    assert first is not None and first.error_message == "clone denied"

    await store.set_index_progress(conn, repository, "main", status="indexing", progress_percent=5)

    retried = await store.load_state(conn, repository, "main")
    assert retried is not None
    assert retried.error_message is None


async def test_set_index_progress_rejects_values_the_banner_cannot_show(conn):
    repository = repo_name()

    with pytest.raises(ValueError, match="unknown index status"):
        await store.set_index_progress(
            conn,
            repository,
            "main",
            status="cloning",  # type: ignore[arg-type]  # the point of the test
            progress_percent=10,
        )
    with pytest.raises(ValueError, match="progress_percent"):
        await store.set_index_progress(
            conn, repository, "main", status="indexing", progress_percent=101
        )
