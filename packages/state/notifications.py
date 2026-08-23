"""Project notifications the dashboard bell lists.

An empty list is a real answer. Nothing here invents a pending analysis or a
passing check. Need-you cards are projected from `project_change_findings`;
the verifier pause is projected only when those findings exist and the
project still has neither a GCP connection nor a Gemini key.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from packages.events.console_notify import EVENT_NOTIFICATIONS, notify_console
from packages.state.pool import StateUnavailableError

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

_KINDS = frozenset({"success", "pending", "question", "info", "error"})
_UNDEFINED_TABLE: Final[str] = "42P01"
_UNDEFINED_COLUMN: Final[str] = "42703"

CHANGE_DEDUPE_PREFIX: Final[str] = "change:"
RUN_WAITING_KEY: Final[str] = "run:human_required:verifier"

# Same copy as the Runs HUMAN_REQUIRED banner.
RUN_WAITING_TITLE: Final[str] = "This run is waiting on you"
RUN_WAITING_MESSAGE: Final[str] = (
    "Connect GCP or add GEMINI_API_KEY so the agent can continue."
)

_VERIFIER_SECRET_NAMES: Final[tuple[str, ...]] = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENERATIVE_AI_API_KEY",
)

_NEEDS_YOU_TAG: Final[dict[str, str]] = {
    "label": "Needs you",
    "className": "bg-amber-500 border-amber-500 text-white",
}

_KIND_LABELS: Final[dict[str, str]] = {
    "deprecation": "Deprecation",
    "replacement": "Replacement",
    "new_identifier": "New identifier",
    "breaking_change": "Breaking change",
    "feature": "Feature",
    "fix": "Fix",
    "issue": "Issue",
    "security": "Security",
    "announcement": "Announcement",
    "change": "Change",
    "libraries": "Libraries",
    "other": "Other",
}

_KIND_TONE: Final[dict[str, str]] = {
    "deprecation": "text-red-400 border-red-400/30",
    "replacement": "text-amber-400 border-amber-400/30",
    "new_identifier": "text-emerald-500 border-emerald-500/30",
    "breaking_change": "text-red-400 border-red-400/30",
    "feature": "text-emerald-500 border-emerald-500/30",
    "fix": "text-sky-400 border-sky-400/30",
    "issue": "text-amber-400 border-amber-400/30",
    "security": "text-red-400 border-red-400/30",
    "announcement": "text-[var(--text-secondary)] border-[var(--border-color)]",
    "change": "text-[var(--text-secondary)] border-[var(--border-color)]",
    "libraries": "text-sky-400 border-sky-400/30",
    "other": "text-[var(--text-secondary)] border-[var(--border-color)]",
}

_NEED_YOU_FINDINGS_SQL: Final[str] = """
SELECT ce.external_id,
       ce.title,
       ce.summary,
       ce.change_kind::text AS kind,
       ce.product,
       ce.replacements,
       f.file_hits,
       f.file_count,
       f.repos
FROM project_change_findings f
JOIN change_events ce ON ce.id = f.change_event_id
WHERE f.project_id = $1 AND f.status = 'needs_you'
ORDER BY ce.effective_at NULLS LAST, ce.title
"""

_VERIFIER_READY_SQL: Final[str] = """
SELECT
    EXISTS (
        SELECT 1 FROM project_change_findings
        WHERE project_id = $1 AND status = 'needs_you'
    ) AS has_need,
    EXISTS (
        SELECT 1 FROM project_secrets
        WHERE project_id = $1 AND secret_name = ANY($2::text[])
    ) AS has_key,
    EXISTS (
        SELECT 1 FROM gcp_connections
        WHERE project_id = $1
    ) AS has_gcp
"""

_INSERT_SQL: Final[str] = """
INSERT INTO project_notifications (
    project_id, kind, title, message, priority, details, actions, metadata, dedupe_key
) VALUES (
    $1, 'pending'::notification_kind, $2, $3, 'high', $4::jsonb, $5::jsonb, $6::jsonb, $7
)
ON CONFLICT (project_id, dedupe_key) WHERE dedupe_key IS NOT NULL
DO NOTHING
"""

_DISMISS_STALE_CHANGES_SQL: Final[str] = """
UPDATE project_notifications
SET dismissed_at = now(), read_at = COALESCE(read_at, now())
WHERE project_id = $1
  AND dismissed_at IS NULL
  AND dedupe_key LIKE 'change:%'
  AND NOT (dedupe_key = ANY($2::text[]))
"""

_DISMISS_KEY_SQL: Final[str] = """
UPDATE project_notifications
SET dismissed_at = now(), read_at = COALESCE(read_at, now())
WHERE project_id = $1
  AND dismissed_at IS NULL
  AND dedupe_key = $2
"""

_LIST_SQL: Final[str] = """
SELECT
    id, project_id, kind::text AS kind, title, message, priority,
    read_at, dismissed_at, details, questions, actions,
    contract_ids, source_commit, metadata, created_at
FROM project_notifications
WHERE project_id = $1 AND dismissed_at IS NULL
ORDER BY created_at DESC
LIMIT $2
"""


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def change_dedupe_key(external_id: str) -> str:
    return f"{CHANGE_DEDUPE_PREFIX}{external_id}"


def kind_tag(kind: str) -> dict[str, str]:
    return {
        "label": _KIND_LABELS.get(kind, _KIND_LABELS["other"]),
        "className": _KIND_TONE.get(kind, _KIND_TONE["other"]),
    }


def change_notification_payload(row: Any) -> dict[str, Any]:
    """Bell card for one Need-you finding. Does not write."""
    external_id = str(row["external_id"])
    kind = str(row["kind"] or "other")
    replacements = row["replacements"] or []
    replacement = None
    if isinstance(replacements, list) and replacements:
        first = replacements[0]
        if isinstance(first, dict):
            replacement = first.get("to")
    repos = list(row["repos"] or [])
    file_hits = int(row["file_hits"] or 0)
    file_count = int(row["file_count"] or 0)
    usage = (
        f"{file_hits} refs in {file_count} files"
        if file_hits > 0
        else "No usages in this project"
    )
    items = [item for item in (replacement and f"Replace with {replacement}", usage, *repos[:2]) if item]
    return {
        "title": str(row["title"]),
        "message": str(row["summary"] or ""),
        "details": {"label": "Why this needs you", "items": items} if items else None,
        "actions": [
            {
                "label": "Open in Changes",
                "action_type": "view_changes",
                "variant": "default",
                "data": {"change_id": external_id},
            },
            {"label": "Dismiss", "action_type": "dismiss", "variant": "ghost"},
        ],
        "metadata": {
            "dedupe_key": change_dedupe_key(external_id),
            "change_id": external_id,
            "status": "needs_you",
            "kind": kind,
            "product": str(row["product"] or ""),
            "tags": [_NEEDS_YOU_TAG, kind_tag(kind)],
        },
        "dedupe_key": change_dedupe_key(external_id),
    }


def run_waiting_payload() -> dict[str, Any]:
    """Bell card for the dual-CTA verifier pause. Does not write."""
    return {
        "title": RUN_WAITING_TITLE,
        "message": RUN_WAITING_MESSAGE,
        "details": None,
        "actions": [
            {"label": "Connect GCP", "action_type": "connect_gcp", "variant": "default"},
            {"label": "Add secret", "action_type": "add_secret", "variant": "outline"},
        ],
        "metadata": {
            "dedupe_key": RUN_WAITING_KEY,
            "status": "needs_you",
            "tags": [_NEEDS_YOU_TAG],
        },
        "dedupe_key": RUN_WAITING_KEY,
    }


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


def _is_missing_projection(exc: BaseException) -> bool:
    sqlstate = getattr(exc, "sqlstate", None)
    return sqlstate in {_UNDEFINED_TABLE, _UNDEFINED_COLUMN}


async def _insert_card(
    connection: asyncpg.Connection, project_id: UUID, card: dict[str, Any]
) -> bool:
    result = await connection.execute(
        _INSERT_SQL,
        project_id,
        card["title"],
        card["message"],
        card["details"],
        card["actions"],
        card["metadata"],
        card["dedupe_key"],
    )
    return result.endswith("1")


async def sync_project_notifications(
    connection: asyncpg.Connection, project_id: UUID
) -> int:
    """Upsert Need-you and verifier-pause cards from live findings.

    A dismissed row with the same `dedupe_key` is left alone. Findings that
    left Need you are dismissed here so the bell does not keep a stale card.
    Returns how many new rows were inserted.
    """
    try:
        findings = await connection.fetch(_NEED_YOU_FINDINGS_SQL, project_id)
        ready = await connection.fetchrow(
            _VERIFIER_READY_SQL, project_id, list(_VERIFIER_SECRET_NAMES)
        )
    except Exception as exc:
        if _is_missing_projection(exc):
            log.warning("notification projection skipped; findings tables missing")
            return 0
        raise

    inserted = 0
    live_keys = [change_dedupe_key(str(row["external_id"])) for row in findings]
    for row in findings:
        if await _insert_card(connection, project_id, change_notification_payload(row)):
            inserted += 1

    await connection.execute(_DISMISS_STALE_CHANGES_SQL, project_id, live_keys)

    wants_pause = bool(ready["has_need"]) and not bool(ready["has_key"]) and not bool(
        ready["has_gcp"]
    )
    if wants_pause:
        if await _insert_card(connection, project_id, run_waiting_payload()):
            inserted += 1
    else:
        await connection.execute(_DISMISS_KEY_SQL, project_id, RUN_WAITING_KEY)

    if inserted:
        try:
            await notify_console(
                connection, event_type=EVENT_NOTIFICATIONS, project_id=project_id
            )
        except Exception:
            log.warning("notification console wake failed for %s", project_id, exc_info=True)
    return inserted


async def _owned(
    connection: asyncpg.Connection, project_id: UUID, owner_id: UUID
) -> bool:
    return (
        await connection.fetchval(
            "SELECT 1 FROM projects WHERE id = $1 AND owner_id = $2",
            project_id,
            owner_id,
        )
        is not None
    )


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
            if not await _owned(connection, project_id, owner_id):
                return None
            try:
                await sync_project_notifications(connection, project_id)
            except Exception as exc:
                if not _is_missing_projection(exc):
                    log.warning("notification sync failed for %s", project_id, exc_info=True)
            rows = await connection.fetch(_LIST_SQL, project_id, capped)
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
            if not await _owned(connection, project_id, owner_id):
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
            try:
                await sync_project_notifications(connection, project_id)
            except Exception as exc:
                if not _is_missing_projection(exc):
                    log.warning("notification sync failed for %s", project_id, exc_info=True)
            rows = await connection.fetch(_LIST_SQL, project_id, capped)
        return [public_notification(row) for row in rows]
    except Exception as exc:
        raise StateUnavailableError(f"could not list notifications: {type(exc).__name__}") from exc


__all__ = [
    "CHANGE_DEDUPE_PREFIX",
    "RUN_WAITING_KEY",
    "RUN_WAITING_MESSAGE",
    "RUN_WAITING_TITLE",
    "apply_notification_action",
    "change_dedupe_key",
    "change_notification_payload",
    "kind_tag",
    "list_notifications",
    "notifications_snapshot",
    "public_notification",
    "run_waiting_payload",
    "sync_project_notifications",
]
