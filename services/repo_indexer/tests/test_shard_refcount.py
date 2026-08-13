"""Shard reference counting: one project's cleanup must not blind another.

`repo-indexer.md` §3.1 — a shard is shared by every project that imported the
`(repository, branch)`, so removal decrements a counter and the shard is dropped
only at zero.
"""

from __future__ import annotations

import os
from uuid import uuid4

import asyncpg
import pytest
from patchapi_repo_indexer import store

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the store tests need Postgres with migration 0007 applied",
)

SHARD = "/var/zoekt/shard-1"


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


async def test_the_first_acquisition_creates_the_row(conn):
    repository = repo_name()

    assert await store.acquire_shard(conn, repository, "main", shard_path=SHARD) == 1

    state = await store.load_state(conn, repository, "main")
    assert state is not None
    assert (state.reference_count, state.shard_path) == (1, SHARD)


async def test_importing_into_a_second_project_only_bumps_the_counter(conn):
    repository = repo_name()
    await store.acquire_shard(conn, repository, "main", shard_path=SHARD)

    # The shard already exists, so the second import costs a counter bump and
    # no clone.
    assert await store.acquire_shard(conn, repository, "main") == 2

    state = await store.load_state(conn, repository, "main")
    assert state is not None
    assert state.shard_path == SHARD


async def test_branches_of_one_repository_are_counted_separately(conn):
    repository = repo_name()

    assert await store.acquire_shard(conn, repository, "main") == 1
    assert await store.acquire_shard(conn, repository, "release") == 1


async def test_releasing_one_of_two_projects_keeps_the_shard(conn):
    repository = repo_name()
    await store.acquire_shard(conn, repository, "main", shard_path=SHARD)
    await store.acquire_shard(conn, repository, "main")
    await store.set_index_progress(conn, repository, "main", status="ready", progress_percent=100)

    assert await store.release_shard(conn, repository, "main") == 1

    state = await store.load_state(conn, repository, "main")
    assert state is not None
    assert (state.reference_count, state.shard_path, state.status) == (1, SHARD, "ready")


async def test_releasing_the_last_reference_drops_the_shard(conn):
    repository = repo_name()
    await store.acquire_shard(conn, repository, "main", shard_path=SHARD)
    await store.acquire_shard(conn, repository, "main")
    await store.set_index_progress(conn, repository, "main", status="ready", progress_percent=100)

    await store.release_shard(conn, repository, "main")
    assert await store.release_shard(conn, repository, "main") == 0

    state = await store.load_state(conn, repository, "main")
    # The row survives: the findings it produced are still history, and
    # re-importing must not read as a repository nobody ever indexed.
    assert state is not None
    assert (state.reference_count, state.shard_path, state.status) == (0, None, "idle")
    assert state.progress_percent == 0


async def test_releasing_below_zero_is_clamped(conn):
    repository = repo_name()
    await store.acquire_shard(conn, repository, "main")

    await store.release_shard(conn, repository, "main")

    # Repository removal is replayed like every other at-least-once event.
    assert await store.release_shard(conn, repository, "main") == 0
    state = await store.load_state(conn, repository, "main")
    assert state is not None
    assert state.reference_count == 0


async def test_releasing_a_shard_nobody_holds_is_a_no_op(conn):
    assert await store.release_shard(conn, repo_name(), "main") == 0


async def test_re_acquiring_a_dropped_shard_restores_it(conn):
    repository = repo_name()
    await store.acquire_shard(conn, repository, "main", shard_path=SHARD)
    await store.release_shard(conn, repository, "main")

    assert await store.acquire_shard(conn, repository, "main", shard_path=SHARD) == 1

    state = await store.load_state(conn, repository, "main")
    assert state is not None
    assert state.shard_path == SHARD
