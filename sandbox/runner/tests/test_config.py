"""The plan contract refuses everything it is not certain about."""

import json

import pytest

from sandbox.runner.config import PLAN_SCHEMA_VERSION, PlanError, SandboxPlan

BASE_PLAN = {
    "schema_version": PLAN_SCHEMA_VERSION,
    "plan_id": "unit",
    "source": {"kind": "path", "location": "sandbox/runner/testdata/image_service"},
    "steps": [{"name": "test", "argv": ["python3", "--version"]}],
}


def plan_with(**overrides):
    data = json.loads(json.dumps(BASE_PLAN))
    data.update(overrides)
    return data


def test_shipped_plans_are_valid(plans_dir):
    plans = sorted(plans_dir.glob("*.json"))
    assert plans, "no plans shipped"
    for path in plans:
        plan = SandboxPlan.load(path)
        assert plan.schema_version == PLAN_SCHEMA_VERSION
        assert plan.steps


def test_unknown_schema_version_is_refused():
    with pytest.raises(PlanError, match="schema_version"):
        SandboxPlan.from_json(plan_with(schema_version="sandbox.plan.v99"))


def test_git_source_must_pin_a_sha():
    data = plan_with(source={"kind": "git", "location": "https://example.invalid/repo.git"})
    with pytest.raises(PlanError, match="exact sha"):
        SandboxPlan.from_json(data)


def test_storygen_live_key_is_on_the_allowlist():
    data = plan_with(
        steps=[
            {
                "name": "live",
                "argv": ["python3", "--version"],
                "phase": "live_verification",
                "credentials": ["GOOGLE_GENERATIVE_AI_API_KEY"],
            }
        ]
    )
    plan = SandboxPlan.from_json(data)
    assert plan.steps[0].credentials == ("GOOGLE_GENERATIVE_AI_API_KEY",)


def test_credentials_outside_the_allowlist_are_refused():
    data = plan_with(
        steps=[
            {
                "name": "live",
                "argv": ["python3", "--version"],
                "phase": "live_verification",
                "credentials": ["GITHUB_APP_PRIVATE_KEY"],
            }
        ]
    )
    with pytest.raises(PlanError, match="allowlist"):
        SandboxPlan.from_json(data)


def test_credentials_are_refused_outside_live_verification():
    data = plan_with(
        steps=[
            {
                "name": "install",
                "argv": ["python3", "--version"],
                "phase": "dependencies",
                "credentials": ["GOOGLE_API_KEY"],
            }
        ]
    )
    with pytest.raises(PlanError, match="live_verification"):
        SandboxPlan.from_json(data)


def test_unknown_phase_is_refused():
    data = plan_with(steps=[{"name": "test", "argv": ["true"], "phase": "internet"}])
    with pytest.raises(PlanError, match="phase"):
        SandboxPlan.from_json(data)


def test_duplicate_step_names_are_refused():
    data = plan_with(
        steps=[
            {"name": "test", "argv": ["true"]},
            {"name": "test", "argv": ["false"]},
        ]
    )
    with pytest.raises(PlanError, match="unique"):
        SandboxPlan.from_json(data)


def test_argv_must_be_a_list_not_a_shell_string():
    data = plan_with(steps=[{"name": "test", "argv": "python3 --version"}])
    with pytest.raises(PlanError, match="argv"):
        SandboxPlan.from_json(data)


def test_round_trip_preserves_the_contract():
    plan = SandboxPlan.from_json(BASE_PLAN)
    assert SandboxPlan.from_json(plan.to_json()) == plan
