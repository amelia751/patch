"""Google Cloud catalog: first-party filter, grouping, and the HTTP surface."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.state.gcp_catalog import (
    CatalogUnavailableError,
    classify_group,
    coerce_summary,
    display_name,
    is_first_party,
    load_google_catalog,
    normalize_service,
    project_id,
)
from packages.state.provider_routes import router as provider_router


def test_first_party_keeps_googleapis_and_drops_marketplace() -> None:
    assert is_first_party("storage.googleapis.com")
    assert is_first_party("aiplatform.googleapis.com")
    marketplace = "a10-vthunder-adc-byol.endpoints.a10networks-public-396315.cloud.goog"
    assert not is_first_party(marketplace)
    assert not is_first_party("something.cloud.goog")


def test_classify_group_uses_the_api_name() -> None:
    assert classify_group("aiplatform.googleapis.com", "Vertex AI API") == "ai"
    assert classify_group("generativelanguage.googleapis.com", "Generative Language API") == "ai"
    assert classify_group("storage.googleapis.com", "Cloud Storage API") == "storage"
    assert classify_group("compute.googleapis.com", "Compute Engine API") == "compute"
    assert classify_group("spanner.googleapis.com", "Cloud Spanner API") == "database"
    assert classify_group("secretmanager.googleapis.com", "Secret Manager API") == "security"
    assert classify_group("dns.googleapis.com", "Cloud DNS API") == "networking"
    assert classify_group("sheets.googleapis.com", "Google Sheets API") == "api"


def test_normalize_service_drops_marketplace_rows() -> None:
    assert (
        normalize_service(
            {
                "config": {
                    "name": "foo.endpoints.vendor-public.cloud.goog",
                    "title": "Vendor Appliance",
                }
            }
        )
        is None
    )


def test_normalize_service_maps_a_first_party_row() -> None:
    service = normalize_service(
        {
            "name": "projects/demo/services/storage.googleapis.com",
            "config": {"name": "storage.googleapis.com", "title": "Cloud Storage API"},
            "state": "ENABLED",
        }
    )
    assert service is not None
    assert service.id == "storage.googleapis.com"
    assert service.name == "Cloud Storage"
    assert service.product == "Cloud Storage"
    assert service.group == "storage"
    assert service.identifiers == ("storage.googleapis.com",)
    assert service.docs_url.endswith("storage.googleapis.com")
    assert service.summary == "Google Cloud service storage.googleapis.com"


def test_display_name_strips_catalog_api_suffix_only() -> None:
    assert display_name("AlloyDB API") == "AlloyDB"
    assert display_name("Vertex AI API") == "Vertex AI"
    assert display_name("Places API (New)") == "Places (New)"
    assert display_name("YouTube Data API v3") == "YouTube Data v3"
    assert display_name("Ad Exchange Buyer API II") == "Ad Exchange Buyer II"
    assert display_name("Data Analytics API with Gemini") == "Data Analytics with Gemini"
    assert display_name("Safe Browsing API (Legacy)") == "Safe Browsing (Legacy)"
    assert display_name("Cloud Storage") == "Cloud Storage"
    assert display_name("App Engine") == "App Engine"
    assert display_name("API Discovery Service") == "API Discovery Service"
    assert display_name("Content API for Shopping") == "Content API for Shopping"
    assert display_name("Google Cloud APIs") == "Google Cloud APIs"
    assert display_name("Anthos Identity Service") == "Anthos Identity Service"


def test_coerce_summary_unwraps_documentation_objects_and_reprs() -> None:
    assert coerce_summary({"summary": "Train, serve, and manage ML models."}) == (
        "Train, serve, and manage ML models."
    )
    assert coerce_summary(
        "{'summary': 'Retrieves the list of AMP URLs (and equivalent AMP Cache URLs) "
        "for a given list of public URL(s).\\n'}"
    ) == (
        "Retrieves the list of AMP URLs (and equivalent AMP Cache URLs) "
        "for a given list of public URL(s)."
    )
    assert coerce_summary("Views Abusive Experience Report data.") == (
        "Views Abusive Experience Report data."
    )


def test_normalize_service_reads_documentation_summary() -> None:
    service = normalize_service(
        {
            "config": {
                "name": "aiplatform.googleapis.com",
                "title": "Vertex AI API",
                "documentation": {"summary": "Train, serve, and manage ML models."},
            }
        }
    )
    assert service is not None
    assert service.summary == "Train, serve, and manage ML models."
    assert service.group == "ai"


def test_project_id_prefers_the_environment(tmp_path: Path) -> None:
    key = tmp_path / "sa.json"
    key.write_text('{"project_id": "from-file"}', encoding="utf-8")
    assert project_id(key, {"GCP_PROJECT": "from-env"}) == "from-env"


def test_project_id_reads_only_project_id(tmp_path: Path) -> None:
    key = tmp_path / "sa.json"
    key.write_text('{"project_id": "patch-demo", "private_key": "REDACTED"}', encoding="utf-8")
    assert project_id(key, {}) == "patch-demo"


def test_project_id_fails_closed_on_garbage(tmp_path: Path) -> None:
    key = tmp_path / "sa.json"
    key.write_text("{not json", encoding="utf-8")
    try:
        project_id(key, {})
    except CatalogUnavailableError as exc:
        assert "unreadable" in str(exc)
    else:
        raise AssertionError("expected CatalogUnavailableError")


def test_google_route_is_mounted_at_providers_slug() -> None:
    source = Path(__file__).resolve().parents[1] / "provider_routes.py"
    text = source.read_text(encoding="utf-8")
    assert 'prefix="/api/providers"' in text
    assert '@router.get("/{slug}")' in text
    assert '@router.get("/{slug}/services")' in text
    assert "list_services" in text


def test_load_google_catalog_reads_the_committed_snapshot() -> None:
    catalog = load_google_catalog()
    assert len(catalog.services) >= 500
    assert all(is_first_party(service.id) for service in catalog.services)
    names = {service.id for service in catalog.services}
    assert "aiplatform.googleapis.com" in names
    assert "storage.googleapis.com" in names


def test_google_route_needs_postgres() -> None:
    app = FastAPI()
    app.include_router(provider_router)
    response = TestClient(app).get("/api/providers/google")
    assert response.status_code == 503


def test_load_google_catalog_fails_closed_when_snapshot_is_missing(tmp_path: Path) -> None:
    try:
        load_google_catalog(path=tmp_path / "missing.json")
    except CatalogUnavailableError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected CatalogUnavailableError")
