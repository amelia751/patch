"""Postgres store for the vendor registry and ingest connections."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from packages.state.google_release_notes import published_day
from packages.state.pool import StateUnavailableError
from packages.state.provider_urls import ParsedProviderUrl

if TYPE_CHECKING:
    import asyncpg

    from packages.state.gcp_catalog import CatalogService
    from packages.state.google_release_notes import ReleaseNote

GOOGLE_PROVIDER_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")
GOOGLE_SLUG = "google"

_CATEGORIES = frozenset(
    {"ai", "cloud", "payments", "communications", "data", "identity", "devtools", "other"}
)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
_RESERVED_SLUGS = frozenset({GOOGLE_SLUG, "check-slug"})


class ProviderStoreError(ValueError):
    """A registry write was rejected. The message is safe to show."""


def _as_datetime(value: str) -> datetime:
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ProviderStoreError("release note published_at is not a timestamp") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _since_label(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return str(value.year)
    text = str(value)
    return text[:4] if len(text) >= 4 else text


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _connection_summary(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    parsed = row["parsed"]
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "adapter": row["adapter"],
        "source_url": row["source_url"],
        "canonical_url": row["canonical_url"],
        "status": row["status"],
        "parsed": parsed if isinstance(parsed, dict) else {},
        "last_error": row["last_error"],
        "fetched_at": _iso(row["fetched_at"]),
    }


def provider_payload(
    row: Any,
    *,
    connections: dict[str, Any | None],
    watching: int = 0,
) -> dict[str, Any]:
    owner_user = row["owner_user_id"]
    owner_org = row["owner_organization_id"]
    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "name": row["name"],
        "website": row["website"] or "",
        "contact_email": row["contact_email"] or "",
        "contact_url": row["contact_url"] or "",
        "category": row["category"],
        "description": row["description"],
        "verified": bool(row["verified"]),
        "status": row["status"],
        "hq": row["hq"] or "",
        "since": _since_label(row["since"]) or "",
        "console_url": row["console_url"] or "",
        "docs_url": row["docs_url"] or "",
        "status_url": row["status_url"] or "",
        "logo_url": row["logo_url"] or "",
        "featured_products": _text_list(row["featured_products"]),
        "registered_at": _iso(row["registered_at"]),
        "watching_orgs": watching,
        "owner": None
        if owner_user is None and owner_org is None
        else {
            "user_id": str(owner_user) if owner_user is not None else None,
            "organization_id": str(owner_org) if owner_org is not None else None,
        },
        "connections": {
            "catalog": connections.get("catalog"),
            "changes": connections.get("changes"),
        },
    }


async def _watching_count(connection: asyncpg.Connection, provider_id: UUID) -> int:
    value = await connection.fetchval(
        "SELECT count(*) FROM project_provider_subscriptions WHERE provider_id = $1",
        provider_id,
    )
    return int(value or 0)


async def _live_connections(
    connection: asyncpg.Connection, provider_id: UUID
) -> dict[str, Any | None]:
    rows = await connection.fetch(
        """
        SELECT * FROM provider_connections
        WHERE provider_id = $1 AND disconnected_at IS NULL
        """,
        provider_id,
    )
    out: dict[str, Any | None] = {"catalog": None, "changes": None}
    for row in rows:
        out[row["kind"]] = _connection_summary(row)
    return out


async def get_provider(pool: asyncpg.Pool, slug: str) -> dict[str, Any] | None:
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT * FROM providers WHERE slug = $1 AND retired_at IS NULL",
            slug,
        )
        if row is None:
            return None
        connections = await _live_connections(connection, row["id"])
        watching = await _watching_count(connection, row["id"])
        return provider_payload(row, connections=connections, watching=watching)


async def list_providers(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT * FROM providers
            WHERE retired_at IS NULL
            ORDER BY verified DESC, name
            """
        )
        payloads: list[dict[str, Any]] = []
        for row in rows:
            connections = await _live_connections(connection, row["id"])
            watching = await _watching_count(connection, row["id"])
            payloads.append(provider_payload(row, connections=connections, watching=watching))
        return payloads


def normalize_provider_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower().replace("'", "")).strip("-")
    return cleaned[:48]


def validate_provider_slug(slug: str) -> str:
    cleaned = slug.strip().lower()
    if len(cleaned) < 3:
        raise ProviderStoreError("Slug must be at least 3 characters.")
    if not _SLUG.fullmatch(cleaned):
        raise ProviderStoreError("Slug must start and end with a letter or number.")
    if "--" in cleaned:
        raise ProviderStoreError("Slug cannot contain consecutive hyphens.")
    if cleaned in _RESERVED_SLUGS:
        raise ProviderStoreError("That slug is reserved.")
    return cleaned


async def provider_slug_available(pool: asyncpg.Pool, slug: str) -> dict[str, Any]:
    cleaned = validate_provider_slug(slug)
    async with pool.acquire() as connection:
        taken = await connection.fetchval(
            "SELECT 1 FROM providers WHERE slug = $1 AND retired_at IS NULL",
            cleaned,
        )
    if taken is not None:
        return {"available": False, "slug": cleaned, "message": "This slug is already taken"}
    return {"available": True, "slug": cleaned}


def _optional_text(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _parse_since_year(value: str) -> date | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if re.fullmatch(r"\d{4}", cleaned) is None:
        raise ProviderStoreError("Since must be a four-digit year.")
    year = int(cleaned)
    if year < 1800 or year > 2100:
        raise ProviderStoreError("Since must be a four-digit year.")
    return date(year, 1, 1)


async def register_provider(
    pool: asyncpg.Pool,
    *,
    owner_user_id: UUID,
    name: str,
    slug: str,
    category: str,
    description: str,
    website: str = "",
    contact_email: str = "",
    contact_url: str = "",
    hq: str = "",
    since: str = "",
    console_url: str = "",
    docs_url: str = "",
    status_url: str = "",
) -> dict[str, Any]:
    cleaned_name = name.strip()
    cleaned_slug = validate_provider_slug(slug)
    cleaned_category = category.strip().lower()
    cleaned_description = description.strip()
    if not cleaned_name:
        raise ProviderStoreError("Enter an organization name.")
    if cleaned_category not in _CATEGORIES:
        raise ProviderStoreError("Choose a category.")
    if not cleaned_description:
        raise ProviderStoreError("Describe what you publish.")
    email = contact_email.strip()
    contact = contact_url.strip()
    if email and "@" not in email:
        raise ProviderStoreError("Enter a valid contact email, or leave it blank.")
    since_date = _parse_since_year(since)
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO providers (
                    name, slug, website, contact_email, contact_url, category, description,
                    owner_user_id, verified, status, hq, since,
                    console_url, docs_url, status_url
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, false, 'draft',
                    $9, $10, $11, $12, $13
                )
                RETURNING *
                """,
                cleaned_name,
                cleaned_slug,
                _optional_text(website),
                email or None,
                _optional_text(contact),
                cleaned_category,
                cleaned_description,
                owner_user_id,
                _optional_text(hq),
                since_date,
                _optional_text(console_url),
                _optional_text(docs_url),
                _optional_text(status_url),
            )
    except Exception as exc:
        message = str(exc)
        if "providers_slug" in message or "unique" in message.lower():
            raise ProviderStoreError("That slug is already registered.") from exc
        raise
    if row is None:
        raise ProviderStoreError("Could not register the provider.")
    return provider_payload(row, connections={"catalog": None, "changes": None}, watching=0)


async def insert_connection(
    pool: asyncpg.Pool,
    *,
    slug: str,
    parsed: ParsedProviderUrl,
    actor: UUID | None,
) -> dict[str, Any]:
    async with pool.acquire() as connection:
        provider = await connection.fetchrow(
            "SELECT * FROM providers WHERE slug = $1 AND retired_at IS NULL",
            slug,
        )
        if provider is None:
            raise ProviderStoreError("Provider not found.")
        owner = provider["owner_user_id"]
        if owner is not None and actor is not None and owner != actor:
            raise ProviderStoreError("Only the owning user can connect this provider.")
        existing = await connection.fetchrow(
            """
            SELECT id FROM provider_connections
            WHERE provider_id = $1 AND kind = $2 AND disconnected_at IS NULL
            """,
            provider["id"],
            parsed.kind,
        )
        if existing is not None:
            raise ProviderStoreError("Disconnect the current endpoint before connecting another.")
        row = await connection.fetchrow(
            """
            INSERT INTO provider_connections (
                provider_id, kind, adapter, source_url, canonical_url, parsed,
                status, created_by
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, 'pending', $7)
            RETURNING *
            """,
            provider["id"],
            parsed.kind,
            parsed.adapter,
            parsed.source_url,
            parsed.canonical_url,
            json.dumps(parsed.parsed),
            actor,
        )
    if row is None:
        raise ProviderStoreError("Could not store the connection.")
    summary = _connection_summary(row)
    assert summary is not None
    return summary


async def mark_connection_error(pool: asyncpg.Pool, connection_id: UUID, message: str) -> None:
    async with pool.acquire() as connection:
        await connection.execute(
            """
            UPDATE provider_connections
            SET status = 'error', last_error = $2, updated_at = now()
            WHERE id = $1 AND disconnected_at IS NULL
            """,
            connection_id,
            message,
        )


async def persist_catalog(
    pool: asyncpg.Pool,
    *,
    connection_id: UUID,
    services: tuple[CatalogService, ...],
    fetched_at: datetime,
    snapshot_sha256: str,
) -> None:
    async with pool.acquire() as connection:
        async with connection.transaction():
            link = await connection.fetchrow(
                """
                SELECT id, provider_id FROM provider_connections
                WHERE id = $1 AND disconnected_at IS NULL
                """,
                connection_id,
            )
            if link is None:
                return
            seen: list[str] = []
            for service in services:
                status = service.status if service.status in {"live", "preview", "deprecated"} else "live"
                await connection.execute(
                    """
                    INSERT INTO provider_services (
                        provider_id, connection_id, external_id, name, slug, product,
                        service_group, summary, status, identifiers, docs_url,
                        last_seen_at, retired_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NULL)
                    ON CONFLICT (provider_id, external_id) DO UPDATE
                    SET connection_id = EXCLUDED.connection_id,
                        name = EXCLUDED.name,
                        slug = EXCLUDED.slug,
                        product = EXCLUDED.product,
                        service_group = EXCLUDED.service_group,
                        summary = EXCLUDED.summary,
                        status = EXCLUDED.status,
                        identifiers = EXCLUDED.identifiers,
                        docs_url = EXCLUDED.docs_url,
                        last_seen_at = EXCLUDED.last_seen_at,
                        retired_at = NULL
                    """,
                    link["provider_id"],
                    connection_id,
                    service.id,
                    service.name,
                    service.slug,
                    service.product,
                    service.group,
                    service.summary,
                    status,
                    list(service.identifiers),
                    service.docs_url,
                    fetched_at,
                )
                seen.append(service.id)
            if seen:
                await connection.execute(
                    """
                    UPDATE provider_services
                    SET retired_at = $3
                    WHERE provider_id = $1
                      AND connection_id = $2
                      AND retired_at IS NULL
                      AND NOT (external_id = ANY($4::text[]))
                    """,
                    link["provider_id"],
                    connection_id,
                    fetched_at,
                    seen,
                )
            else:
                await connection.execute(
                    """
                    UPDATE provider_services
                    SET retired_at = $3
                    WHERE provider_id = $1 AND connection_id = $2 AND retired_at IS NULL
                    """,
                    link["provider_id"],
                    connection_id,
                    fetched_at,
                )
            await _mark_connected(
                connection,
                connection_id=connection_id,
                provider_id=link["provider_id"],
                fetched_at=fetched_at,
                snapshot_sha256=snapshot_sha256,
            )


async def persist_notes(
    pool: asyncpg.Pool,
    *,
    connection_id: UUID,
    notes: tuple[ReleaseNote, ...],
    fetched_at: datetime,
    snapshot_sha256: str,
) -> None:
    async with pool.acquire() as connection:
        async with connection.transaction():
            link = await connection.fetchrow(
                """
                SELECT id, provider_id FROM provider_connections
                WHERE id = $1 AND disconnected_at IS NULL
                """,
                connection_id,
            )
            if link is None:
                return
            rows = [
                (
                    link["provider_id"],
                    connection_id,
                    note.id,
                    note.product,
                    note.kind,
                    note.release_note_type,
                    note.title,
                    note.summary,
                    note.source_url,
                    _as_datetime(note.published_at),
                )
                for note in notes
            ]
            if rows:
                await connection.executemany(
                    """
                    INSERT INTO provider_change_notes (
                        provider_id, connection_id, external_id, product, kind,
                        release_note_type, title, summary, source_url, published_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (provider_id, external_id) DO UPDATE
                    SET connection_id = EXCLUDED.connection_id,
                        product = EXCLUDED.product,
                        kind = EXCLUDED.kind,
                        release_note_type = EXCLUDED.release_note_type,
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        source_url = EXCLUDED.source_url,
                        published_at = EXCLUDED.published_at,
                        ingested_at = now()
                    """,
                    rows,
                )
            await _mark_connected(
                connection,
                connection_id=connection_id,
                provider_id=link["provider_id"],
                fetched_at=fetched_at,
                snapshot_sha256=snapshot_sha256,
            )
            provider_id = link["provider_id"]
        slug = await connection.fetchval(
            "SELECT slug FROM providers WHERE id = $1",
            provider_id,
        )
        if slug:
            from packages.state.findings import refresh_subscribed_projects

            await refresh_subscribed_projects(connection, str(slug))


async def _mark_connected(
    connection: asyncpg.Connection,
    *,
    connection_id: UUID,
    provider_id: UUID,
    fetched_at: datetime,
    snapshot_sha256: str,
) -> None:
    await connection.execute(
        """
        UPDATE provider_connections
        SET status = 'connected',
            last_error = NULL,
            snapshot_sha256 = $2,
            fetched_at = $3,
            connected_at = COALESCE(connected_at, $3),
            updated_at = now()
        WHERE id = $1 AND disconnected_at IS NULL
        """,
        connection_id,
        snapshot_sha256,
        fetched_at,
    )
    await connection.execute(
        """
        UPDATE providers
        SET status = 'live', updated_at = now()
        WHERE id = $1 AND retired_at IS NULL
        """,
        provider_id,
    )


async def disconnect_connection(
    pool: asyncpg.Pool,
    *,
    slug: str,
    kind: str,
    actor: UUID | None,
) -> None:
    async with pool.acquire() as connection:
        async with connection.transaction():
            provider = await connection.fetchrow(
                "SELECT * FROM providers WHERE slug = $1 AND retired_at IS NULL",
                slug,
            )
            if provider is None:
                raise ProviderStoreError("Provider not found.")
            owner = provider["owner_user_id"]
            if owner is not None and actor is not None and owner != actor:
                raise ProviderStoreError("Only the owning user can disconnect this provider.")
            link = await connection.fetchrow(
                """
                SELECT id FROM provider_connections
                WHERE provider_id = $1 AND kind = $2 AND disconnected_at IS NULL
                """,
                provider["id"],
                kind,
            )
            if link is None:
                raise ProviderStoreError("No connection to disconnect.")
            now = datetime.now(UTC)
            await connection.execute(
                """
                UPDATE provider_connections
                SET status = 'disconnected', disconnected_at = $2, updated_at = $2
                WHERE id = $1
                """,
                link["id"],
                now,
            )
            await connection.execute(
                """
                UPDATE provider_services
                SET retired_at = COALESCE(retired_at, $2)
                WHERE connection_id = $1 AND retired_at IS NULL
                """,
                link["id"],
                now,
            )
            remaining = await connection.fetchval(
                """
                SELECT count(*) FROM provider_connections
                WHERE provider_id = $1
                  AND disconnected_at IS NULL
                  AND status = 'connected'
                """,
                provider["id"],
            )
            if int(remaining or 0) == 0:
                await connection.execute(
                    """
                    UPDATE providers
                    SET status = 'draft', updated_at = now()
                    WHERE id = $1
                    """,
                    provider["id"],
                )


async def list_services(pool: asyncpg.Pool, slug: str) -> tuple[list[dict[str, Any]], str | None]:
    async with pool.acquire() as connection:
        provider = await connection.fetchrow(
            "SELECT id FROM providers WHERE slug = $1 AND retired_at IS NULL",
            slug,
        )
        if provider is None:
            raise ProviderStoreError("Provider not found.")
        fetched = await connection.fetchval(
            """
            SELECT fetched_at FROM provider_connections
            WHERE provider_id = $1 AND kind = 'catalog'
              AND disconnected_at IS NULL AND status = 'connected'
            """,
            provider["id"],
        )
        rows = await connection.fetch(
            """
            SELECT s.* FROM provider_services s
            JOIN provider_connections c ON c.id = s.connection_id
            WHERE s.provider_id = $1
              AND s.retired_at IS NULL
              AND c.disconnected_at IS NULL
              AND c.status = 'connected'
              AND c.kind = 'catalog'
            ORDER BY s.service_group, s.name
            """,
            provider["id"],
        )
    services = [
        {
            "id": row["external_id"],
            "name": row["name"],
            "slug": row["slug"],
            "product": row["product"],
            "group": row["service_group"],
            "summary": row["summary"],
            "status": row["status"],
            "identifiers": list(row["identifiers"] or []),
            "docsUrl": row["docs_url"] or "",
            "watchers": 0,
            "lastPublishedAt": _iso(row["last_seen_at"]) or "",
        }
        for row in rows
    ]
    return services, _iso(fetched)


async def list_change_notes(
    pool: asyncpg.Pool,
    slug: str,
    *,
    q: str = "",
    kind: str = "",
    since: str = "",
    until: str = "",
    limit: int = 75,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, str | None, str | None]:
    async with pool.acquire() as connection:
        provider = await connection.fetchrow(
            "SELECT id FROM providers WHERE slug = $1 AND retired_at IS NULL",
            slug,
        )
        if provider is None:
            raise ProviderStoreError("Provider not found.")
        link = await connection.fetchrow(
            """
            SELECT canonical_url, fetched_at FROM provider_connections
            WHERE provider_id = $1 AND kind = 'changes'
              AND disconnected_at IS NULL AND status = 'connected'
            """,
            provider["id"],
        )
        if link is None:
            return [], 0, None, None
        query = q.strip().lower()
        wanted = kind.strip().lower()
        if wanted in {"", "all"}:
            wanted = ""
        clauses = [
            "n.provider_id = $1",
            "c.disconnected_at IS NULL",
            "c.status = 'connected'",
            "c.kind = 'changes'",
        ]
        args: list[Any] = [provider["id"]]
        if wanted:
            args.append(wanted)
            clauses.append(f"n.kind = ${len(args)}")
        since_day = published_day(since)
        until_day = published_day(until)
        if since_day:
            args.append(date.fromisoformat(since_day))
            clauses.append(f"(n.published_at AT TIME ZONE 'UTC')::date >= ${len(args)}")
        if until_day:
            args.append(date.fromisoformat(until_day))
            clauses.append(f"(n.published_at AT TIME ZONE 'UTC')::date <= ${len(args)}")
        if query:
            args.append(f"%{query}%")
            idx = len(args)
            clauses.append(
                f"(n.title ILIKE ${idx} OR n.summary ILIKE ${idx} "
                f"OR n.product ILIKE ${idx} OR n.kind ILIKE ${idx})"
            )
        where = " AND ".join(clauses)
        total = await connection.fetchval(
            f"""
            SELECT count(*) FROM provider_change_notes n
            JOIN provider_connections c ON c.id = n.connection_id
            WHERE {where}
            """,
            *args,
        )
        size = min(max(limit, 1), 200)
        start = max(offset, 0)
        args.extend([size, start])
        rows = await connection.fetch(
            f"""
            SELECT n.* FROM provider_change_notes n
            JOIN provider_connections c ON c.id = n.connection_id
            WHERE {where}
            ORDER BY n.published_at DESC, n.product
            LIMIT ${len(args) - 1} OFFSET ${len(args)}
            """,
            *args,
        )
    notes = [
        {
            "id": row["external_id"],
            "serviceId": row["product"],
            "product": row["product"],
            "title": row["title"],
            "summary": row["summary"],
            "kind": row["kind"],
            "releaseNoteType": row["release_note_type"] or "",
            "status": "published",
            "effectiveAt": _iso(row["published_at"]) or "",
            "retiredIdentifiers": [],
            "recommendedReplacement": None,
            "sourceUrl": row["source_url"],
            "publishedAt": _iso(row["published_at"]) or "",
        }
        for row in rows
    ]
    return notes, int(total or 0), link["canonical_url"], _iso(link["fetched_at"])


async def list_project_subscriptions(
    pool: asyncpg.Pool, project_id: UUID
) -> list[dict[str, Any]]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT p.*, s.subscribed_at
            FROM project_provider_subscriptions s
            JOIN providers p ON p.id = s.provider_id
            WHERE s.project_id = $1 AND p.retired_at IS NULL
            ORDER BY p.name
            """,
            project_id,
        )
    return [
        {
            **provider_payload(row, connections={"catalog": None, "changes": None}),
            "subscribed": True,
            "subscribed_at": _iso(row["subscribed_at"]),
        }
        for row in rows
    ]


async def subscribe_project(pool: asyncpg.Pool, project_id: UUID, slug: str) -> None:
    async with pool.acquire() as connection:
        provider = await connection.fetchrow(
            "SELECT id FROM providers WHERE slug = $1 AND retired_at IS NULL",
            slug,
        )
        if provider is None:
            raise ProviderStoreError("Provider not found.")
        await connection.execute(
            """
            INSERT INTO project_provider_subscriptions (project_id, provider_id)
            VALUES ($1, $2)
            ON CONFLICT (project_id, provider_id) DO NOTHING
            """,
            project_id,
            provider["id"],
        )


async def unsubscribe_project(pool: asyncpg.Pool, project_id: UUID, slug: str) -> None:
    async with pool.acquire() as connection:
        provider = await connection.fetchrow(
            "SELECT id FROM providers WHERE slug = $1 AND retired_at IS NULL",
            slug,
        )
        if provider is None:
            raise ProviderStoreError("Provider not found.")
        await connection.execute(
            """
            DELETE FROM project_provider_subscriptions
            WHERE project_id = $1 AND provider_id = $2
            """,
            project_id,
            provider["id"],
        )


def require_pool(pool: asyncpg.Pool | None) -> asyncpg.Pool:
    if pool is None:
        raise StateUnavailableError("no connection pool; the service has not completed startup")
    return pool
