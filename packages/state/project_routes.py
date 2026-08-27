"""Console project HTTP surface: create, list, import a GitHub repo."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
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
from packages.schemas.run_state import RunState
from packages.state.codebase import (
    codebase_payload_from_repos,
    imported_repos,
    resolve_codebase_file,
)
from packages.state.console_events import (
    ConsoleHub,
    project_event_stream,
)
from packages.state.findings import (
    backfill_project,
    inbox_payload,
    set_finding_status,
)
from packages.state.gcp_connections import (
    GcpConnectionError,
    connection_record,
    delete_connection,
    list_connections,
    reveal_connection,
    update_connection,
    upsert_connection,
)
from packages.state.gcp_viewer import GcpViewerError, list_cloud_run_services
from packages.state.indexing import (
    enqueue_idle_imports,
    indexing_for_project,
    requeue_project_imports,
)
from packages.state.notifications import notifications_snapshot
from packages.state.pool import StateUnavailableError
from packages.state.projects import (
    add_repository,
    create_project,
    delete_project,
    import_repo_workspace,
    list_projects,
    read_project,
    remove_repository,
    update_project_cloud_provider,
    update_project_name,
)
from packages.state.providers import (
    ProviderStoreError,
    list_project_subscriptions,
    list_providers,
    subscribe_project,
    unsubscribe_project,
)
from packages.state.remediation import (
    advance,
    append_trace,
    open_run,
    resolve_target,
)
from packages.state.remediation import (
    list_runs as list_remediation_runs,
)
from packages.state.remediation import (
    read_run as read_remediation_run,
)
from packages.state.run_dispatch import (
    RemediationUnavailableError,
    provisioning_note,
)
from packages.state.run_dispatch import (
    build_dispatcher as build_remediation_dispatcher,
)
from packages.state.secret_manager import GoogleSecretVault, SecretStoreError, gcp_project
from packages.state.secrets import (
    SecretInputError,
    delete_secret,
    list_secrets,
    upsert_secret,
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


def _jsonable(value: Any) -> Any:
    """Render database rows as JSON without a model for every projection.

    Run detail is a bundle of eight small reads whose shape is set by the
    console, not by a contract another service consumes. Declaring Pydantic
    models for each would add a second place to change every time a column is
    added, and nothing would be checking that the two agreed.
    """
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


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
    repos = indexing.get("repositories") or []
    if any(repo.get("status") == "idle" for repo in repos):
        await enqueue_idle_imports(_pool(request), project_id)
        try:
            indexing = await indexing_for_project(_pool(request), project_id, user_id) or indexing
        except StateUnavailableError:
            pass
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
    request: Request,
    project_id: UUID,
    path: str = "",
    ref: str | None = None,
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    if not path.strip():
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
    source = resolve_codebase_file(project, path)
    if source is None:
        return JSONResponse({"detail": "Project has no imported repository"}, status_code=404)
    if connection is None:
        return JSONResponse({"detail": "GitHub App is not installed"}, status_code=409)
    owner, repo_name, default_branch, relative = source
    config = load_config()
    try:
        file = await fetch_repository_file(
            config,
            connection["installation_id"],
            owner=owner,
            repo=repo_name,
            path=relative,
            ref=(ref or "").strip() or default_branch,
        )
    except GitHubResourceError:
        return JSONResponse({"detail": "File not found"}, status_code=404)
    except (AuthConfigurationError, AuthUnavailableError) as exc:
        return _github_failure(exc)
    return JSONResponse(file)


@router.get("/{project_id}/codebase")
async def get_owned_codebase(
    request: Request,
    project_id: UUID,
    ref: str | None = None,
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
    sources = imported_repos(project)
    if not sources:
        return JSONResponse({"detail": "Project has no imported repository"}, status_code=404)
    if connection is None:
        return JSONResponse({"detail": "GitHub App is not installed"}, status_code=409)
    config = load_config()
    override = (ref or "").strip()

    async def _tree(
        source: tuple[str, str, str, str],
    ) -> tuple[str, dict[str, Any] | None, Exception | None]:
        name, owner, repo_name, default_branch = source
        try:
            tree = await fetch_repository_tree(
                config,
                connection["installation_id"],
                owner=owner,
                repo=repo_name,
                ref=override or default_branch,
            )
        except GitHubResourceError as exc:
            return name, None, exc
        except (AuthConfigurationError, AuthUnavailableError) as exc:
            return name, None, exc
        return name, tree, None

    results = await asyncio.gather(*[_tree(source) for source in sources])
    empty_tree = {
        "entries": [],
        "ref": override or "main",
        "default_branch": "main",
        "full_name": "",
        "sha": "",
        "truncated": False,
    }
    named: list[tuple[str, dict[str, Any]]] = []
    auth_failure: AuthConfigurationError | AuthUnavailableError | None = None
    fetched = 0
    for name, tree, exc in results:
        if tree is not None:
            named.append((name, tree))
            fetched += 1
            continue
        if isinstance(exc, (AuthConfigurationError, AuthUnavailableError)):
            auth_failure = exc
        # Keep every imported repo in the payload. Dropping a failed fetch
        # collapses two imports into a flat first-repo tree, and the Codebase
        # tab then has no `directory` roots to render.
        named.append((name, dict(empty_tree)))
    if fetched == 0:
        if auth_failure is not None:
            return _github_failure(auth_failure)
        return JSONResponse({"detail": "Codebase not found"}, status_code=404)
    return JSONResponse(codebase_payload_from_repos(named))


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


@router.patch("/{project_id}/cloud-provider")
async def update_owned_project_cloud_provider(request: Request, project_id: UUID) -> JSONResponse:
    """Set or clear `projects.cloud_provider`. Same contract as JetRun."""
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    if "cloud_provider" not in body:
        return JSONResponse({"detail": "cloud_provider is required"}, status_code=400)
    raw = body.get("cloud_provider")
    if raw is not None and not isinstance(raw, str):
        return JSONResponse(
            {"detail": "Invalid cloud provider. Must be 'aws', 'gcp', or null to clear"},
            status_code=400,
        )
    provider = raw.strip().lower() if isinstance(raw, str) else None
    if provider == "":
        provider = None
    try:
        project = await update_project_cloud_provider(
            _pool(request),
            project_id,
            user_id,
            cloud_provider=provider,
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


@router.delete("/{project_id}/repositories/{repo_name:path}")
async def disconnect_owned_repository(
    request: Request, project_id: UUID, repo_name: str
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await remove_repository(
            _pool(request),
            project_id,
            user_id,
            repo_name=repo_name,
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if project is None:
        return JSONResponse({"detail": "Repository not found"}, status_code=404)
    return JSONResponse({"ok": True})


def _vault() -> GoogleSecretVault | JSONResponse:
    try:
        return GoogleSecretVault(gcp_project())
    except SecretStoreError as exc:
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "secret_manager",
                "reason": str(exc),
            },
            status_code=503,
        )


def _workspace_scope(raw: str | None) -> tuple[UUID | None, bool] | JSONResponse:
    """Parse the optional workspace filter the Secrets tab sends.

    `_shared` means `workspace_id IS NULL`. A missing value matches the unique
    `(project_id, secret_name)` row.
    """
    if raw is None or not raw.strip():
        return None, False
    value = raw.strip()
    if value in {"_shared", "__shared__"}:
        return None, True
    try:
        return UUID(value), False
    except ValueError:
        return JSONResponse({"detail": "workspace_id must be a UUID or _shared"}, status_code=400)


@router.get("/{project_id}/secrets")
async def list_owned_secrets(request: Request, project_id: UUID) -> JSONResponse:
    """Configured secret *names* and Secret Manager pointers. Never payloads."""
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        rows = await list_secrets(_pool(request), project_id, user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if rows is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse({"secrets": rows})


@router.post("/{project_id}/secrets")
async def upsert_owned_secret(request: Request, project_id: UUID) -> JSONResponse:
    """Accept a value once, write Secret Manager, persist only the pointer."""
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    name = str(body.get("secret_name") or "").strip()
    value = body.get("secret_value")
    if not isinstance(value, str):
        return JSONResponse({"detail": "secret_value is required"}, status_code=400)
    workspace_raw = body.get("workspace_id")
    workspace_id: UUID | None = None
    if workspace_raw not in (None, "", "__shared__", "_shared"):
        try:
            workspace_id = UUID(str(workspace_raw))
        except ValueError:
            return JSONResponse({"detail": "workspace_id must be a UUID"}, status_code=400)
    vault = _vault()
    if isinstance(vault, JSONResponse):
        return vault
    try:
        row = await upsert_secret(
            _pool(request),
            project_id,
            user_id,
            secret_name=name,
            secret_value=value,
            vault=vault,
            workspace_id=workspace_id,
            secret_type=str(body.get("type") or "api_key"),
        )
    except SecretInputError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except SecretStoreError as exc:
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "secret_manager",
                "reason": str(exc),
            },
            status_code=503,
        )
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if row is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse(row, status_code=201)


@router.delete("/{project_id}/secrets/{secret_name}")
async def delete_owned_secret(request: Request, project_id: UUID, secret_name: str) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    scope = _workspace_scope(request.query_params.get("workspace_id"))
    if isinstance(scope, JSONResponse):
        return scope
    workspace_id, shared = scope
    vault = _vault()
    if isinstance(vault, JSONResponse):
        return vault
    try:
        deleted = await delete_secret(
            _pool(request),
            project_id,
            user_id,
            secret_name=secret_name,
            vault=vault,
            workspace_id=workspace_id,
            shared=shared,
        )
    except SecretInputError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except SecretStoreError as exc:
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "secret_manager",
                "reason": str(exc),
            },
            status_code=503,
        )
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if deleted is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    if not deleted:
        return JSONResponse({"detail": "Secret not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.get("/{project_id}/providers")
async def get_project_providers(request: Request, project_id: UUID) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await read_project(_pool(request), project_id, user_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)
        catalog = await list_providers(_pool(request))
        subscribed = await list_project_subscriptions(_pool(request), project_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    watching = {row["slug"]: row.get("subscribed_at") for row in subscribed}
    offers = [
        {
            **row,
            "subscribed": row["slug"] in watching,
            "subscribed_at": watching.get(row["slug"]),
        }
        for row in catalog
    ]
    return JSONResponse({"providers": offers})


@router.put("/{project_id}/providers/{slug}")
async def put_project_provider(request: Request, project_id: UUID, slug: str) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await read_project(_pool(request), project_id, user_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)
        await subscribe_project(_pool(request), project_id, slug)
        try:
            async with _pool(request).acquire() as connection:
                result = await backfill_project(connection, project_id, slug)
            await requeue_project_imports(_pool(request), project_id)
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "42P01":
                return JSONResponse(
                    {
                        "error": "dependency_unavailable",
                        "dependency": "postgres",
                        "reason": "change findings tables are missing",
                    },
                    status_code=503,
                )
            raise
    except ProviderStoreError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    return JSONResponse({"ok": True, **result})


@router.get("/{project_id}/changes")
async def get_project_changes(request: Request, project_id: UUID) -> JSONResponse:
    """Project inbox: watchlist notes joined to this project's inventory."""
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await read_project(_pool(request), project_id, user_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)
        async with _pool(request).acquire() as connection:
            payload = await inbox_payload(connection, project_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    except Exception as exc:
        if getattr(exc, "sqlstate", None) == "42P01":
            return JSONResponse(
                {
                    "error": "dependency_unavailable",
                    "dependency": "postgres",
                    "reason": "change findings tables are missing",
                },
                status_code=503,
            )
        raise
    return JSONResponse(payload)


@router.post("/{project_id}/changes/{external_id}/dismiss")
async def dismiss_project_change(
    request: Request, project_id: UUID, external_id: str
) -> JSONResponse:
    return await _set_change_status(request, project_id, external_id, status="dismissed")


@router.post("/{project_id}/changes/{external_id}/reopen")
async def reopen_project_change(
    request: Request, project_id: UUID, external_id: str
) -> JSONResponse:
    return await _set_change_status(request, project_id, external_id, status="watching")


async def _set_change_status(
    request: Request, project_id: UUID, external_id: str, *, status: str
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await read_project(_pool(request), project_id, user_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)
        async with _pool(request).acquire() as connection:
            updated = await set_finding_status(
                connection, project_id, external_id, status=status, user_id=user_id
            )
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if updated is None:
        return JSONResponse({"detail": "Change not found"}, status_code=404)
    return JSONResponse(updated)


# ------------------------------------------------------------ remediation ---


@router.post("/{project_id}/changes/{external_id}/remediate")
async def start_remediation(request: Request, project_id: UUID, external_id: str) -> JSONResponse:
    """Begin, or rejoin, the remediation of one change in one repository.

    The run row is written before anything is dispatched, and the row is unique
    per change and repository. That ordering is what makes the button safe to
    press twice: the second press finds the run the first one opened and starts
    no second execution, so one change cannot become two pull requests.

    A repository this project does not use is answered as nothing to remediate
    rather than as a run against a tree PatchAPI never indexed.
    """
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    repository = str(body.get("repository") or "").strip()

    try:
        project = await read_project(_pool(request), project_id, user_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)
        async with _pool(request).acquire() as connection:
            target = await resolve_target(
                connection,
                external_id=external_id,
                project_id=project_id,
                repository=repository,
            )
            if target is None:
                return JSONResponse({"detail": "Change not found"}, status_code=404)
            change_event_id, resolved_repo, base_sha = target
            if not resolved_repo:
                return JSONResponse(
                    {
                        "detail": "No indexed repository in this project uses that change",
                        "error": "nothing_to_remediate",
                    },
                    status_code=409,
                )
            handle = await open_run(
                connection,
                change_event_id=change_event_id,
                project_id=project_id,
                repository=resolved_repo,
                base_sha=base_sha,
                trace_id=f"run-{external_id}",
            )
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )

    payload: dict[str, Any] = {
        "run_id": handle.run_id,
        "state": str(handle.state),
        "repository": handle.repository,
        "base_sha": handle.base_sha,
        "change_id": external_id,
        "dispatched": False,
    }
    if not handle.dispatch:
        # Already in flight. The console opens the existing run rather than
        # being told nothing happened.
        return JSONResponse(payload, status_code=200)

    dispatcher = build_remediation_dispatcher()
    if dispatcher is None:
        async with _pool(request).acquire() as connection:
            await advance(
                connection,
                handle.run_id,
                RunState.FAILED,
                actor="console",
                reason="no remediation runner is configured for this deployment",
            )
        return JSONResponse(
            {
                **payload,
                "error": "runner_unavailable",
                "detail": "This deployment has no remediation runner configured",
            },
            status_code=503,
        )

    try:
        execution = await dispatcher.dispatch(handle.run_id)
    except RemediationUnavailableError as exc:
        # The run row stays, marked with why nothing picked it up. A row left at
        # RECEIVED with no executor would look like a run that is about to start.
        async with _pool(request).acquire() as connection:
            await advance(
                connection,
                handle.run_id,
                RunState.FAILED,
                actor="console",
                reason=str(exc),
            )
        return JSONResponse(
            {**payload, "error": "dispatch_failed", "detail": str(exc)}, status_code=502
        )

    async with _pool(request).acquire() as connection:
        await append_trace(
            connection,
            handle.run_id,
            state=RunState.RECEIVED,
            kind="narration",
            body=(
                f"Dispatched to {dispatcher.transport}"
                + (f" ({execution})" if execution else "")
                + ". Waiting for the remediator to claim this run."
            ),
        )

    return JSONResponse(
        {**payload, "dispatched": True, "execution": execution, "transport": dispatcher.transport},
        status_code=202,
    )


@router.get("/{project_id}/runs")
async def list_project_runs(request: Request, project_id: UUID) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await read_project(_pool(request), project_id, user_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)
        async with _pool(request).acquire() as connection:
            rows = await list_remediation_runs(connection, project_id=project_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    return JSONResponse({"runs": _jsonable(rows)})


@router.get("/{project_id}/runs/{run_id}")
async def read_project_run(request: Request, project_id: UUID, run_id: str) -> JSONResponse:
    """One run and its evidence. `since` returns only newer worklog lines."""
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        since = int(request.query_params.get("since") or 0)
    except ValueError:
        since = 0
    try:
        identifier = UUID(run_id)
    except ValueError:
        return JSONResponse({"detail": "Run not found"}, status_code=404)

    try:
        project = await read_project(_pool(request), project_id, user_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)
        async with _pool(request).acquire() as connection:
            detail = await read_remediation_run(
                connection, project_id=project_id, run_id=identifier, since=since
            )
            if detail is not None:
                note = provisioning_note(
                    state=str(detail.get("state") or ""),
                    traces=list(detail.get("trace") or []),
                    started_at=detail.get("started_at"),
                )
                if note:
                    await append_trace(
                        connection,
                        identifier,
                        state=RunState.RECEIVED,
                        kind="narration",
                        body=note,
                    )
                    detail = await read_remediation_run(
                        connection, project_id=project_id, run_id=identifier, since=since
                    )
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if detail is None:
        return JSONResponse({"detail": "Run not found"}, status_code=404)
    return JSONResponse(_jsonable(detail))


@router.get("/{project_id}/gcp-connections")
async def list_owned_gcp_connections(request: Request, project_id: UUID) -> JSONResponse:
    """Connection metadata and Secret Manager pointers. Never the JSON key."""
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        rows = await list_connections(_pool(request), project_id, user_id)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if rows is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse({"connections": rows})


@router.post("/{project_id}/gcp-connections")
async def upsert_owned_gcp_connection(request: Request, project_id: UUID) -> JSONResponse:
    """Accept a service-account JSON once, write Secret Manager, persist the pointer."""
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    raw = body.get("credentials_json")
    if not isinstance(raw, str):
        return JSONResponse({"detail": "credentials_json is required"}, status_code=400)
    workspace_raw = body.get("workspace_id")
    workspace_id: UUID | None = None
    if workspace_raw not in (None, "", "__shared__", "_shared"):
        try:
            workspace_id = UUID(str(workspace_raw))
        except ValueError:
            return JSONResponse({"detail": "workspace_id must be a UUID"}, status_code=400)
    vault = _vault()
    if isinstance(vault, JSONResponse):
        return vault
    try:
        row = await upsert_connection(
            _pool(request),
            project_id,
            user_id,
            credentials_json=raw,
            vault=vault,
            workspace_id=workspace_id,
            environment=str(body.get("environment") or "development"),
            region=str(body.get("region") or body.get("default_region") or "us-central1"),
        )
    except GcpConnectionError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except SecretStoreError as exc:
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "secret_manager",
                "reason": str(exc),
            },
            status_code=503,
        )
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if row is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    return JSONResponse({**row, "connected": True}, status_code=201)


@router.patch("/{project_id}/gcp-connections/{connection_id}")
async def patch_owned_gcp_connection(
    request: Request, project_id: UUID, connection_id: UUID
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    body = await _json_body(request)
    try:
        row = await update_connection(
            _pool(request),
            project_id,
            user_id,
            connection_id,
            region=str(body["region"]) if body.get("region") else None,
            environment=str(body["environment"]) if body.get("environment") else None,
        )
    except GcpConnectionError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if row is None:
        return JSONResponse({"detail": "Connection not found"}, status_code=404)
    return JSONResponse(row)


@router.delete("/{project_id}/gcp-connections/{connection_id}")
async def delete_owned_gcp_connection(
    request: Request, project_id: UUID, connection_id: UUID
) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    vault = _vault()
    if isinstance(vault, JSONResponse):
        return vault
    try:
        deleted = await delete_connection(_pool(request), project_id, user_id, connection_id, vault)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if deleted is None:
        return JSONResponse({"detail": "Project not found"}, status_code=404)
    if not deleted:
        return JSONResponse({"detail": "Connection not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.get("/{project_id}/gcp-connections/{connection_id}/runtime")
async def inspect_owned_gcp_runtime(
    request: Request, project_id: UUID, connection_id: UUID
) -> JSONResponse:
    """Cloud Run URLs and secret *refs* visible to the stored viewer identity."""
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    vault = _vault()
    if isinstance(vault, JSONResponse):
        return vault
    try:
        meta = await connection_record(_pool(request), project_id, user_id, connection_id)
        if meta is None:
            owned = await list_connections(_pool(request), project_id, user_id)
            if owned is None:
                return JSONResponse({"detail": "Project not found"}, status_code=404)
            return JSONResponse({"detail": "Connection not found"}, status_code=404)
        payload = await reveal_connection(_pool(request), project_id, user_id, connection_id, vault)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    except SecretStoreError as exc:
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "secret_manager",
                "reason": str(exc),
            },
            status_code=503,
        )
    if payload is None:
        return JSONResponse({"detail": "Connection not found"}, status_code=404)
    try:
        services = list_cloud_run_services(
            payload,
            gcp_project_id=str(meta["gcp_project_id"]),
            region=str(meta["default_region"] or "us-central1"),
        )
    except GcpViewerError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=502)
    return JSONResponse(
        {
            "gcp_project_id": meta["gcp_project_id"],
            "region": meta["default_region"],
            "repo_full_name": meta.get("repo_full_name"),
            "services": services,
        }
    )


@router.delete("/{project_id}/providers/{slug}")
async def delete_project_provider(request: Request, project_id: UUID, slug: str) -> JSONResponse:
    user_id = _require_user(request)
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        project = await read_project(_pool(request), project_id, user_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)
        await unsubscribe_project(_pool(request), project_id, slug)
    except ProviderStoreError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    return JSONResponse({"ok": True})
