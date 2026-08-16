"""Provider catalog HTTP surface.

`GET /api/providers/google` serves the committed Service Usage snapshot plus
the Gemini / Vertex model lifecycle snapshot. Postgres replaces those files
later; the browser still only talks to this process.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from packages.state.gcp_catalog import (
    CatalogUnavailableError,
    catalog_to_payload,
    load_google_catalog,
)
from packages.state.google_models import load_google_models, snapshot_to_payload

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
        payload["changes"] = []
    else:
        lifecycle = snapshot_to_payload(models)
        payload["models"] = lifecycle["models"]
        payload["changes"] = lifecycle["changes"]
        payload["modelTrust"] = lifecycle["trust"]
        payload["modelSources"] = lifecycle["sources"]
    return JSONResponse(payload)
