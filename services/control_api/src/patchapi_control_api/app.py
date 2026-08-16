"""Application factory for the PatchAPI control plane.

Roadmap §7.2: this service receives webhooks, serves the dashboard, exposes the
manual trigger, and reads run state. It explicitly does not execute repository
code — no subprocess, no shell, no dynamic import of anything a run produced.
`tests/test_no_code_execution.py` enforces that against the source.

Dependencies are constructor arguments rather than module globals so a test —
and the local vertical slice — can wire fakes without patching, and so an
unwired dependency is a visible `None` that the routes refuse to work around.
"""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from patchapi_control_api.config import API_PREFIX, SERVICE_NAME, SERVICE_VERSION
from patchapi_control_api.dependencies import (
    DASHBOARD_READ_MODEL,
    EVENT_TRANSPORT,
    WORKFLOW_STATE_STORE,
)
from patchapi_control_api.ports import (
    DashboardReader,
    ProviderCheckDispatcher,
    ReadinessProbe,
    RunStateReader,
)
from patchapi_control_api.routes import (
    changes,
    fleet,
    github_webhooks,
    health,
    providers,
    repositories,
    runs,
)

_DESCRIPTION = (
    "Control plane for PatchAPI runs: manual provider checks, deterministic run "
    "state reads, and health probes. Never executes repository code."
)


def _wired_probe(app: FastAPI, name: str, attribute: str, missing: str) -> ReadinessProbe:
    """A probe satisfied only while `app.state.<attribute>` holds a dependency.

    The lookup happens per check rather than closing over the value passed to
    `create_app`, because a deployment may wire its ports during startup — a
    connection pool has to be built inside the loop that will serve requests.
    A probe that captured the constructor argument would report a fully wired
    service as permanently not ready.
    """

    async def check() -> str | None:
        return None if getattr(app.state, attribute, None) is not None else missing

    return ReadinessProbe(name=name, check=check)


def create_app(
    *,
    provider_check_dispatcher: ProviderCheckDispatcher | None = None,
    run_state_reader: RunStateReader | None = None,
    dashboard_reader: DashboardReader | None = None,
    allowed_origins: Sequence[str] = (),
    extra_probes: Sequence[ReadinessProbe] = (),
) -> FastAPI:
    """Build the ASGI application.

    With no ports supplied the app still serves `/healthz` and its OpenAPI
    document, reports `/readyz` as not ready, and answers every product route
    with a 503 naming the missing dependency.
    """
    app = FastAPI(
        title=SERVICE_NAME,
        version=SERVICE_VERSION,
        description=_DESCRIPTION,
    )
    app.state.provider_check_dispatcher = provider_check_dispatcher
    app.state.run_state_reader = run_state_reader
    app.state.dashboard_reader = dashboard_reader
    app.state.readiness_probes = (
        _wired_probe(
            app,
            EVENT_TRANSPORT,
            "provider_check_dispatcher",
            "no provider-check dispatcher is configured",
        ),
        _wired_probe(
            app,
            WORKFLOW_STATE_STORE,
            "run_state_reader",
            "no authoritative run-state reader is configured",
        ),
        _wired_probe(
            app,
            DASHBOARD_READ_MODEL,
            "dashboard_reader",
            "no dashboard read model is configured",
        ),
        *extra_probes,
    )

    # The dashboard is a separate origin in every environment: a local Next.js
    # dev server, and a hosted front end in deployed ones. Origins are supplied
    # explicitly and default to none, so an unconfigured deployment refuses
    # cross-origin reads rather than allowing any site to call this API.
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["content-type", "authorization", "last-event-id"],
        )

    app.include_router(health.router)
    app.include_router(providers.router, prefix=API_PREFIX)
    app.include_router(runs.router, prefix=API_PREFIX)
    app.include_router(changes.router, prefix=API_PREFIX)
    app.include_router(repositories.router, prefix=API_PREFIX)
    app.include_router(fleet.router, prefix=API_PREFIX)
    # Authenticated by its own HMAC rather than by a wired port: GitHub signs the
    # delivery, so this route works on an app with no dependencies supplied.
    app.include_router(github_webhooks.router, prefix=API_PREFIX)
    return app
