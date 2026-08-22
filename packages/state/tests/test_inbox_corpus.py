"""Official notes become inbox events only when the index already names them."""

from datetime import date

from packages.state.google_models import ModelChange, load_google_models
from packages.state.inbox_corpus import (
    catalog_notes_for_usages,
    identifier_is_covered,
    manifest_event,
    note_identifiers_in_text,
    product_for_identifier,
    release_note_event,
)


def _change(
    model_id: str,
    *,
    effective: str = "2026-08-17T00:00:00Z",
    replacement: str | None = "gemini-3.1-flash-image",
) -> ModelChange:
    return ModelChange(
        id=f"gemini_api:{model_id}",
        service_id="generativelanguage.googleapis.com",
        title=f"{model_id} shuts down",
        kind="deprecation",
        status="published",
        effective_at=effective,
        retired_identifiers=(model_id,),
        recommended_replacement=replacement,
        source_url="https://ai.google.dev/gemini-api/docs/deprecations",
        published_at="2025-06-24T00:00:00Z",
    )


def test_catalog_notes_only_for_used_uncovered_ids() -> None:
    notes = catalog_notes_for_usages(
        (_change("imagen-4.0-generate-001"), _change("gemini-1.5-flash-001")),
        ["models/imagen-4.0-generate-001"],
        ["imagen-4.0-generate-001"],
        today=date(2026, 8, 22),
    )
    assert notes == ()


def test_future_catalog_retirement_is_not_fail_closed() -> None:
    notes = catalog_notes_for_usages(
        (_change("gemini-3.1-flash-image", effective="2027-05-28T00:00:00Z", replacement=None),),
        ["gemini-3.1-flash-image"],
        [],
        today=date(2026, 8, 22),
    )
    assert notes[0]["fail_closed"] is False
    assert notes[0]["severity"] == "medium"


def test_catalog_notes_emit_an_uncovered_retirement() -> None:
    notes = catalog_notes_for_usages(
        (_change("gemini-1.5-flash-001", replacement="gemini-2.5-flash"),),
        ["gemini-1.5-flash-001"],
        [],
        today=date(2026, 8, 22),
    )
    assert len(notes) == 1
    assert notes[0]["external_id"] == "catalog:gemini_api:gemini-1.5-flash-001"
    assert notes[0]["identifiers"] == ["gemini-1.5-flash-001"]
    assert notes[0]["change_kind"] == "deprecation"
    assert notes[0]["severity"] == "high"


def test_models_prefix_usage_matches_bare_catalog_id() -> None:
    notes = catalog_notes_for_usages(
        (_change("imagen-4.0-generate-001"),),
        ["models/imagen-4.0-generate-001"],
        [],
        today=date(2026, 8, 22),
    )
    assert notes[0]["identifiers"] == ["imagen-4.0-generate-001"]


def test_committed_catalog_includes_imagen_and_gemini20() -> None:
    snapshot = load_google_models()
    ids = {change.id for change in snapshot.changes}
    assert "gemini_api:imagen-4.0-generate-001" in ids
    assert "gemini_api:gemini-2.0-flash" in ids


def test_note_text_extracts_used_ids_only() -> None:
    hits = note_identifiers_in_text(
        "Imagen 4 (imagen-4.0-generate-001) is retired. Also gemini-2.0-flash.",
        ["imagen-4.0-generate-001", "gemini-3.5-flash"],
    )
    assert hits == ["imagen-4.0-generate-001"]


def test_release_note_skips_already_covered_ids() -> None:
    event = release_note_event(
        external_id="rn-1",
        product="Imagen",
        kind="deprecation",
        title="Imagen 4 shutdown",
        summary="imagen-4.0-generate-001 stops resolving",
        source_url="https://ai.google.dev/gemini-api/docs/deprecations",
        published_at="2026-08-17T00:00:00Z",
        identifiers=["imagen-4.0-generate-001"],
        covered_identifiers=["imagen-4.0-generate-001"],
    )
    assert event is None


def test_manifest_event_requires_source_url() -> None:
    assert (
        manifest_event(
            {
                "change_id": "google-imagen4-shutdown-2026-08-17",
                "affected_identifiers": ["imagen-4.0-generate-001"],
                "source_urls": [],
            }
        )
        is None
    )
    note = manifest_event(
        {
            "change_id": "google-imagen4-shutdown-2026-08-17",
            "provider": "google",
            "affected_identifiers": ["imagen-4.0-generate-001"],
            "recommended_replacement": "gemini-3.1-flash-image",
            "source_urls": ["https://ai.google.dev/gemini-api/docs/deprecations"],
            "effective_at": "2026-08-17",
            "semantic_migration_required": True,
        }
    )
    assert note is not None
    assert note["migration"] == "semantic"
    assert note["identifiers"] == ["imagen-4.0-generate-001"]


def test_product_and_cover_helpers() -> None:
    assert product_for_identifier("vertex/imagen-4.0-generate-001") == "Imagen"
    assert identifier_is_covered("models/imagen-4.0-generate-001", {"imagen-4.0-generate-001"})
