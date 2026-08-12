"""Application of a candidate patch inside the workspace.

A patch that does not apply cleanly is a terminal condition, not something to
retry with fuzz: the run stops and the record says why. Silently landing a
partial edit and then reporting on test results would make the evidence trail
lie about what was tested.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Patch


class PatchError(RuntimeError):
    """The candidate patch could not be applied to the pinned source."""


@dataclass(frozen=True)
class PatchOutcome:
    """What was applied, and whether it changed anything."""

    kind: str
    applied: bool
    diff_bytes: int
    detail: str


def resolve_diff(patch: Patch, *, base_dir: Path) -> str:
    """Read the patch text for a plan, without applying it."""

    if patch.kind == "none":
        return ""
    if patch.kind == "inline":
        return patch.diff or ""
    assert patch.location is not None  # guaranteed by SandboxPlan validation
    location = (base_dir / patch.location).resolve()
    if not location.is_file():
        raise PatchError(f"patch file {location} does not exist")
    return location.read_text(encoding="utf-8")


def apply_patch(patch: Patch, *, workspace: Path, base_dir: Path) -> PatchOutcome:
    """Apply the plan's patch to the workspace and describe the outcome."""

    diff = resolve_diff(patch, base_dir=base_dir)
    if not diff.strip():
        # An empty diff is the baseline run: prove the pinned source builds and
        # tests green before any generated edit is credited with anything.
        return PatchOutcome(kind=patch.kind, applied=False, diff_bytes=0, detail="no-op patch")

    result = subprocess.run(
        ["git", "apply", f"-p{patch.strip}", "--whitespace=nowarn", "-"],
        cwd=workspace,
        input=diff,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PatchError(f"git apply failed: {result.stderr.strip() or result.stdout.strip()}")
    return PatchOutcome(
        kind=patch.kind,
        applied=True,
        diff_bytes=len(diff.encode("utf-8")),
        detail="applied with git apply",
    )
