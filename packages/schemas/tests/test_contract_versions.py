"""Schema versions come from configuration, never from a call site."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.schemas import (
    CONTRACT_VERSIONS,
    ChangeManifest,
    ImpactReport,
    PatchPlan,
    PolicyDecision,
    UnknownContractError,
    VerificationReport,
    contract_version,
)

CONTRACTS = [ChangeManifest, ImpactReport, PolicyDecision, PatchPlan, VerificationReport]

GOLDEN_BY_CONTRACT = {
    ChangeManifest: "change_manifest.imagen4.json",
    ImpactReport: "impact_report.egaki.json",
    PolicyDecision: "policy_decision.egaki.json",
    PatchPlan: "patch_plan.egaki.json",
    VerificationReport: "verification_report.egaki.json",
}

SEMVER_LITERAL = re.compile(r'"\d+\.\d+\.\d+"')
PACKAGE_SRC = Path(__file__).parents[1]


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.CONTRACT_NAME)
def test_every_contract_has_a_pinned_version(contract):
    assert contract.CONTRACT_NAME in CONTRACT_VERSIONS


def test_no_contract_version_is_pinned_without_a_contract():
    declared = {contract.CONTRACT_NAME for contract in CONTRACTS}
    assert set(CONTRACT_VERSIONS) == declared


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.CONTRACT_NAME)
def test_schema_version_defaults_to_the_pinned_value(contract, load_golden):
    document = load_golden(GOLDEN_BY_CONTRACT[contract])
    assert "schema_version" not in document

    parsed = contract.model_validate(document)

    assert parsed.schema_version == contract_version(contract.CONTRACT_NAME)


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.CONTRACT_NAME)
def test_matching_schema_version_is_accepted(contract, load_golden):
    document = load_golden(GOLDEN_BY_CONTRACT[contract])
    document["schema_version"] = contract_version(contract.CONTRACT_NAME)

    assert contract.model_validate(document).schema_version == document["schema_version"]


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.CONTRACT_NAME)
def test_foreign_schema_version_is_rejected(contract, load_golden):
    document = load_golden(GOLDEN_BY_CONTRACT[contract])
    document["schema_version"] = "0.0.1"

    with pytest.raises(ValidationError, match="pinned at schema_version"):
        contract.model_validate(document)


def test_unknown_contract_fails_closed():
    with pytest.raises(UnknownContractError, match="no pinned schema version"):
        contract_version("not_a_contract")


def test_versions_are_not_inlined_in_the_models():
    offenders = [
        path.name
        for path in sorted(PACKAGE_SRC.glob("*.py"))
        if path.name != "config.py" and SEMVER_LITERAL.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"version literals belong in config.py, found in: {offenders}"
