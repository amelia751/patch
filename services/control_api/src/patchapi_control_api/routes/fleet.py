"""Governance view: which actors acted, and what was refused.

Denials are the product here. A blocked merge capability and a blocked write to
a forbidden path are the evidence that the narrow GitHub tool surface and the
policy allowlists actually hold, so they are served alongside the successes
rather than buried in a log.

What this route reports is *observed* behaviour from the audit trail. It is not
an Agent Registry capability listing (roadmap §12.1), and the response field
names say so: presenting observed actions as declared grants would overstate
what the enterprise has actually asserted about the fleet.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from patchapi_control_api.dependencies import get_dashboard_reader
from patchapi_control_api.models import FleetResponse
from patchapi_control_api.ports import DashboardReader

router = APIRouter(tags=["fleet"])

DEFAULT_DENIAL_LIMIT = 25
MAX_DENIAL_LIMIT = 200


@router.get("/fleet", response_model=FleetResponse, summary="Read fleet governance state")
async def read_fleet(
    reader: Annotated[DashboardReader, Depends(get_dashboard_reader)],
    limit: Annotated[int, Query(ge=1, le=MAX_DENIAL_LIMIT)] = DEFAULT_DENIAL_LIMIT,
) -> FleetResponse:
    snapshot = await reader.read_fleet_snapshot(limit=limit)
    return FleetResponse(
        observed_actors=snapshot.actors,
        denials=snapshot.denials,
        policy_versions=snapshot.policy_versions,
    )
