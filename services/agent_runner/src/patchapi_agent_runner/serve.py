"""Cloud Run HTTP surface for the agent lane.

Pub/Sub push delivers one `change-normalized` envelope per request and a turn
takes far longer than an index write, so the subscription carries a long ack
deadline and this process answers 204 only after the rationale is committed.

A delivery this lane cannot serve is still acked. The deterministic lane has
already produced a correct finding, so redelivering an event that will refuse
again buys nothing and costs a turn.
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

from packages.events.config import EventType
from packages.events.envelope import EventEnvelope
from packages.state.config import database_url
from packages.state.pool import _configure
from patchapi_agent_runner import runner

log = logging.getLogger(__name__)

# A turn calls the model, the probe, and web search. Cloud Run request timeout
# and the subscription ack deadline are set to match.
HANDLER_TIMEOUT_SECONDS = 600.0


def _decode_push(body: dict[str, Any]) -> bytes:
    message = body.get("message")
    if not isinstance(message, dict):
        raise ValueError("Pub/Sub push is missing message")
    raw = message.get("data")
    if not isinstance(raw, str) or not raw:
        raise ValueError("Pub/Sub push is missing message.data")
    return base64.b64decode(raw)


async def handle_push_body(pool: asyncpg.Pool, body: dict[str, Any]) -> runner.RunOutcome:
    data = _decode_push(body)
    envelope = EventEnvelope.from_json(data.decode("utf-8"))
    if EventType(envelope.event_type) is not EventType.CHANGE_NORMALIZED:
        return runner.RunOutcome.skipped("", f"{envelope.event_type} is not served here")
    async with pool.acquire() as connection:
        return await runner.run_change_intelligence(connection, envelope)


async def create_agent_pool() -> asyncpg.Pool:
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
    app.state.pool = await create_agent_pool()
    yield
    await app.state.pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="patchapi-agents", lifespan=lifespan)

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
        "patchapi_agent_runner.serve:app",
        host="0.0.0.0",
        port=port,
        timeout_keep_alive=int(HANDLER_TIMEOUT_SECONDS),
    )


if __name__ == "__main__":
    main()
