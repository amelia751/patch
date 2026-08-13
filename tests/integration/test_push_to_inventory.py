"""A signed GitHub push, end to end, from the HTTP edge to `provider_usages`.

`repo-indexer.md` §9 asks for one test that crosses every seam in the push path:
the receiver's HMAC check, the envelope on the wire, the worker's state machine,
and the rows in Postgres. The unit suites each own one side of that boundary —
`services/control_api` stops at the publisher and `services/repo_indexer`
starts at an envelope it constructs itself — so a receiver that published a
differently shaped payload than the worker reads would pass both and fail in
production. Here the envelope the route publishes is the one the worker consumes.

Git and the scanner are stubbed, for the same reason the worker's own suite
stubs them: this test is about the seams, not about cloning GitHub over the
network. Everything between the signature and the row is real, including the
authoritative store.

Requires `DATABASE_URL` pointing at a database with migration 0007 applied;
skipped otherwise rather than passing on a path it never exercised.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient
from patchapi_control_api.app import create_app
from patchapi_control_api.routes import github_webhooks
from patchapi_repo_indexer import store, worker
from patchapi_repo_indexer.models import ApiUsageInventory, ApiUsageRecord

from packages.events.config import EventType
from packages.events.envelope import EventEnvelope
from packages.events.publisher import PublishResult
from packages.repo_scan.classify import UsageKind

DSN = os.environ.get("DATABASE_URL", "").strip()

requires_postgres = pytest.mark.skipif(
    not DSN,
    reason="DATABASE_URL is unset; the push path needs Postgres with migration 0007 applied",
)

WEBHOOK_PATH = "/v1/github/webhooks"
SECRET = "integration-webhook-secret"
IDENTIFIER = "imagen-4.0-generate-001"
BRANCH = "main"
BEFORE_SHA = "a" * 40
AFTER_SHA = "b" * 40
NULL_SHA = "0" * 40


# --------------------------------------------------------------------------- #
# The receiver
# --------------------------------------------------------------------------- #


class CapturingPublisher:
    """Stands in for Pub/Sub and keeps what the route handed the transport."""

    def __init__(self) -> None:
        self.envelopes: list[EventEnvelope] = []

    async def __call__(self, envelope: EventEnvelope) -> PublishResult:
        self.envelopes.append(envelope)
        return PublishResult(
            event_type=EventType(envelope.event_type),
            event_id=envelope.event_id,
            topic="test-topic",
            published=True,
        )


@pytest.fixture
def publisher(monkeypatch: pytest.MonkeyPatch) -> CapturingPublisher:
    monkeypatch.setenv("PATCHAPI_GITHUB_WEBHOOK_SECRET", SECRET)
    capture = CapturingPublisher()
    monkeypatch.setattr(github_webhooks, "publish_async", capture)
    return capture


@pytest.fixture
def client() -> TestClient:
    # No ports: the webhook route depends on none of them, and an unwired app
    # proves the receiver does not quietly reach for the dashboard's readers.
    return TestClient(create_app(), raise_server_exceptions=False)


def push_body(repository: str, *, branch: str = BRANCH, after: str = AFTER_SHA) -> bytes:
    return json.dumps(
        {
            "ref": f"refs/heads/{branch}",
            "before": BEFORE_SHA,
            "after": after,
            "repository": {"full_name": repository},
            "installation": {"id": 42},
        }
    ).encode()


def deliver(client: TestClient, body: bytes, *, event: str = "push", secret: str = SECRET) -> Any:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        WEBHOOK_PATH,
        content=body,
        headers={
            "X-Hub-Signature-256": f"sha256={digest}",
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": uuid4().hex,
            "Content-Type": "application/json",
        },
    )


# --------------------------------------------------------------------------- #
# The worker's collaborators
# --------------------------------------------------------------------------- #


class StubWorld:
    """Git and the scanner, recorded rather than performed."""

    def __init__(self, usages: tuple[ApiUsageRecord, ...]) -> None:
        self.usages = usages
        self.checkouts: list[tuple[str, str, str]] = []
        self.diffs: list[tuple[str, str]] = []
        self.inventories: list[dict[str, Any]] = []
        self.changed: list[str] = ["src/app.ts"]

    @property
    def touched(self) -> bool:
        return bool(self.checkouts or self.diffs or self.inventories)

    def resolve_head(self, repository: str, branch: str) -> str:
        return AFTER_SHA

    def ensure_checkout(self, repository: str, branch: str, sha: str) -> Path:
        self.checkouts.append((repository, branch, sha))
        return Path("/tmp/patchapi-integration-checkout")

    def changed_paths(self, repo_path: Path, base_sha: str, head_sha: str) -> list[str]:
        self.diffs.append((base_sha, head_sha))
        return list(self.changed)

    def build_inventory(self, **kwargs: Any) -> ApiUsageInventory:
        self.inventories.append(kwargs)
        changed = kwargs.get("changed_paths")
        return ApiUsageInventory(
            repository=kwargs["repository"],
            branch=kwargs["branch"],
            observed_sha=kwargs["observed_sha"],
            provider="google",
            watched_identifiers=(IDENTIFIER,),
            scope="full_tree" if changed is None else "changed_paths",
            files_scanned=3 if changed is None else len(changed),
            usages=self.usages,
        )


def usage(path: str, line: int = 3) -> ApiUsageRecord:
    return ApiUsageRecord(
        provider="google",
        identifier=IDENTIFIER,
        file_path=path,
        line_start=line,
        usage_kind=UsageKind.RUNTIME_SOURCE,
        confidence=1.0,
        excerpt=f'const MODEL = "{IDENTIFIER}";',
    )


def effects_for(world: StubWorld) -> worker.Effects:
    async def publish(envelope: EventEnvelope) -> PublishResult:
        return PublishResult(
            event_type=EventType(envelope.event_type),
            event_id=envelope.event_id,
            topic="test-topic",
            published=True,
        )

    return worker.Effects(
        resolve_head=world.resolve_head,
        ensure_checkout=world.ensure_checkout,
        changed_paths=world.changed_paths,
        build_inventory=world.build_inventory,
        publish=publish,
        index_backend="literal",
    )


# --------------------------------------------------------------------------- #
# Postgres
# --------------------------------------------------------------------------- #


@pytest.fixture
async def conn() -> Any:
    """A connection whose transaction is always rolled back.

    The suite can therefore point at the same instance the console uses without
    leaving test repositories in the inventory.
    """
    connection = await asyncpg.connect(DSN)
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


async def import_repository(conn: Any, full_name: str) -> UUID:
    owner_id = await conn.fetchval(
        "INSERT INTO users (email, display_name) VALUES ($1, $2) RETURNING id",
        f"{uuid4().hex}@integration.test",
        "Push Integration",
    )
    project_id = await conn.fetchval(
        "INSERT INTO projects (owner_id, name) VALUES ($1, $2) RETURNING id",
        owner_id,
        "push-to-inventory",
    )
    await conn.execute(
        """
        INSERT INTO project_repositories (project_id, name, full_name, default_branch)
        VALUES ($1, $2, $3, $4)
        """,
        project_id,
        full_name.split("/")[-1],
        full_name,
        BRANCH,
    )
    return project_id


async def live_usages(conn: Any, repository: str) -> list[tuple[str, int]]:
    rows = await conn.fetch(
        """
        SELECT file_path, line_start FROM provider_usages
        WHERE repository = $1 AND retired_at IS NULL
        ORDER BY file_path, line_start
        """,
        repository,
    )
    return [(row["file_path"], row["line_start"]) for row in rows]


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_unsigned_delivery_is_refused_before_the_body_is_read(
    client: TestClient, publisher: CapturingPublisher
) -> None:
    body = push_body("acme/platform")
    response = client.post(
        WEBHOOK_PATH,
        content=body,
        headers={"X-GitHub-Event": "push", "Content-Type": "application/json"},
    )
    assert response.status_code == 401
    assert publisher.envelopes == [], "an unsigned delivery reached the topic"


def test_wrongly_signed_delivery_is_refused(
    client: TestClient, publisher: CapturingPublisher
) -> None:
    response = deliver(client, push_body("acme/platform"), secret="not-the-secret")
    assert response.status_code == 401
    assert publisher.envelopes == []


def test_deleted_branch_is_acknowledged_without_enqueuing(
    client: TestClient, publisher: CapturingPublisher
) -> None:
    response = deliver(client, push_body("acme/platform", after=NULL_SHA))
    assert response.status_code == 202
    assert response.json()["enqueued"] is False
    assert publisher.envelopes == [], "a branch deletion was queued as index work"


@requires_postgres
async def test_signed_push_lands_in_provider_usages(
    conn: Any, client: TestClient, publisher: CapturingPublisher
) -> None:
    """The full seam: signature → envelope → worker → rows."""
    repository = f"patchapi-test/{uuid4().hex}"
    project_id = await import_repository(conn, repository)

    response = deliver(client, push_body(repository))
    assert response.status_code == 202
    assert response.json()["enqueued"] is True
    assert len(publisher.envelopes) == 1

    envelope = publisher.envelopes[0]
    assert envelope.event_type == EventType.REPO_PUSH.value
    # The receiver must name the branch, not the ref: the worker looks up
    # imported branches, and `refs/heads/main` matches nothing.
    assert envelope.payload["branch"] == BRANCH
    assert envelope.payload["repository"] == repository
    assert envelope.payload["after_sha"] == AFTER_SHA

    world = StubWorld((usage("src/app.ts"), usage("src/legacy.ts")))
    result = await worker.handle_push(conn, envelope, effects=effects_for(world))

    assert result.action == worker.ACTION_INDEXED
    assert str(project_id) in result.notified_projects
    assert await live_usages(conn, repository) == [("src/app.ts", 3), ("src/legacy.ts", 3)]

    state = await store.load_state(conn, repository, BRANCH)
    assert state is not None
    assert (state.status, state.progress_percent, state.indexed_sha) == ("ready", 100, AFTER_SHA)


@requires_postgres
async def test_redelivery_of_the_same_push_changes_no_rows(
    conn: Any, client: TestClient, publisher: CapturingPublisher
) -> None:
    """Pub/Sub is at-least-once, so a replayed push must be a no-op."""
    repository = f"patchapi-test/{uuid4().hex}"
    await import_repository(conn, repository)

    deliver(client, push_body(repository))
    envelope = publisher.envelopes[0]

    world = StubWorld((usage("src/app.ts"),))
    effects = effects_for(world)
    await worker.handle_push(conn, envelope, effects=effects)
    first = await live_usages(conn, repository)

    replay = await worker.handle_push(conn, envelope, effects=effects)
    assert replay.action == worker.ACTION_INDEXED
    assert replay.paths_retired == 0
    assert await live_usages(conn, repository) == first


@requires_postgres
async def test_push_to_an_unimported_branch_is_dropped_before_any_fetch(
    conn: Any, client: TestClient, publisher: CapturingPublisher
) -> None:
    """The §7.2 early return: no clone, no diff, no scan, and no state row.

    This is the branch that carries the push path for a busy repository, so a
    regression here is a subscriber that queues behind work nobody reads.
    """
    repository = f"patchapi-test/{uuid4().hex}"
    await import_repository(conn, repository)

    deliver(client, push_body(repository, branch="feature/nobody-imported-this"))
    envelope = publisher.envelopes[0]
    assert envelope.payload["branch"] == "feature/nobody-imported-this"

    world = StubWorld((usage("src/app.ts"),))
    result = await worker.handle_push(conn, envelope, effects=effects_for(world))

    assert result.action == worker.ACTION_DROPPED
    assert not world.touched, "an unimported ref reached git or the scanner"
    assert await live_usages(conn, repository) == []
    assert await store.load_state(conn, repository, "feature/nobody-imported-this") is None
