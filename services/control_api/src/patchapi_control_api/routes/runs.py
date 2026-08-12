"""Read-only access to deterministic run state.

Postgres is authoritative (roadmap §10.1). These routes report what the store
holds and what the shared transition table still permits; they never advance a
run, and they never answer from a cache when the store is unavailable.

`GET /runs/{run_id}` answers the narrow question an orchestrator asks — where
is this run. `GET /runs/{run_id}/detail` answers the question the dashboard
asks — what did this run actually do, and what evidence exists for it. They are
separate because the first must stay cheap enough to poll.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from packages.schemas.run_state import ALLOWED_RUN_STATE_TRANSITIONS, is_terminal
from patchapi_control_api.dependencies import get_dashboard_reader, get_run_state_reader
from patchapi_control_api.errors import run_not_found
from patchapi_control_api.models import RunDetailResponse, RunListResponse, RunStateResponse
from patchapi_control_api.ports import DashboardReader, RunStateReader

router = APIRouter(tags=["runs"])

DEFAULT_RUN_LIMIT = 50
MAX_RUN_LIMIT = 200


@router.get("/runs", response_model=RunListResponse, summary="List remediation runs")
async def list_runs(
    reader: Annotated[DashboardReader, Depends(get_dashboard_reader)],
    change_id: Annotated[str | None, Query()] = None,
    repository: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_RUN_LIMIT)] = DEFAULT_RUN_LIMIT,
) -> RunListResponse:
    runs = await reader.list_runs(change_id=change_id, repository=repository, limit=limit)
    return RunListResponse(runs=runs)


@router.get("/runs/{run_id}", response_model=RunStateResponse, summary="Read run state")
async def read_run(
    run_id: str,
    reader: Annotated[RunStateReader, Depends(get_run_state_reader)],
) -> RunStateResponse:
    record = await reader.read(run_id)
    if record is None:
        raise run_not_found(run_id)
    return RunStateResponse(
        run_id=record.run_id,
        state=record.state,
        repository=record.repository,
        base_sha=record.base_sha,
        updated_at=record.updated_at,
        reason=record.reason,
        terminal=is_terminal(record.state),
        allowed_next=tuple(sorted(ALLOWED_RUN_STATE_TRANSITIONS[record.state])),
    )


@router.get(
    "/runs/{run_id}/detail",
    response_model=RunDetailResponse,
    summary="Read one run's evidence bundle",
)
async def read_run_detail(
    run_id: str,
    reader: Annotated[DashboardReader, Depends(get_dashboard_reader)],
) -> RunDetailResponse:
    detail = await reader.read_run_detail(run_id)
    if detail is None:
        raise run_not_found(run_id)
    state = detail.summary.state
    return RunDetailResponse(
        detail=detail,
        terminal=is_terminal(state),
        allowed_next=tuple(sorted(ALLOWED_RUN_STATE_TRANSITIONS[state])),
    )
