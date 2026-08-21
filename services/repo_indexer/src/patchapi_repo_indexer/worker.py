"""Event handlers for the repository lifecycle (`repo-indexer.md` §5.6, §7.2, §7.3).

Four events, four handlers, one shared discipline: Postgres is where a pass is
recorded, and nothing is claimed that was not done.

* `handle_repo_added` — take a reference on the `(repository, branch)` shard and
  full-index it. The second project to import a repository pays a counter bump
  rather than a clone: findings are facts about a repository, not about a
  project, and re-indexing would produce the rows that are already there.
* `handle_repo_removed` — drop one reference. The shard survives while any other
  project still imports the target.
* `handle_push` — **drop before doing any work when no project imports the ref**.
  Most pushes to a busy repository are to branches nobody imported, and the
  early return is the difference between a subscriber that keeps up and one that
  queues behind clones it never needed (§7.2).
* `handle_manifest` — answer "which projects use these identifiers" from the
  index, and from `provider_usages` when the index is unreachable. No clone, no
  fetch, no per-project scan; that is the §7.3 scalability claim.

Every side effect a handler needs is injected through `Effects`, so the state
machine can be exercised without git, an index, or a broker. The defaults are
the real collaborators.

Failures fail closed and stay visible: the target is marked `error` with the
reason before the exception propagates, and the subscriber nacks. A handler
never returns a quiet success for a pass that did not finish, because "indexed,
no usages" and "never indexed" would otherwise read identically to every
consumer downstream.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from packages.events.config import EventType
from packages.events.publisher import publish_async
from packages.events.repo_events import branch_from_ref, index_updated_event
from patchapi_repo_indexer import git, store
from patchapi_repo_indexer.config import (
    DEFAULT_PROVIDER,
    INDEX_BACKEND,
    INDEXER_VERSION,
    SCANNER_VERSION,
)
from patchapi_repo_indexer.errors import (
    IndexerError,
    ShardCorruptError,
    UnknownProviderError,
    ZoektUnavailableError,
)
from patchapi_repo_indexer.index import ZOEKT_BACKEND, build_inventory
from patchapi_repo_indexer.zoekt import patterns as zoekt_patterns
from patchapi_repo_indexer.zoekt import query as zoekt_query
from patchapi_repo_indexer.zoekt.shard import ShardRef

if TYPE_CHECKING:  # pragma: no cover - import cost is paid only by type checkers
    import asyncpg

    from packages.events.envelope import EventEnvelope
    from packages.events.publisher import PublishResult
    from patchapi_repo_indexer.models import ApiUsageInventory

log = logging.getLogger(__name__)

# GitHub reports a created branch, and a deleted one, as the null SHA. There is
# no base commit to diff against, so a push carrying it is indexed in full.
NULL_SHA: Final[str] = "0" * 40

_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{7,40}$")

# Progress the Codebase tab banner reads while a pass runs (`store.py` §7.6).
# Coarse on purpose: these are the three points at which the work actually
# changes shape, not a spinner.
PROGRESS_START: Final[int] = 0
PROGRESS_FETCHED: Final[int] = 25
PROGRESS_SCANNED: Final[int] = 75
PROGRESS_DONE: Final[int] = 100

# `repo_index_state.error_message` is what an operator reads first. Bounded so a
# driver traceback cannot push the useful first line out of the banner.
MAX_ERROR_CHARS: Final[int] = 500

ACTION_INDEXED: Final[str] = "indexed"
ACTION_REFERENCED: Final[str] = "referenced"
ACTION_RELEASED: Final[str] = "released"
ACTION_DROPPED: Final[str] = "dropped"

# Where a manifest answer came from. Recorded rather than logged because the two
# have different recall: the index finds family members nobody enumerated, the
# table holds only what a previous pass already wrote.
SOURCE_INDEX: Final[str] = "index"
SOURCE_DATABASE: Final[str] = "database"


class EventPayloadError(IndexerError):
    """An event payload lacks a field the handler refuses to guess at.

    Defined here rather than in `errors.py` because it belongs to the event
    surface; promoting it is a follow-up, not a behaviour change.
    """


@dataclass(frozen=True, slots=True)
class HandlerResult:
    """What one lifecycle handler did, for the subscriber's log and for tests."""

    action: str
    repository: str
    branch: str
    reason: str | None = None
    indexed_sha: str | None = None
    usages_written: int = 0
    paths_retired: int = 0
    reference_count: int | None = None
    notified_projects: tuple[str, ...] = ()

    @property
    def indexed(self) -> bool:
        return self.action == ACTION_INDEXED


@dataclass(frozen=True, slots=True)
class AffectedRepository:
    """One `(project, repository)` pair a manifest reaches.

    The unit is deliberately the pair and not the repository: a project with a
    frontend and a backend that both use the identifier gets two impact
    analyses, two runs, and two pull requests (§7.3).
    """

    project_id: UUID
    project_repository_id: UUID
    repository: str
    branch: str
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManifestResult:
    """Which projects a change manifest reaches, and what answered the question."""

    source: str
    affected: tuple[AffectedRepository, ...]
    reason: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def resolve_head(repository: str, branch: str, *, remote_url: str | None = None) -> str:
    """Return the commit at the tip of `branch`, updating the mirror to find it.

    A `project-repo-added` event names a branch and no commit — the import is a
    branch, and the tip moves — so the first index has to resolve one. `git.py`
    exposes checkout-by-sha but not tip resolution, so the fetch and the
    rev-parse are borrowed from it here; the composition is the only new thing.
    Promoting this into `git.py` is a follow-up.
    """
    branch = git._validate_branch(branch)
    mirror = git._ensure_mirror(repository, branch, remote_url)
    proc = git._run_git(["rev-parse", f"refs/heads/{branch}"], cwd=mirror)
    sha = proc.stdout.strip()
    if not _SHA_RE.match(sha):
        raise git.RevisionNotFoundError(f"{repository}@{branch} resolved to no commit after fetch")
    return sha.lower()


@dataclass(frozen=True, slots=True)
class Effects:
    """The side-effecting collaborators a handler needs, injected.

    Grouped into one object so a test substitutes a whole environment rather
    than patching module globals, and so a handler's dependencies are visible in
    its signature instead of in its imports.
    """

    resolve_head: Callable[[str, str], str] = resolve_head
    ensure_checkout: Callable[[str, str, str], Path] = git.ensure_checkout
    changed_paths: Callable[[Path, str, str], list[str]] = git.changed_paths
    build_inventory: Callable[..., ApiUsageInventory] = build_inventory
    search_shards: Callable[[Sequence[str], Sequence[ShardRef]], list[zoekt_query.ZoektMatch]] = (
        zoekt_query.search_shards
    )
    publish: Callable[[EventEnvelope], Awaitable[PublishResult]] = publish_async
    now: Callable[[], datetime] = _utc_now
    index_backend: str = field(default=INDEX_BACKEND)


DEFAULT_EFFECTS: Final[Effects] = Effects()


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _require(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not value:
        raise EventPayloadError(f"event payload has no {key}; refusing to guess at a target")
    return value


def _identifiers(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(
        dict.fromkeys(item.strip() for item in raw if isinstance(item, str) and item.strip())
    )


def _error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]


async def _mark_error(
    conn: asyncpg.Connection, repository: str, branch: str, exc: BaseException
) -> None:
    """Record why a pass stopped, so a failed index cannot read as an idle one."""
    try:
        await store.set_index_progress(
            conn,
            repository,
            branch,
            status="error",
            progress_percent=PROGRESS_START,
            error_message=_error_text(exc),
        )
    except Exception:  # pragma: no cover - the original failure is the one to report
        log.exception("could not record index failure for %s@%s", repository, branch)


def _ready_state(
    *,
    repository: str,
    branch: str,
    inventory: ApiUsageInventory,
    previous: store.RepoIndexState | None,
    references: int,
    full: bool,
    now: datetime,
) -> store.RepoIndexState:
    """The `repo_index_state` row a finished pass writes.

    `shard_path` is carried over rather than derived: `build_inventory` may have
    degraded to the literal walk, and naming a shard that was never built would
    tell an operator the index is healthy when it is not.

    A delta pass keeps the previous `file_count` for the same reason it keeps the
    shard: it scanned the files a push touched, and reporting that as the size of
    the repository would shrink the corpus every time somebody edited one file.
    """
    return store.RepoIndexState(
        repository=repository,
        branch=branch,
        status="ready",
        progress_percent=PROGRESS_DONE,
        indexed_sha=inventory.observed_sha,
        shard_path=previous.shard_path if previous else None,
        indexer_version=INDEXER_VERSION,
        scanner_version=SCANNER_VERSION,
        last_full_index=now if full else (previous.last_full_index if previous else None),
        last_delta_index=now if not full else (previous.last_delta_index if previous else None),
        file_count=inventory.files_scanned if full or previous is None else previous.file_count,
        reference_count=previous.reference_count if previous else references,
        error_message=None,
    )


async def _fan_out(
    conn: asyncpg.Connection,
    repository: str,
    branch: str,
    indexed_sha: str,
    effects: Effects,
    scopes: Sequence[store.ProjectScope] | None = None,
) -> tuple[str, ...]:
    """Notify every project that imports the target. Index once, notify many.

    A publish that does not land is reported, never raised: the rows are already
    committed, and losing the broker must not undo an index that happened. The
    publisher has already logged the topic and the event id an operator replays
    from.
    """
    targets = scopes if scopes is not None else await store.projects_for(conn, repository, branch)
    occurred_at = effects.now().isoformat()
    project_ids = sorted({str(scope.project_id) for scope in targets})
    if not project_ids:
        # Indexed before any project claimed it: the event addresses the
        # repository itself rather than a project.
        project_ids = [""]

    notified: list[str] = []
    for project_id in project_ids:
        result = await effects.publish(
            index_updated_event(
                repository=repository,
                branch=branch,
                indexed_sha=indexed_sha,
                project_id=project_id or None,
                occurred_at=occurred_at,
            )
        )
        if result.published:
            notified.append(project_id)
    return tuple(notified)


async def _index(
    conn: asyncpg.Connection,
    repository: str,
    branch: str,
    *,
    sha: str,
    changed: Sequence[str] | None,
    references: int,
    effects: Effects,
) -> HandlerResult:
    """Index one target at `sha` and record the pass.

    `changed is None` is a full pass; a sequence — including an empty one — is a
    push-driven delta over exactly those paths.

    The write is one transaction: an inventory persisted without its retirements
    would leave a migrated identifier live, and a state row recorded without its
    inventory would claim a commit was indexed when its findings never landed.
    """
    full = changed is None
    await store.set_index_progress(
        conn, repository, branch, status="indexing", progress_percent=PROGRESS_START
    )
    try:
        checkout = effects.ensure_checkout(repository, branch, sha)
        await store.set_index_progress(
            conn, repository, branch, status="indexing", progress_percent=PROGRESS_FETCHED
        )
        inventory = effects.build_inventory(
            root=checkout,
            repository=repository,
            observed_sha=sha,
            branch=branch,
            changed_paths=None if full else list(changed or ()),
        )
        await store.set_index_progress(
            conn, repository, branch, status="indexing", progress_percent=PROGRESS_SCANNED
        )

        previous = await store.load_state(conn, repository, branch)
        async with conn.transaction():
            written = await store.persist_inventory(conn, inventory)
            retired = (
                0
                if full
                else await store.retire_paths(conn, repository, branch, list(changed or ()), sha)
            )
            await store.record_state(
                conn,
                _ready_state(
                    repository=repository,
                    branch=branch,
                    inventory=inventory,
                    previous=previous,
                    references=references,
                    full=full,
                    now=effects.now(),
                ),
            )
    except Exception as exc:
        await _mark_error(conn, repository, branch, exc)
        raise

    notified = await _fan_out(conn, repository, branch, sha, effects)
    return HandlerResult(
        action=ACTION_INDEXED,
        repository=repository,
        branch=branch,
        indexed_sha=sha,
        usages_written=written.total,
        paths_retired=retired,
        reference_count=references,
        notified_projects=notified,
    )


async def handle_repo_added(
    conn: asyncpg.Connection, envelope: EventEnvelope, *, effects: Effects = DEFAULT_EFFECTS
) -> HandlerResult:
    """Take a reference on a target's shard, and full-index it if nothing has.

    Fires per `project_repositories` row, not per project. An already-indexed
    target costs a counter bump and a notification: its findings carry no
    project, so the importing project can read them the moment the reference
    lands.
    """
    repository = _require(envelope.payload, "repository")
    branch = _require(envelope.payload, "branch")

    references = await store.acquire_shard(conn, repository, branch)
    previous = await store.load_state(conn, repository, branch)
    if previous is not None and previous.status == "ready" and previous.indexed_sha:
        notified = await _fan_out(conn, repository, branch, previous.indexed_sha, effects)
        # Import may have flipped the row to `indexing` for the banner. Put
        # `ready` back and wake consoles so the overlay does not stick at 0%.
        await store.set_index_progress(
            conn, repository, branch, status="ready", progress_percent=PROGRESS_DONE
        )
        return HandlerResult(
            action=ACTION_REFERENCED,
            repository=repository,
            branch=branch,
            reason=f"already indexed at {previous.indexed_sha[:12]}",
            indexed_sha=previous.indexed_sha,
            reference_count=references,
            notified_projects=notified,
        )

    await store.set_index_progress(
        conn, repository, branch, status="indexing", progress_percent=PROGRESS_START
    )
    try:
        head = effects.resolve_head(repository, branch)
    except Exception as exc:
        await _mark_error(conn, repository, branch, exc)
        raise

    return await _index(
        conn,
        repository,
        branch,
        sha=head,
        changed=None,
        references=references,
        effects=effects,
    )


async def handle_repo_removed(
    conn: asyncpg.Connection, envelope: EventEnvelope, *, effects: Effects = DEFAULT_EFFECTS
) -> HandlerResult:
    """Release one reference on a target's shard.

    A decrement, never a delete: one project removing a repository must not
    blind the projects that still import it. The findings stay as history even
    at zero, because what a repository used at an earlier commit remains true.
    """
    repository = _require(envelope.payload, "repository")
    branch = _require(envelope.payload, "branch")

    references = await store.release_shard(conn, repository, branch)
    return HandlerResult(
        action=ACTION_RELEASED,
        repository=repository,
        branch=branch,
        reference_count=references,
        reason="shard is unreferenced" if references == 0 else None,
    )


async def handle_push(
    conn: asyncpg.Connection, envelope: EventEnvelope, *, effects: Effects = DEFAULT_EFFECTS
) -> HandlerResult:
    """Delta-index a pushed ref, then fan out to the projects that import it.

    The unimported-ref check runs before any git call. It is the cheapest branch
    in this module and the one that carries the push path: a busy repository
    pushes constantly to refs no project imported, and fetching first would
    queue the subscriber behind work whose answer nobody reads.
    """
    payload = envelope.payload
    repository = _require(payload, "repository")
    branch = _text(payload, "branch") or (branch_from_ref(_text(payload, "ref")) or "")
    after = _text(payload, "after_sha")
    before = _text(payload, "before_sha")

    if not branch:
        return HandlerResult(
            action=ACTION_DROPPED,
            repository=repository,
            branch="",
            reason="push does not name a branch",
        )
    if not after or after == NULL_SHA:
        # A deleted branch has no commit to index. Its findings are retired by
        # the removal path, which knows whether any project still wants them.
        return HandlerResult(
            action=ACTION_DROPPED,
            repository=repository,
            branch=branch,
            reason="push carries no head commit",
        )

    scopes = await store.projects_for(conn, repository, branch)
    if not scopes:
        return HandlerResult(
            action=ACTION_DROPPED,
            repository=repository,
            branch=branch,
            reason="no project imports this ref",
        )

    state = await store.load_state(conn, repository, branch)
    references = state.reference_count if state else len(scopes)
    if state is not None and state.status == "ready" and state.indexed_sha == after:
        return HandlerResult(
            action=ACTION_DROPPED,
            repository=repository,
            branch=branch,
            reason="already indexed at this sha",
            indexed_sha=after,
            reference_count=references,
        )

    changed: list[str] | None = None
    if _SHA_RE.match(before) and before != NULL_SHA:
        try:
            checkout = effects.ensure_checkout(repository, branch, after)
            changed = list(effects.changed_paths(checkout, before, after))
        except git.RevisionNotFoundError as exc:
            # A force-push or a rewritten history leaves no base to diff from.
            # Re-index the tree: more work, and still the right answer, where a
            # skipped delta would leave the inventory pinned at a dead commit.
            log.warning("no diff base for %s@%s (%s); re-indexing in full", repository, branch, exc)
            changed = None

    return await _index(
        conn,
        repository,
        branch,
        sha=after,
        changed=changed,
        references=references,
        effects=effects,
    )


def _covered(path_prefix: str | None, paths: Sequence[str]) -> tuple[str, ...]:
    """The subset of `paths` inside a project's workspace.

    `None` is the whole repository. The prefix is `workspaces.workspace_path`,
    and matching it as a path segment rather than as a string keeps `apps/web`
    from claiming `apps/webhooks`.
    """
    if path_prefix is None:
        return tuple(sorted(paths))
    prefix = path_prefix.strip("/")
    if not prefix:
        return tuple(sorted(paths))
    return tuple(sorted(p for p in paths if p == prefix or p.startswith(f"{prefix}/")))


def _index_paths(
    effects: Effects,
    provider: str,
    identifiers: Sequence[str],
    targets: Sequence[store.IndexTarget],
) -> dict[tuple[str, str], set[str]]:
    """One query across every shard, grouped back onto the targets it answers for.

    A shard built from a plain tree carries no branch metadata, so a match that
    names no branch is attributed to every imported branch of that repository —
    the same rule `search_shards` scopes by, and the direction that cannot turn
    a real finding into silence.
    """
    patterns = zoekt_patterns.patterns_for(provider, list(identifiers))
    refs = [ShardRef(repository=t.repository, branch=t.branch) for t in targets]
    matches = effects.search_shards(patterns, refs)

    found: dict[tuple[str, str], set[str]] = {}
    for match in matches:
        for target in targets:
            if target.repository != match.repository:
                continue
            if match.branch is not None and match.branch != target.branch:
                continue
            found.setdefault((target.repository, target.branch), set()).add(match.path)
    return found


async def _database_paths(
    conn: asyncpg.Connection,
    identifiers: Sequence[str],
    scopes_by_target: Mapping[tuple[str, str], Sequence[store.ProjectScope]],
) -> dict[tuple[str, str], set[str]]:
    """The same answer from `provider_usages`, for when the index is unreachable.

    Lower recall by construction — the table holds what a previous pass wrote,
    where the index also finds family members nobody enumerated — and that is
    the tolerable direction: a slower, narrower answer beats reporting a fleet
    as unaffected because a search server was down.

    Read through `usages_for_project`, so the workspace prefix filter is applied
    by the view that owns it rather than by this function.
    """
    project_ids = sorted(
        {scope.project_id for scopes in scopes_by_target.values() for scope in scopes}
    )
    found: dict[tuple[str, str], set[str]] = {}
    for project_id in project_ids:
        for usage in await store.usages_for_project(conn, project_id, list(identifiers)):
            key = (usage.repository, usage.branch)
            if key in scopes_by_target:
                found.setdefault(key, set()).add(usage.record.file_path)
    return found


async def handle_manifest(
    conn: asyncpg.Connection, envelope: EventEnvelope, *, effects: Effects = DEFAULT_EFFECTS
) -> ManifestResult:
    """Answer which `(project, repository)` pairs a change manifest reaches.

    No clone, no fetch, no per-project scan: the shards are already built, and
    "which of 2,000 repositories use this model ID" is one index query. When the
    index cannot answer, `provider_usages` does.

    Fails closed on a manifest that names no identifier: a manifest that watches
    nothing affects nothing, and widening that to "every finding" would open
    runs against the entire fleet.
    """
    payload = envelope.payload
    identifiers = _identifiers(payload, "affected_identifiers")
    if not identifiers:
        return ManifestResult(
            source=SOURCE_INDEX,
            affected=(),
            reason="manifest names no identifier",
        )
    provider = _text(payload, "provider") or DEFAULT_PROVIDER

    targets = await store.indexable_targets(conn)
    if not targets:
        return ManifestResult(
            source=SOURCE_DATABASE, affected=(), reason="no repository is imported"
        )

    scopes_by_target: dict[tuple[str, str], list[store.ProjectScope]] = {}
    for target in targets:
        scopes_by_target[(target.repository, target.branch)] = await store.projects_for(
            conn, target.repository, target.branch
        )

    source = SOURCE_INDEX
    reason: str | None = None
    if effects.index_backend != ZOEKT_BACKEND:
        source = SOURCE_DATABASE
        reason = f"index backend is {effects.index_backend!r}"
        found = await _database_paths(conn, identifiers, scopes_by_target)
    else:
        try:
            found = _index_paths(effects, provider, identifiers, targets)
        except (ZoektUnavailableError, ShardCorruptError, UnknownProviderError) as exc:
            log.warning("manifest query degraded to provider_usages: %s", exc)
            source = SOURCE_DATABASE
            reason = _error_text(exc)
            found = await _database_paths(conn, identifiers, scopes_by_target)

    affected: list[AffectedRepository] = []
    for key, scopes in scopes_by_target.items():
        paths = found.get(key)
        if not paths:
            continue
        repository, branch = key
        for scope in scopes:
            visible = _covered(scope.path_prefix, sorted(paths))
            if not visible:
                continue
            affected.append(
                AffectedRepository(
                    project_id=scope.project_id,
                    project_repository_id=scope.project_repository_id,
                    repository=repository,
                    branch=branch,
                    paths=visible,
                )
            )

    affected.sort(key=lambda item: (str(item.project_id), item.repository, item.branch))
    return ManifestResult(source=source, affected=tuple(affected), reason=reason)


Handler = Callable[..., Awaitable[HandlerResult | ManifestResult]]

# The events this worker acts on. A subscription whose type is absent here is a
# subscription nobody in this process can serve, which is a wiring error rather
# than something to discover at delivery time.
HANDLERS: Final[Mapping[EventType, Handler]] = MappingProxyType(
    {
        EventType.PROJECT_REPO_ADDED: handle_repo_added,
        EventType.PROJECT_REPO_REMOVED: handle_repo_removed,
        EventType.REPO_PUSH: handle_push,
        EventType.CHANGE_NORMALIZED: handle_manifest,
    }
)


async def dispatch(
    conn: asyncpg.Connection, envelope: EventEnvelope, *, effects: Effects = DEFAULT_EFFECTS
) -> HandlerResult | ManifestResult | None:
    """Route one envelope to its handler, or `None` when this worker serves none."""
    handler = HANDLERS.get(EventType(envelope.event_type))
    if handler is None:
        return None
    return await handler(conn, envelope, effects=effects)


__all__ = [
    "ACTION_DROPPED",
    "ACTION_INDEXED",
    "ACTION_REFERENCED",
    "ACTION_RELEASED",
    "HANDLERS",
    "NULL_SHA",
    "PROGRESS_DONE",
    "PROGRESS_FETCHED",
    "PROGRESS_SCANNED",
    "PROGRESS_START",
    "SOURCE_DATABASE",
    "SOURCE_INDEX",
    "AffectedRepository",
    "Effects",
    "EventPayloadError",
    "HandlerResult",
    "ManifestResult",
    "dispatch",
    "handle_manifest",
    "handle_push",
    "handle_repo_added",
    "handle_repo_removed",
    "resolve_head",
]
