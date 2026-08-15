"""Patch debug-loop tools: inspect, edit, and run inside the workspace.

Roadmap §8.4. These are the only tools that touch the sandbox workspace. They
do not allocate it, they do not hold a Google credential, and they do not
reach GitHub. Command output is diagnostic; the orchestrator's clean evidence
run is what the Verification agent grades.

The four function names are the contract. ADK's experimental `EnvironmentToolset`
(`Execute` / `ReadFile` / `EditFile` / `WriteFile`) is not used: those names
would break the allowlist invariant, and `Execute` hard-codes a 30s timeout
that cannot run `pnpm install`.

Where the work happens is a transport detail. When the run carries a
`SandboxSession` every operation goes through it, so the same four tools drive
a local temp workspace in Phase 1 and a GKE Agent Sandbox claim later. What does
not move with the transport is the checking: containment, the forbidden-path
table and the command allowlist are all applied here, before the session is
asked to do anything.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from agents.command_allowlist import CommandNotAllowedError, match_command
from agents.config import MAX_UNTRUSTED_EXCERPT_CHARS, AgentId
from agents.context import PathOutsideRootError, RunContext, resolve_within
from agents.environment import apply_unified_diff, execute
from agents.tools.results import ReasonCode, ok, refusal
from packages.policy.globs import normalize_path
from packages.policy.paths import is_forbidden_path

AGENT: Final[AgentId] = AgentId.PATCH

# Roadmap §8.4: build output is far longer than is useful in context. Return
# the tail plus the exit code; the full log belongs in Cloud Storage.
MAX_COMMAND_OUTPUT_CHARS: Final[int] = 16_000

# File reads can be larger than a provider excerpt — SDK type definitions are
# the point of inspect-before-migrate — but they are still capped.
MAX_FILE_CHARS: Final[int] = 32_000

# How the workspace-relative form of the workspace root itself is spelled.
_WORKSPACE_ROOT_PATH: Final[str] = "."

# A session exposes read / write / execute and nothing that enumerates a
# directory, so `list_dir` supplies its own lister. Written as a fixed program
# rather than an `ls` argv because only a program PatchAPI pins crosses the
# session boundary, and because `ls` output would have to be parsed anyway.
_LIST_PROGRAM: Final[str] = (
    "import pathlib,sys\n"
    "root = pathlib.Path(sys.argv[1])\n"
    "if not root.is_dir():\n"
    "    sys.exit(3)\n"
    "for child in sorted(root.iterdir(), key=lambda item: item.name):\n"
    "    sys.stdout.write(('dir' if child.is_dir() else 'file') + '\\t' + child.name + '\\n')\n"
)

_LIST_TIMEOUT_SECONDS: Final[float] = 30.0


def _tail(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"... ({omitted} chars omitted)\n{text[-limit:]}"


def paths_in_unified_diff(diff: str) -> list[str]:
    """Repository-relative paths a unified diff would create, edit, or delete."""
    found: list[str] = []
    seen: set[str] = set()
    for line in diff.splitlines():
        if not (line.startswith("+++ ") or line.startswith("--- ")):
            continue
        rest = line[4:].split("\t", 1)[0].strip()
        if rest in {"", "/dev/null"}:
            continue
        if rest.startswith(("a/", "b/")):
            rest = rest[2:]
        if rest and rest not in seen:
            seen.add(rest)
            found.append(rest)
    return found


def workspace_relative(root: Path | None, candidate: str) -> str:
    """Normalise `candidate` to a workspace-relative path, refusing escapes.

    Two checks, because neither alone is enough. The lexical one rejects
    absolute paths and `..` segments and is the only one available when the
    workspace lives in a remote sandbox. `resolve_within` additionally resolves
    symlinks, so it runs whenever the run has a real local tree — which is every
    Phase 1 run, and the case where a planted link could reach the operator's
    home directory.
    """
    stripped = candidate.strip()
    if stripped in {"", ".", "./"}:
        relative = _WORKSPACE_ROOT_PATH
    else:
        if stripped.startswith(("/", "~")):
            raise PathOutsideRootError(f"{candidate!r} is not a workspace-relative path")
        try:
            relative = normalize_path(stripped)
        except ValueError as exc:
            raise PathOutsideRootError(str(exc)) from exc
    if root is not None:
        resolve_within(root, relative)
    return relative


def build_workspace_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Build the Patch debug-loop tools bound to `context`'s workspace."""

    def _target() -> tuple[Path | None, Any] | dict[str, Any]:
        """The local root and the session, or a refusal when the run has neither."""
        root = context.workspace_root
        session = context.sandbox
        if root is None and session is None:
            return refusal(
                ReasonCode.STAGE_NOT_READY,
                "this run has no sandbox workspace; the orchestrator allocates one",
            )
        return root, session

    def _relative(root: Path | None, candidate: str) -> str | dict[str, Any]:
        try:
            return workspace_relative(root, candidate)
        except PathOutsideRootError as exc:
            return refusal(ReasonCode.OUT_OF_SCOPE, str(exc))

    def _session_path(session: Any, relative: str) -> str:
        """`relative` as the session addresses it, absolute inside its workspace.

        Absolute because `kubectl exec` gives a command no working directory of
        its own, so a relative path would resolve against the image's WORKDIR.
        """
        if relative == _WORKSPACE_ROOT_PATH:
            return str(session.working_dir)
        return str(session.working_dir / relative)

    def read_file(path: str) -> dict[str, Any]:
        """Read one file from the sandbox workspace.

        Bound to the workspace root. Secret and CI paths are refused even for
        read — credential material is never shown to an agent.
        """
        target = _target()
        if isinstance(target, dict):
            return target
        root, session = target
        relative = _relative(root, path)
        if isinstance(relative, dict):
            return relative
        if is_forbidden_path(relative):
            return refusal(
                ReasonCode.POLICY_DENIED,
                f"{path!r} is a forbidden path and cannot be read",
            )

        if session is not None:
            try:
                text = session.read_file(relative)
            except UnicodeDecodeError:
                return refusal(
                    ReasonCode.INVALID_CONTRACT,
                    f"{path!r} is not valid UTF-8; use list_dir to inspect, not a binary read",
                )
            except (OSError, RuntimeError, ValueError) as exc:
                return refusal(
                    ReasonCode.NOT_FOUND,
                    f"{path!r} could not be read from the sandbox workspace: {exc}",
                )
        else:
            assert root is not None  # _target() refuses when both are missing
            resolved = root / relative
            if not resolved.is_file():
                return refusal(ReasonCode.NOT_FOUND, f"{path!r} is not a file in the workspace")
            try:
                text = resolved.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return refusal(
                    ReasonCode.INVALID_CONTRACT,
                    f"{path!r} is not valid UTF-8; use list_dir to inspect, not a binary read",
                )

        return ok(
            path=relative,
            truncated=len(text) > MAX_FILE_CHARS,
            content=text[:MAX_FILE_CHARS],
        )

    def list_dir(path: str) -> dict[str, Any]:
        """List entries in one directory of the sandbox workspace.

        Returns names and whether each is a file or a directory. Bound to the
        workspace root; pass '.' for the root itself.
        """
        target = _target()
        if isinstance(target, dict):
            return target
        root, session = target
        relative = _relative(root, path)
        if isinstance(relative, dict):
            return relative

        entries: list[dict[str, str]] = []
        if session is not None:
            result = session.execute(
                ["python3", "-c", _LIST_PROGRAM, _session_path(session, relative)],
                _LIST_TIMEOUT_SECONDS,
            )
            if result.exit_code != 0:
                return refusal(
                    ReasonCode.NOT_FOUND,
                    f"{path!r} is not a directory in the workspace",
                    detail=_tail(result.stderr, MAX_UNTRUSTED_EXCERPT_CHARS),
                )
            for line in result.stdout.splitlines():
                kind, _, name = line.partition("\t")
                if name:
                    entries.append({"name": name, "kind": kind})
        else:
            assert root is not None
            resolved = root / relative
            if not resolved.is_dir():
                return refusal(
                    ReasonCode.NOT_FOUND, f"{path!r} is not a directory in the workspace"
                )
            for child in sorted(resolved.iterdir(), key=lambda item: item.name):
                entries.append({"name": child.name, "kind": "dir" if child.is_dir() else "file"})

        return ok(path=relative, entries=entries)

    def apply_patch(diff: str) -> dict[str, Any]:
        """Apply a unified diff to the sandbox workspace.

        Every path the diff names is checked against the forbidden-path table
        before `git apply` runs. A forbidden path is refused, not applied. A
        diff that does not apply cleanly is reported as rejected so you can
        revise; it is not a policy denial.
        """
        target = _target()
        if isinstance(target, dict):
            return target
        root, session = target
        if not diff.strip():
            return refusal(
                ReasonCode.INVALID_CONTRACT,
                "apply_patch needs a non-empty unified diff",
            )

        paths = paths_in_unified_diff(diff)
        if not paths:
            return refusal(
                ReasonCode.INVALID_CONTRACT,
                "diff names no files; pass a unified diff with --- / +++ headers",
            )

        blocked = [item for item in paths if is_forbidden_path(item)]
        if blocked:
            return refusal(
                ReasonCode.POLICY_DENIED,
                "diff names forbidden paths; the patch was not applied",
                blocked_paths=blocked,
            )

        for item in paths:
            contained = _relative(root, item)
            if isinstance(contained, dict):
                return contained

        if session is not None:
            result = session.apply_unified_diff(diff)
        else:
            assert root is not None
            result = apply_unified_diff(diff, workspace=root)
        if result.timed_out:
            return ok(applied=False, files=paths, detail="git apply timed out")
        if result.exit_code != 0:
            detail = (result.stderr or result.stdout or "git apply failed").strip()
            return ok(
                applied=False,
                files=paths,
                detail=detail[:MAX_UNTRUSTED_EXCERPT_CHARS],
            )
        return ok(applied=True, files=paths, detail="applied with git apply")

    def run_command(command: str) -> dict[str, Any]:
        """Run one allowlisted command in the sandbox workspace.

        The command is split into argv and matched against the pinned allowlist
        before anything executes. stdout and stderr are returned as tails.
        Output is diagnostic, not evidence.
        """
        target = _target()
        if isinstance(target, dict):
            return target
        root, session = target
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return refusal(ReasonCode.INVALID_CONTRACT, f"could not parse command: {exc}")
        try:
            allowed = match_command(argv)
        except CommandNotAllowedError as exc:
            return refusal(ReasonCode.POLICY_DENIED, str(exc), command=command)

        if session is not None:
            result = session.execute(list(allowed.argv), allowed.timeout_seconds)
        else:
            assert root is not None
            result = execute(
                list(allowed.argv),
                workspace=root,
                run_id=context.run_id,
                timeout_seconds=allowed.timeout_seconds,
            )
        payload: dict[str, Any] = {
            "command": " ".join(allowed.argv),
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "stdout": _tail(result.stdout, MAX_COMMAND_OUTPUT_CHARS),
            "stderr": _tail(result.stderr, MAX_COMMAND_OUTPUT_CHARS),
        }
        if result.timed_out:
            payload["detail"] = f"exceeded {allowed.timeout_seconds}s"
        return ok(**payload)

    return [read_file, list_dir, apply_patch, run_command]


__all__ = [
    "AGENT",
    "MAX_COMMAND_OUTPUT_CHARS",
    "MAX_FILE_CHARS",
    "build_workspace_tools",
    "paths_in_unified_diff",
    "workspace_relative",
]
