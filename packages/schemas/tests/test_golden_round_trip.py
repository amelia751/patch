"""Every contract survives JSON -> model -> JSON -> model unchanged."""

import json

import pytest

from packages.schemas import (
    ChangeManifest,
    ImpactReport,
    PatchPlan,
    PolicyDecision,
    VerificationReport,
)

GOLDEN_CASES = [
    (ChangeManifest, "change_manifest.imagen4.json"),
    (ImpactReport, "impact_report.storygen.json"),
    (PolicyDecision, "policy_decision.storygen.json"),
    (PatchPlan, "patch_plan.storygen.json"),
    (VerificationReport, "verification_report.storygen.json"),
]


@pytest.mark.parametrize(
    ("contract", "filename"), GOLDEN_CASES, ids=[case[0].CONTRACT_NAME for case in GOLDEN_CASES]
)
def test_golden_document_round_trips(contract, filename, golden_dir):
    raw = (golden_dir / filename).read_text(encoding="utf-8")

    parsed = contract.model_validate_json(raw)
    serialized = parsed.model_dump_json()
    reparsed = contract.model_validate_json(serialized)

    assert reparsed == parsed
    assert json.loads(serialized) == parsed.model_dump(mode="json")


@pytest.mark.parametrize(
    ("contract", "filename"), GOLDEN_CASES, ids=[case[0].CONTRACT_NAME for case in GOLDEN_CASES]
)
def test_serialized_document_carries_its_version(contract, filename, golden_dir):
    parsed = contract.model_validate_json((golden_dir / filename).read_text(encoding="utf-8"))

    assert json.loads(parsed.model_dump_json())["schema_version"] == parsed.schema_version


def test_change_manifest_golden_matches_the_pinned_demo_change(golden_dir):
    manifest = ChangeManifest.model_validate_json(
        (golden_dir / "change_manifest.imagen4.json").read_text(encoding="utf-8")
    )

    assert manifest.provider == "google"
    assert manifest.change_id == "imagen4-retirement-2026-08-17"
    assert manifest.retires("imagen-4.0-generate-001")
    assert manifest.recommended_replacement == "gemini-3.1-flash-image"
    assert manifest.semantic_migration_required is True
    # No snapshot has been captured and hashed yet, so the manifest is not yet
    # evidence a policy stage may act on.
    assert manifest.has_verifiable_evidence is False


def test_impact_report_golden_separates_runtime_from_documentation(golden_dir):
    report = ImpactReport.model_validate_json(
        (golden_dir / "impact_report.storygen.json").read_text(encoding="utf-8")
    )

    assert report.affected is True
    assert len(report.findings) == 3
    assert len(report.runtime_findings) == 2
    assert "README.md" in report.affected_files


def test_verification_golden_permits_a_pull_request(golden_dir):
    report = VerificationReport.model_validate_json(
        (golden_dir / "verification_report.storygen.json").read_text(encoding="utf-8")
    )

    assert report.permits_pull_request is True
    assert report.patch_agent_id != report.verifier_agent_id
