"""An Impact report may not claim impact it cannot point at."""

import pytest
from pydantic import ValidationError

from packages.schemas import ImpactFinding, ImpactReport, UsageKind


def test_affected_without_findings_is_rejected(load_golden):
    document = load_golden("impact_report.storygen.json")
    document["findings"] = []

    with pytest.raises(ValidationError, match="at least one finding"):
        ImpactReport.model_validate(document)


def test_unaffected_with_findings_is_rejected(load_golden):
    document = load_golden("impact_report.storygen.json")
    document["affected"] = False

    with pytest.raises(ValidationError, match="must carry no findings"):
        ImpactReport.model_validate(document)


def test_affected_without_migration_character_is_rejected(load_golden):
    document = load_golden("impact_report.storygen.json")
    del document["migration_character"]

    with pytest.raises(ValidationError, match="must state a migration_character"):
        ImpactReport.model_validate(document)


def test_affected_without_required_checks_is_rejected(load_golden):
    document = load_golden("impact_report.storygen.json")
    document["required_checks"] = []

    with pytest.raises(ValidationError, match="checks a patch has to pass"):
        ImpactReport.model_validate(document)


def test_unaffected_report_is_valid(load_golden):
    document = load_golden("impact_report.storygen.json")
    document.update(affected=False, findings=[], required_checks=[], confidence=0.99)
    del document["migration_character"]

    report = ImpactReport.model_validate(document)

    assert report.affected is False
    assert report.runtime_findings == []


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_outside_the_unit_interval_is_rejected(confidence, load_golden):
    document = load_golden("impact_report.storygen.json")
    document["confidence"] = confidence

    with pytest.raises(ValidationError):
        ImpactReport.model_validate(document)


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "../../.ssh/id_rsa", "cli\\src\\models.ts", "~/secrets.env"],
)
def test_findings_cannot_address_files_outside_the_repository(path):
    with pytest.raises(ValidationError):
        ImpactFinding.model_validate(
            {"identifier": "imagen-4.0-generate-001", "file": path, "kind": "runtime_source"}
        )


def test_documentation_hits_are_not_runtime_hits():
    finding = ImpactFinding.model_validate(
        {
            "identifier": "imagen-4.0-generate-001",
            "file": "README.md",
            "kind": UsageKind.DOCUMENTATION_EXAMPLE.value,
        }
    )

    assert finding.is_runtime is False
