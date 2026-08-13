"""Console project HTTP surface: create, list, import a GitHub repo."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from packages.auth.config import load_config
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError
from packages.auth.github_oauth import (
    GitHubResourceError,
    fetch_repository_file,
    fetch_repository_tree,
)
from packages.state.codebase import codebase_payload, imported_repo, safe_repo_path
from packages.state.console_events import (
    ConsoleHub,
    project_event_stream,
)
from packages.state.indexing import indexing_for_project
from packages.state.notifications import notifications_snapshot
from packages.state.pool import StateUnavailableError
from packages.state.projects import (
    add_repository,
    create_project,
    delete_project,
    import_repo_workspace,
    list_projects,
    read_project,
    update_project_name,
)
from packages.state.session import COOKIE_NAME, load_session_secret, parse
from packages.state.users import read_github_connection

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _hub(request: Request) -> ConsoleHub:
    hub = getattr(request.app.state, "console_hub", None)
    if hub is None:
        hub = ConsoleHub()
        request.app.state.console_hub = hub
    return hub


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


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _github_failure(exc: AuthConfigurationError | AuthUnavailableError) -> JSONResponse:
    if isinstance(exc, AuthConfigurationError):
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "github_app",
                "reason": "GitHub App private key is not configured",
            },
            status_code=503,
        )
    return JSONResponse(
        {"error": "dependency_unavailable", "dependency": "github", "reason": str(exc)},
        status_code=503,
    )


@router.get("/{project_id}/indexing")
async def get_owned_project_indexing(request: Request, project_id: UUID) -> JSONResponse:
    """The Codebase tab's indexing banner.

    Live updates arrive on `GET /events`. This GET remains for the first paint
    and for the poll fallback if the EventSource drops. Unreachable Postgres —
    or a database the indexer's migration has not been applied to — answers 503
    naming the dependency rather than `idle`: a banner that hid itself because
    the read failed would report an unindexed repository as one with nothing
    to find.
    """
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        indexing = await indexing_for_project(_pool(request), project_id, user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if indexing is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse(indexing)


@router.get("/{project_id}/events", response_model=None)
async def stream_owned_project_events(
    request: Request, project_id: UUID
) -> JSONResponse | StreamingResponse:
    """Live console stream: snapshot on connect, then indexing and notifications.

    The browser never holds Pub/Sub credentials. This is cookie-authenticated
    SSE. A dropped stream is the dashboard's cue to poll `/indexing` and
    `/api/notifications` until it reconnects.
    """
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        indexing = await indexing_for_project(_pool(request), project_id, user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if indexing is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    try:
        notifications = await notifications_snapshot(_pool(request), project_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    return StreamingResponse(
        project_event_stream(
            request_is_disconnected=request.is_disconnected,
            pool=_pool(request),
            hub=_hub(request),
            project_id=project_id,
            initial={"indexing": indexing, "notifications": notifications},
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{project_id}/codebase/file")
async def get_owned_codebase_file(
    request: Request, project_id: UUID, path: str = "", ref: str | None = None
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    safe_path = safe_repo_path(path)
    if safe_path is None:
        return JSONResponse({"detail": "path is required"}, status_code=400)
    try:
        project = await read_project(_pool(request), project_id, user_id)
        connection = await read_github_connection(_pool(request), user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if project is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    source = imported_repo(project)
    if source is None:
        return JSONResponse({"detail": "Project has no imported repository"}, status_code=404)
    if connection is None:
        return JSONResponse({"detail": "GitHub App is not installed"}, status_code=409)
    owner, repo, default_branch = source
    config = load_config()
    try:
        file = await fetch_repository_file(
            config,
            connection["installation_id"],
            owner=owner,
            repo=repo,
            path=safe_path,
            ref=(ref or "").strip() or default_branch,
        )
    except GitHubResourceError:
        return JSONResponse({"detail": "File not found"}, status_code=404)
    except (AuthConfigurationError, AuthUnavailableError) as exc:
        return _github_failure(exc)
    return JSONResponse(file)


@router.get("/{project_id}/codebase")
async def get_owned_codebase(
    request: Request, project_id: UUID, ref: str | None = None
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await read_project(_pool(request), project_id, user_id)
        connection = await read_github_connection(_pool(request), user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if project is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    source = imported_repo(project)
    if source is None:
        return JSONResponse({"detail": "Project has no imported repository"}, status_code=404)
    if connection is None:
        return JSONResponse({"detail": "GitHub App is not installed"}, status_code=409)
    owner, repo, default_branch = source
    config = load_config()
    try:
        tree = await fetch_repository_tree(
            config,
            connection["installation_id"],
            owner=owner,
            repo=repo,
            ref=(ref or "").strip() or default_branch,
        )
    except GitHubResourceError:
        return JSONResponse({"detail": "Codebase not found"}, status_code=404)
    except (AuthConfigurationError, AuthUnavailableError) as exc:
        return _github_failure(exc)
    return JSONResponse(codebase_payload(tree))


@router.get("")
@router.get("/")
async def list_owned_projects(request: Request) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        projects = await list_projects(_pool(request), user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    return JSONResponse({"projects": projects})


@router.post("")
@router.post("/")
async def create_owned_project(request: Request) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    name = str(body.get("name") or "").strip()
    if not name:
        return JSONResponse({"detail": "Project name cannot be empty"}, status_code=400)
    try:
        project = await create_project(_pool(request), user_id, name)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    return JSONResponse(project, status_code=201)


@router.get("/{project_id}")
async def get_owned_project(request: Request, project_id: UUID) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await read_project(_pool(request), project_id, user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if project is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse(project)


@router.put("/{project_id}")
async def rename_owned_project(request: Request, project_id: UUID) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    name = str(body.get("name") or "").strip()
    if not name:
        return JSONResponse({"detail": "Project name cannot be empty"}, status_code=400)
    try:
        project = await update_project_name(_pool(request), project_id, user_id, name)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if project is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse(project)


@router.delete("/{project_id}")
async def delete_owned_project(request: Request, project_id: UUID) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        deleted = await delete_project(_pool(request), project_id, user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if not deleted:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.post("/{project_id}/workspaces/import-repo")
async def import_owned_repo(request: Request, project_id: UUID) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    try:
        project = await import_repo_workspace(
            _pool(request),
            project_id,
            user_id,
            name=str(body.get("name") or ""),
            repo_url=str(body.get("repo_url") or ""),
            repo_branch=str(body.get("repo_branch") or "main"),
            workspace_path=(str(body["workspace_path"]) if body.get("workspace_path") else None),
            environment=str(body.get("environment") or "dev"),
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if project is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse(project)


@router.post("/{project_id}/repositories")
async def add_owned_repository(request: Request, project_id: UUID) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    full_name = str(body.get("github_repo_full_name") or "").strip()
    if not full_name:
        return JSONResponse({"detail": "github_repo_full_name is required"}, status_code=400)
    try:
        project = await add_repository(
            _pool(request),
            project_id,
            user_id,
            github_repo_full_name=full_name,
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if project is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse(project)
