"""Liveness and readiness probes.

Deliberately unversioned: a platform health check must not have to follow an
API version bump.
"""

from fastapi import APIRouter, Request, Response, status

from patchapi_control_api.config import SERVICE_NAME, SERVICE_VERSION, environment
from patchapi_control_api.models import HealthResponse, ReadinessResponse
from patchapi_control_api.readiness import evaluate

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse, summary="Liveness probe")
async def healthz() -> HealthResponse:
    """Report that the process is serving. Touches no dependency."""
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        environment=environment(),
    )


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readyz(request: Request, response: Response) -> ReadinessResponse:
    """Report per-dependency readiness; 503 unless every probe is satisfied."""
    checks = await evaluate(request.app.state.readiness_probes)
    ready = all(check.ready for check in checks)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "not_ready",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        environment=environment(),
        checks=checks,
    )
