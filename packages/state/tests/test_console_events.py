"""Console SSE hub and the `/events` snapshot contract."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.events.console_notify import EVENT_INDEXING, encode_notify
from packages.state.console_events import (
    SSE_INDEXING,
    SSE_SNAPSHOT,
    ConsoleHub,
    emit_from_notify,
    project_event_stream,
    sse_bytes,
)
from packages.state.project_routes import router as project_router
from packages.state.session import COOKIE_NAME, issue

OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")
PROJECT_ID = UUID("33333333-3333-4333-8333-333333333333")
SESSION_SECRET = "test-session-secret"


class FakeConnection:
    def __init__(self, *, owner_id: UUID, rows: list[dict[str, Any]]) -> None:
        self._owner_id = owner_id
        self._rows = rows
        self.queries: list[str] = []

    async def fetchval(self, query: str, *args: Any) -> int | None:
        self.queries.append(query)
        return 1 if args[1] == self._owner_id else None

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        if "project_notifications" in query:
            return []
        return self._rows

    async def execute(self, query: str, *args: Any) -> str:
        self.queries.append(query)
        return "OK"


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


def events_client(connection: FakeConnection, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PATCHAPI_SESSION_SECRET", SESSION_SECRET)
    app = FastAPI()
    app.include_router(project_router)
    app.state.postgres_pool = FakePool(connection)
    app.state.console_hub = ConsoleHub()
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set(COOKIE_NAME, issue(OWNER_ID, SESSION_SECRET))
    return client


def test_hub_delivers_only_to_the_named_project() -> None:
    hub = ConsoleHub()
    mine = hub.subscribe(PROJECT_ID)
    other = hub.subscribe(OTHER_ID)
    payload = {"status": "indexing", "progress_percent": 40, "repositories": []}
    hub.publish(PROJECT_ID, SSE_INDEXING, payload)
    assert mine.get_nowait() == (SSE_INDEXING, payload)
    assert other.empty()


def test_sse_frame_is_a_named_event() -> None:
    frame = sse_bytes(SSE_INDEXING, {"status": "indexing"}).decode()
    assert frame.startswith("event: indexing\n")
    assert 'data: {"status": "indexing"}' in frame
    assert frame.endswith("\n\n")


def test_events_route_requires_a_session(monkeypatch: pytest.MonkeyPatch) -> None:
    client = events_client(FakeConnection(owner_id=OWNER_ID, rows=[]), monkeypatch)
    client.cookies.clear()
    assert client.get(f"/api/projects/{PROJECT_ID}/events").status_code == 401


def test_events_route_hides_another_tenants_project(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection(
        owner_id=OTHER_ID,
        rows=[
            {
                "repository": "a/b",
                "branch": "main",
                "status": "indexing",
                "progress_percent": 40,
            }
        ],
    )
    response = events_client(connection, monkeypatch).get(f"/api/projects/{PROJECT_ID}/events")
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}


async def test_event_stream_opens_with_a_snapshot_then_stops() -> None:
    """TestClient.stream waits for the generator to finish; this does not."""
    hub = ConsoleHub()
    disconnected = False

    async def is_disconnected() -> bool:
        return disconnected

    initial = {
        "indexing": {
            "status": "indexing",
            "progress_percent": 47,
            "repositories": [
                {
                    "full_name": "amelia751/egaki",
                    "branch": "main",
                    "status": "indexing",
                    "progress_percent": 47,
                }
            ],
        },
        "notifications": [],
    }
    gen = project_event_stream(
        request_is_disconnected=is_disconnected,
        pool=FakePool(FakeConnection(owner_id=OWNER_ID, rows=[])),  # type: ignore[arg-type]
        hub=hub,
        project_id=PROJECT_ID,
        initial=initial,
    )
    first = await anext(gen)
    disconnected = True
    rest = [chunk async for chunk in gen]

    frame = first.decode()
    assert frame.startswith(f"event: {SSE_SNAPSHOT}\n")
    payload = json.loads(frame.split("data: ", 1)[1].strip())
    assert payload == initial
    assert rest == []
    assert not hub.subscribed(PROJECT_ID)


async def test_emit_from_notify_pushes_indexing_when_subscribed() -> None:
    hub = ConsoleHub()
    queue = hub.subscribe(PROJECT_ID)
    connection = FakeConnection(
        owner_id=OWNER_ID,
        rows=[
            {
                "repository": "amelia751/egaki",
                "branch": "main",
                "status": "indexing",
                "progress_percent": 25,
            }
        ],
    )
    await emit_from_notify(
        FakePool(connection),  # type: ignore[arg-type]
        hub,
        encode_notify(event_type=EVENT_INDEXING, project_id=PROJECT_ID),
    )
    event, data = queue.get_nowait()
    assert event == SSE_INDEXING
    assert data["status"] == "indexing"
    assert data["progress_percent"] == 25


async def test_emit_from_notify_skips_projects_with_no_listener() -> None:
    hub = ConsoleHub()
    connection = FakeConnection(owner_id=OWNER_ID, rows=[])
    await emit_from_notify(
        FakePool(connection),  # type: ignore[arg-type]
        hub,
        encode_notify(event_type=EVENT_INDEXING, project_id=PROJECT_ID),
    )
    assert connection.queries == []
