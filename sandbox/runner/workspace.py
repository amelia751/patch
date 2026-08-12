"""Allocation, population, and destruction of the disposable workspace.

Layout of one run, rooted outside the repository under test:

    <sandbox_root>/patchapi-sandbox/<run_id>/
        workspace/     the only thing generated code may touch; destroyed
        logs/          per-step output; survives destruction and timeouts
        patch.diff     the exact edit that was applied, or absent
        result.json    the run record

Evidence lives beside the workspace, never inside it, so a timeout can destroy
the environment without destroying the reason it timed out.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from .config import Source

# Never copied into a workspace: version-control internals that would let a
# tool discover the operator's remotes, and caches that are rebuilt anyway.
_EXCLUDED_NAMES: tuple[str, ...] = (
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".ruff_cache",
    ".secrets",
)
_COPY_EXCLUDES = shutil.ignore_patterns(*_EXCLUDED_NAMES)

# Created inside the workspace only after the source is in place, so a `git
# clone` still sees the empty directory it requires.
_RUNTIME_DIRS: tuple[str, ...] = (".sandbox-home", ".sandbox-tmp")

_RUN_ROOT_DIRNAME = "patchapi-sandbox"


class IsolationError(RuntimeError):
    """The requested layout would let a run write into the source of truth."""


class SourceError(RuntimeError):
    """The pinned source could not be materialised exactly as specified."""


@dataclass(frozen=True)
class Workspace:
    """Paths for one run. `workspace` is disposable; the rest is evidence."""

    run_id: str
    run_dir: Path
    workspace: Path
    logs: Path

    @property
    def result_path(self) -> Path:
        return self.run_dir / "result.json"

    @property
    def patch_path(self) -> Path:
        return self.run_dir / "patch.diff"


def new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def repository_root(path: Path) -> Path:
    """Nearest ancestor holding a `.git` entry, else the path itself."""

    resolved = path.resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    return resolved


def _is_within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def assert_isolated(run_root: Path, source_path: Path | None) -> None:
    """Refuse any layout where the run could write into the checkout.

    This is the guard behind the rule that an unverified agent edit is never
    applied to a developer's primary checkout as finished work.
    """

    run_root = run_root.resolve()
    if source_path is None:
        return
    guarded = repository_root(source_path)
    if _is_within(run_root, guarded):
        raise IsolationError(
            f"sandbox root {run_root} is inside the source repository {guarded}; "
            "generated code must never execute inside the checkout under test"
        )
    if _is_within(guarded, run_root):
        raise IsolationError(
            f"source repository {guarded} is inside the sandbox root {run_root}; "
            "destroying the sandbox would destroy the checkout"
        )


def allocate(*, sandbox_root: Path, run_id: str, source_path: Path | None = None) -> Workspace:
    """Create an empty run directory and its disposable workspace."""

    root = sandbox_root.resolve()
    assert_isolated(root, source_path)
    run_dir = root / _RUN_ROOT_DIRNAME / run_id
    if run_dir.exists():
        raise IsolationError(f"run directory {run_dir} already exists; run ids must be unique")
    workspace = run_dir / "workspace"
    logs = run_dir / "logs"
    workspace.mkdir(parents=True)
    logs.mkdir(parents=True)
    return Workspace(run_id=run_id, run_dir=run_dir, workspace=workspace, logs=logs)


def populate(workspace: Workspace, source: Source, *, base_dir: Path) -> str | None:
    """Materialise the pinned source into the workspace.

    Returns the resolved commit sha for a git source, or None for a path copy.
    """

    if source.kind == "path":
        origin = (base_dir / source.location).resolve()
        if not origin.is_dir():
            raise SourceError(f"source path {origin} is not a directory")
        _copy_tree(origin, workspace.workspace)
        resolved = None
    else:
        resolved = _clone_pinned(source, workspace.workspace)
    for name in _RUNTIME_DIRS:
        (workspace.workspace / name).mkdir(exist_ok=True)
    return resolved


def _excluded(name: str) -> bool:
    return any(fnmatch(name, pattern) for pattern in _EXCLUDED_NAMES)


def _copy_tree(origin: Path, destination: Path) -> None:
    # `shutil.ignore_patterns` filters a directory's children, never the
    # directory itself, so top-level entries are screened here as well.
    for entry in origin.iterdir():
        if _excluded(entry.name):
            continue
        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, ignore=_COPY_EXCLUDES, symlinks=True)
        else:
            shutil.copy2(entry, target, follow_symlinks=False)


def _clone_pinned(source: Source, destination: Path) -> str:
    assert source.sha is not None  # guaranteed by SandboxPlan validation
    clone = subprocess.run(
        ["git", "clone", "--quiet", "--no-single-branch", source.location, str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if clone.returncode != 0:
        raise SourceError(f"git clone of {source.location} failed: {clone.stderr.strip()}")
    checkout = subprocess.run(
        ["git", "-C", str(destination), "checkout", "--quiet", "--detach", source.sha],
        capture_output=True,
        text=True,
        check=False,
    )
    if checkout.returncode != 0:
        raise SourceError(f"checkout of pinned sha {source.sha} failed: {checkout.stderr.strip()}")
    head = subprocess.run(
        ["git", "-C", str(destination), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    resolved = head.stdout.strip()
    if head.returncode != 0 or not resolved.startswith(source.sha):
        raise SourceError(f"workspace HEAD {resolved!r} does not match pinned sha {source.sha!r}")
    return resolved


def destroy(workspace: Workspace) -> None:
    """Remove the disposable workspace, preserving logs and the run record."""

    shutil.rmtree(workspace.workspace, ignore_errors=True)
