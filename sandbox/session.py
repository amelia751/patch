"""Claim / exec / destroy sessions for the Patch debug loop.

A session is the only handle an agent gets on an execution environment. It is
opened for one run, driven step by step, and destroyed — there is no long-lived
sandbox to forget about, because a forgotten sandbox is a billed Running pod
(`.local/research/gke-agent-sandbox-lifecycle.md` §2.3).

Two implementations satisfy the same contract: `LocalSession` over a temporary
workspace (Phase 1) and `sandbox.gke.session.GkeSession` over a GKE Agent
Sandbox claim. Because the command contract is identical, swapping transports
does not rewrite the agents that drive it.

`ExecutionResult` duplicates the four fields of `agents.environment
.ExecutionResult` rather than importing them: the sandbox tree must not depend
on the agent tree, and the dataclass is small enough that a copy is cheaper than
a cycle.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Protocol, runtime_checkable

# Inherited verbatim when present, and nothing else. Built from an allowlist so
# a credential added to the operator's shell tomorrow — GITHUB_TOKEN,
# GOOGLE_APPLICATION_CREDENTIALS, a cloud SDK config pointer — is excluded by
# default rather than leaked by omission (roadmap §13.4).
_INHERITED_BASE_VARS: tuple[str, ...] = ("PATH", "LANG")

_KILL_GRACE_SECONDS = 5


class SandboxError(RuntimeError):
    """Base class for every failure a session reports."""


class SandboxUnavailableError(SandboxError):
    """The execution environment could not be obtained.

    Raised instead of degrading to a weaker environment: a run that cannot be
    isolated fails closed rather than reporting a result nothing verified.
    """


class SandboxPathError(SandboxError):
    """A path argument pointed outside the session workspace."""


@dataclass(frozen=True)
class ExecutionResult:
    """Result of one command in a session workspace."""

    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


@runtime_checkable
class SandboxSession(Protocol):
    """What the Patch loop is allowed to do to an execution environment."""

    @property
    def working_dir(self) -> PurePath:
        """Directory every relative path in this session resolves against."""

    def execute(self, argv: list[str], timeout_seconds: float) -> ExecutionResult:
        """Run `argv` in the workspace. Never a shell string."""

    def read_file(self, relpath: str) -> str:
        """Read a workspace-relative text file."""

    def write_file(self, relpath: str, content: str) -> None:
        """Write a workspace-relative text file, creating parents."""

    def apply_unified_diff(self, diff: str) -> ExecutionResult:
        """Apply a unified diff to the workspace with `git apply -p1`."""

    def close(self) -> None:
        """Destroy the environment. Safe to call twice."""


def resolve_within(root: PurePath, relpath: str) -> PurePath:
    """Resolve `relpath` under `root`, refusing anything that escapes it.

    Traversal is rejected on the lexical form as well as the resolved one, so a
    symlink planted inside the workspace by generated code cannot widen the
    boundary.
    """

    candidate = PurePath(relpath)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise SandboxPathError(f"path {relpath!r} escapes the session workspace")
    resolved = root / candidate
    if isinstance(root, Path):
        real_root = root.resolve()
        real = Path(resolved).resolve()
        if real != real_root and real_root not in real.parents:
            raise SandboxPathError(f"path {relpath!r} escapes {real_root}")
        return real
    return resolved


def build_workspace_environment(
    workspace: Path,
    *,
    run_id: str,
    parent_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the exact environment a session command may observe.

    HOME and TMPDIR point inside the disposable workspace so a tool that writes
    a cache or a credential helper cannot reach the operator's home directory.
    """

    parent = os.environ if parent_environment is None else parent_environment
    env: dict[str, str] = {
        name: parent[name] for name in _INHERITED_BASE_VARS if parent.get(name) is not None
    }
    env.setdefault("PATH", os.defpath)
    home = workspace / ".sandbox-home"
    tmp = workspace / ".sandbox-tmp"
    home.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["TMPDIR"] = str(tmp)
    env["PATCHAPI_SANDBOX"] = "1"
    env["PATCHAPI_RUN_ID"] = run_id
    return env


class LocalSession:
    """A session over a temporary directory on this machine.

    The local runner cannot enforce gVisor or default-deny networking; GKE Agent
    Sandbox does that. What it enforces identically in both environments is the
    command contract, the credential allowlist, and workspace confinement.
    """

    def __init__(self, root: Path, run_id: str, *, retain: bool = False) -> None:
        self._run_id = run_id
        self._retain = retain
        self._workspace = Path(root) / run_id / "workspace"
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._closed = False

    @property
    def working_dir(self) -> Path:
        return self._workspace

    @property
    def run_id(self) -> str:
        return self._run_id

    def execute(self, argv: list[str], timeout_seconds: float = 300) -> ExecutionResult:
        if not argv:
            raise ValueError("argv must not be empty")
        environment = build_workspace_environment(self._workspace, run_id=self._run_id)
        try:
            process = subprocess.Popen(
                argv,
                cwd=self._workspace,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # Its own process group, so a timeout kills the whole tree a
                # build spawned rather than only the process we started.
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

    def read_file(self, relpath: str) -> str:
        path = resolve_within(self._workspace, relpath)
        return Path(path).read_text(encoding="utf-8")

    def write_file(self, relpath: str, content: str) -> None:
        path = Path(resolve_within(self._workspace, relpath))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def apply_unified_diff(self, diff: str, timeout_seconds: float = 30) -> ExecutionResult:
        try:
            completed = subprocess.run(
                ["git", "apply", "-p1", "--whitespace=nowarn", "-"],
                cwd=self._workspace,
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

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self._retain:
            shutil.rmtree(self._workspace.parent, ignore_errors=True)

    def __enter__(self) -> LocalSession:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def open_session(kind: str, **kwargs: object) -> SandboxSession:
    """Open a session of `kind` — 'local' or 'gke' — ready to execute.

    The GKE implementation is imported lazily so a local run never needs a
    kubeconfig, a cluster, or the gcloud SDK on PATH.
    """

    if kind == "local":
        return LocalSession(**kwargs)  # type: ignore[arg-type]
    if kind == "gke":
        from .gke.session import GkeSession

        session = GkeSession(**kwargs)  # type: ignore[arg-type]
        session.open()
        return session
    raise ValueError(f"unknown session kind {kind!r}; expected 'local' or 'gke'")


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
    time.sleep(0)
    try:
        process.communicate(timeout=1)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return


__all__ = [
    "ExecutionResult",
    "LocalSession",
    "SandboxError",
    "SandboxPathError",
    "SandboxSession",
    "SandboxUnavailableError",
    "build_workspace_environment",
    "open_session",
    "resolve_within",
]
