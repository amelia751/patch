"""The batch job opens its own connection, so it must configure its own codecs.

This failed in Cloud Run and nowhere else. Every other caller reaches Postgres
through `create_pool`, which registers the codecs in `init`; the refresh job
opens a single `asyncpg.connect` and inherited none of them. The shape of the
failure is the reason it is worth a test: the job polls every surface, works out
what changed, and only then dies on the first `jsonb` argument it writes.
"""

from __future__ import annotations

from typing import Any

import pytest

from packages.state import refresh


class FakeConnection:
    def __init__(self) -> None:
        self.codecs: list[str] = []
        self.closed = False

    async def set_type_codec(self, name: str, **_kwargs: Any) -> None:
        self.codecs.append(name)

    async def close(self) -> None:
        self.closed = True


async def test_the_job_registers_codecs_before_it_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    order: list[str] = []

    async def fake_connect(_dsn: str) -> FakeConnection:
        order.append("connect")
        return connection

    async def fake_refresh(conn: Any, *, provider: str) -> refresh.RefreshSummary:
        order.append("refresh")
        assert "jsonb" in conn.codecs, "the job reached its work without codecs"
        return refresh.RefreshSummary(provider=provider)

    import asyncpg

    monkeypatch.setattr(asyncpg, "connect", fake_connect)
    monkeypatch.setattr(refresh, "refresh_releases", fake_refresh)

    assert await refresh._run("google", "postgresql://unused") == refresh.EXIT_OK
    assert order == ["connect", "refresh"]
    assert connection.closed
    # jsonb and json both carry agent output; numeric is the confidence column.
    assert set(connection.codecs) == {"jsonb", "json", "numeric"}
