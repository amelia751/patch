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


def test_execute_can_inject_a_live_verification_key(session, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghs-should-never-be-visible")
    program = (
        "import os; "
        "print('present' if os.environ.get('GOOGLE_GENERATIVE_AI_API_KEY') else 'missing'); "
        "print('github' if 'GITHUB_TOKEN' in os.environ else 'no-github')"
    )
    result = session.execute(
        ["python3", "-c", program],
        timeout_seconds=30,
        extra_env={"GOOGLE_GENERATIVE_AI_API_KEY": "not-a-real-key"},
    )
    assert result.exit_code == 0
    assert result.stdout.splitlines() == ["present", "no-github"]


def test_execute_refuses_a_host_credential_as_extra_env(session):
    with pytest.raises(ValueError, match="allowlist"):
        session.execute(
            ["python3", "--version"],
            timeout_seconds=30,
            extra_env={"GITHUB_TOKEN": "nope"},
        )


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


def test_a_hunk_header_that_miscounts_still_applies(session):
    """The commonest way a model's diff is thrown out is arithmetic, not content.

    Plain `git apply` reads the `@@` counts as authoritative and refuses the
    whole patch with "corrupt patch at line N" when they disagree with the hunk
    body. The body here is correct and unambiguous; only the numbers are wrong.
    """
    session.write_file("greeting.txt", "hello\nimagen-4\nbye\n")
    miscounted = (
        "--- a/greeting.txt\n"
        "+++ b/greeting.txt\n"
        "@@ -1,9 +1,9 @@\n"
        " hello\n"
        "-imagen-4\n"
        "+gemini-3.1-flash-image\n"
        " bye\n"
    )

    result = session.apply_unified_diff(miscounted)

    assert result.exit_code == 0, result.stderr
    assert session.read_file("greeting.txt") == "hello\ngemini-3.1-flash-image\nbye\n"


def test_a_diff_whose_content_is_wrong_is_still_refused(session):
    """Recounting fixes arithmetic. It must not make a wrong edit land."""
    session.write_file("greeting.txt", "hello\nsomething-else\nbye\n")
    miscounted = (
        "--- a/greeting.txt\n"
        "+++ b/greeting.txt\n"
        "@@ -1,9 +1,9 @@\n"
        " hello\n"
        "-imagen-4\n"
        "+gemini-3.1-flash-image\n"
        " bye\n"
    )

    result = session.apply_unified_diff(miscounted)

    assert result.exit_code != 0
    assert session.read_file("greeting.txt") == "hello\nsomething-else\nbye\n"


def test_write_tree_puts_a_whole_checkout_in(session, tmp_path):
    source = tmp_path / "checkout"
    (source / "lib").mkdir(parents=True)
    (source / "lib" / "gemini.ts").write_text("export const MODEL = 'imagen-4';\n")
    (source / "logo.png").write_bytes(b"\x89PNG\x00\xff")

    session.write_tree(source, ["lib/gemini.ts", "logo.png"])

    assert session.read_file("lib/gemini.ts") == "export const MODEL = 'imagen-4';\n"
    assert (session.working_dir / "logo.png").read_bytes() == b"\x89PNG\x00\xff"


@pytest.mark.parametrize(
    "relpath",
    ["../escape.txt", "src/../../escape.txt", "/etc/passwd", "src/../../"],
)
def test_paths_may_not_escape_the_workspace(session, relpath):
    with pytest.raises(SandboxPathError):
        session.write_file(relpath, "nope")
    with pytest.raises(SandboxPathError):
        session.read_file(relpath)


@pytest.mark.parametrize("relpath", ["../escape.txt", "src/../../escape.txt", "/etc/passwd"])
def test_a_staged_tree_may_not_escape_the_workspace(session, tmp_path, relpath):
    """A bulk write is still a write. One guard for both, or only one is guarded."""
    source = tmp_path / "hostile"
    source.mkdir()

    with pytest.raises(SandboxPathError):
        session.write_tree(source, [relpath])


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


def test_open_session_accepts_the_call_shape_the_job_uses(tmp_path):
    """The remediation job names the directory `scratch_root` for both transports.

    It has to, because it does not know which one it asked for. Only the GKE
    session took that keyword, so `PATCHAPI_SANDBOX=local` died on an unexpected
    argument and the run ended with no generated code executed at all. The other
    test in this file passes `root=`, which is why nothing caught it.
    """
    session = open_session(
        "local", run_id="run-local-6", scratch_root=tmp_path / "scratch" / "sandbox"
    )
    try:
        assert isinstance(session, LocalSession)
        session.write_file("bound.txt", "gemini-3.5-flash")
        assert session.read_file("bound.txt") == "gemini-3.5-flash"
        assert (tmp_path / "scratch" / "sandbox") in session.working_dir.parents
    finally:
        session.close()
