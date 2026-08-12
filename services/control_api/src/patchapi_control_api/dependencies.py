"""Resolution of the ports a request needs, or a fail-closed 503.

A handler asks for a dependency and either gets a working one or does not run.
There is no third branch where a route proceeds with a missing store and
returns something that looks like an answer.
"""

from typing import Final

from fastapi import Request

from patchapi_control_api.errors import dependency_unavailable
from patchapi_control_api.ports import (
    DashboardReader,
    ProviderCheckDispatcher,
    RunStateReader,
)

# Dependency labels shared by the readiness report and the 503 payloads, so an
# operator sees the same name in both places.
EVENT_TRANSPORT: Final[str] = "event_transport"
WORKFLOW_STATE_STORE: Final[str] = "workflow_state_store"
DASHBOARD_READ_MODEL: Final[str] = "dashboard_read_model"


def get_provider_check_dispatcher(request: Request) -> ProviderCheckDispatcher:
    dispatcher: ProviderCheckDispatcher | None = request.app.state.provider_check_dispatcher
    if dispatcher is None:
        raise dependency_unavailable(EVENT_TRANSPORT, "no provider-check dispatcher is configured")
    return dispatcher


def get_run_state_reader(request: Request) -> RunStateReader:
    reader: RunStateReader | None = request.app.state.run_state_reader
    if reader is None:
        raise dependency_unavailable(
            WORKFLOW_STATE_STORE, "no authoritative run-state reader is configured"
        )
    return reader


def get_dashboard_reader(request: Request) -> DashboardReader:
    reader: DashboardReader | None = request.app.state.dashboard_reader
    if reader is None:
        raise dependency_unavailable(DASHBOARD_READ_MODEL, "no dashboard read model is configured")
    return reader
