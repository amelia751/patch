"""Dashboard GitHub import: list repositories the signed-in installation can see.

Tokens are minted per request and never stored. The session cookie identifies
the console user; `github_connections` identifies the App installation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from packages.auth.config import load_config
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError
from packages.auth.github_oauth import list_installation_repositories
from packages.state.pool import StateUnavailableError
from packages.state.session import COOKIE_NAME, load_session_secret, parse
from packages.state.users import read_github_connection

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/github", tags=["github"])


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "postgres_pool", None)
    if pool is None:
        raise StateUnavailableError("no connection pool; the service has not completed startup")
    return pool


def _session_user_id(request: Request) -> UUID | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            raw = auth[7:].strip()
    if not raw:
        return None
    return parse(raw, load_session_secret())


@router.get("/repos")
async def list_repos(request: Request) -> JSONResponse:
    """Return repositories visible to the signed-in user's GitHub App install."""
    user_id = _session_user_id(request)
    if user_id is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    try:
        connection = await read_github_connection(_pool(request), user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if connection is None:
        return JSONResponse({"detail": "GitHub App is not installed"}, status_code=409)
    config = load_config()
    try:
        repos = await list_installation_repositories(config, connection["installation_id"])
    except AuthConfigurationError:
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "github_app",
                "reason": "GitHub App private key is not configured",
            },
            status_code=503,
        )
    except AuthUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "github", "reason": str(exc)},
            status_code=503,
        )
    return JSONResponse(repos)
