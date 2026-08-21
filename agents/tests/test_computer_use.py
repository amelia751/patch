"""computer_use_step serves the workspace viewer and records a screenshot."""

from pathlib import Path

from agents.config import AgentId
from agents.context import RunContext
from agents.tools.patch.computer_use import build_computer_use_tools
from agents.tools.results import is_refusal
from packages.schemas.change_manifest import ChangeManifest


def _tools(tmp_path: Path, repo_root: Path, *, manifest: ChangeManifest | None = None):
    context = RunContext(
        run_id="run-cu",
        repo_root=repo_root,
        feed_dir=repo_root / "demo" / "fixtures",
        workspace_root=tmp_path,
    )
    if manifest is not None:
        context.record("change_manifest", AgentId.ORCHESTRATOR, manifest)
    return context, {f.__name__: f for f in build_computer_use_tools(context)}


def test_computer_use_step_screenshots_the_viewer(tmp_path, repo_root):
    viewer = tmp_path / "viewer"
    viewer.mkdir()
    (viewer / "index.html").write_text(
        "<html><body><p>status:ok</p><p>ok:gemini-3.5-flash</p></body></html>\n",
        encoding="utf-8",
    )
    manifest = ChangeManifest.model_validate_json(
        (repo_root / "agents" / "fixtures" / "change_manifest.gemini20.json").read_text(
            encoding="utf-8"
        )
    )
    _, tools = _tools(tmp_path, repo_root, manifest=manifest)
    result = tools["computer_use_step"]("Confirm the viewer shows gemini-3.5-flash")
    assert result["status"] == "ok"
    assert result["goal_met"] is True
    assert Path(result["screenshot"]).is_file()
    assert (tmp_path / ".patchapi-ui" / "actions.json").is_file()
    assert (tmp_path / ".patchapi-ui" / "page.html").is_file()


def test_computer_use_step_fails_the_goal_when_a_retired_id_is_visible(tmp_path, repo_root):
    viewer = tmp_path / "viewer"
    viewer.mkdir()
    (viewer / "index.html").write_text(
        "<html><body><p>error:gemini-2.0-flash retired</p></body></html>\n",
        encoding="utf-8",
    )
    manifest = ChangeManifest.model_validate_json(
        (repo_root / "agents" / "fixtures" / "change_manifest.gemini20.json").read_text(
            encoding="utf-8"
        )
    )
    _, tools = _tools(tmp_path, repo_root, manifest=manifest)
    result = tools["computer_use_step"]("Confirm the viewer is migrated")
    assert result["status"] == "ok"
    assert result["goal_met"] is False


def test_computer_use_step_writes_a_viewer_from_the_entrypoint(tmp_path, repo_root):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "gemini.ts").write_text(
        'export const MODEL = "gemini-3.5-flash";\n', encoding="utf-8"
    )
    manifest = ChangeManifest.model_validate_json(
        (repo_root / "agents" / "fixtures" / "change_manifest.gemini20.json").read_text(
            encoding="utf-8"
        )
    )
    _, tools = _tools(tmp_path, repo_root, manifest=manifest)
    result = tools["computer_use_step"]("Confirm the viewer shows the replacement")
    assert result["status"] == "ok"
    assert result["goal_met"] is True
    assert (tmp_path / "viewer" / "model.json").is_file()


def test_computer_use_step_refuses_a_non_loopback_url(tmp_path, repo_root):
    _, tools = _tools(tmp_path, repo_root)
    result = tools["computer_use_step"]("click around", url="https://example.com/")
    assert is_refusal(result)
    assert result["reason_code"] == "policy_denied"
