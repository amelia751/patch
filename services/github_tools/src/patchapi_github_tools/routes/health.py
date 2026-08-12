"""Liveness and readiness.

Readiness is the honest signal about credentials: with no GitHub App wired the
service still starts, serves its capability catalog, and refuses every
invocation with a 503 that names the missing dependency. It never reports ready.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from patchapi_github_tools.config import SERVICE_NAME, SERVICE_VERSION, environment
from patchapi_github_tools.dependencies import GITHUB_APP_INSTALLATION, optional_github_client
from patchapi_github_tools.github_rest import GitHubRest

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "environment": environment(),
    }


@router.get("/readyz", summary="Readiness probe")
async def readyz(
    github: Annotated[GitHubRest | None, Depends(optional_github_client)],
    response: Response,
) -> dict[str, object]:
    ready = github is not None
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "checks": [
            {
                "name": GITHUB_APP_INSTALLATION,
                "ready": ready,
                "reason": None if ready else "no GitHub App installation credentials are wired",
            }
        ],
    }
