"""Feed → `ChangeManifest`: the accepted mapping and the refused documents."""

import shutil

import pytest
from pydantic import ValidationError

from packages.providers.google.errors import ProviderEvidenceError
from packages.providers.google.normalize import (
    load_notice_file,
    manifest_from_feed_file,
    notice_to_manifest,
)
from packages.providers.google.snapshot import sha256_file
from packages.schemas.change_manifest import ChangeManifest
from packages.schemas.enums import ChangeType, Severity, TrustClassification

# Every refused document, with the reason it must be refused for. Asserting the
# message keeps a fixture from passing this suite by failing for some unrelated
# second defect.
REJECTED: dict[str, str] = {
    "announced-after-effective.json": "must not be later than",
    "duplicate-identifiers.json": "must not repeat",
    "no-affected-identifiers.json": "at least 1 item",
    "no-source-urls.json": "at least 1 item",
    "replacement-also-retired.json": "also listed as retired",
    "retirement-without-effective-date.json": "requires an effective_at date",
    "smuggled-remediation-field.json": "Extra inputs are not permitted",
    "snapshot-captured-without-hash.json": "must carry sha256",
    "trust-claims-internal-analysis.json": "untrusted input",
    "unknown-change-type.json": "vibes_shift",
    "unknown-feed-version.json": "unsupported deprecation feed version",
    "wrong-provider.json": "cannot read a 'acme-cloud' feed",
}


def test_demo_fixture_normalizes_to_a_manifest(demo_fixture_path):
    manifest = manifest_from_feed_file(demo_fixture_path)

    assert isinstance(manifest, ChangeManifest)
    assert manifest.schema_version == "1.0.0"
    assert manifest.provider == "google"
    assert manifest.change_id == "imagen4-retirement-2026-08-17"
    assert manifest.change_type is ChangeType.MODEL_RETIREMENT
    assert manifest.severity is Severity.CRITICAL
    assert manifest.trust is TrustClassification.UNTRUSTED_PROVIDER_INPUT
    assert manifest.retires("imagen-4.0-generate-001")
    assert manifest.recommended_replacement == "gemini-3.1-flash-image"


def test_demo_fixture_requires_a_semantic_migration(demo_fixture_path):
    """No `migration_character` in the feed means the change is not a string rewrite."""
    manifest = manifest_from_feed_file(demo_fixture_path)
    assert manifest.semantic_migration_required is True
    assert manifest.migration_constraints
    assert any("different request surfaces" in line for line in manifest.migration_constraints)


def test_normalized_constraints_describe_the_replacement_surface(demo_fixture_path):
    """Retired-family bullets are dropped; what the replacement lacks is what constrains."""
    manifest = manifest_from_feed_file(demo_fixture_path)
    joined = " ".join(manifest.migration_constraints)
    assert "response parts of a content generation call" in joined
    assert "Dedicated image-generation endpoint" not in joined
    assert len(manifest.migration_constraints) == len(set(manifest.migration_constraints))


def test_uncaptured_snapshot_leaves_the_manifest_without_evidence(demo_fixture_path):
    manifest = manifest_from_feed_file(demo_fixture_path)
    assert manifest.source_snapshots == []
    assert manifest.has_verifiable_evidence is False


def test_manifest_round_trips_as_json(demo_fixture_path):
    manifest = manifest_from_feed_file(demo_fixture_path)
    assert ChangeManifest.model_validate_json(manifest.model_dump_json()) == manifest


def test_captured_snapshot_becomes_hashed_evidence(golden_dir):
    manifest = manifest_from_feed_file(golden_dir / "valid" / "captured-snapshot.json")

    assert manifest.has_verifiable_evidence is True
    (snapshot,) = manifest.source_snapshots
    assert snapshot.content_uri.startswith("file://")
    assert snapshot.content_uri.endswith("/golden/pages/deprecations.html")
    assert snapshot.content_sha256 == sha256_file(golden_dir / "pages" / "deprecations.html")


def test_a_feed_declared_mechanical_is_not_forced_semantic(golden_dir):
    manifest = manifest_from_feed_file(golden_dir / "valid" / "mechanical-parameter-change.json")
    assert manifest.semantic_migration_required is False
    assert manifest.severity is Severity.MEDIUM
    assert manifest.migration_constraints == []


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_invalid_feed_documents_are_refused(golden_dir, name):
    with pytest.raises(ValidationError, match=REJECTED[name]):
        manifest_from_feed_file(golden_dir / "invalid" / name)


def test_every_invalid_golden_is_covered(golden_dir):
    on_disk = {path.name for path in (golden_dir / "invalid").glob("*.json")}
    assert on_disk == set(REJECTED)


def test_a_capture_whose_bytes_are_absent_is_not_evidence(golden_dir):
    with pytest.raises(ProviderEvidenceError, match="no file is there"):
        manifest_from_feed_file(golden_dir / "unverifiable" / "snapshot-path-missing.json")


def test_a_capture_that_no_longer_hashes_is_rejected(golden_dir):
    with pytest.raises(ProviderEvidenceError, match="hashes to"):
        manifest_from_feed_file(golden_dir / "unverifiable" / "snapshot-hash-mismatch.json")


def test_snapshot_paths_resolve_against_an_explicit_base_dir(golden_dir, tmp_path):
    """A relocated capture is verified where the caller says it lives, not where the feed sat."""
    (tmp_path / "pages").mkdir()
    shutil.copy(
        golden_dir / "pages" / "deprecations.html", tmp_path / "pages" / "deprecations.html"
    )
    notice = load_notice_file(golden_dir / "valid" / "captured-snapshot.json")

    manifest = notice_to_manifest(notice, base_dir=tmp_path / "valid")

    (snapshot,) = manifest.source_snapshots
    assert snapshot.content_uri == (tmp_path / "pages" / "deprecations.html").resolve().as_uri()
