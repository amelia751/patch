"""The feed model accepts the pinned demo document and refuses smuggled structure."""

import json

import pytest
from pydantic import ValidationError

from packages.providers.google.deprecation_feed import GoogleDeprecationNotice, SnapshotStatus
from packages.providers.google.normalize import load_notice, load_notice_file
from packages.schemas.enums import ChangeType, TrustClassification


def test_demo_fixture_parses(demo_fixture_path):
    assert demo_fixture_path.is_file(), f"pinned demo fixture missing: {demo_fixture_path}"
    notice = load_notice_file(demo_fixture_path)

    assert notice.provider == "google"
    assert notice.change_id == "imagen4-retirement-2026-08-17"
    assert notice.change_type is ChangeType.MODEL_RETIREMENT
    assert notice.effective_at.isoformat() == "2026-08-17"
    assert notice.recommended_replacement == "gemini-3.1-flash-image"
    assert len(notice.affected_identifiers) == 3
    assert notice.trust.classification is TrustClassification.UNTRUSTED_PROVIDER_INPUT


def test_demo_fixture_declares_no_captured_snapshot(demo_fixture_path):
    notice = load_notice_file(demo_fixture_path)
    assert notice.source_snapshot.status is SnapshotStatus.NOT_CAPTURED
    assert notice.has_captured_snapshot is False


def test_a_captured_snapshot_is_recognised(golden_dir):
    notice = load_notice_file(golden_dir / "valid" / "captured-snapshot.json")
    assert notice.has_captured_snapshot is True


def test_notice_is_frozen(demo_fixture_path):
    notice = load_notice_file(demo_fixture_path)
    with pytest.raises(ValidationError):
        notice.recommended_replacement = "imagen-4.0-generate-001"


def test_verification_requirements_are_read_as_evidence(demo_fixture_path):
    notice = load_notice_file(demo_fixture_path)
    assert notice.verification_requirements.build is True
    assert notice.verification_requirements.live_replacement_model_call is True


def test_a_dict_is_never_accepted_verbatim(demo_fixture_path):
    payload = json.loads(demo_fixture_path.read_text(encoding="utf-8"))
    assert isinstance(load_notice(payload), GoogleDeprecationNotice)


def test_capability_notes_stay_descriptive(demo_fixture_path):
    """The feed model has no field a provider could use to state a decision."""
    forbidden = {"remediation", "policy", "policy_decision", "auto_merge", "patch", "instructions"}
    assert forbidden.isdisjoint(GoogleDeprecationNotice.model_fields)
