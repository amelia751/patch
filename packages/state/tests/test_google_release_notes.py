"""Release notes snapshot: HTML strip, type map, and the HTTP surface."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from packages.state.gcp_catalog import CatalogUnavailableError
from packages.state.google_release_notes import (
    ReleaseNote,
    build_snapshot,
    filter_notes,
    load_google_release_notes,
    normalize_note,
    note_kind,
    strip_html,
    uniquify_note_ids,
)
from packages.state.provider_routes import router as provider_router


def test_strip_html_keeps_text_only() -> None:
    assert strip_html('<p><strong>CocoaPods is deprecated.</strong> Use Swift.</p>') == (
        "CocoaPods is deprecated. Use Swift."
    )


def test_note_kind_maps_known_types_and_does_not_invent() -> None:
    assert note_kind("DEPRECATION") == "deprecation"
    assert note_kind("BREAKING_CHANGE") == "breaking_change"
    assert note_kind("FEATURE") == "feature"
    assert note_kind("not-a-real-type") == "other"


def test_normalize_note_requires_a_product_and_a_day() -> None:
    assert (
        normalize_note({"product_name": "AlloyDB", "published_at": "", "description": "x"})
        is None
    )
    note = normalize_note(
        {
            "product_name": "AlloyDB",
            "published_at": "2026-08-11",
            "release_note_type": "DEPRECATION",
            "description": "<p>Old instance type is shutting down.</p>",
        }
    )
    assert note is not None
    assert note.product == "AlloyDB"
    assert note.kind == "deprecation"
    assert note.published_at == "2026-08-11T00:00:00Z"
    assert "<p>" not in note.summary
    assert note.summary.startswith("Old instance type")


def test_build_snapshot_skips_incomplete_rows() -> None:
    snapshot = build_snapshot(
        [
            {"product_name": "", "published_at": "2026-01-01", "description": "nope"},
            {
                "product_name": "BigQuery",
                "published_at": "2026-01-02",
                "release_note_type": "FEATURE",
                "description": "New SQL syntax.",
            },
        ],
        fetched_at="2026-08-16T00:00:00Z",
    )
    assert len(snapshot.notes) == 1
    assert snapshot.notes[0].kind == "feature"


def test_load_google_release_notes_fails_closed_when_missing(tmp_path: Path) -> None:
    try:
        load_google_release_notes(path=tmp_path / "missing.json")
    except CatalogUnavailableError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("expected CatalogUnavailableError")


def test_changes_route_is_mounted() -> None:
    source = Path(__file__).resolve().parents[1] / "provider_routes.py"
    text = source.read_text(encoding="utf-8")
    assert '@router.get("/google/changes")' in text
    assert "load_google_release_notes" in text


def test_uniquify_note_ids_disambiguates_collisions() -> None:
    def note(note_id: str, product: str) -> ReleaseNote:
        return ReleaseNote(
            id=note_id,
            product=product,
            kind="feature",
            release_note_type="FEATURE",
            title=product,
            summary=product,
            published_at="2026-08-11T00:00:00Z",
            source_url="https://cloud.google.com/release-notes",
        )

    unique = uniquify_note_ids((note("rn:same", "A"), note("rn:same", "B"), note("rn:other", "C")))
    assert [item.id for item in unique] == ["rn:same", "rn:same:2", "rn:other"]


def test_filter_notes_respects_published_window() -> None:
    def note(day: str) -> ReleaseNote:
        return ReleaseNote(
            id=f"rn:{day}",
            product="BigQuery",
            kind="feature",
            release_note_type="FEATURE",
            title="BigQuery",
            summary="BigQuery",
            published_at=f"{day}T00:00:00Z",
            source_url="https://cloud.google.com/release-notes",
        )

    notes = (note("2026-08-01"), note("2026-08-10"), note("2026-08-20"))
    page, total = filter_notes(notes, since="2026-08-05", until="2026-08-15")
    assert total == 1
    assert page[0].published_at.startswith("2026-08-10")
    assert filter_notes(notes, since="not-a-day")[1] == 3


def test_filter_notes_matches_kind_and_query() -> None:
    snapshot = load_google_release_notes()
    page, total = filter_notes(snapshot.notes, kind="deprecation", limit=20, offset=0)
    assert total >= 1
    assert all(note.kind == "deprecation" for note in page)
    assert len(page) <= 20
    queried, query_total = filter_notes(snapshot.notes, q="alloydb", limit=50, offset=0)
    assert query_total == len(
        [
            note
            for note in snapshot.notes
            if "alloydb" in f"{note.product} {note.title} {note.summary}".lower()
        ]
    )
    assert all(
        "alloydb" in f"{note.product} {note.title} {note.summary}".lower() for note in queried
    )


def test_changes_route_serves_the_committed_snapshot() -> None:
    app = FastAPI()
    app.include_router(provider_router)
    response = TestClient(app).get("/api/providers/google/changes")
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 365
    assert body["total"] >= 1000
    assert len(body["changes"]) <= 75
    assert body["trust"]["classification"] == "untrusted_provider_input"
    first = body["changes"][0]
    assert first["product"]
    assert first["effectiveAt"]
    assert "<p>" not in (first.get("summary") or "")
    ids = [row["id"] for row in body["changes"]]
    assert len(ids) == len(set(ids))


def test_changes_route_filters_on_the_server() -> None:
    app = FastAPI()
    app.include_router(provider_router)
    response = TestClient(app).get("/api/providers/google/changes?kind=deprecation&limit=30")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "deprecation"
    assert all(row["kind"] == "deprecation" for row in body["changes"])
    searched = TestClient(app).get("/api/providers/google/changes?q=bigquery&limit=20")
    assert searched.status_code == 200
    for row in searched.json()["changes"]:
        hay = f"{row.get('product', '')} {row.get('title', '')} {row.get('summary', '')}".lower()
        assert "bigquery" in hay
    empty = TestClient(app).get("/api/providers/google/changes?since=2099-01-01&limit=10")
    assert empty.status_code == 200
    assert empty.json()["total"] == 0
    assert empty.json()["since"] == "2099-01-01"
