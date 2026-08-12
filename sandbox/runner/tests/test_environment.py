"""Generated code sees an environment built from nothing, not a filtered one."""

from sandbox.runner.config import Step
from sandbox.runner.environment import build_step_environment, missing_credentials

HOST = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/Users/operator",
    "LANG": "en_US.UTF-8",
    "GITHUB_APP_PRIVATE_KEY": "-----BEGIN RSA PRIVATE KEY-----",
    "GITHUB_TOKEN": "ghp_example",
    "GOOGLE_APPLICATION_CREDENTIALS": "/Users/operator/patch/.secrets/gcp-service-account.json",
    "GOOGLE_API_KEY": "AIza-example",
    "AWS_SECRET_ACCESS_KEY": "example",
    "KUBECONFIG": "/Users/operator/.kube/config",
}

OFFLINE_STEP = Step(name="test", argv=("python3", "--version"))
LIVE_STEP = Step(
    name="live",
    argv=("python3", "--version"),
    phase="live_verification",
    credentials=("GOOGLE_API_KEY",),
)


def test_no_host_credential_reaches_an_offline_step(tmp_path):
    env = build_step_environment(
        OFFLINE_STEP, workspace=tmp_path, run_id="run-x", parent_environment=HOST
    )
    for leaked in (
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "KUBECONFIG",
    ):
        assert leaked not in env


def test_home_and_tmp_are_redirected_into_the_workspace(tmp_path):
    env = build_step_environment(
        OFFLINE_STEP, workspace=tmp_path, run_id="run-x", parent_environment=HOST
    )
    assert env["HOME"] == str(tmp_path / ".sandbox-home")
    assert env["TMPDIR"] == str(tmp_path / ".sandbox-tmp")
    assert env["HOME"] != HOST["HOME"]


def test_declared_credential_is_released_only_to_its_step(tmp_path):
    live = build_step_environment(
        LIVE_STEP, workspace=tmp_path, run_id="run-x", parent_environment=HOST
    )
    offline = build_step_environment(
        OFFLINE_STEP, workspace=tmp_path, run_id="run-x", parent_environment=HOST
    )
    assert live["GOOGLE_API_KEY"] == HOST["GOOGLE_API_KEY"]
    assert "GOOGLE_API_KEY" not in offline
    # Even the step that gets one credential gets nothing else.
    assert "GITHUB_TOKEN" not in live


def test_run_context_is_exported_for_log_correlation(tmp_path):
    env = build_step_environment(
        LIVE_STEP, workspace=tmp_path, run_id="run-x", parent_environment=HOST
    )
    assert env["PATCHAPI_SANDBOX"] == "1"
    assert env["PATCHAPI_RUN_ID"] == "run-x"
    assert env["PATCHAPI_STEP"] == "live"
    assert env["PATCHAPI_NETWORK_PHASE"] == "live_verification"


def test_missing_credentials_are_reported_rather_than_ignored():
    assert missing_credentials(LIVE_STEP, {"PATH": "/bin"}) == ["GOOGLE_API_KEY"]
    assert missing_credentials(LIVE_STEP, HOST) == []
    assert missing_credentials(OFFLINE_STEP, {}) == []
