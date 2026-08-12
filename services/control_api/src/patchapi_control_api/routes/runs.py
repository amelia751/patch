"""Read-only access to deterministic run state.

Postgres is authoritative (roadmap §10.1). This route reports what the store
holds and what the shared transition table still permits; it never advances a
run, and it never answers from a cache when the store is unavailable.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from packages.schemas.run_state import ALLOWED_RUN_STATE_TRANSITIONS, is_terminal
from patchapi_control_api.dependencies import get_run_state_reader
from patchapi_control_api.errors import run_not_found
from patchapi_control_api.models import RunStateResponse
from patchapi_control_api.ports import RunStateReader

router = APIRouter(tags=["runs"])


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
