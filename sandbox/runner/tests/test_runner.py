"""End-to-end runs: the outcomes the verifier and the PR decision depend on."""

import hashlib
import json

from sandbox.runner.config import SandboxPlan
from sandbox.runner.entrypoint import main
from sandbox.runner.runner import execute_plan


def tree_digest(root):
    """Stable digest of a directory tree, used to prove the checkout is untouched."""

    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run(plan_name, repo_root, sandbox_root, **kwargs):
    plan = SandboxPlan.load(repo_root / "sandbox" / "runner" / "plans" / plan_name)
    return execute_plan(plan, sandbox_root=sandbox_root, base_dir=repo_root, **kwargs)


def test_noop_patch_run_passes_and_leaves_logs(repo_root, sandbox_root):
    result = run("testdata-noop.v1.json", repo_root, sandbox_root)

    assert result.status == "PASS"
    assert result.patch_applied is False
    assert [step.name for step in result.steps] == ["install", "build", "test"]
    for step in result.steps:
        assert step.log_path.is_file()
        assert step.log_path.read_text(encoding="utf-8").startswith("$ ")
    assert (result.run_dir / "logs" / "build.txt").is_file()


def test_known_good_patch_passes(repo_root, sandbox_root):
    result = run("testdata-good.v1.json", repo_root, sandbox_root)

    assert result.status == "PASS"
    assert result.patch_applied is True
    assert "gemini-3.1-flash-image" in (result.run_dir / "patch.diff").read_text(encoding="utf-8")


def test_known_bad_patch_fails_at_the_test_step(repo_root, sandbox_root):
    result = run("testdata-bad.v1.json", repo_root, sandbox_root)

    assert result.status == "FAIL"
    assert result.patch_applied is True
    assert [step.status for step in result.steps] == ["PASS", "PASS", "FAIL"]
    test_log = (result.run_dir / "logs" / "test.txt").read_text(encoding="utf-8")
    assert "UnsupportedModelError" in test_log


def test_unappliable_patch_stops_before_any_step_runs(repo_root, sandbox_root):
    result = run("testdata-unappliable.v1.json", repo_root, sandbox_root)

    assert result.status == "PATCH_FAILED"
    assert result.steps == []
    assert "patch does not apply" in result.detail


def test_run_never_writes_into_the_checkout(repo_root, sandbox_root):
    fixture = repo_root / "sandbox" / "runner" / "testdata" / "image_service"
    before = tree_digest(fixture)

    result = run("testdata-good.v1.json", repo_root, sandbox_root)

    assert result.status == "PASS"
    assert tree_digest(fixture) == before
    assert not (fixture / "dist").exists()
    assert 'MODEL_ID = "imagen-4.0-generate-001"' in (
        fixture / "image_service" / "client.py"
    ).read_text(encoding="utf-8")


def test_build_artifacts_land_in_the_workspace(repo_root, sandbox_root):
    result = run("testdata-good.v1.json", repo_root, sandbox_root, retain=True)

    manifest = result.workspace_path / "dist" / "manifest.json"
    assert result.workspace_retained is True
    assert json.loads(manifest.read_text(encoding="utf-8"))["model_id"] == "gemini-3.1-flash-image"


def test_workspace_is_destroyed_by_default(repo_root, sandbox_root):
    result = run("testdata-noop.v1.json", repo_root, sandbox_root)

    assert result.workspace_retained is False
    assert not result.workspace_path.exists()
    assert result.run_dir.is_dir()


def test_result_record_is_written_for_every_run(repo_root, sandbox_root):
    result = run("testdata-bad.v1.json", repo_root, sandbox_root)

    record = json.loads((result.run_dir / "result.json").read_text(encoding="utf-8"))
    assert record["schema_version"] == "sandbox.result.v1"
    assert record["status"] == "FAIL"
    assert record["plan_id"] == "testdata-bad"
    assert record["steps"][-1]["exit_code"] == 1


def test_timeout_destroys_the_sandbox_and_keeps_the_log(repo_root, sandbox_root):
    plan = SandboxPlan.from_json(
        {
            "schema_version": "sandbox.plan.v1",
            "plan_id": "timeout",
            "source": {"kind": "path", "location": "sandbox/runner/testdata/image_service"},
            "steps": [
                {
                    "name": "test",
                    "argv": ["python3", "-c", "import time; time.sleep(120)"],
                    "timeout_seconds": 1,
                }
            ],
        }
    )

    result = execute_plan(plan, sandbox_root=sandbox_root, base_dir=repo_root)

    assert result.status == "TIMEOUT"
    assert not result.workspace_path.exists()
    assert "[timeout]" in (result.run_dir / "logs" / "test.txt").read_text(encoding="utf-8")


def test_missing_live_credential_fails_closed(repo_root, sandbox_root, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    plan = SandboxPlan.from_json(
        {
            "schema_version": "sandbox.plan.v1",
            "plan_id": "live-verification",
            "source": {"kind": "path", "location": "sandbox/runner/testdata/image_service"},
            "steps": [
                {
                    "name": "live",
                    "argv": ["python3", "--version"],
                    "phase": "live_verification",
                    "credentials": ["GOOGLE_API_KEY"],
                }
            ],
        }
    )

    result = execute_plan(plan, sandbox_root=sandbox_root, base_dir=repo_root)

    assert result.status == "ERROR"
    assert result.steps == []
    assert "GOOGLE_API_KEY" in result.detail


def test_cli_exit_codes_match_the_run_outcome(repo_root, sandbox_root, capsys):
    plans = repo_root / "sandbox" / "runner" / "plans"
    passing = main(
        ["--plan", str(plans / "testdata-good.v1.json"), "--sandbox-root", str(sandbox_root)]
    )
    failing = main(
        ["--plan", str(plans / "testdata-bad.v1.json"), "--sandbox-root", str(sandbox_root)]
    )

    assert passing == 0
    assert failing == 1
    assert "PASS: testdata-good" in capsys.readouterr().out
