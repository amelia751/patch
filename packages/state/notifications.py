"""Project notifications the dashboard bell lists.

An empty list is a real answer. Nothing here invents a pending analysis or a
passing check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from packages.events.console_notify import EVENT_NOTIFICATIONS, notify_console
from packages.state.pool import StateUnavailableError

if TYPE_CHECKING:
    import asyncpg

_KINDS = frozenset({"success", "pending", "question", "info", "error"})


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def public_notification(row: Any) -> dict[str, Any]:
    """Project a row onto the dashboard Notification shape."""
    kind = row["kind"]
    if kind not in _KINDS:
        kind = "info"
    details = row["details"] if isinstance(row["details"], dict) else None
    questions = row["questions"] if isinstance(row["questions"], dict) else None
    actions = row["actions"] if isinstance(row["actions"], list) else []
    metadata = row["metadata"] if isinstance(row["metadata"], dict) else {}
    contract_ids = list(row["contract_ids"] or ())
    return {
        "id": str(row["id"]),
        "project_id": str(row["project_id"]),
        "type": kind,
        "title": row["title"],
        "message": row["message"],
        "timestamp": _iso(row["created_at"]) or "",
        "priority": row["priority"],
        "read": row["read_at"] is not None,
        "dismissed": row["dismissed_at"] is not None,
        "details": details,
        "questions": questions,
        "actions": actions,
        "contract_ids": contract_ids,
        "source_commit": row["source_commit"],
        "metadata": metadata,
    }


async def list_notifications(
    pool: asyncpg.Pool,
    *,
    project_id: UUID,
    owner_id: UUID,
    limit: int,
) -> list[dict[str, Any]] | None:
    """Return undismissed notifications for a project the user owns.

    None means the project is not theirs. An empty list means we looked and
    found nothing.
    """
    capped = min(max(limit, 1), 50)
    try:
        async with pool.acquire() as connection:
            owned = await connection.fetchval(
                "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
                project_id,
                owner_id,
            )
            if owned is None:
                return None
            rows = await connection.fetch(
                """
                SELECT
                    id, project_id, kind::text AS kind, title, message, priority,
                    read_at, dismissed_at, details, questions, actions,
                    contract_ids, source_commit, metadata, created_at
                FROM project_notifications
                WHERE project_id = $1 AND dismissed_at IS NULL
                ORDER BY created_at DESC
                LIMIT $2
                """,
                project_id,
                capped,
            )
        return [public_notification(row) for row in rows]
    except Exception as exc:
        raise StateUnavailableError(f"could not list notifications: {type(exc).__name__}") from exc


async def apply_notification_action(
    pool: asyncpg.Pool,
    *,
    project_id: UUID,
    owner_id: UUID,
    notification_id: UUID,
    action_type: str,
) -> dict[str, Any] | None:
    """Mark a notification read or dismissed. None if it is not theirs."""
    dismissed = action_type.strip() == "dismiss"
    try:
        async with pool.acquire() as connection:
            owned = await connection.fetchval(
                "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
                project_id,
                owner_id,
            )
            if owned is None:
                return None
            if dismissed:
                row = await connection.fetchrow(
                    """
                    UPDATE project_notifications
                    SET dismissed_at = now(), read_at = COALESCE(read_at, now())
                    WHERE id = $1 AND project_id = $2
                    RETURNING id
                    """,
                    notification_id,
                    project_id,
                )
            else:
                row = await connection.fetchrow(
                    """
                    UPDATE project_notifications
                    SET read_at = COALESCE(read_at, now())
                    WHERE id = $1 AND project_id = $2
                    RETURNING id
                    """,
                    notification_id,
                    project_id,
                )
            if row is None:
                return None
            try:
                await notify_console(
                    connection, event_type=EVENT_NOTIFICATIONS, project_id=project_id
                )
            except Exception:
                # The write already landed; the other tab falls back to polling.
                pass
        return {"ok": True, "action_type": action_type}
    except Exception as exc:
        raise StateUnavailableError(f"could not update notification: {type(exc).__name__}") from exc


async def notifications_snapshot(
    pool: asyncpg.Pool, project_id: UUID, *, limit: int = 20
) -> list[dict[str, Any]]:
    """Undismissed notifications for an already-authorized project (SSE fan-out)."""
    capped = min(max(limit, 1), 50)
    try:
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    id, project_id, kind::text AS kind, title, message, priority,
                    read_at, dismissed_at, details, questions, actions,
                    contract_ids, source_commit, metadata, created_at
                FROM project_notifications
                WHERE project_id = $1 AND dismissed_at IS NULL
                ORDER BY created_at DESC
                LIMIT $2
                """,
                project_id,
                capped,
            )
        return [public_notification(row) for row in rows]
    except Exception as exc:
        raise StateUnavailableError(f"could not list notifications: {type(exc).__name__}") from exc
