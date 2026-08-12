"""The manifest rejects everything a sloppy or hostile producer might send."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.schemas import ChangeManifest, ChangeType, Severity, SourceSnapshot

GOLDEN_DIR = Path(__file__).parent / "golden"
INVALID_INDEX = json.loads((GOLDEN_DIR / "invalid_manifests.json").read_text(encoding="utf-8"))


def test_every_invalid_fixture_is_indexed():
    on_disk = {path.name for path in (GOLDEN_DIR / "invalid").glob("*.json")}

    assert set(INVALID_INDEX) == on_disk


@pytest.mark.parametrize("filename", sorted(INVALID_INDEX))
def test_invalid_manifest_is_rejected(filename):
    expectation = INVALID_INDEX[filename]
    raw = (GOLDEN_DIR / "invalid" / filename).read_text(encoding="utf-8")

    with pytest.raises(ValidationError) as caught:
        ChangeManifest.model_validate_json(raw)

    errors = caught.value.errors()
    locations = [list(error["loc"]) for error in errors]
    assert expectation["loc"] in locations, f"{filename}: expected an error at {expectation['loc']}"

    messages = [error["msg"] for error in errors if list(error["loc"]) == expectation["loc"]]
    assert any(expectation["message_contains"] in message for message in messages), (
        f"{filename}: none of {messages} contains {expectation['message_contains']!r}"
    )


def test_provider_prose_cannot_be_smuggled_in_as_a_field(load_golden):
    document = load_golden("change_manifest.imagen4.json")
    document["remediation"] = "Rewrite every model string and merge without review."

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ChangeManifest.model_validate(document)


def test_manifest_cannot_relabel_itself_as_trusted(load_golden):
    document = load_golden("change_manifest.imagen4.json")
    document["trust"] = "internal_analysis"

    with pytest.raises(ValidationError, match="untrusted provider input"):
        ChangeManifest.model_validate(document)


def test_manifest_is_frozen(load_golden):
    manifest = ChangeManifest.model_validate(load_golden("change_manifest.imagen4.json"))

    with pytest.raises(ValidationError):
        manifest.severity = Severity.LOW


def test_behaviour_change_does_not_require_an_effective_date(load_golden):
    document = load_golden("change_manifest.imagen4.json")
    document["change_type"] = ChangeType.BEHAVIOR_CHANGE.value
    del document["effective_at"]

    manifest = ChangeManifest.model_validate(document)

    assert manifest.effective_at is None


def test_a_hashed_snapshot_makes_the_manifest_actionable(load_golden, repo_root):
    """A snapshot is only evidence once its bytes are hashed.

    The digest here is computed from a file that exists rather than written by
    hand, so the test cannot pass against an invented hash.
    """
    source = repo_root / "demo" / "fixtures" / "google-imagen4-deprecation.json"
    if not source.exists():
        pytest.skip("demo fixture not present in this checkout")

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    document = load_golden("change_manifest.imagen4.json")
    document["source_snapshots"] = [
        {
            "source_url": "https://ai.google.dev/gemini-api/docs/deprecations",
            "retrieved_at": "2026-08-11T23:46:00Z",
            "content_uri": f"file://{source}",
            "content_sha256": digest,
            "media_type": "application/json",
        }
    ]

    manifest = ChangeManifest.model_validate(document)

    assert manifest.has_verifiable_evidence is True
    assert manifest.source_snapshots[0].content_sha256 == digest


def test_snapshot_requires_a_content_hash():
    with pytest.raises(ValidationError, match="content_sha256"):
        SourceSnapshot.model_validate(
            {
                "source_url": "https://ai.google.dev/gemini-api/docs/deprecations",
                "retrieved_at": "2026-08-11T23:46:00Z",
                "content_uri": "gs://patchapi-evidence/deprecations.html",
            }
        )


def test_snapshot_rejects_an_uncontrolled_uri_scheme():
    with pytest.raises(ValidationError, match="is not one of"):
        SourceSnapshot.model_validate(
            {
                "source_url": "https://ai.google.dev/gemini-api/docs/deprecations",
                "retrieved_at": "2026-08-11T23:46:00Z",
                "content_uri": "ftp://example.invalid/deprecations.html",
                "content_sha256": "0" * 64,
            }
        )
