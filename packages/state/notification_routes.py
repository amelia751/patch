"""Console notification HTTP surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from packages.state.notifications import apply_notification_action, list_notifications
from packages.state.pool import StateUnavailableError
from packages.state.session import COOKIE_NAME, load_session_secret, parse

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


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


def _project_id(raw: str | None) -> UUID | JSONResponse:
    if not raw:
        return JSONResponse({"detail": "project_id is required"}, status_code=400)
    try:
        return UUID(raw)
    except ValueError:
        return JSONResponse({"detail": "project_id is not a valid id"}, status_code=400)


@router.get("")
@router.get("/")
async def get_notifications(
    request: Request, project_id: str | None = None, limit: int = 20
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    pid = _project_id(project_id)
    if isinstance(pid, JSONResponse):
        return pid
    try:
        items = await list_notifications(
            _pool(request), project_id=pid, owner_id=user_id, limit=limit
        )
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if items is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse({"notifications": items})


@router.post("/{notification_id}/action")
async def post_notification_action(
    request: Request, notification_id: UUID, project_id: str | None = None
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    pid = _project_id(project_id)
    if isinstance(pid, JSONResponse):
        return pid
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    body: dict[str, Any] = payload if isinstance(payload, dict) else {}
    action_type = str(body.get("action_type") or "read").strip() or "read"
    try:
        result = await apply_notification_action(
            _pool(request),
            project_id=pid,
            owner_id=user_id,
            notification_id=notification_id,
            action_type=action_type,
        )
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if result is None:
        return JSONResponse({"detail": "Notification not found"}, status_code=404)
    return JSONResponse(result)
