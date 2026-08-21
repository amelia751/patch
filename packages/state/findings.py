"""Project-scoped change inbox: watchlist joined to `provider_usages`.

Change Intelligence never sees the tree. This module is the deterministic
join the Changes tab reads. A human-dismissed row is left alone on refresh.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date
from typing import TYPE_CHECKING, Any, Final, Literal
from uuid import UUID

from packages.events.console_notify import EVENT_CHANGES, notify_console
from packages.state.watchlist import watchlist_for

if TYPE_CHECKING:
    import asyncpg

log = logging.getLogger(__name__)

ACTIONABLE_KINDS: Final[frozenset[str]] = frozenset({"runtime_source", "configuration", "test"})
FALSE_POSITIVE_PREFIXES: Final[tuple[str, ...]] = ("fal-ai/",)
VERTEX_PREFIX: Final[str] = "vertex/"

FindingStatus = Literal["needs_you", "watching", "dismissed"]
FindingReason = Literal[
    "runtime_hit",
    "docs_only",
    "no_usage",
    "false_positive",
    "fail_closed",
    "not_an_identifier",
    "new_identifier",
    "user",
]

_UNDEFINED_TABLE: Final[str] = "42P01"

_LATEST_EVENTS_SQL: Final[str] = """
SELECT DISTINCT ON (external_id)
       id, external_id, provider, product, change_kind, severity, title,
       summary, source_urls, affected_identifiers, replacements,
       announced_at, effective_at, fail_closed, false_positive, migration,
       detected_at
FROM change_events
WHERE provider = $1
ORDER BY external_id, detected_at DESC
"""

_USAGES_SQL: Final[str] = """
SELECT u.identifier, u.repository, u.file_path, u.usage_kind, u.observed_sha
FROM project_provider_usages u
WHERE u.project_id = $1
  AND u.provider = $2
  AND u.identifier = ANY($3::text[])
"""

_INDEX_READY_SQL: Final[str] = """
SELECT COALESCE(bool_and(COALESCE(s.status::text, 'idle') = 'ready'), true)
FROM (
    SELECT pr.full_name AS repository, pr.default_branch AS branch
    FROM project_repositories pr
    WHERE pr.project_id = $1::uuid
    UNION
    SELECT pr.full_name AS repository, w.repo_branch AS branch
    FROM workspaces w
    JOIN project_repositories pr ON pr.id = w.repository_id
    WHERE pr.project_id = $1::uuid
) t
LEFT JOIN repo_index_state s
       ON s.repository = t.repository AND s.branch = t.branch
"""

_SUBSCRIBED_PROJECTS_FOR_REPO_SQL: Final[str] = """
SELECT DISTINCT p.id AS project_id, prov.slug AS provider
FROM project_repositories pr
JOIN projects p ON p.id = pr.project_id
JOIN project_provider_subscriptions s ON s.project_id = p.id
JOIN providers prov ON prov.id = s.provider_id AND prov.retired_at IS NULL
WHERE pr.full_name = $1
"""

_SUBSCRIBED_PROJECTS_FOR_PROVIDER_SQL: Final[str] = """
SELECT s.project_id
FROM project_provider_subscriptions s
JOIN providers p ON p.id = s.provider_id
WHERE p.slug = $1 AND p.retired_at IS NULL
"""

_ENSURE_EVENT_SQL: Final[str] = """
INSERT INTO change_events (
    external_id, provider, product, change_kind, severity, title, summary,
    source_urls, affected_identifiers, replacements, announced_at,
    effective_at, fail_closed, false_positive, migration
)
SELECT $1, $2, $3, $4::change_kind, $5::change_severity, $6, $7, $8::text[],
       $9::text[], $10::jsonb, $11::date, $12::date, $13, $14, $15
WHERE NOT EXISTS (
    SELECT 1 FROM change_events WHERE external_id = $1
)
"""

_UPSERT_FINDING_SQL: Final[str] = """
INSERT INTO project_change_findings (
    project_id, change_event_id, status, status_reason, repos,
    file_hits, file_count, identifier_counts, files, classified_at
)
VALUES (
    $1, $2, $3::finding_status, $4::finding_reason, $5::text[],
    $6, $7, $8::jsonb, $9::jsonb, now()
)
ON CONFLICT (project_id, change_event_id) DO UPDATE
SET status = CASE
        WHEN project_change_findings.status_reason = 'user'
         AND project_change_findings.status = 'dismissed'
        THEN project_change_findings.status
        ELSE EXCLUDED.status
    END,
    status_reason = CASE
        WHEN project_change_findings.status_reason = 'user'
         AND project_change_findings.status = 'dismissed'
        THEN project_change_findings.status_reason
        ELSE EXCLUDED.status_reason
    END,
    repos = EXCLUDED.repos,
    file_hits = EXCLUDED.file_hits,
    file_count = EXCLUDED.file_count,
    identifier_counts = EXCLUDED.identifier_counts,
    files = EXCLUDED.files,
    classified_at = now()
"""

_LIST_CHANGES_SQL: Final[str] = """
SELECT ce.external_id,
       ce.provider,
       p.name AS provider_name,
       ce.product,
       ce.title,
       ce.summary,
       ce.change_kind::text AS kind,
       f.status::text AS status,
       f.status_reason::text AS status_reason,
       ce.announced_at,
       ce.effective_at,
       ce.affected_identifiers AS identifiers,
       f.identifier_counts,
       ce.replacements,
       ce.migration,
       ce.fail_closed,
       f.repos,
       f.file_hits,
       f.file_count,
       f.files,
       ce.source_urls
FROM project_change_findings f
JOIN change_events ce ON ce.id = f.change_event_id
JOIN providers p ON p.slug = ce.provider AND p.retired_at IS NULL
JOIN project_provider_subscriptions s
  ON s.project_id = f.project_id AND s.provider_id = p.id
WHERE f.project_id = $1
ORDER BY
    CASE f.status::text
        WHEN 'needs_you' THEN 0
        WHEN 'watching' THEN 1
        ELSE 2
    END,
    ce.effective_at NULLS LAST,
    ce.title
"""


def file_hit_kind(path: str, usage_kind: str) -> str:
    """Map a usage row to the Changes tab file chip."""
    name = path.rsplit("/", 1)[-1].lower()
    if "changelog" in name:
        return "changelog"
    if usage_kind in ACTIONABLE_KINDS:
        return "runtime"
    return "documentation"


def is_false_positive(identifier: str) -> bool:
    """Third-party ids that share a substring with a Google model."""
    lowered = identifier.lower()
    return any(lowered.startswith(prefix) for prefix in FALSE_POSITIVE_PREFIXES)


def classify(
    *,
    identifiers: list[str],
    hits: list[dict[str, Any]],
    fail_closed: bool,
    false_positive: bool,
    change_kind: str,
) -> tuple[FindingStatus, FindingReason]:
    """Deterministic inbox bucket. The model does not pick this."""
    if false_positive or (identifiers and all(is_false_positive(item) for item in identifiers)):
        return "dismissed", "false_positive"
    if not identifiers:
        if change_kind == "new_identifier":
            return "watching", "new_identifier"
        return "watching", "not_an_identifier"

    runtime = [hit for hit in hits if hit.get("usage_kind") in ACTIONABLE_KINDS]
    vertex = any(item.startswith(VERTEX_PREFIX) for item in identifiers)
    if runtime:
        if fail_closed or vertex:
            return "needs_you", "fail_closed"
        return "needs_you", "runtime_hit"
    if hits:
        return "watching", "docs_only"
    if change_kind == "new_identifier":
        return "watching", "new_identifier"
    return "watching", "no_usage"


def aggregate_hits(
    hits: list[dict[str, Any]],
) -> tuple[list[str], int, int, dict[str, int], list[dict[str, Any]]]:
    """Roll file-and-line usages into the inbox file list."""
    repos: set[str] = set()
    counts: dict[str, int] = defaultdict(int)
    files: dict[str, dict[str, Any]] = {}
    for hit in hits:
        path = str(hit["file_path"])
        identifier = str(hit["identifier"])
        repo = str(hit["repository"])
        repos.add(repo)
        counts[identifier] += 1
        kind = file_hit_kind(path, str(hit.get("usage_kind") or ""))
        current = files.get(path)
        if current is None:
            files[path] = {"path": path, "hits": 1, "kind": kind}
            continue
        current["hits"] += 1
        if kind == "runtime" or (kind == "changelog" and current["kind"] != "runtime"):
            current["kind"] = kind
    ordered = sorted(files.values(), key=lambda item: (-int(item["hits"]), str(item["path"])))
    return sorted(repos), sum(counts.values()), len(ordered), dict(counts), ordered


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _is_undefined_table(exc: BaseException) -> bool:
    return getattr(exc, "sqlstate", None) == _UNDEFINED_TABLE


async def ensure_watchlist(connection: asyncpg.Connection, provider: str) -> int:
    """Insert missing pinned notes. Existing detections are left alone."""
    inserted = 0
    for note in watchlist_for(provider):
        status = await connection.execute(
            _ENSURE_EVENT_SQL,
            note["external_id"],
            note["provider"],
            note["product"],
            note["change_kind"],
            note["severity"],
            note["title"],
            note["summary"],
            note["source_urls"],
            note["identifiers"],
            json.dumps(note["replacements"]),
            _as_date(note["announced_at"]),
            _as_date(note["effective_at"]),
            note["fail_closed"],
            note["false_positive"],
            note["migration"],
        )
        if status.endswith("1"):
            inserted += 1
    return inserted


async def mark_scan(
    connection: asyncpg.Connection,
    project_id: UUID,
    provider: str,
    *,
    status: str,
    progress_percent: int,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Upsert the Subscribe overlay row and wake the console."""
    started = status == "scanning"
    finished = status in {"ready", "error"}
    await connection.execute(
        """
        INSERT INTO project_change_scans (
            project_id, provider, status, progress_percent,
            started_at, finished_at, error_message
        )
        VALUES (
            $1, $2, $3::change_scan_status, $4,
            CASE WHEN $5 THEN now() ELSE NULL END,
            CASE WHEN $6 THEN now() ELSE NULL END,
            $7
        )
        ON CONFLICT (project_id, provider) DO UPDATE
        SET status = EXCLUDED.status,
            progress_percent = EXCLUDED.progress_percent,
            started_at = CASE
                WHEN $5 THEN COALESCE(project_change_scans.started_at, now())
                ELSE project_change_scans.started_at
            END,
            finished_at = CASE
                WHEN $6 THEN now()
                ELSE project_change_scans.finished_at
            END,
            error_message = EXCLUDED.error_message
        """,
        project_id,
        provider,
        status,
        progress_percent,
        started,
        finished,
        error_message,
    )
    await _wake_changes(connection, project_id)
    return {
        "provider": provider,
        "status": status,
        "progress_percent": progress_percent,
        "error_message": error_message,
    }


async def read_scan(
    connection: asyncpg.Connection, project_id: UUID, provider: str
) -> dict[str, Any]:
    row = await connection.fetchrow(
        """
        SELECT provider, status::text AS status, progress_percent, error_message
        FROM project_change_scans
        WHERE project_id = $1 AND provider = $2
        """,
        project_id,
        provider,
    )
    if row is None:
        return {
            "provider": provider,
            "status": "idle",
            "progress_percent": 0,
            "error_message": None,
        }
    return dict(row)


async def project_index_ready(connection: asyncpg.Connection, project_id: UUID) -> bool:
    """True when every imported target is `ready`, or the project imported none."""
    ready = await connection.fetchval(_INDEX_READY_SQL, project_id)
    return bool(ready)


async def refresh_project_findings(
    connection: asyncpg.Connection, project_id: UUID, provider: str
) -> int:
    """Reclassify every latest event for `provider` against this project's inventory."""
    events = await connection.fetch(_LATEST_EVENTS_SQL, provider)
    identifiers = sorted({item for row in events for item in (row["affected_identifiers"] or [])})
    usages: list[dict[str, Any]] = []
    if identifiers:
        usages = [
            dict(row)
            for row in await connection.fetch(_USAGES_SQL, project_id, provider, identifiers)
        ]
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for usage in usages:
        by_id[str(usage["identifier"])].append(usage)

    written = 0
    for event in events:
        wanted = list(event["affected_identifiers"] or [])
        hits = [hit for identifier in wanted for hit in by_id.get(identifier, ())]
        status, reason = classify(
            identifiers=wanted,
            hits=hits,
            fail_closed=bool(event["fail_closed"]),
            false_positive=bool(event["false_positive"]),
            change_kind=str(event["change_kind"]),
        )
        repos, file_hits, file_count, counts, files = aggregate_hits(hits)
        await connection.execute(
            _UPSERT_FINDING_SQL,
            project_id,
            event["id"],
            status,
            reason,
            repos,
            file_hits,
            file_count,
            json.dumps(counts),
            json.dumps(files),
        )
        written += 1
    return written


async def backfill_project(
    connection: asyncpg.Connection, project_id: UUID, provider: str
) -> dict[str, Any]:
    """Subscribe kickoff: pin the watchlist, join, set the overlay."""
    await mark_scan(connection, project_id, provider, status="scanning", progress_percent=20)
    await ensure_watchlist(connection, provider)
    await mark_scan(connection, project_id, provider, status="scanning", progress_percent=55)
    written = await refresh_project_findings(connection, project_id, provider)
    ready = await project_index_ready(connection, project_id)
    if ready:
        scan = await mark_scan(
            connection, project_id, provider, status="ready", progress_percent=100
        )
    else:
        scan = await mark_scan(
            connection, project_id, provider, status="scanning", progress_percent=70
        )
    return {"written": written, "scan": scan, "index_ready": ready}


async def refresh_after_repo_ready(
    connection: asyncpg.Connection, repository: str, branch: str
) -> tuple[str, ...]:
    """Indexer hook: re-join subscribed projects that import this target.

    Missing findings tables must not nack an index. The inventory write is
    already the truth; Subscribe can catch up after the migration lands.
    """
    del branch  # join is project-scoped; branch is selected by the usages view
    try:
        rows = await connection.fetch(_SUBSCRIBED_PROJECTS_FOR_REPO_SQL, repository)
    except Exception as exc:
        if _is_undefined_table(exc):
            log.warning("change findings tables missing; skip refresh for %s", repository)
            return ()
        raise
    refreshed: list[str] = []
    for row in rows:
        project_id = row["project_id"]
        provider = str(row["provider"])
        try:
            await ensure_watchlist(connection, provider)
            await refresh_project_findings(connection, project_id, provider)
            ready = await project_index_ready(connection, project_id)
            await mark_scan(
                connection,
                project_id,
                provider,
                status="ready" if ready else "scanning",
                progress_percent=100 if ready else 80,
            )
        except Exception as exc:
            if _is_undefined_table(exc):
                log.warning("change findings tables missing; skip refresh for %s", repository)
                return tuple(refreshed)
            log.exception("findings refresh failed for project %s", project_id)
            continue
        refreshed.append(str(project_id))
    return tuple(refreshed)


async def refresh_subscribed_projects(connection: asyncpg.Connection, provider: str) -> int:
    """New-release hook: re-join every project watching this provider."""
    try:
        await ensure_watchlist(connection, provider)
        rows = await connection.fetch(_SUBSCRIBED_PROJECTS_FOR_PROVIDER_SQL, provider)
    except Exception as exc:
        if _is_undefined_table(exc):
            log.warning("change findings tables missing; skip provider refresh")
            return 0
        raise
    count = 0
    for row in rows:
        await refresh_project_findings(connection, row["project_id"], provider)
        ready = await project_index_ready(connection, row["project_id"])
        await mark_scan(
            connection,
            row["project_id"],
            provider,
            status="ready" if ready else "scanning",
            progress_percent=100 if ready else 80,
        )
        count += 1
    return count


async def inbox_payload(
    connection: asyncpg.Connection, project_id: UUID, provider: str = "google"
) -> dict[str, Any]:
    """Changes tab document: findings plus the Subscribe overlay."""
    subscribed = await connection.fetchval(
        """
        SELECT 1
        FROM project_provider_subscriptions s
        JOIN providers p ON p.id = s.provider_id
        WHERE s.project_id = $1 AND p.slug = $2 AND p.retired_at IS NULL
        """,
        project_id,
        provider,
    )
    scan = await read_scan(connection, project_id, provider)
    changes = await list_project_changes(connection, project_id) if subscribed else []
    return {
        "subscribed": bool(subscribed),
        "scan": scan,
        "changes": changes,
    }


async def list_project_changes(
    connection: asyncpg.Connection, project_id: UUID
) -> list[dict[str, Any]]:
    rows = await connection.fetch(_LIST_CHANGES_SQL, project_id)
    return [_change_payload(row) for row in rows]


async def set_finding_status(
    connection: asyncpg.Connection,
    project_id: UUID,
    external_id: str,
    *,
    status: FindingStatus,
    user_id: UUID,
) -> dict[str, Any] | None:
    """Persist dismiss / reopen. Refresh will not overwrite a user dismiss."""
    if status != "dismissed":
        # Reopen: drop the user pin so the next refresh can reclassify.
        row = await connection.fetchrow(
            """
            UPDATE project_change_findings f
            SET status = 'watching'::finding_status,
                status_reason = 'no_usage'::finding_reason,
                dismissed_at = NULL,
                dismissed_by = NULL
            FROM change_events ce
            WHERE f.change_event_id = ce.id
              AND f.project_id = $1
              AND ce.external_id = $2
            RETURNING f.id
            """,
            project_id,
            external_id,
        )
        if row is None:
            return None
        provider = await connection.fetchval(
            """
            SELECT provider FROM change_events
            WHERE external_id = $1
            ORDER BY detected_at DESC
            LIMIT 1
            """,
            external_id,
        )
        if provider:
            await refresh_project_findings(connection, project_id, str(provider))
        await _wake_changes(connection, project_id)
        return {"id": external_id, "status": "watching"}

    row = await connection.fetchrow(
        """
        UPDATE project_change_findings f
        SET status = $3::finding_status,
            status_reason = 'user'::finding_reason,
            dismissed_at = now(),
            dismissed_by = $4
        FROM change_events ce
        WHERE f.change_event_id = ce.id
          AND f.project_id = $1
          AND ce.external_id = $2
        RETURNING f.status::text AS status
        """,
        project_id,
        external_id,
        status,
        user_id,
    )
    if row is None:
        return None
    await _wake_changes(connection, project_id)
    return {"id": external_id, "status": row["status"]}


def _change_payload(row: asyncpg.Record) -> dict[str, Any]:
    replacements = row["replacements"] or []
    replacement = None
    if isinstance(replacements, list) and replacements:
        replacement = replacements[0].get("to") if isinstance(replacements[0], dict) else None
    repos = list(row["repos"] or [])
    announced = row["announced_at"]
    effective = row["effective_at"]
    counts = row["identifier_counts"] or {}
    if not isinstance(counts, dict):
        counts = {}
    files = row["files"] or []
    if not isinstance(files, list):
        files = []
    return {
        "id": row["external_id"],
        "provider": row["provider_name"],
        "providerSlug": row["provider"],
        "product": row["product"],
        "title": row["title"],
        "summary": row["summary"],
        "kind": row["kind"],
        "status": row["status"],
        "statusReason": row["status_reason"],
        "announcedAt": announced.isoformat() if announced else None,
        "effectiveAt": effective.isoformat() if effective else None,
        "identifiers": list(row["identifiers"] or []),
        "identifierCounts": {str(key): int(value) for key, value in counts.items()},
        "replacement": replacement,
        "migration": row["migration"],
        "failClosed": bool(row["fail_closed"]),
        "repo": repos[0] if repos else None,
        "repos": repos,
        "fileHits": int(row["file_hits"]),
        "fileCount": int(row["file_count"]),
        "files": files,
        "sourceUrls": list(row["source_urls"] or []),
        "source": "live",
    }


async def _wake_changes(connection: asyncpg.Connection, project_id: UUID) -> None:
    try:
        await notify_console(connection, event_type=EVENT_CHANGES, project_id=project_id)
    except Exception:
        log.warning("changes console wake failed for %s", project_id, exc_info=True)


__all__ = [
    "ACTIONABLE_KINDS",
    "EVENT_CHANGES",
    "aggregate_hits",
    "backfill_project",
    "classify",
    "ensure_watchlist",
    "file_hit_kind",
    "inbox_payload",
    "is_false_positive",
    "list_project_changes",
    "mark_scan",
    "project_index_ready",
    "read_scan",
    "refresh_after_repo_ready",
    "refresh_project_findings",
    "refresh_subscribed_projects",
    "set_finding_status",
]
