"""Cloud Run HTTP surface for the indexer (`repo-indexer.md` §5.6).

Pub/Sub **push** delivers one envelope per request. That is the queue: a second
repository's import or push waits in the subscription while this instance is
busy, and Cloud Run starts another instance when concurrency allows. Same
`(repository, branch)` work is serialized with a Postgres advisory lock so two
pushes cannot interleave writes to one shard.

Ack is HTTP 204 after the handler commits. Anything else is a nack and Pub/Sub
redelivers.
"""

from __future__ import annotations

import base64
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from packages.events.envelope import EventEnvelope
from packages.state.config import database_url
from packages.state.pool import _configure
from patchapi_repo_indexer import worker
from patchapi_repo_indexer.github_token import ensure_installation_token

log = logging.getLogger(__name__)

HANDLER_TIMEOUT_SECONDS = 900.0


def _decode_push(body: dict[str, Any]) -> bytes:
    message = body.get("message")
    if not isinstance(message, dict):
        raise ValueError("Pub/Sub push is missing message")
    raw = message.get("data")
    if not isinstance(raw, str) or not raw:
        raise ValueError("Pub/Sub push is missing message.data")
    return base64.b64decode(raw)


async def _lock_target(conn: asyncpg.Connection, repository: str, branch: str) -> None:
    """Serialize work on one `(repository, branch)`. Other targets stay parallel."""
    await conn.execute(
        "SELECT pg_advisory_lock(hashtext($1), hashtext($2))",
        repository,
        branch or "-",
    )


async def _unlock_target(conn: asyncpg.Connection, repository: str, branch: str) -> None:
    await conn.execute(
        "SELECT pg_advisory_unlock(hashtext($1), hashtext($2))",
        repository,
        branch or "-",
    )


async def handle_push_body(
    pool: asyncpg.Pool, body: dict[str, Any]
) -> worker.HandlerResult | worker.ManifestResult | None:
    data = _decode_push(body)
    envelope = EventEnvelope.from_json(data.decode("utf-8"))
    repository = str(envelope.payload.get("repository") or "")
    branch = str(envelope.payload.get("branch") or "")
    ensure_installation_token(repository=repository or None)
    async with pool.acquire() as conn:
        locked = bool(repository)
        if locked:
            await _lock_target(conn, repository, branch)
        try:
            return await worker.dispatch(conn, envelope)
        finally:
            if locked:
                await _unlock_target(conn, repository, branch)


async def create_indexer_pool() -> asyncpg.Pool:
    """Own pool: advisory locks can wait out a sibling index of the same repo."""
    return await asyncpg.create_pool(
        database_url(),
        min_size=0,
        max_size=2,
        command_timeout=HANDLER_TIMEOUT_SECONDS,
        init=_configure,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=logging.INFO)
    app.state.pool = await create_indexer_pool()
    yield
    await app.state.pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="patchapi-repo-indexer", lifespan=lifespan)

    @app.get("/healthz")
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/events")
    async def receive_event(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"detail": "expected a JSON Pub/Sub push"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"detail": "expected a JSON object"}, status_code=400)
        try:
            outcome = await handle_push_body(request.app.state.pool, body)
        except Exception as exc:
            log.warning("event not handled, returning it to the subscription: %s", exc)
            return JSONResponse({"detail": type(exc).__name__}, status_code=500)
        log.info("handled event: %s", outcome)
        return Response(status_code=204)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "patchapi_repo_indexer.serve:app",
        host="0.0.0.0",
        port=port,
        timeout_keep_alive=int(HANDLER_TIMEOUT_SECONDS),
    )


if __name__ == "__main__":
    main()
