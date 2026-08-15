"""The local session must honour the contract the GKE session implements.

`sandbox/` is a namespace package with no distribution of its own, so the
repository root is placed on `sys.path` here rather than by an install step.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sandbox.session import (  # noqa: E402
    ExecutionResult,
    LocalSession,
    SandboxPathError,
    SandboxSession,
    open_session,
)

DIFF = """--- a/greeting.txt
+++ b/greeting.txt
@@ -1,2 +1,2 @@
 hello
-imagen-4
+gemini-3.1-flash-image
"""


@pytest.fixture
def session(tmp_path):
    with LocalSession(tmp_path / "sessions", run_id="run-local-1") as opened:
        yield opened


def test_session_satisfies_the_protocol(session):
    assert isinstance(session, SandboxSession)
    assert session.working_dir.is_dir()


def test_execute_runs_argv_and_reports_exit_code(session):
    result = session.execute(["python3", "--version"], timeout_seconds=30)

    assert result.exit_code == 0
    assert result.timed_out is False
    assert "Python 3" in (result.stdout + result.stderr)


def test_execute_reports_a_failing_command_without_raising(session):
    result = session.execute(["python3", "-c", "import sys; sys.exit(3)"], timeout_seconds=30)

    assert result == ExecutionResult(exit_code=3, stdout="", stderr="", timed_out=False)


def test_execute_times_out_instead_of_hanging(session):
    result = session.execute(["python3", "-c", "import time; time.sleep(30)"], timeout_seconds=1)

    assert result.timed_out is True
    assert result.exit_code == -1


def test_execute_hides_operator_credentials(session, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghs-should-never-be-visible")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/adc.json")

    program = "import os; print(sorted(k for k in os.environ if 'TOKEN' in k or 'GOOGLE' in k))"
    result = session.execute(["python3", "-c", program], timeout_seconds=30)

    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"


def test_execute_redirects_home_into_the_workspace(session):
    result = session.execute(
        ["python3", "-c", "import os; print(os.environ['HOME']); print(os.environ['TMPDIR'])"],
        timeout_seconds=30,
    )

    for line in result.stdout.strip().splitlines():
        assert Path(line).is_relative_to(session.working_dir)


def test_write_then_read_round_trips(session):
    session.write_file("src/models.ts", "export const MODEL = 'imagen-4';\n")

    assert session.read_file("src/models.ts") == "export const MODEL = 'imagen-4';\n"
    assert (session.working_dir / "src" / "models.ts").is_file()


def test_apply_unified_diff_edits_the_workspace(session):
    session.write_file("greeting.txt", "hello\nimagen-4\n")

    result = session.apply_unified_diff(DIFF)

    assert result.exit_code == 0, result.stderr
    assert session.read_file("greeting.txt") == "hello\ngemini-3.1-flash-image\n"


def test_apply_unified_diff_reports_a_patch_that_does_not_apply(session):
    session.write_file("greeting.txt", "hello\nsomething-else\n")

    result = session.apply_unified_diff(DIFF)

    assert result.exit_code != 0
    assert result.stderr != ""


@pytest.mark.parametrize(
    "relpath",
    ["../escape.txt", "src/../../escape.txt", "/etc/passwd", "src/../../"],
)
def test_paths_may_not_escape_the_workspace(session, relpath):
    with pytest.raises(SandboxPathError):
        session.write_file(relpath, "nope")
    with pytest.raises(SandboxPathError):
        session.read_file(relpath)


def test_close_destroys_the_workspace(tmp_path):
    session = LocalSession(tmp_path / "sessions", run_id="run-local-2")
    workspace = session.working_dir
    session.write_file("artifact.txt", "x")

    session.close()
    session.close()  # idempotent: close() runs in a finally, possibly twice

    assert not workspace.exists()


def test_close_keeps_the_workspace_when_retained(tmp_path):
    session = LocalSession(tmp_path / "sessions", run_id="run-local-3", retain=True)
    session.write_file("artifact.txt", "x")

    session.close()

    assert (session.working_dir / "artifact.txt").read_text() == "x"


def test_open_session_builds_a_local_session(tmp_path):
    session = open_session("local", root=tmp_path / "sessions", run_id="run-local-4")
    try:
        assert isinstance(session, LocalSession)
        assert session.execute(["python3", "--version"], timeout_seconds=30).exit_code == 0
    finally:
        session.close()


def test_open_session_rejects_an_unknown_kind(tmp_path):
    with pytest.raises(ValueError, match="unknown session kind"):
        open_session("docker", root=tmp_path, run_id="run-local-5")
