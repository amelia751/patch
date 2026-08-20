"""Versioned contracts for the sandbox runner.

The plan is the whole command contract between an agent and an execution
environment. Keeping it as data — never inlined at a call site — is what lets
the GKE Agent Sandbox replace the local temp-workspace runner without any agent
being rewritten: the same plan document is handed to both.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sandbox.credentials import LIVE_VERIFICATION_CREDENTIALS

PLAN_SCHEMA_VERSION = "sandbox.plan.v1"
RESULT_SCHEMA_VERSION = "sandbox.result.v1"

# Phases exist so the network and credential posture can widen for exactly one
# step and no further (roadmap §13.3, §13.4). "none" is the default because a
# step that never declares a need never gets one.
NetworkPhase = Literal["none", "dependencies", "live_verification"]
NETWORK_PHASES: tuple[NetworkPhase, ...] = ("none", "dependencies", "live_verification")

# Re-exported so existing `from sandbox.runner.config import …` call sites keep
# working. The allowlist itself lives in sandbox/credentials.py.

DEFAULT_STEP_TIMEOUT_SECONDS = 900


class PlanError(ValueError):
    """A plan document is malformed, or asks for something the runner refuses."""


@dataclass(frozen=True)
class Source:
    """Where the code under test comes from, pinned to an exact revision.

    `kind="git"` clones and detaches at `sha`; a clone whose HEAD does not match
    is an error, never a warning. `kind="path"` copies a directory tree and is
    for fixtures and pre-vendored checkouts only.
    """

    kind: Literal["git", "path"]
    location: str
    sha: str | None = None

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> Source:
        kind = data.get("kind")
        if kind not in ("git", "path"):
            raise PlanError(f"source.kind must be 'git' or 'path', got {kind!r}")
        location = data.get("location")
        if not isinstance(location, str) or not location:
            raise PlanError("source.location must be a non-empty string")
        sha = data.get("sha")
        if sha is not None and not isinstance(sha, str):
            raise PlanError("source.sha must be a string or null")
        if kind == "git" and not sha:
            raise PlanError("a git source must pin an exact sha; 'latest' is not a revision")
        return Source(kind=kind, location=location, sha=sha)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "location": self.location, "sha": self.sha}


@dataclass(frozen=True)
class Patch:
    """The candidate edit. `kind="none"` is the honest no-op baseline run."""

    kind: Literal["none", "file", "inline"]
    location: str | None = None
    diff: str | None = None
    strip: int = 1

    @staticmethod
    def from_json(data: Mapping[str, Any] | None) -> Patch:
        if data is None:
            return Patch(kind="none")
        kind = data.get("kind", "none")
        if kind not in ("none", "file", "inline"):
            raise PlanError(f"patch.kind must be 'none', 'file' or 'inline', got {kind!r}")
        location = data.get("location")
        diff = data.get("diff")
        if kind == "file" and not isinstance(location, str):
            raise PlanError("patch.location must be a string when patch.kind is 'file'")
        if kind == "inline" and not isinstance(diff, str):
            raise PlanError("patch.diff must be a string when patch.kind is 'inline'")
        strip = data.get("strip", 1)
        if not isinstance(strip, int) or strip < 0:
            raise PlanError("patch.strip must be a non-negative integer")
        return Patch(kind=kind, location=location, diff=diff, strip=strip)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "location": self.location, "strip": self.strip}


@dataclass(frozen=True)
class Step:
    """One command, its phase, and how long it is allowed to take."""

    name: str
    argv: tuple[str, ...]
    phase: NetworkPhase = "none"
    timeout_seconds: int = DEFAULT_STEP_TIMEOUT_SECONDS
    credentials: tuple[str, ...] = ()
    workdir: str = "."

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> Step:
        name = data.get("name")
        if not isinstance(name, str) or not name or "/" in name:
            raise PlanError(f"step.name must be a non-empty path-free string, got {name!r}")
        argv = data.get("argv")
        if not isinstance(argv, Sequence) or isinstance(argv, str) or not argv:
            raise PlanError(f"step[{name}].argv must be a non-empty list of strings")
        if not all(isinstance(part, str) for part in argv):
            raise PlanError(f"step[{name}].argv must contain only strings")
        phase = data.get("phase", "none")
        if phase not in NETWORK_PHASES:
            raise PlanError(f"step[{name}].phase must be one of {NETWORK_PHASES}, got {phase!r}")
        timeout = data.get("timeout_seconds", DEFAULT_STEP_TIMEOUT_SECONDS)
        if not isinstance(timeout, int) or timeout <= 0:
            raise PlanError(f"step[{name}].timeout_seconds must be a positive integer")
        credentials = tuple(data.get("credentials", ()))
        if not all(isinstance(name_, str) for name_ in credentials):
            raise PlanError(f"step[{name}].credentials must contain only strings")
        if credentials and phase != "live_verification":
            raise PlanError(
                f"step[{name}] requests credentials in phase {phase!r}; "
                "credentials are only released during live_verification"
            )
        unknown = sorted(set(credentials) - LIVE_VERIFICATION_CREDENTIALS)
        if unknown:
            raise PlanError(
                f"step[{name}] requests credentials outside the allowlist: {unknown}. "
                "The sandbox never receives GitHub, admin, or control-plane credentials."
            )
        workdir = data.get("workdir", ".")
        if not isinstance(workdir, str):
            raise PlanError(f"step[{name}].workdir must be a string")
        return Step(
            name=name,
            argv=tuple(argv),
            phase=phase,
            timeout_seconds=timeout,
            credentials=credentials,
            workdir=workdir,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "argv": list(self.argv),
            "phase": self.phase,
            "timeout_seconds": self.timeout_seconds,
            "credentials": list(self.credentials),
            "workdir": self.workdir,
        }


@dataclass(frozen=True)
class SandboxPlan:
    """A complete, self-describing unit of untrusted work."""

    plan_id: str
    source: Source
    steps: tuple[Step, ...]
    patch: Patch = field(default_factory=lambda: Patch(kind="none"))
    schema_version: str = PLAN_SCHEMA_VERSION
    description: str = ""

    @staticmethod
    def from_json(data: Mapping[str, Any]) -> SandboxPlan:
        version = data.get("schema_version")
        if version != PLAN_SCHEMA_VERSION:
            raise PlanError(
                f"unsupported plan schema_version {version!r}; this runner speaks "
                f"{PLAN_SCHEMA_VERSION}"
            )
        plan_id = data.get("plan_id")
        if not isinstance(plan_id, str) or not plan_id:
            raise PlanError("plan_id must be a non-empty string")
        source_data = data.get("source")
        if not isinstance(source_data, Mapping):
            raise PlanError("source must be an object")
        steps_data = data.get("steps")
        if not isinstance(steps_data, Sequence) or not steps_data:
            raise PlanError("steps must be a non-empty list")
        steps = tuple(Step.from_json(step) for step in steps_data)
        names = [step.name for step in steps]
        if len(set(names)) != len(names):
            raise PlanError(f"step names must be unique; got {names}")
        patch_data = data.get("patch")
        if patch_data is not None and not isinstance(patch_data, Mapping):
            raise PlanError("patch must be an object or null")
        description = data.get("description", "")
        if not isinstance(description, str):
            raise PlanError("description must be a string")
        return SandboxPlan(
            plan_id=plan_id,
            source=Source.from_json(source_data),
            steps=steps,
            patch=Patch.from_json(patch_data),
            description=description,
        )

    @staticmethod
    def load(path: str | Path) -> SandboxPlan:
        raw = Path(path).read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PlanError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, Mapping):
            raise PlanError(f"{path} must contain a JSON object")
        return SandboxPlan.from_json(data)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "description": self.description,
            "source": self.source.to_json(),
            "patch": self.patch.to_json(),
            "steps": [step.to_json() for step in self.steps],
        }
