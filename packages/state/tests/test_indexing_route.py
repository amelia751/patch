"""The two HTTP surfaces the repo indexer needs, exercised through real routing.

`GET /api/projects/{id}/indexing` is driven against a fake pool: the query text
is asserted by `test_store.py` on a real database, and what matters here is the
rollup, the tenancy check, and the fail-closed 503.

The webhook cases live in this file rather than under `services/control_api`
because the two surfaces land together and one command has to cover both. They
go through `TestClient`, so the signature check runs where it will run in
production — inside FastAPI's request handling, on the raw body.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from patchapi_control_api.app import create_app
from patchapi_control_api.webhooks import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SECRET_VAR,
    SIGNATURE_HEADER,
    expected_signature,
    signature_matches,
)

from packages.events import EventType, TrustLevel
from packages.events.publisher import (
    DEFAULT_TOPIC_PREFIX,
    TOPIC_PREFIX_VAR,
    publish,
    topic_id,
    topic_path,
)
from packages.events.repo_events import branch_from_ref, repo_push_event
from packages.state.indexing import indexing_for_project, rollup
from packages.state.project_routes import router as project_router
from packages.state.session import COOKIE_NAME, issue

OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")
PROJECT_ID = UUID("33333333-3333-4333-8333-333333333333")
SESSION_SECRET = "test-session-secret"
WEBHOOK_SECRET = "test-webhook-secret"
AFTER_SHA = "c09e1a44200ff5e951746e013035e68aeb3a14b1"
BEFORE_SHA = "a" * 40


# --- indexing route ---------------------------------------------------------


class FakeConnection:
    """Answers the two queries `indexing_for_project` issues, in order."""

    def __init__(
        self, *, owner_id: UUID, rows: list[dict[str, Any]], error: Exception | None = None
    ):
        self._owner_id = owner_id
        self._rows = rows
        self._error = error
        self.queries: list[str] = []

    async def fetchval(self, query: str, *args: Any) -> int | None:
        self.queries.append(query)
        return 1 if args[1] == self._owner_id else None

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        if self._error is not None:
            raise self._error
        return self._rows


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def acquire(self) -> Any:
        connection = self._connection

        class _Acquire:
            async def __aenter__(self) -> FakeConnection:
                return connection

            async def __aexit__(self, *_: Any) -> bool:
                return False

        return _Acquire()


class UndefinedTable(Exception):
    """Stands in for `asyncpg.exceptions.UndefinedTableError`, which carries this sqlstate."""

    sqlstate = "42P01"


def repo_row(repository: str, branch: str, status: str, progress: int) -> dict[str, Any]:
    """A `repo_index_state` row as asyncpg would hand it back."""
    return {
        "repository": repository,
        "branch": branch,
        "status": status,
        "progress_percent": progress,
    }


def wire_row(status: str, progress: int) -> dict[str, Any]:
    """One repository as the route serializes it — `full_name`, not `repository`."""
    return {
        "full_name": "a/b",
        "branch": "main",
        "status": status,
        "progress_percent": progress,
    }


def indexing_client(connection: FakeConnection, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PATCHAPI_SESSION_SECRET", SESSION_SECRET)
    app = FastAPI()
    app.include_router(project_router)
    app.state.postgres_pool = FakePool(connection)
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(COOKIE_NAME, issue(OWNER_ID, SESSION_SECRET))
    return client


def test_indexing_route_returns_the_project_rollup(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection(
        owner_id=OWNER_ID,
        rows=[
            repo_row("amelia751/egaki", "main", "indexing", 20),
            repo_row("amelia751/patch", "main", "indexing", 80),
        ],
    )

    response = indexing_client(connection, monkeypatch).get(f"/api/projects/{PROJECT_ID}/indexing")

    assert response.status_code == 200
    assert response.json() == {
        "status": "indexing",
        "progress_percent": 50,
        "repositories": [
            {
                "full_name": "amelia751/egaki",
                "branch": "main",
                "status": "indexing",
                "progress_percent": 20,
            },
            {
                "full_name": "amelia751/patch",
                "branch": "main",
                "status": "indexing",
                "progress_percent": 80,
            },
        ],
    }


def test_indexing_route_requires_a_session(monkeypatch: pytest.MonkeyPatch) -> None:
    client = indexing_client(FakeConnection(owner_id=OWNER_ID, rows=[]), monkeypatch)
    client.cookies.clear()

    assert client.get(f"/api/projects/{PROJECT_ID}/indexing").status_code == 401


def test_indexing_route_hides_another_tenants_project(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection(owner_id=OTHER_ID, rows=[repo_row("x/y", "main", "ready", 100)])

    response = indexing_client(connection, monkeypatch).get(f"/api/projects/{PROJECT_ID}/indexing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


def test_indexing_route_reports_missing_indexer_tables_as_a_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(owner_id=OWNER_ID, rows=[], error=UndefinedTable())

    response = indexing_client(connection, monkeypatch).get(f"/api/projects/{PROJECT_ID}/indexing")

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "dependency_unavailable"
    assert body["dependency"] == "postgres"
    assert "0007_provider_usages.sql" in body["reason"]


async def test_indexing_for_project_returns_none_when_unowned() -> None:
    connection = FakeConnection(owner_id=OTHER_ID, rows=[])

    assert await indexing_for_project(FakePool(connection), PROJECT_ID, OWNER_ID) is None
    # The rollup query is never issued for a project the caller does not own.
    assert len(connection.queries) == 1


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([], ("idle", 0)),
        ([("ready", 100), ("ready", 100)], ("ready", 100)),
        ([("ready", 100), ("indexing", 40)], ("indexing", 40)),
        ([("error", 0), ("indexing", 50)], ("indexing", 50)),
        ([("error", 0), ("ready", 100)], ("error", 0)),
        ([("idle", 0), ("ready", 100)], ("idle", 0)),
        ([("indexing", 20), ("indexing", 81)], ("indexing", 51)),
    ],
)
def test_rollup_follows_the_documented_precedence(
    rows: list[tuple[str, int]], expected: tuple[str, int]
) -> None:
    repositories = [wire_row(status, progress) for status, progress in rows]

    assert rollup(repositories) == expected


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [("ready", 100)],
        [("ready", 100), ("indexing", 40)],
        [("error", 0), ("ready", 100)],
        [("idle", 0), ("ready", 100)],
        [("indexing", 20), ("indexing", 81)],
        [("error", 0), ("indexing", 50)],
    ],
)
def test_rollup_agrees_with_the_indexer(rows: list[tuple[str, int]]) -> None:
    """The duplicated rollup must not drift from the one the indexer ships."""
    store = pytest.importorskip(
        "patchapi_repo_indexer.store",
        reason="services/repo_indexer is not installed in this environment",
    )
    repositories = [wire_row(status, progress) for status, progress in rows]
    theirs = [
        store.RepositoryIndexing(
            repository=repo["full_name"],
            branch=repo["branch"],
            status=repo["status"],
            progress_percent=repo["progress_percent"],
        )
        for repo in repositories
    ]

    assert rollup(repositories) == store._rollup(theirs)


# --- webhook ----------------------------------------------------------------


class FakePublisher:
    """Stands in for `pubsub_v1.PublisherClient`, recording what was published."""

    def __init__(self, *, fail: bool = False) -> None:
        self.messages: list[tuple[str, bytes]] = []
        self._fail = fail

    def publish(self, topic: str, data: bytes) -> Any:
        if self._fail:
            raise RuntimeError("broker unreachable")
        self.messages.append((topic, data))

        class _Future:
            def result(self, timeout: float | None = None) -> str:
                return "message-1"

        return _Future()


@pytest.fixture
def publisher(monkeypatch: pytest.MonkeyPatch) -> FakePublisher:
    """Route every publish through a fake broker instead of GCP."""
    client = FakePublisher()
    monkeypatch.setattr("packages.events.publisher._client", lambda: client)
    monkeypatch.setenv("GCP_PROJECT", "patch-505223")
    monkeypatch.setenv(TOPIC_PREFIX_VAR, DEFAULT_TOPIC_PREFIX)
    return client


@pytest.fixture
def webhook_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv(SECRET_VAR, WEBHOOK_SECRET)
    return TestClient(create_app(), raise_server_exceptions=False)


def push_body(*, ref: str = "refs/heads/main", after: str = AFTER_SHA) -> bytes:
    return json.dumps(
        {
            "ref": ref,
            "before": BEFORE_SHA,
            "after": after,
            "repository": {"full_name": "amelia751/egaki", "private": False},
            "installation": {"id": 90210},
            # Present in a real delivery and deliberately not carried into the
            # event: commit content is not a scalar the transport may hold.
            "commits": [{"id": AFTER_SHA, "message": "swap the image model"}],
        }
    ).encode("utf-8")


def signed(body: bytes, event: str, *, delivery: str = "delivery-1") -> dict[str, str]:
    return {
        SIGNATURE_HEADER: expected_signature(WEBHOOK_SECRET, body),
        EVENT_HEADER: event,
        DELIVERY_HEADER: delivery,
        "content-type": "application/json",
    }


def test_ping_is_acknowledged(webhook_client: TestClient) -> None:
    body = b'{"zen": "Design for failure."}'

    response = webhook_client.post(
        "/v1/github/webhooks", content=body, headers=signed(body, "ping")
    )

    assert response.status_code == 200
    assert response.json()["enqueued"] is False


def test_push_is_accepted_and_published(
    webhook_client: TestClient, publisher: FakePublisher
) -> None:
    body = push_body()

    response = webhook_client.post(
        "/v1/github/webhooks", content=body, headers=signed(body, "push")
    )

    assert response.status_code == 202
    assert response.json() == {
        "event": "push",
        "delivery_id": "delivery-1",
        "enqueued": True,
        "reason": None,
    }
    topic, data = publisher.messages[0]
    assert topic == f"projects/patch-505223/topics/{DEFAULT_TOPIC_PREFIX}-repo-push"
    published = json.loads(data)
    assert published["event_type"] == EventType.REPO_PUSH.value
    assert published["payload"] == {
        "repository": "amelia751/egaki",
        "branch": "main",
        "before_sha": BEFORE_SHA,
        "after_sha": AFTER_SHA,
        "installation_id": 90210,
    }
    assert published["idempotency_key"] == f"repo-push:amelia751/egaki:main:{AFTER_SHA}"
    assert published["trust"] == TrustLevel.INTERNAL_ANALYSIS.value


def test_a_replayed_delivery_is_the_same_unit_of_work(publisher: FakePublisher) -> None:
    first = repo_push_event(
        repository="amelia751/egaki",
        branch="main",
        before_sha=BEFORE_SHA,
        after_sha=AFTER_SHA,
        installation_id=90210,
        occurred_at="2026-08-13T00:00:00+00:00",
    )
    later = repo_push_event(
        repository="amelia751/egaki",
        branch="main",
        before_sha=BEFORE_SHA,
        after_sha=AFTER_SHA,
        installation_id=90210,
        occurred_at="2026-08-13T00:05:00+00:00",
    )

    assert first.idempotency_key == later.idempotency_key
    assert first.run_id == later.run_id
    assert first.event_id == later.event_id


def test_an_unsigned_delivery_is_refused(webhook_client: TestClient) -> None:
    body = push_body()

    response = webhook_client.post(
        "/v1/github/webhooks", content=body, headers={EVENT_HEADER: "push"}
    )

    assert response.status_code == 401


def test_a_wrongly_signed_delivery_is_refused(
    webhook_client: TestClient, publisher: FakePublisher
) -> None:
    body = push_body()
    forged = hmac.new(b"not-the-secret", body, hashlib.sha256).hexdigest()

    response = webhook_client.post(
        "/v1/github/webhooks",
        content=body,
        headers={SIGNATURE_HEADER: f"sha256={forged}", EVENT_HEADER: "push"},
    )

    assert response.status_code == 401
    assert publisher.messages == []


def test_a_tampered_body_no_longer_verifies(webhook_client: TestClient) -> None:
    body = push_body()
    headers = signed(body, "push")

    response = webhook_client.post(
        "/v1/github/webhooks",
        content=push_body(after="b" * 40),
        headers=headers,
    )

    assert response.status_code == 401


def test_an_unconfigured_receiver_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SECRET_VAR, raising=False)
    monkeypatch.setenv("PATCHAPI_GITHUB_WEBHOOK_SECRET_FILE", "/nonexistent/webhook-secret.txt")
    client = TestClient(create_app(), raise_server_exceptions=False)
    body = push_body()

    response = client.post("/v1/github/webhooks", content=body, headers=signed(body, "push"))

    assert response.status_code == 503
    assert response.json()["detail"]["dependency"] == "github_webhook_secret"


def test_a_tag_push_is_acknowledged_without_indexing(
    webhook_client: TestClient, publisher: FakePublisher
) -> None:
    body = push_body(ref="refs/tags/v1.0.0")

    response = webhook_client.post(
        "/v1/github/webhooks", content=body, headers=signed(body, "push")
    )

    assert response.status_code == 202
    assert response.json()["enqueued"] is False
    assert publisher.messages == []


def test_a_deleted_branch_is_acknowledged_without_indexing(
    webhook_client: TestClient, publisher: FakePublisher
) -> None:
    body = push_body(after="0" * 40)

    response = webhook_client.post(
        "/v1/github/webhooks", content=body, headers=signed(body, "push")
    )

    assert response.status_code == 202
    assert response.json()["reason"] == "branch was deleted"
    assert publisher.messages == []


def test_an_unsubscribed_event_is_acknowledged_and_ignored(
    webhook_client: TestClient, publisher: FakePublisher
) -> None:
    body = b"{}"

    response = webhook_client.post(
        "/v1/github/webhooks", content=body, headers=signed(body, "pull_request")
    )

    assert response.status_code == 202
    assert response.json()["enqueued"] is False
    assert publisher.messages == []


def test_a_push_without_a_repository_is_rejected(webhook_client: TestClient) -> None:
    body = json.dumps({"ref": "refs/heads/main", "after": AFTER_SHA}).encode("utf-8")

    response = webhook_client.post(
        "/v1/github/webhooks", content=body, headers=signed(body, "push")
    )

    assert response.status_code == 400


def test_an_unreachable_broker_still_accepts_the_delivery(
    webhook_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Losing Pub/Sub must not make GitHub retry a delivery already decided about."""
    monkeypatch.setattr("packages.events.publisher._client", lambda: FakePublisher(fail=True))
    monkeypatch.setenv("GCP_PROJECT", "patch-505223")
    body = push_body()

    response = webhook_client.post(
        "/v1/github/webhooks", content=body, headers=signed(body, "push")
    )

    assert response.status_code == 202
    assert response.json()["enqueued"] is False


# --- publishing primitives --------------------------------------------------


def test_topics_are_derived_from_the_configured_prefix() -> None:
    env = {TOPIC_PREFIX_VAR: "patchapi-prod", "GCP_PROJECT": "patch-505223"}

    assert topic_id(EventType.REPO_PUSH, env) == "patchapi-prod-repo-push"
    assert topic_id(EventType.PROJECT_REPO_ADDED, env) == "patchapi-prod-project-repo-added"
    assert (
        topic_path(EventType.REPO_PUSH, env)
        == "projects/patch-505223/topics/patchapi-prod-repo-push"
    )


def test_publishing_without_a_project_fails_soft() -> None:
    result = publish(
        repo_push_event(
            repository="amelia751/egaki",
            branch="main",
            before_sha=BEFORE_SHA,
            after_sha=AFTER_SHA,
            installation_id=None,
            occurred_at="2026-08-13T00:00:00+00:00",
        ),
        env={},
    )

    assert result.published is False
    assert "no GCP project configured" in (result.reason or "")


def test_signature_helper_rejects_a_malformed_header() -> None:
    body = b"{}"

    assert signature_matches(WEBHOOK_SECRET, body, expected_signature(WEBHOOK_SECRET, body))
    assert not signature_matches(WEBHOOK_SECRET, body, None)
    assert not signature_matches(WEBHOOK_SECRET, body, "sha1=deadbeef")
    assert not signature_matches(WEBHOOK_SECRET, body, "deadbeef")


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("refs/heads/main", "main"),
        ("refs/heads/feature/imagen-migration", "feature/imagen-migration"),
        ("refs/tags/v1.0.0", None),
        ("refs/heads/", None),
        ("main", None),
    ],
)
def test_branch_is_read_only_from_a_branch_ref(ref: str, expected: str | None) -> None:
    assert branch_from_ref(ref) == expected


# --- project-repo-added -----------------------------------------------------


async def test_importing_a_repository_announces_it(publisher: FakePublisher) -> None:
    from packages.state.projects import announce_repository_added

    published = await announce_repository_added(uuid4(), "amelia751/egaki", "main")

    assert published is True
    topic, data = publisher.messages[0]
    assert topic == f"projects/patch-505223/topics/{DEFAULT_TOPIC_PREFIX}-project-repo-added"
    event = json.loads(data)
    assert event["event_type"] == EventType.PROJECT_REPO_ADDED.value
    assert set(event["payload"]) == {"project_id", "repository", "branch"}
    assert event["payload"]["repository"] == "amelia751/egaki"
    assert event["payload"]["branch"] == "main"


async def test_an_import_survives_a_broken_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """The row is authoritative; a publish failure is reported, never raised."""
    from packages.state.projects import announce_repository_added

    monkeypatch.setattr("packages.events.publisher._client", lambda: FakePublisher(fail=True))
    monkeypatch.setenv("GCP_PROJECT", "patch-505223")

    assert await announce_repository_added(uuid4(), "amelia751/egaki", "main") is False
