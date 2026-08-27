"""The verifier is independent, and PASS is only expressible when earned."""

import pytest
from pydantic import ValidationError

from packages.schemas import CheckOutcome, Verdict, VerificationReport


def test_the_patch_author_cannot_grade_itself(load_golden):
    document = load_golden("verification_report.egaki.json")
    document["verifier_agent_id"] = document["patch_agent_id"]

    with pytest.raises(ValidationError, match="must be independent"):
        VerificationReport.model_validate(document)


@pytest.mark.parametrize("check", ["build", "tests", "live_api", "policy"])
def test_pass_rejects_a_failed_check(check, load_golden):
    document = load_golden("verification_report.egaki.json")
    document[check] = CheckOutcome.FAIL.value

    with pytest.raises(ValidationError, match=r"failed check|policy to pass"):
        VerificationReport.model_validate(document)


def test_pass_allows_a_skipped_live_check_when_the_local_gate_is_green(load_golden):
    document = load_golden("verification_report.egaki.json")
    document["live_api"] = CheckOutcome.SKIP.value
    report = VerificationReport.model_validate(document)
    assert report.permits_pull_request is True


def test_pass_allows_skipped_local_checks_when_live_resolves(load_golden):
    document = load_golden("verification_report.egaki.json")
    document["build"] = CheckOutcome.SKIP.value
    document["tests"] = CheckOutcome.SKIP.value
    report = VerificationReport.model_validate(document)
    assert report.permits_pull_request is True


def test_pass_rejects_when_neither_gate_ran(load_golden):
    document = load_golden("verification_report.egaki.json")
    document["build"] = CheckOutcome.SKIP.value
    document["tests"] = CheckOutcome.SKIP.value
    document["live_api"] = CheckOutcome.SKIP.value

    with pytest.raises(ValidationError, match="local gate or a live provider resolve"):
        VerificationReport.model_validate(document)


def test_an_unavailable_live_check_is_inconclusive(load_golden):
    document = load_golden("verification_report.egaki.json")
    document.update(live_api=CheckOutcome.SKIP.value, verdict=Verdict.INCONCLUSIVE.value)

    report = VerificationReport.model_validate(document)

    assert report.permits_pull_request is False


def test_a_failed_check_is_not_inconclusive(load_golden):
    document = load_golden("verification_report.egaki.json")
    document.update(tests=CheckOutcome.FAIL.value, verdict=Verdict.INCONCLUSIVE.value)

    with pytest.raises(ValidationError, match="not INCONCLUSIVE"):
        VerificationReport.model_validate(document)


def test_pass_requires_an_untouched_forbidden_surface(load_golden):
    document = load_golden("verification_report.egaki.json")
    document["unexpected_files"] = [".github/workflows/release.yml"]

    with pytest.raises(ValidationError, match="no unexpected file changes"):
        VerificationReport.model_validate(document)


def test_pass_requires_the_retired_identifiers_to_be_gone(load_golden):
    document = load_golden("verification_report.egaki.json")
    document["deprecated_identifiers_absent"] = False

    with pytest.raises(ValidationError, match="retired identifiers to be gone"):
        VerificationReport.model_validate(document)


def test_pass_requires_evidence(load_golden):
    document = load_golden("verification_report.egaki.json")
    document["evidence"] = []

    with pytest.raises(ValidationError, match="at least one piece of evidence"):
        VerificationReport.model_validate(document)


def test_a_failing_run_may_be_reported_without_evidence(load_golden):
    document = load_golden("verification_report.egaki.json")
    document.update(
        verdict=Verdict.FAIL.value,
        tests=CheckOutcome.FAIL.value,
        evidence=[],
        notes="Vitest exited non-zero after the third attempt.",
    )

    report = VerificationReport.model_validate(document)

    assert report.permits_pull_request is False


def test_evidence_uri_scheme_is_restricted(load_golden):
    document = load_golden("verification_report.egaki.json")
    document["evidence"] = [{"kind": "build_log", "uri": "http2://elsewhere/build.log"}]

    with pytest.raises(ValidationError, match="is not one of"):
        VerificationReport.model_validate(document)
