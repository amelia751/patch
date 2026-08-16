"""Provider catalog HTTP surface.

`GET /api/providers/google` serves the Service Usage and model snapshots.
`GET /api/providers/google/changes` serves the last year of release notes.
Those notes are a different shape from the API catalog: one BigQuery job,
thousands of rows, no 1 QPS list quota.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from packages.state.gcp_catalog import (
    CatalogUnavailableError,
    catalog_to_payload,
    load_google_catalog,
)
from packages.state.google_models import load_google_models
from packages.state.google_models import snapshot_to_payload as models_to_payload
from packages.state.google_release_notes import (
    filter_notes,
    load_google_release_notes,
    notes_to_changes,
)
from packages.state.google_release_notes import (
    snapshot_to_payload as notes_to_payload,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/google")
async def get_google_catalog() -> JSONResponse:
    """Return the current first-party Google Cloud API catalog."""
    try:
        catalog = load_google_catalog()
    except CatalogUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    payload = catalog_to_payload(catalog)
    try:
        models = load_google_models()
    except CatalogUnavailableError:
        payload["models"] = []
        payload["modelChanges"] = []
    else:
        lifecycle = models_to_payload(models)
        payload["models"] = lifecycle["models"]
        payload["modelChanges"] = lifecycle["changes"]
        payload["modelTrust"] = lifecycle["trust"]
        payload["modelSources"] = lifecycle["sources"]
    return JSONResponse(payload)


@router.get("/google/changes")
async def get_google_changes(
    q: str = Query(default=""),
    kind: str = Query(default=""),
    limit: int = Query(default=75, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """Return a filtered page of the committed release-notes snapshot."""
    try:
        snapshot = load_google_release_notes()
    except CatalogUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=503)
    page, total = filter_notes(snapshot.notes, q=q, kind=kind, limit=limit, offset=offset)
    payload = notes_to_payload(snapshot)
    payload["changes"] = notes_to_changes(page)
    payload["total"] = total
    payload["limit"] = limit
    payload["offset"] = offset
    payload["q"] = q
    payload["kind"] = kind
    return JSONResponse(payload)
