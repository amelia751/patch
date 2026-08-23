"""Composition root: the control plane wired to authoritative Postgres.

This lives here rather than in `services/control_api` because of the dependency
direction. The control plane defines the ports and must not know which store
implements them; this package implements them and therefore already depends on
the control plane. Putting the wiring in the service would close that into a
cycle the workspace cannot resolve.

The provider-check dispatcher is wired only where a refresh job exists to run.
A local checkout has none, and `/readyz` reporting the transport as unwired is
the truth: a stub that accepted triggers and dropped them would make the
dashboard's "Check now" button report success for work nobody started.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from patchapi_control_api.app import create_app
from patchapi_control_api.dependencies import EVENT_TRANSPORT
from patchapi_control_api.errors import dependency_unavailable
from patchapi_control_api.ports import ReadinessProbe

from packages.state.auth_routes import router as auth_router
from packages.state.config import cors_origins, database_url
from packages.state.console_events import ConsoleHub, listen_console
from packages.state.dashboard import PostgresDashboardReader
from packages.state.evidence_routes import router as evidence_router
from packages.state.github_routes import router as github_router
from packages.state.notification_routes import router as notification_router
from packages.state.organization_routes import router as organization_router
from packages.state.pool import StateUnavailableError, create_pool, ping
from packages.state.project_routes import router as project_router
from packages.state.provider_check import RefreshJobUnavailableError, build_dispatcher
from packages.state.provider_routes import router as provider_router
from packages.state.runs import PostgresRunStateReader

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import FastAPI

# Reported by `/readyz` alongside the wiring probes, so an operator can tell a
# service that was never configured from one whose database went away.
POSTGRES_PROBE = "postgres"

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 8080


def build_app() -> FastAPI:
    """Build the control plane, connecting to Postgres during startup.

    The pool is opened in the lifespan rather than here because an asyncpg pool
    binds to the event loop that created it; one built on a different loop would
    fail on first use, after the service had already reported itself healthy.
    """
    # Fail before binding a port if the DSN is missing: a service that starts
    # and then answers every read with 503 is harder to diagnose than one that
    # refuses to start and says why.
    dsn = database_url()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = await create_pool(dsn)
        hub = ConsoleHub()
        app.state.run_state_reader = PostgresRunStateReader(pool)
        app.state.dashboard_reader = PostgresDashboardReader(pool)
        app.state.postgres_pool = pool
        app.state.console_hub = hub
        listener = asyncio.create_task(listen_console(pool, hub), name="patchapi-console-listen")
        try:
            from packages.auth.google_oauth import ensure_google_idp

            await ensure_google_idp()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning("google IdP enable skipped: %s", exc)
        try:
            yield
        finally:
            listener.cancel()
            with suppress(asyncio.CancelledError):
                await listener
            app.state.run_state_reader = None
            app.state.dashboard_reader = None
            app.state.postgres_pool = None
            app.state.console_hub = None
            await pool.close()

    app = create_app(
        allowed_origins=cors_origins(),
        provider_check_dispatcher=build_dispatcher(),
    )

    @app.exception_handler(RefreshJobUnavailableError)
    async def _refresh_unavailable(_request: Request, exc: RefreshJobUnavailableError) -> Response:
        # Mapped here rather than in the adapter: the adapter reports what Cloud
        # Run said, and only the composition root knows that answer is being
        # served over HTTP.
        error = dependency_unavailable(EVENT_TRANSPORT, str(exc))
        return JSONResponse(error.detail, status_code=error.status_code)

    app.include_router(auth_router)
    app.include_router(github_router)
    app.include_router(project_router)
    app.include_router(notification_router)
    app.include_router(organization_router)
    app.include_router(provider_router)
    app.include_router(evidence_router)
    app.state.readiness_probes = (
        *app.state.readiness_probes,
        ReadinessProbe(name=POSTGRES_PROBE, check=_postgres_probe(app)),
    )
    app.router.lifespan_context = lifespan
    return app


def _postgres_probe(app: FastAPI) -> Callable[[], Awaitable[str | None]]:
    """Build a readiness check that asks Postgres whether it is answering.

    Distinct from the wiring probes: those report whether a reader was supplied,
    this reports whether the database behind it still responds. A pool that was
    built successfully and has since become unreachable is not ready.
    """

    async def check() -> str | None:
        pool = getattr(app.state, "postgres_pool", None)
        if pool is None:
            return "no connection pool; the service has not completed startup"
        try:
            await ping(pool)
        except StateUnavailableError as exc:
            return str(exc)
        return None

    return check


def main() -> None:
    """Run the wired control plane until interrupted."""
    import uvicorn

    uvicorn.run(
        build_app(),
        host=os.environ.get("HOST", _DEFAULT_HOST),
        port=int(os.environ.get("PORT", _DEFAULT_PORT)),
        # Cloud Run terminates TLS in front of the container. Without these
        # flags Starlette builds `http://` callback URLs and GitHub refuses
        # the registered https redirect.
        proxy_headers=True,
        forwarded_allow_ips="*",
        # Never reload from a watched directory: reload imports whatever is on
        # disk, which is the opposite of the guarantee that the control plane
        # runs only code it shipped with.
        reload=False,
    )


if __name__ == "__main__":
    main()
