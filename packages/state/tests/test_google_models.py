# HTML fixtures are easier to read as single-row tables.
# ruff: noqa: E501
"""Gemini / Vertex lifecycle parsing: dates, tables, and the HTTP surface."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.state.google_models import (
    CatalogUnavailableError,
    build_snapshot,
    extract_model_id,
    infer_status,
    load_google_models,
    parse_lifecycle_tables,
    parse_provider_date,
)
from packages.state.provider_routes import router as provider_router

GEMINI_HTML = """
<table>
  <tr><th>Model</th><th>Release date</th><th>Shutdown date</th><th>Recommended replacement</th></tr>
  <tr><td>gemini-3.5-flash</td><td>May 19, 2026</td><td>No shutdown date announced</td><td></td></tr>
  <tr><td>gemini-3.7-flash</td><td>August 2026</td><td>No shutdown date announced</td><td></td></tr>
  <tr><td>Preview models</td><td></td><td></td><td></td></tr>
  <tr><td>gemini-3.1-flash-image-preview</td><td>February 26, 2026</td><td>June 25, 2026</td><td>gemini-3.1-flash-image</td></tr>
  <tr><td>imagen-4.0-generate-001</td><td>June 24, 2025</td><td>August 17, 2026</td><td>gemini-3.1-flash-image</td></tr>
</table>
"""

VERTEX_HTML = """
<table>
  <tr><th>Model ID</th><th>Release date</th><th>Retirement date</th><th>Replacement model</th></tr>
  <tr><td>gemini-3.5-flash</td><td>May 19, 2026</td><td>May 19, 2027 or later</td><td></td></tr>
  <tr><td>gemini-2.0-flash</td><td>February 5, 2025</td><td>June 1, 2026</td><td>gemini-3.1-flash-lite</td></tr>
</table>
"""


def test_parse_provider_date_keeps_month_only_without_inventing_a_day() -> None:
    assert parse_provider_date("August 2026") == ("2026-08", None)
    assert parse_provider_date("May 19, 2026") == ("2026-05-19", None)
    assert parse_provider_date("No shutdown date announced") == (None, None)
    assert parse_provider_date("May 19, 2027 or later") == ("2027-05-19", "or_later")
    assert parse_provider_date("No sooner than May 20, 2028") == ("2028-05-20", "no_sooner_than")
    assert parse_provider_date("sometime soon") == (None, None)


def test_extract_model_id_does_not_invent_an_identifier() -> None:
    assert extract_model_id("gemini-3.1-flash-image") == "gemini-3.1-flash-image"
    assert extract_model_id("Gemini 3.5 Flash") is None
    assert extract_model_id("veo-3.1-generate-previewor the GA models") == "veo-3.1-generate-preview"


def test_infer_status_uses_past_shutdown_and_preview_suffix() -> None:
    today = date(2026, 8, 15)
    assert (
        infer_status(
            model_id="gemini-2.0-flash",
            launch_stage="GA",
            shutdown_date="2026-06-01",
            preview_section=False,
            today=today,
        )
        == "retired"
    )
    assert (
        infer_status(
            model_id="gemini-3.1-flash-image-preview",
            launch_stage=None,
            shutdown_date="2026-06-25",
            preview_section=True,
            today=today,
        )
        == "retired"
    )
    assert (
        infer_status(
            model_id="gemini-3.1-pro-preview",
            launch_stage="PUBLIC_PREVIEW",
            shutdown_date=None,
            preview_section=True,
            today=today,
        )
        == "preview"
    )
    assert (
        infer_status(
            model_id="gemini-3.5-flash",
            launch_stage="GA",
            shutdown_date="2027-05-19",
            preview_section=False,
            today=today,
        )
        == "live"
    )


def test_parse_lifecycle_tables_skips_section_headers() -> None:
    rows = parse_lifecycle_tables(
        GEMINI_HTML,
        surface="gemini_api",
        source_url="https://ai.google.dev/gemini-api/docs/deprecations",
    )
    ids = [row.model_id for row in rows]
    assert "Preview models" not in ids
    assert "imagen-4.0-generate-001" in ids
    imagen = next(row for row in rows if row.model_id == "imagen-4.0-generate-001")
    assert imagen.shutdown_date == "2026-08-17"
    assert imagen.replacement == "gemini-3.1-flash-image"
    flash = next(row for row in rows if row.model_id == "gemini-3.7-flash")
    assert flash.release_date == "2026-08"
    assert flash.shutdown_date is None
    preview = next(row for row in rows if row.model_id == "gemini-3.1-flash-image-preview")
    assert preview.preview_section is True


def test_build_snapshot_emits_changes_only_for_day_precision_shutdowns() -> None:
    snapshot = build_snapshot(
        gemini_html=GEMINI_HTML,
        vertex_html=VERTEX_HTML,
        gemini_raw=[
            {
                "name": "models/gemini-3.5-flash",
                "displayName": "Gemini 3.5 Flash",
                "description": "Fast GA model",
                "version": "3.5",
            }
        ],
        vertex_raw=[
            {
                "name": "publishers/google/models/gemini-3.5-flash",
                "launchStage": "GA",
                "versionId": "default",
            }
        ],
        fetched_at="2026-08-16T00:00:00Z",
        today=date(2026, 8, 15),
        sources=(),
    )
    change_ids = {change.id: change for change in snapshot.changes}
    assert "gemini_api:imagen-4.0-generate-001" in change_ids
    assert change_ids["gemini_api:imagen-4.0-generate-001"].recommended_replacement == (
        "gemini-3.1-flash-image"
    )
    assert change_ids["vertex:gemini-2.0-flash"].status == "superseded"
    assert "gemini_api:gemini-3.7-flash" not in change_ids
    gemini_flash = next(
        model
        for model in snapshot.models
        if model.id == "gemini-3.5-flash" and model.surface == "gemini_api"
    )
    assert gemini_flash.display_name == "Gemini 3.5 Flash"
    assert gemini_flash.launch_stage is None
    vertex_flash = next(
        model
        for model in snapshot.models
        if model.id == "gemini-3.5-flash" and model.surface == "vertex"
    )
    assert vertex_flash.launch_stage == "GA"
    assert vertex_flash.shutdown_date == "2027-05-19"
    assert vertex_flash.shutdown_qualifier == "or_later"


def test_load_google_models_reads_the_committed_snapshot() -> None:
    snapshot = load_google_models()
    assert len(snapshot.models) >= 50
    assert len(snapshot.changes) >= 10
    names = {model.id for model in snapshot.models}
    assert "imagen-4.0-generate-001" in names
    assert "gemini-3.5-flash" in names
    imagen = next(
        change for change in snapshot.changes if "imagen-4.0-generate-001" in change.id
    )
    assert imagen.effective_at.startswith("2026-08-17")
    assert imagen.recommended_replacement == "gemini-3.1-flash-image"


def test_google_route_includes_model_changes() -> None:
    app = FastAPI()
    app.include_router(provider_router)
    response = TestClient(app).get("/api/providers/google")
    assert response.status_code == 200
    body = response.json()
    assert len(body["changes"]) >= 10
    assert any(row["id"] == "imagen-4.0-generate-001" for row in body["models"])
    assert body["modelTrust"]["classification"] == "untrusted_provider_input"


def test_load_google_models_fails_closed_when_snapshot_is_missing(tmp_path: Path) -> None:
    try:
        load_google_models(path=tmp_path / "missing.json")
    except CatalogUnavailableError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected CatalogUnavailableError")
