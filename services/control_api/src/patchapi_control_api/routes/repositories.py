"""Organization-wide exposure, read from the API usage inventory.

Roadmap §11: impact is an index lookup, not a fleet-wide clone-and-grep. This
route reports what the indexer already recorded, including the commit it was
recorded at, so a stale inventory is visible rather than silently presented as
the current state of the repository.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from patchapi_control_api.dependencies import get_dashboard_reader
from patchapi_control_api.models import RepositoryImpactResponse
from patchapi_control_api.ports import DashboardReader

router = APIRouter(tags=["repositories"])


@router.get(
    "/repositories",
    response_model=RepositoryImpactResponse,
    summary="List repository impact",
)
async def list_repository_impact(
    reader: Annotated[DashboardReader, Depends(get_dashboard_reader)],
    change_id: Annotated[str | None, Query()] = None,
) -> RepositoryImpactResponse:
    """Report each in-scope repository's exposure, affected or not.

    Without `change_id` the counts cover every identifier in the inventory;
    with one they are scoped to that change's affected identifiers.
    """
    return RepositoryImpactResponse(
        change_id=change_id,
        repositories=await reader.list_repository_impact(change_id=change_id),
    )
