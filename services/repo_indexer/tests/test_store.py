"""Inventory persistence: upsert idempotency and retirement instead of deletion.

Every test runs inside a transaction that is rolled back, so the suite can point
at the same Cloud SQL instance the console uses without leaving rows behind.
"""

from __future__ import annotations

import os
from dataclasses import replace
from uuid import uuid4

import asyncpg
import pytest
from patchapi_repo_indexer import store
from patchapi_repo_indexer.config import IMAGEN_4_IDENTIFIERS, SCOPE_CHANGED_PATHS, SCOPE_FULL_TREE
from patchapi_repo_indexer.models import ApiUsageInventory, ApiUsageRecord

from packages.repo_scan.classify import UsageKind

DSN = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the store tests need Postgres with migration 0007 applied",
)

SHA_A = "a" * 40
SHA_B = "b" * 40


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


def usage(path: str, line: int, identifier: str = IMAGEN_4_IDENTIFIERS[0]) -> ApiUsageRecord:
    return ApiUsageRecord(
        provider="google",
        identifier=identifier,
        file_path=path,
        line_start=line,
        usage_kind=UsageKind.RUNTIME_SOURCE,
        confidence=1.0,
        excerpt=f'const MODEL = "{identifier}";',
    )


def inventory(
    repository: str,
    *usages: ApiUsageRecord,
    sha: str = SHA_A,
    branch: str = "main",
    scope: str = SCOPE_FULL_TREE,
) -> ApiUsageInventory:
    return ApiUsageInventory(
        repository=repository,
        branch=branch,
        observed_sha=sha,
        provider="google",
        watched_identifiers=IMAGEN_4_IDENTIFIERS,
        scope=scope,
        files_scanned=4,
        usages=usages,
    )


async def live_rows(conn, repository: str) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM provider_usages WHERE repository = $1 AND retired_at IS NULL",
        repository,
    )


async def all_rows(conn, repository: str) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM provider_usages WHERE repository = $1", repository
    )


async def test_persist_writes_one_row_per_finding(conn):
    repository = repo_name()

    result = await store.persist_inventory(
        conn, inventory(repository, usage("src/gen.ts", 12), usage("src/gen.ts", 40))
    )

    assert result == store.PersistResult(inserted=2, updated=0)
    assert await all_rows(conn, repository) == 2


async def test_replay_of_the_same_push_changes_no_row_count(conn):
    repository = repo_name()
    document = inventory(repository, usage("src/gen.ts", 12), usage("src/gen.ts", 40))

    first = await store.persist_inventory(conn, document)
    second = await store.persist_inventory(conn, document)

    assert first == store.PersistResult(inserted=2, updated=0)
    assert second == store.PersistResult(inserted=0, updated=2)
    assert await all_rows(conn, repository) == 2


async def test_replay_bumps_last_seen_without_moving_first_seen(conn):
    repository = repo_name()
    document = inventory(repository, usage("src/gen.ts", 12))
    await store.persist_inventory(conn, document)
    before = await conn.fetchrow(
        "SELECT first_seen_at, last_seen_at FROM provider_usages WHERE repository = $1", repository
    )

    await store.persist_inventory(conn, document)

    after = await conn.fetchrow(
        "SELECT first_seen_at, last_seen_at FROM provider_usages WHERE repository = $1", repository
    )
    assert after["first_seen_at"] == before["first_seen_at"]
    assert after["last_seen_at"] > before["last_seen_at"]


async def test_records_colliding_on_the_unique_key_collapse_to_one_row(conn):
    repository = repo_name()

    result = await store.persist_inventory(
        conn, inventory(repository, usage("src/gen.ts", 12), usage("src/gen.ts", 12))
    )

    assert result.total == 1
    assert await all_rows(conn, repository) == 1


async def test_empty_inventory_writes_nothing(conn):
    repository = repo_name()

    result = await store.persist_inventory(conn, inventory(repository))

    assert result == store.PersistResult(inserted=0, updated=0)
    assert await all_rows(conn, repository) == 0


async def test_deleted_path_is_retired_rather_than_deleted(conn):
    repository = repo_name()
    await store.persist_inventory(
        conn, inventory(repository, usage("src/gen.ts", 12), usage("src/keep.ts", 3))
    )

    # The push deleted src/gen.ts, so the delta inventory carries only the file
    # that survived it.
    await store.persist_inventory(
        conn,
        inventory(repository, usage("src/keep.ts", 3), sha=SHA_B, scope=SCOPE_CHANGED_PATHS),
    )
    retired = await store.retire_paths(conn, repository, "main", ["src/gen.ts"], SHA_B)

    assert retired == 1
    assert await all_rows(conn, repository) == 2
    assert await live_rows(conn, repository) == 1
    assert (
        await conn.fetchval(
            "SELECT retired_at IS NOT NULL FROM provider_usages"
            " WHERE repository = $1 AND file_path = 'src/gen.ts'",
            repository,
        )
        is True
    )


async def test_retire_spares_findings_re_observed_at_the_same_sha(conn):
    repository = repo_name()
    await store.persist_inventory(conn, inventory(repository, usage("src/gen.ts", 12)))
    # The push edited src/gen.ts but the identifier is still on line 12, so the
    # delta pass re-stamped the row at the head SHA before retirement runs.
    await store.persist_inventory(
        conn,
        inventory(repository, usage("src/gen.ts", 12), sha=SHA_B, scope=SCOPE_CHANGED_PATHS),
    )

    retired = await store.retire_paths(conn, repository, "main", ["src/gen.ts"], SHA_B)

    assert retired == 0
    assert await live_rows(conn, repository) == 1


async def test_retire_ignores_other_branches(conn):
    repository = repo_name()
    await store.persist_inventory(conn, inventory(repository, usage("src/gen.ts", 12)))
    await store.persist_inventory(
        conn, inventory(repository, usage("src/gen.ts", 12), branch="release")
    )

    retired = await store.retire_paths(conn, repository, "main", ["src/gen.ts"], SHA_B)

    assert retired == 1
    assert await live_rows(conn, repository) == 1


async def test_retire_with_no_paths_is_a_no_op(conn):
    repository = repo_name()
    await store.persist_inventory(conn, inventory(repository, usage("src/gen.ts", 12)))

    assert await store.retire_paths(conn, repository, "main", [], SHA_B) == 0
    assert await live_rows(conn, repository) == 1


async def test_reappearing_finding_is_revived(conn):
    repository = repo_name()
    await store.persist_inventory(conn, inventory(repository, usage("src/gen.ts", 12)))
    await store.retire_paths(conn, repository, "main", ["src/gen.ts"], SHA_B)
    assert await live_rows(conn, repository) == 0

    # The revert put the identifier back. A row left retired would hide a real
    # usage from every project that imported the repository.
    result = await store.persist_inventory(
        conn, inventory(repository, usage("src/gen.ts", 12), sha=SHA_B)
    )

    assert result == store.PersistResult(inserted=0, updated=1)
    assert await live_rows(conn, repository) == 1


async def test_load_state_is_none_before_the_first_index(conn):
    assert await store.load_state(conn, repo_name(), "main") is None


async def test_record_state_round_trips(conn):
    repository = repo_name()
    written = store.RepoIndexState(
        repository=repository,
        branch="main",
        status="ready",
        progress_percent=100,
        indexed_sha=SHA_A,
        shard_path="/var/zoekt/shard-1",
        indexer_version="1.1.0",
        scanner_version="0.1.0",
        last_full_index=None,
        last_delta_index=None,
        file_count=484,
        reference_count=1,
        error_message=None,
    )

    await store.record_state(conn, written)

    assert await store.load_state(conn, repository, "main") == written


async def test_record_state_leaves_the_reference_count_alone(conn):
    repository = repo_name()
    await store.acquire_shard(conn, repository, "main")
    await store.acquire_shard(conn, repository, "main")
    state = await store.load_state(conn, repository, "main")
    assert state is not None

    # A worker that read the state before a second project imported the
    # repository must not write its stale count back over the acquisition.
    await store.record_state(conn, replace(state, reference_count=1))

    refreshed = await store.load_state(conn, repository, "main")
    assert refreshed is not None
    assert refreshed.reference_count == 2


async def test_record_state_rejects_an_unknown_status(conn):
    state = store.RepoIndexState(
        repository=repo_name(),
        branch="main",
        status="finished",  # type: ignore[arg-type]  # the point of the test
        progress_percent=100,
        indexed_sha=None,
        shard_path=None,
        indexer_version="1.1.0",
        scanner_version="0.1.0",
        last_full_index=None,
        last_delta_index=None,
        file_count=0,
        reference_count=0,
        error_message=None,
    )

    with pytest.raises(ValueError, match="unknown index status"):
        await store.record_state(conn, state)
