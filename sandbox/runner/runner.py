"""Orchestration of one sandbox run: allocate, populate, patch, execute, record.

The step names mirror the observability spans in roadmap §12.8
(`sandbox.allocate`, `sandbox.clone`, `sandbox.patch`, `sandbox.build`,
`sandbox.test`) so the local runner and the GKE runner produce comparable
evidence for the same plan.

Every terminal condition that is not an unambiguous green run resolves to a
non-PASS status. Nothing here decides whether a pull request may be opened; it
only reports, truthfully, what happened.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .commands import StepResult, run_step
from .config import RESULT_SCHEMA_VERSION, SandboxPlan
from .environment import build_step_environment, missing_credentials
from .patching import PatchError, apply_patch, resolve_diff
from .workspace import (
    IsolationError,
    SourceError,
    Workspace,
    allocate,
    destroy,
    new_run_id,
    populate,
)

RunStatus = Literal["PASS", "FAIL", "TIMEOUT", "PATCH_FAILED", "ERROR"]


@dataclass
class RunResult:
    """The complete record of one run, written to `result.json`."""

    run_id: str
    plan_id: str
    status: RunStatus
    run_dir: Path
    workspace_path: Path
    workspace_retained: bool
    resolved_sha: str | None = None
    patch_applied: bool = False
    steps: list[StepResult] = field(default_factory=list)
    detail: str = ""
    schema_version: str = RESULT_SCHEMA_VERSION

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "status": self.status,
            "detail": self.detail,
            "runner": {
                "kind": "local-temp-workspace",
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
            "run_dir": str(self.run_dir),
            "workspace": {
                "path": str(self.workspace_path),
                "retained": self.workspace_retained,
            },
            "source": {"resolved_sha": self.resolved_sha},
            "patch": {"applied": self.patch_applied},
            "steps": [step.to_json() for step in self.steps],
        }


def execute_plan(
    plan: SandboxPlan,
    *,
    sandbox_root: Path,
    base_dir: Path,
    run_id: str | None = None,
    retain: bool = False,
) -> RunResult:
    """Run a plan end to end in a disposable workspace.

    `base_dir` resolves relative source and patch locations — normally the
    repository root. Nothing under it is ever written to.
    """

    run_id = run_id or new_run_id()
    source_path = (base_dir / plan.source.location) if plan.source.kind == "path" else None
    space = allocate(sandbox_root=sandbox_root, run_id=run_id, source_path=source_path)

    result = RunResult(
        run_id=run_id,
        plan_id=plan.plan_id,
        status="ERROR",
        run_dir=space.run_dir,
        workspace_path=space.workspace,
        workspace_retained=retain,
    )

    try:
        _run(plan, space, result, base_dir=base_dir)
    except (SourceError, IsolationError) as exc:
        result.status = "ERROR"
        result.detail = str(exc)
    except PatchError as exc:
        result.status = "PATCH_FAILED"
        result.detail = str(exc)
    finally:
        if not retain:
            destroy(space)
        result.workspace_retained = retain and space.workspace.exists()
        space.result_path.write_text(
            json.dumps(result.to_json(), indent=2) + "\n", encoding="utf-8"
        )

    return result


def _run(plan: SandboxPlan, space: Workspace, result: RunResult, *, base_dir: Path) -> None:
    result.resolved_sha = populate(space, plan.source, base_dir=base_dir)

    outcome = apply_patch(plan.patch, workspace=space.workspace, base_dir=base_dir)
    result.patch_applied = outcome.applied
    space.patch_path.write_text(
        _patch_evidence(plan, outcome.detail, base_dir=base_dir), encoding="utf-8"
    )

    for step in plan.steps:
        absent = missing_credentials(step)
        if absent:
            # Fail closed: a live verification step without its credential would
            # otherwise "pass" while proving nothing about the replacement API.
            result.status = "ERROR"
            result.detail = f"step {step.name!r} requires unset credentials: {absent}"
            return

        environment = build_step_environment(step, workspace=space.workspace, run_id=result.run_id)
        step_result = run_step(
            step,
            workspace=space.workspace,
            logs_dir=space.logs,
            environment=environment,
        )
        result.steps.append(step_result)

        if step_result.status != "PASS":
            result.status = step_result.status
            result.detail = (
                f"step {step.name!r} {step_result.status.lower()}"
                f" (exit {step_result.exit_code})"
                + (f": {step_result.detail}" if step_result.detail else "")
            )
            return

    result.status = "PASS"
    result.detail = f"{len(result.steps)} step(s) passed"


def _patch_evidence(plan: SandboxPlan, detail: str, *, base_dir: Path) -> str:
    diff = resolve_diff(plan.patch, base_dir=base_dir)
    header = f"# patch kind: {plan.patch.kind}\n# outcome: {detail}\n"
    return header if not diff.strip() else header + diff
