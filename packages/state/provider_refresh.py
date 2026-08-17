"""Ingest a connected catalog or changes URL into Postgres.

Connect returns immediately with `pending`. This job fetches from Google and
writes rows. It does not write JSON snapshots.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from packages.state.gcp_catalog import CatalogUnavailableError, fetch_service_usage_catalog
from packages.state.google_release_notes import fetch_release_notes
from packages.state.providers import mark_connection_error, persist_catalog, persist_notes

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


def _parse_fetched_at(value: str) -> datetime:
    text = (value or "").strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def ingest_connection(
    pool: asyncpg.Pool,
    *,
    connection_id: UUID,
    kind: str,
    parsed: dict[str, str],
    canonical_url: str,
) -> None:
    """Fetch the endpoint and persist. Failures mark the connection `error`."""
    try:
        if kind == "catalog":
            project = (parsed.get("project") or "").strip()
            if not project:
                raise CatalogUnavailableError("catalog connection has no project")
            catalog = await fetch_service_usage_catalog(project)
            await persist_catalog(
                pool,
                connection_id=connection_id,
                services=catalog.services,
                fetched_at=_parse_fetched_at(catalog.fetched_at),
                snapshot_sha256=_sha256([service.id for service in catalog.services]),
            )
            return
        if kind == "changes":
            table = canonical_url.strip() or ".".join(
                parsed[key] for key in ("project", "dataset", "table") if parsed.get(key)
            )
            snapshot = await fetch_release_notes(qualified_table=table)
            await persist_notes(
                pool,
                connection_id=connection_id,
                notes=snapshot.notes,
                fetched_at=_parse_fetched_at(snapshot.fetched_at),
                snapshot_sha256=_sha256([note.id for note in snapshot.notes]),
            )
            return
        raise CatalogUnavailableError("unknown connection kind")
    except Exception as exc:
        message = str(exc) if str(exc) else "ingest failed"
        logger.warning("provider ingest failed for %s: %s", connection_id, message)
        await mark_connection_error(pool, connection_id, message)
