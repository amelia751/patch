"""The manual "check this provider for changes" trigger.

This route validates the request, derives the idempotency key, and hands the
command to the event transport. It does not fetch provider content, does not
decide impact, and does not run anything from a customer repository — provider
material is untrusted input handled downstream by the Change Intelligence
Agent (roadmap §8.1).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from patchapi_control_api.dependencies import get_provider_check_dispatcher
from patchapi_control_api.errors import dispatch_integrity
from patchapi_control_api.idempotency import provider_check_key
from patchapi_control_api.models import ProviderCheckRequest, ProviderCheckResponse
from patchapi_control_api.ports import ProviderCheckCommand, ProviderCheckDispatcher

router = APIRouter(tags=["providers"])


@router.post(
    "/provider-checks",
    response_model=ProviderCheckResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a provider change check",
)
async def request_provider_check(
    payload: ProviderCheckRequest,
    dispatcher: Annotated[ProviderCheckDispatcher, Depends(get_provider_check_dispatcher)],
) -> ProviderCheckResponse:
    """Enqueue one provider check, or acknowledge an already-enqueued replay."""
    command = ProviderCheckCommand(
        provider_id=payload.provider_id,
        since=payload.since,
        requested_by=payload.requested_by,
        idempotency_key=provider_check_key(payload.provider_id, payload.since),
    )
    dispatched = await dispatcher.dispatch(command)
    if dispatched.idempotency_key != command.idempotency_key:
        raise dispatch_integrity(command.idempotency_key, dispatched.idempotency_key)
    return ProviderCheckResponse(
        provider_id=command.provider_id,
        idempotency_key=dispatched.idempotency_key,
        created=dispatched.created,
        run_id=dispatched.run_id,
    )
