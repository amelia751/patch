"""The Cloud Run push receiver: decode, queue, ack or nack."""

from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

import pytest
from patchapi_repo_indexer import serve, worker

from packages.events.envelope import EventEnvelope
from packages.events.repo_events import project_repo_added_event, repo_push_event

OCCURRED_AT = "2026-08-13T00:00:00+00:00"


def _push_body(envelope) -> dict[str, Any]:
    encoded = base64.b64encode(envelope.to_json().encode("utf-8")).decode("ascii")
    return {
        "message": {"data": encoded, "messageId": "1"},
        "subscription": "projects/p/subscriptions/s",
    }


def test_decode_push_reads_the_envelope() -> None:
    envelope = repo_push_event(
        repository="amelia751/storygen",
        branch="main",
        before_sha="a" * 40,
        after_sha="b" * 40,
        installation_id=1,
        occurred_at=OCCURRED_AT,
    )
    raw = serve._decode_push(_push_body(envelope))
    assert b"repo-push" in raw
    assert b"amelia751/storygen" in raw


def test_decode_push_rejects_a_bare_object() -> None:
    with pytest.raises(ValueError):
        serve._decode_push({"hello": "world"})


def test_health_route_is_registered() -> None:
    app = serve.create_app()
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/healthz" in paths
    assert "/v1/events" in paths


class _FakeConn:
    def __init__(self) -> None:
        self.locks: list[tuple[str, str]] = []
        self.unlocks: list[tuple[str, str]] = []

    async def execute(self, sql: str, *args: object) -> str:
        if "pg_advisory_lock" in sql:
            self.locks.append((str(args[0]), str(args[1])))
        if "pg_advisory_unlock" in sql:
            self.unlocks.append((str(args[0]), str(args[1])))
        return "SELECT 1"


class _Acquire:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def acquire(self) -> _Acquire:
        return _Acquire(self._conn)


@pytest.mark.asyncio
async def test_handle_push_body_locks_per_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _FakeConn()
    pool = _FakePool(conn)
    seen: list[str] = []

    async def fake_dispatch(
        _conn: object, envelope: EventEnvelope, **_kwargs: object
    ) -> worker.HandlerResult:
        seen.append(envelope.event_type.value)
        return worker.HandlerResult(
            action=worker.ACTION_INDEXED,
            repository="amelia751/a",
            branch="main",
        )

    monkeypatch.setattr(serve.worker, "dispatch", fake_dispatch)
    monkeypatch.setattr(serve, "ensure_installation_token", lambda **_k: True)

    first = project_repo_added_event(
        project_id=str(uuid4()),
        repository="amelia751/a",
        branch="main",
        occurred_at=OCCURRED_AT,
    )
    second = project_repo_added_event(
        project_id=str(uuid4()),
        repository="amelia751/b",
        branch="main",
        occurred_at=OCCURRED_AT,
    )
    await serve.handle_push_body(pool, _push_body(first))  # type: ignore[arg-type]
    await serve.handle_push_body(pool, _push_body(second))  # type: ignore[arg-type]

    assert seen == ["project-repo-added", "project-repo-added"]
    assert conn.locks == [("amelia751/a", "main"), ("amelia751/b", "main")]
    assert conn.unlocks == conn.locks
