"""Command-line entrypoint for the sandbox runner.

Identical invocation shape locally and inside the runner container image:

    python -m sandbox.runner.entrypoint --plan <plan.json> [--sandbox-root DIR]

Exit code 0 means, and only means, that every planned step passed. Any other
outcome — failed step, timeout, unappliable patch, missing credential — exits
non-zero with the run record on disk.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .config import PlanError, SandboxPlan
from .runner import execute_plan
from .workspace import IsolationError

_SANDBOX_ROOT_ENV = "PATCHAPI_SANDBOX_ROOT"


def default_sandbox_root() -> Path:
    configured = os.environ.get(_SANDBOX_ROOT_ENV)
    return Path(configured) if configured else Path(tempfile.gettempdir())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sandbox.runner",
        description="Run a pinned source tree plus a candidate patch in an isolated workspace.",
    )
    parser.add_argument("--plan", required=True, type=Path, help="path to a sandbox.plan.v1 file")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="root for relative source and patch locations (default: repository root)",
    )
    parser.add_argument(
        "--sandbox-root",
        type=Path,
        default=None,
        help=f"parent of the run directory (default: ${_SANDBOX_ROOT_ENV} or the system temp dir)",
    )
    parser.add_argument("--run-id", default=None, help="stable id for this run; must be unique")
    parser.add_argument(
        "--retain",
        action="store_true",
        help="keep the workspace after the run for evidence; logs are kept either way",
    )
    parser.add_argument("--json", action="store_true", help="print the run record to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Default base dir is the repository this file lives in, so a plan can name
    # `sandbox/runner/testdata/...` and mean the same thing from any cwd.
    base_dir = (args.base_dir or Path(__file__).resolve().parents[2]).resolve()
    sandbox_root = (args.sandbox_root or default_sandbox_root()).resolve()

    try:
        plan = SandboxPlan.load(args.plan)
    except (PlanError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    try:
        result = execute_plan(
            plan,
            sandbox_root=sandbox_root,
            base_dir=base_dir,
            run_id=args.run_id,
            retain=args.retain,
        )
    except (IsolationError, OSError) as exc:
        # An unwritable or unreachable sandbox root is a setup failure, not a
        # verdict on the patch: exit 2, distinct from a run that reached a
        # conclusion and failed.
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_json(), indent=2))
    else:
        print(f"{result.status}: {plan.plan_id} ({result.detail})")
        print(f"run dir: {result.run_dir}")
        for step in result.steps:
            print(f"  {step.status:<7} {step.name:<12} {step.log_path}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
