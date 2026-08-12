"""Read-only views of normalized provider changes.

A change event is the enterprise's record of something a provider published.
The provider text behind it is untrusted (constraint 4); this route serves the
normalized record and the source URLs that back it, so a reader can go check
the original rather than take the summary on faith.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from patchapi_control_api.dependencies import get_dashboard_reader
from patchapi_control_api.errors import change_not_found
from patchapi_control_api.models import ChangeListResponse
from patchapi_control_api.ports import ChangeRecord, DashboardReader

router = APIRouter(tags=["changes"])

# A dashboard page, not an export endpoint. Bounded so one request cannot ask
# the read model for the entire change history.
DEFAULT_CHANGE_LIMIT = 50
MAX_CHANGE_LIMIT = 200


@router.get("/changes", response_model=ChangeListResponse, summary="List provider changes")
async def list_changes(
    reader: Annotated[DashboardReader, Depends(get_dashboard_reader)],
    limit: Annotated[int, Query(ge=1, le=MAX_CHANGE_LIMIT)] = DEFAULT_CHANGE_LIMIT,
) -> ChangeListResponse:
    return ChangeListResponse(changes=await reader.list_changes(limit=limit))


@router.get(
    "/changes/{change_id}",
    response_model=ChangeRecord,
    summary="Read one provider change",
)
async def read_change(
    change_id: str,
    reader: Annotated[DashboardReader, Depends(get_dashboard_reader)],
) -> ChangeRecord:
    record = await reader.read_change(change_id)
    if record is None:
        raise change_not_found(change_id)
    return record
