"""A patch plan is bounded, repository-relative, and tied to one base SHA."""

import pytest
from pydantic import ValidationError

from packages.schemas import MAX_PATCH_ATTEMPTS, PatchPlan


def test_attempt_is_capped(load_golden):
    document = load_golden("patch_plan.egaki.json")
    document["attempt"] = MAX_PATCH_ATTEMPTS + 1

    with pytest.raises(ValidationError, match="less than or equal"):
        PatchPlan.model_validate(document)


def test_attempt_starts_at_one(load_golden):
    document = load_golden("patch_plan.egaki.json")
    document["attempt"] = 0

    with pytest.raises(ValidationError, match="greater than or equal"):
        PatchPlan.model_validate(document)


def test_a_plan_must_expect_at_least_one_file(load_golden):
    document = load_golden("patch_plan.egaki.json")
    document["files_expected"] = []

    with pytest.raises(ValidationError, match="at least 1 item"):
        PatchPlan.model_validate(document)


def test_a_plan_must_state_how_it_will_be_verified(load_golden):
    document = load_golden("patch_plan.egaki.json")
    document["verification_commands"] = []

    with pytest.raises(ValidationError, match="at least 1 item"):
        PatchPlan.model_validate(document)


def test_repeated_expected_files_are_rejected(load_golden):
    document = load_golden("patch_plan.egaki.json")
    document["files_expected"] = ["cli/src/models.ts", "cli/src/models.ts"]

    with pytest.raises(ValidationError, match="must not repeat a path"):
        PatchPlan.model_validate(document)


@pytest.mark.parametrize("path", ["/etc/hosts", "../other-repo/src/index.ts"])
def test_expected_files_stay_inside_the_repository(path, load_golden):
    document = load_golden("patch_plan.egaki.json")
    document["files_expected"] = [path]

    with pytest.raises(ValidationError):
        PatchPlan.model_validate(document)


def test_a_short_base_sha_is_rejected(load_golden):
    document = load_golden("patch_plan.egaki.json")
    document["base_sha"] = "c09e1a4"

    with pytest.raises(ValidationError, match="base_sha"):
        PatchPlan.model_validate(document)


def test_skill_id_and_version_are_recorded_together(load_golden):
    document = load_golden("patch_plan.egaki.json")
    del document["skill_version"]

    with pytest.raises(ValidationError, match="recorded together"):
        PatchPlan.model_validate(document)
