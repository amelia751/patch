"""GCP viewer-connection metadata in Postgres; the JSON key stays in Secret Manager.

`gcp_connections` has no credentials column. HTTP handlers never return the
payload. `reveal_connection` is the owner-scoped reader for the inspector.
`reveal_latest_connection` is the remediator's reader for live verification.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID, uuid4

from packages.state.pool import StateUnavailableError
from packages.state.projects import full_name_from_repo_url
from packages.state.secret_manager import (
    SecretStoreError,
    SecretVault,
    is_managed_resource,
    secret_id_for_connection,
)
from packages.state.secrets import default_workspace_id

if TYPE_CHECKING:
    import asyncpg

_MAX_JSON_BYTES: Final[int] = 64 * 1024
_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"development", "staging", "production"})
_ENV_ALIASES: Final[dict[str, str]] = {
    "dev": "development",
    "development": "development",
    "staging": "staging",
    "prod": "production",
    "production": "production",
}


class GcpConnectionError(ValueError):
    """The request named or valued a connection in a way this store refuses."""


def normalize_environment(raw: str | None) -> str:
    key = (raw or "development").strip().lower()
    mapped = _ENV_ALIASES.get(key)
    if mapped is None:
        raise GcpConnectionError("environment must be development, staging, or production")
    return mapped


def parse_service_account_json(raw: str) -> tuple[str, str]:
    """Return `(gcp_project_id, client_email)` after refusing a non-SA payload."""
    if not raw or not raw.strip():
        raise GcpConnectionError("credentials_json cannot be empty")
    if len(raw.encode("utf-8")) > _MAX_JSON_BYTES:
        raise GcpConnectionError("credentials_json exceeds Secret Manager's 64 KiB limit")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GcpConnectionError("credentials_json is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise GcpConnectionError("credentials_json must be a service-account object")
    if payload.get("type") != "service_account":
        raise GcpConnectionError("credentials_json must have type service_account")
    project_id = payload.get("project_id")
    email = payload.get("client_email")
    private_key = payload.get("private_key")
    if not isinstance(project_id, str) or not project_id.strip():
        raise GcpConnectionError("service-account JSON is missing project_id")
    if not isinstance(email, str) or "@" not in email:
        raise GcpConnectionError("service-account JSON is missing client_email")
    if not isinstance(private_key, str) or "BEGIN" not in private_key:
        raise GcpConnectionError("service-account JSON is missing private_key")
    return project_id.strip(), email.strip()


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _row(record: Any) -> dict[str, Any]:
    repo_url = record["repo_url"]
    return {
        "id": str(record["id"]),
        "environment": record["environment"],
        "gcp_project_id": record["gcp_project_id"],
        "gcp_project_number": record["gcp_project_number"],
        "service_account_email": record["service_account_email"],
        "default_region": record["default_region"],
        "secret_arn": record["secret_arn"],
        "workspace_id": str(record["workspace_id"]) if record["workspace_id"] is not None else None,
        "workspace_name": record["workspace_name"],
        "workspace_path": record["workspace_path"],
        "repo_full_name": full_name_from_repo_url(repo_url) if repo_url else None,
        "is_active": True,
        "last_validated_at": _iso(record["last_validated_at"]),
        "created_at": _iso(record["created_at"]),
        "updated_at": _iso(record["updated_at"]),
    }


_LIST_SQL = """
    SELECT
        c.id, c.environment, c.gcp_project_id, c.gcp_project_number,
        c.service_account_email, c.default_region, c.secret_arn,
        c.workspace_id, c.last_validated_at, c.created_at, c.updated_at,
        w.name AS workspace_name,
        w.workspace_path AS workspace_path,
        w.repo_url AS repo_url
    FROM gcp_connections c
    LEFT JOIN workspaces w ON w.id = c.workspace_id
    WHERE c.project_id = $1
    ORDER BY w.repo_url NULLS LAST, c.environment, c.created_at
"""


async def _owned(connection: asyncpg.Connection, project_id: UUID, owner_id: UUID) -> bool:
    found = await connection.fetchval(
        "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
        project_id,
        owner_id,
    )
    return found is not None


async def _workspace_in_project(
    connection: asyncpg.Connection, project_id: UUID, workspace_id: UUID
) -> bool:
    found = await connection.fetchval(
        "SELECT 1 FROM workspaces WHERE id = $1 AND project_id = $2",
        workspace_id,
        project_id,
    )
    return found is not None


async def list_connections(
    pool: asyncpg.Pool, project_id: UUID, owner_id: UUID
) -> list[dict[str, Any]] | None:
    try:
        async with pool.acquire() as connection:
            if not await _owned(connection, project_id, owner_id):
                return None
            rows = await connection.fetch(_LIST_SQL, project_id)
    except Exception as exc:
        raise StateUnavailableError(f"could not list gcp connections: {type(exc).__name__}") from exc
    return [_row(row) for row in rows]


async def upsert_connection(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    *,
    credentials_json: str,
    vault: SecretVault,
    workspace_id: UUID | None = None,
    environment: str | None = None,
    region: str | None = None,
) -> dict[str, Any] | None:
    """Write the JSON to Secret Manager and a pointer in Postgres."""
    gcp_project_id, email = parse_service_account_json(credentials_json)
    env = normalize_environment(environment)
    default_region = (region or "us-central1").strip() or "us-central1"
    try:
        async with pool.acquire() as connection:
            if not await _owned(connection, project_id, owner_id):
                return None
            if workspace_id is None:
                workspace_id = await default_workspace_id(connection, project_id)
            if workspace_id is not None and not await _workspace_in_project(
                connection, project_id, workspace_id
            ):
                raise GcpConnectionError("workspace_id is not part of this project")
            existing = await connection.fetchrow(
                """
                SELECT id, secret_arn FROM gcp_connections
                WHERE project_id = $1 AND workspace_id IS NOT DISTINCT FROM $2
                  AND environment = $3
                """,
                project_id,
                workspace_id,
                env,
            )
    except GcpConnectionError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not read gcp connection: {type(exc).__name__}") from exc

    if existing is not None and existing["secret_arn"]:
        vault.add_version(existing["secret_arn"], credentials_json)
        return await _touch(
            pool,
            project_id,
            existing["id"],
            gcp_project_id=gcp_project_id,
            service_account_email=email,
            default_region=default_region,
        )

    row_id = existing["id"] if existing is not None else uuid4()
    create = getattr(vault, "create")
    try:
        resource = create(secret_id_for_connection(row_id), credentials_json, purpose="gcp-connection")
    except TypeError:
        resource = create(secret_id_for_connection(row_id), credentials_json)
    now = datetime.now(UTC)
    try:
        async with pool.acquire() as connection:
            if existing is None:
                await connection.execute(
                    """
                    INSERT INTO gcp_connections (
                        id, project_id, workspace_id, environment,
                        gcp_project_id, service_account_email, default_region,
                        secret_arn, last_validated_at, created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9, $9)
                    """,
                    row_id,
                    project_id,
                    workspace_id,
                    env,
                    gcp_project_id,
                    email,
                    default_region,
                    resource,
                    now,
                )
            else:
                await connection.execute(
                    """
                    UPDATE gcp_connections
                    SET secret_arn = $3, gcp_project_id = $4, service_account_email = $5,
                        default_region = $6, last_validated_at = $7, updated_at = $7
                    WHERE id = $1 AND project_id = $2
                    """,
                    row_id,
                    project_id,
                    resource,
                    gcp_project_id,
                    email,
                    default_region,
                    now,
                )
    except Exception as exc:
        if is_managed_resource(resource):
            vault.delete(resource)
        raise StateUnavailableError(f"could not write gcp connection: {type(exc).__name__}") from exc
    listed = await list_connections(pool, project_id, owner_id)
    if listed is None:
        return None
    return next((row for row in listed if row["id"] == str(row_id)), None)


async def _touch(
    pool: asyncpg.Pool,
    project_id: UUID,
    row_id: UUID,
    *,
    gcp_project_id: str,
    service_account_email: str,
    default_region: str,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    try:
        async with pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE gcp_connections
                SET gcp_project_id = $3, service_account_email = $4,
                    default_region = $5, last_validated_at = $6, updated_at = $6
                WHERE id = $1 AND project_id = $2
                """,
                row_id,
                project_id,
                gcp_project_id,
                service_account_email,
                default_region,
                now,
            )
    except Exception as exc:
        raise StateUnavailableError(f"could not update gcp connection: {type(exc).__name__}") from exc
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                _LIST_SQL.replace("WHERE c.project_id = $1", "WHERE c.project_id = $1 AND c.id = $2"),
                project_id,
                row_id,
            )
    except Exception as exc:
        raise StateUnavailableError(f"could not reread gcp connection: {type(exc).__name__}") from exc
    return _row(row) if row is not None else None


async def update_connection(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    connection_id: UUID,
    *,
    region: str | None = None,
    environment: str | None = None,
) -> dict[str, Any] | None:
    env = normalize_environment(environment) if environment is not None else None
    default_region = region.strip() if isinstance(region, str) and region.strip() else None
    if env is None and default_region is None:
        raise GcpConnectionError("region or environment is required")
    try:
        async with pool.acquire() as connection:
            if not await _owned(connection, project_id, owner_id):
                return None
            current = await connection.fetchrow(
                """
                SELECT id, workspace_id, environment, default_region
                FROM gcp_connections
                WHERE id = $1 AND project_id = $2
                """,
                connection_id,
                project_id,
            )
            if current is None:
                return None
            next_env = env or current["environment"]
            next_region = default_region or current["default_region"]
            clash = await connection.fetchval(
                """
                SELECT 1 FROM gcp_connections
                WHERE project_id = $1 AND workspace_id IS NOT DISTINCT FROM $2
                  AND environment = $3 AND id <> $4
                """,
                project_id,
                current["workspace_id"],
                next_env,
                connection_id,
            )
            if clash is not None:
                raise GcpConnectionError("a connection already exists for that repository and environment")
            await connection.execute(
                """
                UPDATE gcp_connections
                SET environment = $3, default_region = $4, updated_at = $5
                WHERE id = $1 AND project_id = $2
                """,
                connection_id,
                project_id,
                next_env,
                next_region,
                datetime.now(UTC),
            )
    except GcpConnectionError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not update gcp connection: {type(exc).__name__}") from exc
    listed = await list_connections(pool, project_id, owner_id)
    if listed is None:
        return None
    return next((row for row in listed if row["id"] == str(connection_id)), None)


async def delete_connection(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    connection_id: UUID,
    vault: SecretVault,
) -> bool | None:
    try:
        async with pool.acquire() as connection:
            if not await _owned(connection, project_id, owner_id):
                return None
            record = await connection.fetchrow(
                """
                SELECT id, secret_arn FROM gcp_connections
                WHERE id = $1 AND project_id = $2
                """,
                connection_id,
                project_id,
            )
            if record is None:
                return False
            await connection.execute(
                "DELETE FROM gcp_connections WHERE id = $1 AND project_id = $2",
                connection_id,
                project_id,
            )
    except Exception as exc:
        raise StateUnavailableError(f"could not delete gcp connection: {type(exc).__name__}") from exc
    resource = record["secret_arn"]
    if resource and is_managed_resource(resource):
        try:
            vault.delete(resource)
        except SecretStoreError:
            pass
    return True


async def reveal_connection(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    connection_id: UUID,
    vault: SecretVault,
) -> str | None:
    """Return the stored JSON. Callers must not log or serialize the return."""
    try:
        async with pool.acquire() as connection:
            if not await _owned(connection, project_id, owner_id):
                return None
            resource = await connection.fetchval(
                """
                SELECT secret_arn FROM gcp_connections
                WHERE id = $1 AND project_id = $2
                """,
                connection_id,
                project_id,
            )
    except Exception as exc:
        raise StateUnavailableError(f"could not read gcp connection pointer: {type(exc).__name__}") from exc
    if not resource:
        return None
    return vault.reveal(resource)


async def reveal_latest_connection(
    pool: asyncpg.Pool,
    project_id: UUID,
    vault: SecretVault,
) -> tuple[dict[str, Any], str] | None:
    """Return `(metadata, credentials_json)` for the project's newest connection.

    The remediator is a trusted backend and has no operator session, so this
    path does not re-check project ownership. Callers must not log the JSON.
    """
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT gcp_project_id, default_region, secret_arn
                FROM gcp_connections
                WHERE project_id = $1
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                project_id,
            )
    except Exception as exc:
        raise StateUnavailableError(
            f"could not read latest gcp connection: {type(exc).__name__}"
        ) from exc
    if row is None or not row["secret_arn"]:
        return None
    try:
        payload = vault.reveal(row["secret_arn"])
    except SecretStoreError:
        return None
    if not payload:
        return None
    return (
        {
            "gcp_project_id": row["gcp_project_id"],
            "default_region": row["default_region"] or "us-central1",
        },
        payload,
    )


async def connection_record(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    connection_id: UUID,
) -> dict[str, Any] | None:
    listed = await list_connections(pool, project_id, owner_id)
    if listed is None:
        return None
    return next((row for row in listed if row["id"] == str(connection_id)), None)
