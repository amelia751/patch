"""Application factory for the GitHub tool service.

Roadmap §7.3 and §14: this service owns the GitHub App credentials so that
agents and sandboxes never do. It exposes the approved read and write
operations and nothing else — there is no merge route, no administration route,
no secret route, and no branch-protection route to disable, because none is
ever registered.

The GitHub client is a constructor argument. Started with none, the service is
fully inspectable — health, readiness, and the capability catalog all work —
and every invocation fails closed with 503.
"""

from fastapi import FastAPI

from patchapi_github_tools.config import API_PREFIX, SERVICE_NAME, SERVICE_VERSION
from patchapi_github_tools.github_rest import GitHubRest
from patchapi_github_tools.routes import capabilities, health

_DESCRIPTION = (
    "Narrow GitHub App capability adapter for PatchAPI. Agents receive "
    "capabilities, never tokens. Merge, administration, secret, and "
    "branch-protection operations are not part of this surface."
)


def create_app(*, github: GitHubRest | None = None) -> FastAPI:
    """Build the ASGI application around an optional GitHub client."""
    app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION, description=_DESCRIPTION)
    app.state.github = github
    app.include_router(health.router)
    app.include_router(capabilities.router, prefix=API_PREFIX)
    return app
