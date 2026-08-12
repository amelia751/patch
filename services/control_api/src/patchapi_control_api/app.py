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

from patchapi_control_api.config import API_PREFIX, SERVICE_NAME, SERVICE_VERSION
from patchapi_control_api.dependencies import EVENT_TRANSPORT, WORKFLOW_STATE_STORE
from patchapi_control_api.ports import (
    ProviderCheckDispatcher,
    ReadinessProbe,
    RunStateReader,
)
from patchapi_control_api.routes import health, providers, runs

_DESCRIPTION = (
    "Control plane for PatchAPI runs: manual provider checks, deterministic run "
    "state reads, and health probes. Never executes repository code."
)


def _wired_probe(name: str, dependency: object | None, missing: str) -> ReadinessProbe:
    """A probe that is satisfied only once `dependency` has been supplied."""

    async def check() -> str | None:
        return None if dependency is not None else missing

    return ReadinessProbe(name=name, check=check)


def create_app(
    *,
    provider_check_dispatcher: ProviderCheckDispatcher | None = None,
    run_state_reader: RunStateReader | None = None,
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
    app.state.readiness_probes = (
        _wired_probe(
            EVENT_TRANSPORT,
            provider_check_dispatcher,
            "no provider-check dispatcher is configured",
        ),
        _wired_probe(
            WORKFLOW_STATE_STORE,
            run_state_reader,
            "no authoritative run-state reader is configured",
        ),
        *extra_probes,
    )

    app.include_router(health.router)
    app.include_router(providers.router, prefix=API_PREFIX)
    app.include_router(runs.router, prefix=API_PREFIX)
    return app
