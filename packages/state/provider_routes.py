"""Provider registry HTTP surface.

Register, connect, and disconnect persist in Postgres. Catalog and changes
lists read those tables. Live Google fetches run in the background after
Connect; a page load never crawls Service Usage or BigQuery.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from packages.state.pool import StateUnavailableError
from packages.state.provider_refresh import ingest_connection
from packages.state.provider_urls import UnsupportedProviderUrl, parse_provider_url
from packages.state.providers import (
    ProviderStoreError,
    disconnect_connection,
    get_provider,
    insert_connection,
    list_change_notes,
    list_providers,
    list_services,
    register_provider,
    require_pool,
)
from packages.state.session import COOKIE_NAME, load_session_secret, parse

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _pool(request: Request) -> asyncpg.Pool:
    return require_pool(getattr(request.app.state, "postgres_pool", None))


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


def _store_error(exc: ProviderStoreError, *, status: int = 400) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=status)


@router.get("")
async def get_providers(request: Request) -> JSONResponse:
    try:
        providers = await list_providers(_pool(request))
    except StateUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    return JSONResponse({"providers": providers})


@router.post("")
async def post_provider(request: Request) -> JSONResponse:
    user = _require_user(request)
    if isinstance(user, JSONResponse):
        return user
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"detail": "Expected a JSON object."}, status_code=400)
    if body.get("attested") is not True:
        return JSONResponse(
            {"detail": "Confirm the trust boundary before registering."},
            status_code=400,
        )
    try:
        provider = await register_provider(
            _pool(request),
            owner_user_id=user,
            name=str(body.get("name") or ""),
            slug=str(body.get("slug") or ""),
            category=str(body.get("category") or ""),
            description=str(body.get("description") or ""),
            website=str(body.get("website") or ""),
            contact_email=str(body.get("contact_email") or body.get("contactEmail") or ""),
        )
    except ProviderStoreError as exc:
        status = 409 if "already registered" in str(exc) else 400
        return _store_error(exc, status=status)
    except StateUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    return JSONResponse(provider, status_code=201)


@router.get("/{slug}/services")
async def get_provider_services(request: Request, slug: str) -> JSONResponse:
    try:
        provider = await get_provider(_pool(request), slug)
        if provider is None:
            return JSONResponse({"detail": "Provider not found."}, status_code=404)
        services, fetched_at = await list_services(_pool(request), slug)
    except ProviderStoreError as exc:
        return _store_error(exc, status=404)
    except StateUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    catalog = provider["connections"].get("catalog")
    return JSONResponse(
        {
            "provider": {
                "id": provider["slug"],
                "name": provider["name"],
                "slug": provider["slug"],
                "website": provider["website"],
                "category": provider["category"],
                "description": provider["description"],
                "verified": provider["verified"],
            },
            "source": (catalog or {}).get("source_url") or "",
            "project": ((catalog or {}).get("parsed") or {}).get("project") or "",
            "fetched_at": fetched_at or "",
            "services": services,
            "connection": catalog,
        }
    )


@router.get("/{slug}/changes")
async def get_provider_changes(
    request: Request,
    slug: str,
    q: str = Query(default=""),
    kind: str = Query(default=""),
    since: str = Query(default=""),
    until: str = Query(default=""),
    limit: int = Query(default=75, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    try:
        notes, total, source, fetched_at = await list_change_notes(
            _pool(request),
            slug,
            q=q,
            kind=kind,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )
    except ProviderStoreError as exc:
        return _store_error(exc, status=404)
    except StateUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    except Exception as exc:
        return JSONResponse({"detail": str(exc) or "Could not load changes."}, status_code=500)
    return JSONResponse(
        {
            "trust": {
                "classification": "untrusted_provider_input",
                "note": "Release notes are changelog text, not a typed shutdown catalog.",
            },
            "source": source or "",
            "fetched_at": fetched_at or "",
            "window_days": 365,
            "changes": notes,
            "total": total,
            "limit": limit,
            "offset": offset,
            "q": q,
            "kind": kind,
            "since": since,
            "until": until,
        }
    )


@router.get("/{slug}/connections")
async def get_provider_connections(request: Request, slug: str) -> JSONResponse:
    try:
        provider = await get_provider(_pool(request), slug)
    except StateUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    if provider is None:
        return JSONResponse({"detail": "Provider not found."}, status_code=404)
    return JSONResponse({"connections": provider["connections"]})


@router.post("/{slug}/connections")
async def post_provider_connection(request: Request, slug: str) -> JSONResponse:
    user = _require_user(request)
    if isinstance(user, JSONResponse):
        return user
    body = await request.json()
    if not isinstance(body, dict):
        return JSONResponse({"detail": "Expected a JSON object."}, status_code=400)
    kind = str(body.get("kind") or "").strip()
    url = str(body.get("url") or "").strip()
    if kind not in {"catalog", "changes"}:
        return JSONResponse({"detail": "kind must be catalog or changes."}, status_code=400)
    try:
        parsed = parse_provider_url(kind, url)  # type: ignore[arg-type]
        connection = await insert_connection(
            _pool(request), slug=slug, parsed=parsed, actor=user
        )
    except UnsupportedProviderUrl as exc:
        return JSONResponse({"error": exc.code, "detail": exc.detail}, status_code=422)
    except ProviderStoreError as exc:
        return _store_error(exc)
    except StateUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    asyncio.create_task(
        ingest_connection(
            _pool(request),
            connection_id=UUID(connection["id"]),
            kind=connection["kind"],
            parsed=connection["parsed"],
            canonical_url=connection["canonical_url"],
        ),
        name=f"provider-ingest-{connection['id']}",
    )
    return JSONResponse(connection, status_code=202)


@router.delete("/{slug}/connections/{kind}")
async def delete_provider_connection(request: Request, slug: str, kind: str) -> JSONResponse:
    user = _require_user(request)
    if isinstance(user, JSONResponse):
        return user
    if kind not in {"catalog", "changes"}:
        return JSONResponse({"detail": "kind must be catalog or changes."}, status_code=400)
    try:
        await disconnect_connection(_pool(request), slug=slug, kind=kind, actor=user)
    except ProviderStoreError as exc:
        return _store_error(exc)
    except StateUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    return JSONResponse({"ok": True})


@router.get("/{slug}")
async def get_provider_profile(request: Request, slug: str) -> JSONResponse:
    try:
        provider = await get_provider(_pool(request), slug)
    except StateUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    if provider is None:
        return JSONResponse({"detail": "Provider not found."}, status_code=404)
    return JSONResponse(provider)
