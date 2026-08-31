"""Policy cannot express an action PatchAPI is not allowed to take."""

import pytest
from pydantic import ValidationError

from packages.schemas import PolicyDecision, PolicyOutcome


def test_auto_merge_cannot_be_enabled(load_golden):
    document = load_golden("policy_decision.storygen.json")
    document["auto_merge"] = True

    with pytest.raises(ValidationError, match="auto_merge"):
        PolicyDecision.model_validate(document)


def test_auto_merge_defaults_to_false_when_absent(load_golden):
    document = load_golden("policy_decision.storygen.json")
    del document["auto_merge"]

    assert PolicyDecision.model_validate(document).auto_merge is False


def test_blocked_decision_cannot_permit_patching(load_golden):
    document = load_golden("policy_decision.storygen.json")
    document["outcome"] = PolicyOutcome.BLOCKED.value

    with pytest.raises(ValidationError, match="must not permit patching"):
        PolicyDecision.model_validate(document)


def test_human_required_decision_is_analysis_only(load_golden):
    document = load_golden("policy_decision.storygen.json")
    document["outcome"] = PolicyOutcome.HUMAN_REQUIRED.value

    with pytest.raises(ValidationError, match="analysis-only"):
        PolicyDecision.model_validate(document)


def test_human_required_decision_must_flag_human_review(load_golden):
    document = load_golden("policy_decision.storygen.json")
    document.update(
        outcome=PolicyOutcome.HUMAN_REQUIRED.value,
        auto_patch=False,
        auto_pr=False,
        human_review_required=False,
    )

    with pytest.raises(ValidationError, match="human_review_required"):
        PolicyDecision.model_validate(document)


def test_pr_without_patching_is_rejected(load_golden):
    document = load_golden("policy_decision.storygen.json")
    document["auto_patch"] = False

    with pytest.raises(ValidationError, match="nothing to open a PR for"):
        PolicyDecision.model_validate(document)


def test_a_decision_must_name_forbidden_paths_and_checks(load_golden):
    for field in ("forbidden_globs", "required_checks", "rule_ids"):
        document = load_golden("policy_decision.storygen.json")
        document[field] = []

        with pytest.raises(ValidationError, match="at least 1 item"):
            PolicyDecision.model_validate(document)


def test_allow_decision_permits_patching(load_golden):
    decision = PolicyDecision.model_validate(load_golden("policy_decision.storygen.json"))

    assert decision.permits_patching is True
    assert decision.auto_merge is False
