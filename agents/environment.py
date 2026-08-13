"""Local workspace execution for the Patch debug loop.

The shape matches `google.adk.environment.ExecutionResult` — `exit_code`,
`stdout`, `stderr`, `timed_out` — so a GKE Agent Sandbox adapter is a transport
swap (roadmap §8.4). This module does not import ADK: the experimental
`EnvironmentToolset` is not the tool surface the fleet exposes, and ADK must
not be imported at module scope.

Commands run as an argv list, never a shell string. The environment is built
from an allowlist, not scrubbed from the operator's shell, so a credential
added tomorrow is excluded by default.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

# Inherited verbatim when present. Deliberately excludes every *_TOKEN, *_KEY,
# and credential-file pointer — the same rule sandbox/runner/environment.py
# enforces for the orchestrator's clean evidence run.
_INHERITED_BASE_VARS: tuple[str, ...] = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "SHELL",
    "SYSTEMROOT",
)

_KILL_GRACE_SECONDS = 5


@dataclass(frozen=True)
class ExecutionResult:
    """Result of one allowlisted command in the workspace."""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


def build_workspace_environment(
    workspace: Path,
    *,
    run_id: str,
    parent_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the exact environment a Patch-loop command may observe."""
    parent = os.environ if parent_environment is None else parent_environment
    env: dict[str, str] = {
        name: parent[name] for name in _INHERITED_BASE_VARS if parent.get(name) is not None
    }
    env.setdefault("PATH", os.defpath)
    home = workspace / ".sandbox-home"
    tmp = workspace / ".sandbox-tmp"
    home.mkdir(exist_ok=True)
    tmp.mkdir(exist_ok=True)
    env["HOME"] = str(home)
    env["TMPDIR"] = str(tmp)
    env["PATCHAPI_SANDBOX"] = "1"
    env["PATCHAPI_RUN_ID"] = run_id
    return env


def apply_unified_diff(
    diff: str,
    *,
    workspace: Path,
    timeout_seconds: float = 30,
) -> ExecutionResult:
    """Apply a unified diff with `git apply` reading stdin. Not a shell."""
    try:
        completed = subprocess.run(
            ["git", "apply", "-p1", "--whitespace=nowarn", "-"],
            cwd=workspace,
            input=diff,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(exit_code=-1, timed_out=True)
    except OSError as exc:
        return ExecutionResult(exit_code=127, stderr=str(exc))
    return ExecutionResult(
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def execute(
    argv: list[str],
    *,
    workspace: Path,
    run_id: str,
    timeout_seconds: float,
    parent_environment: Mapping[str, str] | None = None,
) -> ExecutionResult:
    """Run `argv` in `workspace`. Never invokes a shell."""
    environment = build_workspace_environment(
        workspace, run_id=run_id, parent_environment=parent_environment
    )
    try:
        process = subprocess.Popen(
            argv,
            cwd=workspace,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        return ExecutionResult(exit_code=127, stderr=str(exc))

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_group(process)
        return ExecutionResult(exit_code=-1, timed_out=True)
    return ExecutionResult(
        exit_code=process.returncode or 0,
        stdout=stdout or "",
        stderr=stderr or "",
    )


def _terminate_group(process: subprocess.Popen[str]) -> None:
    try:
        group = os.getpgid(process.pid)
    except ProcessLookupError:
        return
    for sig, wait in ((signal.SIGTERM, _KILL_GRACE_SECONDS), (signal.SIGKILL, _KILL_GRACE_SECONDS)):
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue
    # communicate() after a timeout leaves pipes unread; drain so the child
    # cannot block on a full pipe during teardown.
    time.sleep(0)
    try:
        process.communicate(timeout=1)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return


__all__ = [
    "ExecutionResult",
    "apply_unified_diff",
    "build_workspace_environment",
    "execute",
]
