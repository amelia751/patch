"""The indexer's event handlers, exercised without git, an index, or a broker.

Every collaborator that touches the world is injected (`worker.Effects`) or
substituted for an in-memory double (`FakeStore`), so these tests assert the
state machine itself: what is dropped before any work happens, what is
persisted, what is retired, what is published, and what a failure records.

Nothing here needs Pub/Sub or Postgres. The store double records the calls the
handlers make and answers them the way `store.py` documents it answers them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from patchapi_repo_indexer import pubsub, store, worker
from patchapi_repo_indexer.config import IMAGEN_4_IDENTIFIERS, INDEXER_VERSION
from patchapi_repo_indexer.errors import ZoektUnavailableError
from patchapi_repo_indexer.git import RevisionNotFoundError
from patchapi_repo_indexer.models import ApiUsageInventory, ApiUsageRecord
from patchapi_repo_indexer.zoekt.query import ZoektMatch

from packages.events.config import EventType, TrustLevel
from packages.events.envelope import EventEnvelope
from packages.events.publisher import PublishResult
from packages.events.repo_events import (
    project_repo_added_event,
    project_repo_removed_event,
    repo_push_event,
)
from packages.repo_scan.classify import UsageKind

REPOSITORY = "patchapi-test/egaki"
BRANCH = "main"
BEFORE_SHA = "a" * 40
AFTER_SHA = "b" * 40
OCCURRED_AT = "2026-08-13T00:00:00+00:00"
NOW = datetime(2026, 8, 13, tzinfo=UTC)

IDENTIFIER = IMAGEN_4_IDENTIFIERS[0]


# --------------------------------------------------------------------------- #
# Doubles
# --------------------------------------------------------------------------- #


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeTransaction:
        self._connection.transactions += 1
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class FakeConnection:
    """Only the surface the handlers touch: an explicit transaction."""

    def __init__(self) -> None:
        self.transactions = 0

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)


@dataclass
class FakeStore:
    """An in-memory stand-in for `store.py`, recording what a handler asked for."""

    RepoIndexState = store.RepoIndexState

    scopes: dict[tuple[str, str], list[store.ProjectScope]] = field(default_factory=dict)
    states: dict[tuple[str, str], store.RepoIndexState] = field(default_factory=dict)
    targets: list[store.IndexTarget] = field(default_factory=list)
    project_usages: dict[UUID, list[store.ProjectUsage]] = field(default_factory=dict)

    progress: list[tuple[str, str, str, int, str | None]] = field(default_factory=list)
    persisted: list[ApiUsageInventory] = field(default_factory=list)
    retired: list[tuple[str, str, tuple[str, ...], str]] = field(default_factory=list)
    recorded: list[store.RepoIndexState] = field(default_factory=list)
    acquired: list[tuple[str, str]] = field(default_factory=list)
    released: list[tuple[str, str]] = field(default_factory=list)
    references: dict[tuple[str, str], int] = field(default_factory=dict)

    async def acquire_shard(
        self, conn: Any, repository: str, branch: str, *, shard_path: str | None = None
    ) -> int:
        self.acquired.append((repository, branch))
        key = (repository, branch)
        self.references[key] = self.references.get(key, 0) + 1
        return self.references[key]

    async def release_shard(self, conn: Any, repository: str, branch: str) -> int:
        self.released.append((repository, branch))
        key = (repository, branch)
        self.references[key] = max(self.references.get(key, 0) - 1, 0)
        return self.references[key]

    async def load_state(
        self, conn: Any, repository: str, branch: str
    ) -> store.RepoIndexState | None:
        return self.states.get((repository, branch))

    async def set_index_progress(
        self,
        conn: Any,
        repository: str,
        branch: str,
        *,
        status: str,
        progress_percent: int,
        error_message: str | None = None,
    ) -> None:
        self.progress.append((repository, branch, status, progress_percent, error_message))

    async def persist_inventory(
        self, conn: Any, inventory: ApiUsageInventory
    ) -> store.PersistResult:
        self.persisted.append(inventory)
        return store.PersistResult(inserted=len(inventory.usages), updated=0)

    async def retire_paths(
        self, conn: Any, repository: str, branch: str, paths: list[str], sha: str
    ) -> int:
        self.retired.append((repository, branch, tuple(paths), sha))
        return len(paths)

    async def record_state(self, conn: Any, state: store.RepoIndexState) -> None:
        self.recorded.append(state)
        self.states[(state.repository, state.branch)] = state

    async def projects_for(
        self, conn: Any, repository: str, branch: str
    ) -> list[store.ProjectScope]:
        return list(self.scopes.get((repository, branch), []))

    async def indexable_targets(self, conn: Any) -> list[store.IndexTarget]:
        return list(self.targets)

    async def usages_for_project(
        self, conn: Any, project_id: UUID, identifiers: list[str]
    ) -> list[store.ProjectUsage]:
        rows = self.project_usages.get(project_id, [])
        return [row for row in rows if row.record.identifier in set(identifiers)]


@dataclass
class FakeWorld:
    """Records every side effect a handler tried to perform."""

    checkouts: list[tuple[str, str, str]] = field(default_factory=list)
    diffs: list[tuple[str, str]] = field(default_factory=list)
    inventories: list[dict[str, Any]] = field(default_factory=list)
    published: list[EventEnvelope] = field(default_factory=list)
    searches: list[tuple[tuple[str, ...], tuple[tuple[str, str], ...]]] = field(
        default_factory=list
    )

    head_sha: str = AFTER_SHA
    changed: list[str] = field(default_factory=lambda: ["src/app.ts"])
    usages: tuple[ApiUsageRecord, ...] = ()
    matches: list[ZoektMatch] = field(default_factory=list)
    checkout_error: Exception | None = None
    diff_error: Exception | None = None
    head_error: Exception | None = None
    search_error: Exception | None = None
    publish_succeeds: bool = True

    @property
    def touched(self) -> bool:
        """True when the handler reached git, the scanner, or the broker."""
        return bool(self.checkouts or self.diffs or self.inventories or self.published)

    def resolve_head(self, repository: str, branch: str) -> str:
        if self.head_error is not None:
            raise self.head_error
        return self.head_sha

    def ensure_checkout(self, repository: str, branch: str, sha: str) -> Path:
        if self.checkout_error is not None:
            raise self.checkout_error
        self.checkouts.append((repository, branch, sha))
        return Path("/tmp/patchapi-test-checkout")

    def changed_paths(self, repo_path: Path, base_sha: str, head_sha: str) -> list[str]:
        if self.diff_error is not None:
            raise self.diff_error
        self.diffs.append((base_sha, head_sha))
        return list(self.changed)

    def build_inventory(self, **kwargs: Any) -> ApiUsageInventory:
        self.inventories.append(kwargs)
        changed_paths = kwargs.get("changed_paths")
        return ApiUsageInventory(
            repository=kwargs["repository"],
            branch=kwargs["branch"],
            observed_sha=kwargs["observed_sha"],
            provider="google",
            watched_identifiers=(IDENTIFIER,),
            scope="full_tree" if changed_paths is None else "changed_paths",
            files_scanned=7 if changed_paths is None else len(changed_paths),
            usages=self.usages,
        )

    def search_shards(self, patterns: Any, shards: Any, **kwargs: Any) -> list[ZoektMatch]:
        if self.search_error is not None:
            raise self.search_error
        self.searches.append(
            (tuple(patterns), tuple((shard.repository, shard.branch) for shard in shards))
        )
        return list(self.matches)

    async def publish(self, envelope: EventEnvelope) -> PublishResult:
        self.published.append(envelope)
        return PublishResult(
            event_type=EventType(envelope.event_type),
            event_id=envelope.event_id,
            topic="test-topic",
            published=self.publish_succeeds,
        )


@pytest.fixture
def conn() -> FakeConnection:
    return FakeConnection()


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    double = FakeStore()
    monkeypatch.setattr(worker, "store", double)
    return double


@pytest.fixture
def world() -> FakeWorld:
    return FakeWorld()


async def _noop_refresh_findings(*_args: object, **_kwargs: object) -> tuple[str, ...]:
    return ()


@pytest.fixture
def effects(world: FakeWorld) -> worker.Effects:
    return worker.Effects(
        resolve_head=world.resolve_head,
        ensure_checkout=world.ensure_checkout,
        changed_paths=world.changed_paths,
        build_inventory=world.build_inventory,
        search_shards=world.search_shards,
        publish=world.publish,
        now=lambda: NOW,
        index_backend="zoekt",
        refresh_findings=_noop_refresh_findings,
    )


def scope(*, project_id: UUID | None = None, path_prefix: str | None = None) -> store.ProjectScope:
    return store.ProjectScope(
        project_id=project_id or uuid4(),
        project_repository_id=uuid4(),
        kind="service",
        path_prefix=path_prefix,
    )


def usage_record(path: str, identifier: str = IDENTIFIER) -> ApiUsageRecord:
    return ApiUsageRecord(
        provider="google",
        identifier=identifier,
        file_path=path,
        line_start=3,
        usage_kind=UsageKind.RUNTIME_SOURCE,
        confidence=1.0,
        excerpt=f'const MODEL = "{identifier}";',
    )


def ready_state(sha: str = BEFORE_SHA, **overrides: Any) -> store.RepoIndexState:
    state = store.RepoIndexState(
        repository=REPOSITORY,
        branch=BRANCH,
        status="ready",
        progress_percent=100,
        indexed_sha=sha,
        shard_path="/var/zoekt/egaki",
        indexer_version=INDEXER_VERSION,
        scanner_version="1.0.0",
        last_full_index=NOW,
        last_delta_index=None,
        file_count=42,
        reference_count=1,
        error_message=None,
    )
    return replace(state, **overrides) if overrides else state


def push_event(*, before: str = BEFORE_SHA, after: str = AFTER_SHA, branch: str = BRANCH):
    return repo_push_event(
        repository=REPOSITORY,
        branch=branch,
        before_sha=before,
        after_sha=after,
        installation_id=42,
        occurred_at=OCCURRED_AT,
    )


def manifest_event(identifiers: list[str], provider: str = "google") -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.CHANGE_NORMALIZED,
        event_id="manifest-1",
        run_id="run-1",
        occurred_at=OCCURRED_AT,
        trust=TrustLevel.INTERNAL_ANALYSIS,
        payload={
            "manifest_id": "manifest-1",
            "provider": provider,
            "affected_identifiers": identifiers,
        },
    )


# --------------------------------------------------------------------------- #
# handle_push
# --------------------------------------------------------------------------- #


async def test_push_to_unimported_branch_is_dropped_before_any_work(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    """No project imports the ref, so nothing is fetched, scanned, or written."""
    result = await worker.handle_push(conn, push_event(), effects=effects)

    assert result.action == worker.ACTION_DROPPED
    assert result.reason == "no project imports this ref"
    assert not world.touched
    assert fake_store.progress == []
    assert fake_store.persisted == []
    assert fake_store.recorded == []


async def test_push_to_a_tag_is_dropped(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    envelope = EventEnvelope(
        event_type=EventType.REPO_PUSH,
        event_id="delivery-1",
        run_id="push-1",
        occurred_at=OCCURRED_AT,
        trust=TrustLevel.INTERNAL_ANALYSIS,
        payload={"repository": REPOSITORY, "ref": "refs/tags/v1.0.0", "after_sha": AFTER_SHA},
    )

    result = await worker.handle_push(conn, envelope, effects=effects)

    assert result.action == worker.ACTION_DROPPED
    assert result.reason == "push does not name a branch"
    assert not world.touched


async def test_push_deleting_a_branch_is_dropped(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    fake_store.scopes[(REPOSITORY, BRANCH)] = [scope()]

    result = await worker.handle_push(conn, push_event(after=worker.NULL_SHA), effects=effects)

    assert result.action == worker.ACTION_DROPPED
    assert result.reason == "push carries no head commit"
    assert not world.touched


async def test_push_to_an_already_indexed_sha_is_dropped(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    fake_store.scopes[(REPOSITORY, BRANCH)] = [scope()]
    fake_store.states[(REPOSITORY, BRANCH)] = ready_state(sha=AFTER_SHA)

    result = await worker.handle_push(conn, push_event(), effects=effects)

    assert result.action == worker.ACTION_DROPPED
    assert result.reason == "already indexed at this sha"
    assert not world.touched
    assert fake_store.persisted == []


async def test_push_delta_indexes_retires_and_fans_out(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    project_a, project_b = uuid4(), uuid4()
    fake_store.scopes[(REPOSITORY, BRANCH)] = [
        scope(project_id=project_a),
        scope(project_id=project_b, path_prefix="apps/web"),
    ]
    fake_store.states[(REPOSITORY, BRANCH)] = ready_state()
    world.usages = (usage_record("src/app.ts"),)

    result = await worker.handle_push(conn, push_event(), effects=effects)

    assert result.action == worker.ACTION_INDEXED
    assert result.indexed_sha == AFTER_SHA
    assert world.diffs == [(BEFORE_SHA, AFTER_SHA)]
    assert world.inventories[0]["changed_paths"] == ["src/app.ts"]

    # Persist first, then retire at the same head SHA: the guard in
    # `retire_paths` is what keeps the second call from undoing the first.
    assert fake_store.persisted[0].observed_sha == AFTER_SHA
    assert fake_store.retired == [(REPOSITORY, BRANCH, ("src/app.ts",), AFTER_SHA)]
    assert conn.transactions == 1

    recorded = fake_store.recorded[0]
    assert (recorded.status, recorded.progress_percent) == ("ready", 100)
    assert recorded.indexed_sha == AFTER_SHA
    assert recorded.last_delta_index == NOW
    # A delta scanned the pushed files, not the repository.
    assert recorded.file_count == 42
    assert recorded.shard_path == "/var/zoekt/egaki"

    assert [entry[2:4] for entry in fake_store.progress] == [
        ("indexing", 0),
        ("indexing", 25),
        ("indexing", 75),
    ]

    fanned = {envelope.payload["project_id"] for envelope in world.published}
    assert fanned == {str(project_a), str(project_b)}
    assert result.notified_projects == tuple(sorted({str(project_a), str(project_b)}))
    for envelope in world.published:
        assert envelope.event_type is EventType.INDEX_UPDATED
        assert envelope.payload["indexed_sha"] == AFTER_SHA


async def test_push_without_a_diff_base_reindexes_in_full(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    """A force-push leaves no base to diff from; a full pass beats a stale index."""
    fake_store.scopes[(REPOSITORY, BRANCH)] = [scope()]
    world.diff_error = RevisionNotFoundError("base is gone")

    result = await worker.handle_push(conn, push_event(), effects=effects)

    assert result.action == worker.ACTION_INDEXED
    assert world.inventories[0]["changed_paths"] is None
    assert fake_store.retired == []
    assert fake_store.recorded[0].last_full_index == NOW


async def test_push_records_the_failure_and_reraises(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    """A failed pass is visible as `error`, never as an idle or ready target."""
    fake_store.scopes[(REPOSITORY, BRANCH)] = [scope()]
    world.checkout_error = RevisionNotFoundError("commit is not reachable")

    with pytest.raises(RevisionNotFoundError):
        await worker.handle_push(conn, push_event(), effects=effects)

    status, progress, message = fake_store.progress[-1][2:]
    assert (status, progress) == ("error", 0)
    assert "RevisionNotFoundError" in (message or "")
    assert fake_store.recorded == []
    assert world.published == []


# --------------------------------------------------------------------------- #
# handle_repo_added / handle_repo_removed
# --------------------------------------------------------------------------- #


async def test_repo_added_acquires_and_full_indexes(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    project = uuid4()
    fake_store.scopes[(REPOSITORY, BRANCH)] = [scope(project_id=project)]
    world.usages = (usage_record("src/app.ts"),)

    envelope = project_repo_added_event(
        project_id=str(project),
        repository=REPOSITORY,
        branch=BRANCH,
        occurred_at=OCCURRED_AT,
    )
    result = await worker.handle_repo_added(conn, envelope, effects=effects)

    assert fake_store.acquired == [(REPOSITORY, BRANCH)]
    assert result.action == worker.ACTION_INDEXED
    assert world.checkouts == [(REPOSITORY, BRANCH, AFTER_SHA)]
    assert world.inventories[0]["changed_paths"] is None
    assert fake_store.persisted[0].scope == "full_tree"
    assert fake_store.recorded[0].last_full_index == NOW
    assert fake_store.recorded[0].file_count == 7
    assert result.usages_written == 1
    assert [envelope.payload["project_id"] for envelope in world.published] == [str(project)]


async def test_repo_added_to_an_indexed_target_only_takes_a_reference(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    """The second project to import a repository pays a counter bump, not a clone."""
    project = uuid4()
    fake_store.references[(REPOSITORY, BRANCH)] = 1
    fake_store.states[(REPOSITORY, BRANCH)] = ready_state(sha=AFTER_SHA)
    fake_store.scopes[(REPOSITORY, BRANCH)] = [scope(project_id=project)]

    envelope = project_repo_added_event(
        project_id=str(project),
        repository=REPOSITORY,
        branch=BRANCH,
        occurred_at=OCCURRED_AT,
    )
    result = await worker.handle_repo_added(conn, envelope, effects=effects)

    assert result.action == worker.ACTION_REFERENCED
    assert result.reference_count == 2
    assert world.checkouts == []
    assert world.inventories == []
    assert fake_store.persisted == []
    assert fake_store.progress[-1][2:4] == ("ready", 100)
    # The importing project still learns the repository is ready to read.
    assert [envelope.payload["indexed_sha"] for envelope in world.published] == [AFTER_SHA]


async def test_repo_added_marks_error_when_the_branch_cannot_be_resolved(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    world.head_error = RevisionNotFoundError("no such branch")

    envelope = project_repo_added_event(
        project_id=str(uuid4()),
        repository=REPOSITORY,
        branch=BRANCH,
        occurred_at=OCCURRED_AT,
    )
    with pytest.raises(RevisionNotFoundError):
        await worker.handle_repo_added(conn, envelope, effects=effects)

    assert fake_store.progress[-1][2:4] == ("error", 0)
    assert fake_store.persisted == []


async def test_repo_removed_releases_one_reference(
    conn: FakeConnection, fake_store: FakeStore, effects: worker.Effects
) -> None:
    fake_store.references[(REPOSITORY, BRANCH)] = 2

    envelope = project_repo_removed_event(
        project_id=str(uuid4()),
        repository=REPOSITORY,
        branch=BRANCH,
        occurred_at=OCCURRED_AT,
    )
    result = await worker.handle_repo_removed(conn, envelope, effects=effects)

    assert result.action == worker.ACTION_RELEASED
    assert result.reference_count == 1
    assert result.reason is None
    assert fake_store.released == [(REPOSITORY, BRANCH)]


async def test_repo_added_without_a_repository_fails_closed(
    conn: FakeConnection, fake_store: FakeStore, effects: worker.Effects
) -> None:
    envelope = EventEnvelope(
        event_type=EventType.PROJECT_REPO_ADDED,
        event_id="e1",
        run_id="r1",
        occurred_at=OCCURRED_AT,
        trust=TrustLevel.INTERNAL_ANALYSIS,
        payload={"project_id": str(uuid4()), "branch": BRANCH},
    )

    with pytest.raises(worker.EventPayloadError):
        await worker.handle_repo_added(conn, envelope, effects=effects)


# --------------------------------------------------------------------------- #
# handle_manifest
# --------------------------------------------------------------------------- #


async def test_manifest_answers_from_the_index_scoped_to_each_workspace(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    whole_repo, workspace = uuid4(), uuid4()
    fake_store.targets = [store.IndexTarget(repository=REPOSITORY, branch=BRANCH)]
    fake_store.scopes[(REPOSITORY, BRANCH)] = [
        scope(project_id=whole_repo),
        scope(project_id=workspace, path_prefix="apps/web"),
    ]
    world.matches = [
        ZoektMatch(
            repository=REPOSITORY,
            branch=BRANCH,
            path="apps/web/page.tsx",
            line_number=4,
            line=f'"{IDENTIFIER}"',
            matched_text=IDENTIFIER,
        ),
        ZoektMatch(
            repository=REPOSITORY,
            branch=None,
            path="services/api/main.py",
            line_number=9,
            line=f'"{IDENTIFIER}"',
            matched_text=IDENTIFIER,
        ),
    ]

    result = await worker.handle_manifest(conn, manifest_event([IDENTIFIER]), effects=effects)

    assert result.source == worker.SOURCE_INDEX
    # One index query for the whole fleet, and no checkout anywhere.
    assert len(world.searches) == 1
    assert world.searches[0][1] == ((REPOSITORY, BRANCH),)
    assert world.checkouts == []

    by_project = {pair.project_id: pair.paths for pair in result.affected}
    assert by_project[whole_repo] == ("apps/web/page.tsx", "services/api/main.py")
    assert by_project[workspace] == ("apps/web/page.tsx",)


async def test_manifest_falls_back_to_provider_usages_when_the_index_is_down(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    project = uuid4()
    target_scope = scope(project_id=project)
    fake_store.targets = [store.IndexTarget(repository=REPOSITORY, branch=BRANCH)]
    fake_store.scopes[(REPOSITORY, BRANCH)] = [target_scope]
    fake_store.project_usages[project] = [
        store.ProjectUsage(
            project_id=project,
            project_repository_id=target_scope.project_repository_id,
            repository=REPOSITORY,
            branch=BRANCH,
            kind="service",
            observed_sha=BEFORE_SHA,
            record=usage_record("src/app.ts"),
        )
    ]
    world.search_error = ZoektUnavailableError("connection refused")

    result = await worker.handle_manifest(conn, manifest_event([IDENTIFIER]), effects=effects)

    assert result.source == worker.SOURCE_DATABASE
    assert "ZoektUnavailableError" in (result.reason or "")
    assert [(pair.project_id, pair.paths) for pair in result.affected] == [
        (project, ("src/app.ts",))
    ]


async def test_manifest_with_no_identifier_affects_nothing(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    """Fail closed: a manifest that watches nothing must not select every finding."""
    fake_store.targets = [store.IndexTarget(repository=REPOSITORY, branch=BRANCH)]

    result = await worker.handle_manifest(conn, manifest_event([]), effects=effects)

    assert result.affected == ()
    assert result.reason == "manifest names no identifier"
    assert world.searches == []


async def test_manifest_uses_sql_when_the_backend_is_literal(
    conn: FakeConnection, fake_store: FakeStore, world: FakeWorld, effects: worker.Effects
) -> None:
    fake_store.targets = [store.IndexTarget(repository=REPOSITORY, branch=BRANCH)]
    fake_store.scopes[(REPOSITORY, BRANCH)] = [scope()]

    result = await worker.handle_manifest(
        conn, manifest_event([IDENTIFIER]), effects=replace(effects, index_backend="literal")
    )

    assert result.source == worker.SOURCE_DATABASE
    assert world.searches == []


def test_workspace_prefix_matches_path_segments_only() -> None:
    paths = ["apps/web/page.tsx", "apps/webhooks/main.py", "apps/web"]
    assert worker._covered("apps/web", paths) == ("apps/web", "apps/web/page.tsx")
    assert worker._covered(None, paths) == tuple(sorted(paths))


# --------------------------------------------------------------------------- #
# Routing and transport naming
# --------------------------------------------------------------------------- #


async def test_dispatch_routes_each_subscribed_event(
    conn: FakeConnection, fake_store: FakeStore, effects: worker.Effects
) -> None:
    result = await worker.dispatch(conn, push_event(), effects=effects)
    assert isinstance(result, worker.HandlerResult)
    assert result.action == worker.ACTION_DROPPED


async def test_dispatch_ignores_an_event_this_worker_does_not_serve(
    conn: FakeConnection, fake_store: FakeStore, effects: worker.Effects
) -> None:
    envelope = EventEnvelope(
        event_type=EventType.PATCH_REQUESTED,
        event_id="e1",
        run_id="r1",
        occurred_at=OCCURRED_AT,
        trust=TrustLevel.INTERNAL_ANALYSIS,
        payload={"repository": REPOSITORY},
    )

    assert await worker.dispatch(conn, envelope, effects=effects) is None


def test_subscription_names_match_the_provisioned_ones() -> None:
    """`{prefix}-{event-type}-sub`, the name `modules/eventing` creates."""
    env: dict[str, str] = {"GCP_PROJECT": "patch-505223"}
    assert pubsub.subscription_id(EventType.REPO_PUSH, env) == "patchapi-dev-repo-push-sub"
    assert (
        pubsub.subscription_id(EventType.PROJECT_REPO_ADDED, env)
        == "patchapi-dev-project-repo-added-sub"
    )
    assert pubsub.subscription_path(EventType.REPO_PUSH, env) == (
        "projects/patch-505223/subscriptions/patchapi-dev-repo-push-sub"
    )
    assert EventType.CHANGE_NORMALIZED not in pubsub.SUBSCRIBED_EVENTS


class FakePool:
    """`pool.acquire()` as an async context manager over one connection."""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def acquire(self) -> FakePool:
        return self

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


async def test_handle_message_decodes_and_dispatches(
    conn: FakeConnection, fake_store: FakeStore, effects: worker.Effects
) -> None:
    data = push_event().to_json().encode("utf-8")

    result = await pubsub.handle_message(FakePool(conn), data, effects=effects)

    assert isinstance(result, worker.HandlerResult)
    assert result.action == worker.ACTION_DROPPED


async def test_handle_message_raises_on_a_malformed_envelope(
    conn: FakeConnection, fake_store: FakeStore, effects: worker.Effects
) -> None:
    """An undecodable message must not be acknowledged as handled."""
    with pytest.raises(ValueError):
        await pubsub.handle_message(FakePool(conn), b'{"event_type": "repo-push"}', effects=effects)


# --------------------------------------------------------------------------- #
# The same handlers against the authoritative store
# --------------------------------------------------------------------------- #

DSN = os.environ.get("DATABASE_URL", "").strip()

requires_postgres = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the state-machine run needs Postgres with 0007 applied",
)

THIRD_SHA = "c" * 40


async def seed_project(pg_conn: Any, full_name: str) -> UUID:
    owner_id = await pg_conn.fetchval(
        "INSERT INTO users (email, display_name) VALUES ($1, $2) RETURNING id",
        f"{uuid4().hex}@worker.test",
        "Worker Test",
    )
    project_id = await pg_conn.fetchval(
        "INSERT INTO projects (owner_id, name) VALUES ($1, $2) RETURNING id",
        owner_id,
        "worker-state-machine",
    )
    await pg_conn.execute(
        """
        INSERT INTO project_repositories (project_id, name, full_name, default_branch)
        VALUES ($1, $2, $3, 'main')
        """,
        project_id,
        full_name.split("/")[-1],
        full_name,
    )
    return project_id


async def live_paths(pg_conn: Any, repository: str) -> list[str]:
    rows = await pg_conn.fetch(
        """
        SELECT file_path FROM provider_usages
        WHERE repository = $1 AND retired_at IS NULL
        ORDER BY file_path
        """,
        repository,
    )
    return [row["file_path"] for row in rows]


@requires_postgres
async def test_state_machine_against_postgres(world: FakeWorld, effects: worker.Effects) -> None:
    """Import, push, replay, and an unimported branch — read back from the tables.

    Git and the scanner are stubbed; the transitions, the rows, and the
    idempotency are the real ones.
    """
    connection = await asyncpg.connect(DSN)
    transaction = connection.transaction()
    await transaction.start()
    try:
        repository = f"patchapi-test/{uuid4().hex}"
        project_id = await seed_project(connection, repository)

        # Import: acquire a reference and full-index the default branch.
        world.usages = (usage_record("src/app.ts"), usage_record("src/legacy.ts"))
        added = await worker.handle_repo_added(
            connection,
            project_repo_added_event(
                project_id=str(project_id),
                repository=repository,
                branch=BRANCH,
                occurred_at=OCCURRED_AT,
            ),
            effects=effects,
        )
        assert added.action == worker.ACTION_INDEXED
        state = await store.load_state(connection, repository, BRANCH)
        assert state is not None
        assert (state.status, state.progress_percent, state.indexed_sha) == (
            "ready",
            100,
            AFTER_SHA,
        )
        assert state.reference_count == 1
        assert await live_paths(connection, repository) == ["src/app.ts", "src/legacy.ts"]
        assert added.notified_projects == (str(project_id),)

        # Push: the identifier is gone from one changed file, so its row retires.
        world.changed = ["src/legacy.ts"]
        world.usages = ()
        push = repo_push_event(
            repository=repository,
            branch=BRANCH,
            before_sha=AFTER_SHA,
            after_sha=THIRD_SHA,
            installation_id=42,
            occurred_at=OCCURRED_AT,
        )
        pushed = await worker.handle_push(connection, push, effects=effects)
        assert pushed.action == worker.ACTION_INDEXED
        assert pushed.paths_retired == 1
        assert await live_paths(connection, repository) == ["src/app.ts"]
        delta = await store.load_state(connection, repository, BRANCH)
        assert delta is not None
        assert (delta.status, delta.indexed_sha) == ("ready", THIRD_SHA)
        assert delta.last_delta_index is not None
        # A delta scanned one file; the repository is still the size the full
        # pass measured.
        assert delta.file_count == state.file_count

        # Replay: at-least-once delivery must not double-write or re-retire.
        replayed = await worker.handle_push(connection, push, effects=effects)
        assert replayed.action == worker.ACTION_DROPPED
        assert replayed.reason == "already indexed at this sha"
        assert await live_paths(connection, repository) == ["src/app.ts"]

        # A branch no project imported is dropped, and leaves no state behind.
        unimported = await worker.handle_push(
            connection,
            repo_push_event(
                repository=repository,
                branch="feature/nobody-imported-this",
                before_sha=AFTER_SHA,
                after_sha=THIRD_SHA,
                installation_id=42,
                occurred_at=OCCURRED_AT,
            ),
            effects=effects,
        )
        assert unimported.action == worker.ACTION_DROPPED
        assert (
            await store.load_state(connection, repository, "feature/nobody-imported-this") is None
        )

        # Removal drops the last reference; the findings stay as history.
        released = await worker.handle_repo_removed(
            connection,
            project_repo_removed_event(
                project_id=str(project_id),
                repository=repository,
                branch=BRANCH,
                occurred_at=OCCURRED_AT,
            ),
            effects=effects,
        )
        assert released.reference_count == 0
        final = await store.load_state(connection, repository, BRANCH)
        assert final is not None
        assert (final.status, final.progress_percent) == ("idle", 0)
        assert await live_paths(connection, repository) == ["src/app.ts"]
    finally:
        await transaction.rollback()
        await connection.close()
