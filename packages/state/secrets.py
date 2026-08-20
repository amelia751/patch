"""Project secret metadata in Postgres; payloads stay in Secret Manager.

`project_secrets` has no value column. This module is the only writer of those
rows, and the only caller of `SecretVault.reveal`. HTTP handlers never return
the payload.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID, uuid4

from packages.state.pool import StateUnavailableError
from packages.state.secret_manager import (
    SecretStoreError,
    SecretVault,
    is_managed_resource,
    secret_id_for,
)

if TYPE_CHECKING:
    import asyncpg

_SECRET_NAME: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_MAX_VALUE_BYTES: Final[int] = 64 * 1024


class SecretInputError(ValueError):
    """The request named or valued a secret in a way this store refuses."""


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def validate_secret_name(name: str) -> str:
    cleaned = name.strip()
    if _SECRET_NAME.fullmatch(cleaned) is None:
        raise SecretInputError(
            "secret_name must be an environment-variable name "
            "(letter or underscore, then letters, digits, underscores)"
        )
    return cleaned


def validate_secret_value(value: str) -> str:
    if not value:
        raise SecretInputError("secret_value cannot be empty")
    if len(value.encode("utf-8")) > _MAX_VALUE_BYTES:
        raise SecretInputError("secret_value exceeds Secret Manager's 64 KiB limit")
    return value


def _row(record: Any) -> dict[str, Any]:
    return {
        "id": str(record["id"]),
        "secret_name": record["secret_name"],
        "secret_arn": record["secret_arn"],
        "type": record["type"],
        "status": record["status"],
        "workspace_id": str(record["workspace_id"]) if record["workspace_id"] is not None else None,
        "workspace_name": record["workspace_name"],
        "workspace_path": record["workspace_path"],
        "referenced_by": list(record["referenced_by"] or []),
        "last_rotated_at": _iso(record["last_rotated_at"]),
        "created_at": _iso(record["created_at"]),
        "updated_at": _iso(record["updated_at"]),
    }


_LIST_SQL = """
    SELECT
        s.id, s.secret_name, s.secret_arn, s.type,
        s.status::text AS status,
        s.workspace_id, s.referenced_by, s.last_rotated_at,
        s.created_at, s.updated_at,
        w.name AS workspace_name,
        w.workspace_path AS workspace_path
    FROM project_secrets s
    LEFT JOIN workspaces w ON w.id = s.workspace_id
    WHERE s.project_id = $1
    ORDER BY s.secret_name
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


async def default_workspace_id(connection: asyncpg.Connection, project_id: UUID) -> UUID | None:
    """The project's repo-root workspace, else the oldest workspace."""
    found = await connection.fetchval(
        """
        SELECT id
        FROM workspaces
        WHERE project_id = $1
        ORDER BY
            (workspace_path IS NULL OR btrim(coalesce(workspace_path, '')) = '') DESC,
            created_at ASC
        LIMIT 1
        """,
        project_id,
    )
    return found


async def list_secrets(
    pool: asyncpg.Pool, project_id: UUID, owner_id: UUID
) -> list[dict[str, Any]] | None:
    """Return configured secret metadata, or None when the project is not owned."""
    try:
        async with pool.acquire() as connection:
            if not await _owned(connection, project_id, owner_id):
                return None
            rows = await connection.fetch(_LIST_SQL, project_id)
    except Exception as exc:
        raise StateUnavailableError(f"could not list secrets: {type(exc).__name__}") from exc
    return [_row(row) for row in rows]


async def upsert_secret(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    *,
    secret_name: str,
    secret_value: str,
    vault: SecretVault,
    workspace_id: UUID | None = None,
    secret_type: str = "api_key",
) -> dict[str, Any] | None:
    """Store `secret_value` in Secret Manager and a pointer in Postgres.

    The payload is not an argument to any SQL statement. A second POST with the
    same name adds a version (rotate) rather than creating a second row.
    """
    name = validate_secret_name(secret_name)
    payload = validate_secret_value(secret_value)
    kind = secret_type.strip() or "api_key"
    try:
        async with pool.acquire() as connection:
            if not await _owned(connection, project_id, owner_id):
                return None
            if workspace_id is None:
                workspace_id = await default_workspace_id(connection, project_id)
            if workspace_id is not None and not await _workspace_in_project(
                connection, project_id, workspace_id
            ):
                raise SecretInputError("workspace_id is not part of this project")
            existing = await connection.fetchrow(
                """
                SELECT id, secret_arn FROM project_secrets
                WHERE project_id = $1 AND secret_name = $2
                """,
                project_id,
                name,
            )
    except SecretInputError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not read secret row: {type(exc).__name__}") from exc

    if existing is not None and existing["secret_arn"]:
        vault.add_version(existing["secret_arn"], payload)
        return await _touch(
            pool,
            project_id,
            existing["id"],
            workspace_id=workspace_id,
            secret_type=kind,
            rotated=True,
        )

    row_id = existing["id"] if existing is not None else uuid4()
    resource = vault.create(secret_id_for(row_id), payload)
    now = datetime.now(UTC)
    try:
        async with pool.acquire() as connection:
            if existing is None:
                await connection.execute(
                    """
                    INSERT INTO project_secrets (
                        id, project_id, workspace_id, secret_name, secret_arn,
                        type, status, last_rotated_at, created_at, updated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, 'configured', $7, $7, $7)
                    """,
                    row_id,
                    project_id,
                    workspace_id,
                    name,
                    resource,
                    kind,
                    now,
                )
            else:
                await connection.execute(
                    """
                    UPDATE project_secrets
                    SET secret_arn = $3, workspace_id = $4, type = $5,
                        last_rotated_at = $6, updated_at = $6
                    WHERE id = $1 AND project_id = $2
                    """,
                    row_id,
                    project_id,
                    resource,
                    workspace_id,
                    kind,
                    now,
                )
    except Exception as exc:
        if is_managed_resource(resource):
            vault.delete(resource)
        raise StateUnavailableError(f"could not write secret row: {type(exc).__name__}") from exc
    listed = await list_secrets(pool, project_id, owner_id)
    if listed is None:
        return None
    return next((row for row in listed if row["id"] == str(row_id)), None)


async def _touch(
    pool: asyncpg.Pool,
    project_id: UUID,
    row_id: UUID,
    *,
    workspace_id: UUID | None,
    secret_type: str,
    rotated: bool,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE project_secrets
                SET workspace_id = $3, type = $4,
                    last_rotated_at = CASE WHEN $5 THEN $6 ELSE last_rotated_at END,
                    updated_at = $6
                WHERE id = $1 AND project_id = $2
                RETURNING id
                """,
                row_id,
                project_id,
                workspace_id,
                secret_type,
                rotated,
                now,
            )
    except Exception as exc:
        raise StateUnavailableError(f"could not update secret row: {type(exc).__name__}") from exc
    if row is None:
        return None
    return await _get(pool, project_id, row_id)


async def _get(pool: asyncpg.Pool, project_id: UUID, row_id: UUID) -> dict[str, Any] | None:
    try:
        async with pool.acquire() as connection:
            record = await connection.fetchrow(
                _LIST_SQL.replace(
                    "WHERE s.project_id = $1",
                    "WHERE s.project_id = $1 AND s.id = $2",
                ),
                project_id,
                row_id,
            )
    except Exception as exc:
        raise StateUnavailableError(f"could not read secret row: {type(exc).__name__}") from exc
    return None if record is None else _row(record)


async def delete_secret(
    pool: asyncpg.Pool,
    project_id: UUID,
    owner_id: UUID,
    *,
    secret_name: str,
    vault: SecretVault,
    workspace_id: UUID | None = None,
    shared: bool = False,
) -> bool | None:
    """Delete the row and, when we created the container, the Secret Manager secret.

    Returns None when the project is not owned, False when the name is missing,
    True when the row is gone.
    """
    name = validate_secret_name(secret_name)
    try:
        async with pool.acquire() as connection:
            if not await _owned(connection, project_id, owner_id):
                return None
            if shared:
                record = await connection.fetchrow(
                    """
                    SELECT id, secret_arn FROM project_secrets
                    WHERE project_id = $1 AND secret_name = $2 AND workspace_id IS NULL
                    """,
                    project_id,
                    name,
                )
            elif workspace_id is not None:
                record = await connection.fetchrow(
                    """
                    SELECT id, secret_arn FROM project_secrets
                    WHERE project_id = $1 AND secret_name = $2 AND workspace_id = $3
                    """,
                    project_id,
                    name,
                    workspace_id,
                )
            else:
                record = await connection.fetchrow(
                    """
                    SELECT id, secret_arn FROM project_secrets
                    WHERE project_id = $1 AND secret_name = $2
                    """,
                    project_id,
                    name,
                )
            if record is None:
                return False
            await connection.execute(
                "DELETE FROM project_secrets WHERE id = $1 AND project_id = $2",
                record["id"],
                project_id,
            )
    except SecretInputError:
        raise
    except Exception as exc:
        raise StateUnavailableError(f"could not delete secret row: {type(exc).__name__}") from exc
    resource = record["secret_arn"]
    if isinstance(resource, str) and is_managed_resource(resource):
        vault.delete(resource)
    return True


async def reveal_secret(
    pool: asyncpg.Pool,
    project_id: UUID,
    *,
    secret_name: str,
    vault: SecretVault,
) -> str | None:
    """Return the payload for a live-verification step. Never an HTTP handler.

    Ownership is the caller's problem: this is invoked by the sandbox broker
    after a run has already been authorized, not by the dashboard.
    """
    name = validate_secret_name(secret_name)
    try:
        async with pool.acquire() as connection:
            resource = await connection.fetchval(
                """
                SELECT secret_arn FROM project_secrets
                WHERE project_id = $1 AND secret_name = $2
                """,
                project_id,
                name,
            )
    except Exception as exc:
        raise StateUnavailableError(f"could not look up secret: {type(exc).__name__}") from exc
    if not resource:
        return None
    return vault.reveal(resource)


__all__ = [
    "SecretInputError",
    "SecretStoreError",
    "delete_secret",
    "list_secrets",
    "reveal_secret",
    "upsert_secret",
    "validate_secret_name",
    "validate_secret_value",
]
