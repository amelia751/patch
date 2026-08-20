"""Personal organization HTTP surface for the dashboard breadcrumb."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from packages.state.organizations import (
    read_personal_organization,
    update_personal_organization,
)
from packages.state.pool import StateUnavailableError
from packages.state.session import COOKIE_NAME, load_session_secret, parse

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


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


def _require_user(request: Request) -> UUID | JSONResponse:
    user_id = _session_user_id(request)
    if user_id is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return user_id


@router.get("/current")
async def get_current_organization(request: Request) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        return JSONResponse(await read_personal_organization(_pool(request), user_id))
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )


@router.get("")
@router.get("/")
async def list_organizations(request: Request) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        current = await read_personal_organization(_pool(request), user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    return JSONResponse([current])


@router.patch("/{organization_id}")
async def patch_organization(request: Request, organization_id: str) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    if organization_id != str(user_id):
        return JSONResponse({"detail": "Organization not found"}, status_code=404)
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}
    name = body.get("name")
    slug = body.get("slug")
    if name is not None and not isinstance(name, str):
        return JSONResponse({"detail": "name must be a string"}, status_code=400)
    if slug is not None and not isinstance(slug, str):
        return JSONResponse({"detail": "slug must be a string"}, status_code=400)
    try:
        return JSONResponse(
            await update_personal_organization(
                _pool(request), user_id, name=name, slug=slug
            )
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
