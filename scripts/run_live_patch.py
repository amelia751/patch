"""Seed the Patch agent with the pinned storygen task and stream the turn.

This is the live path: Vertex Gemini, real tools, workspace outside the
checkout. Impact and policy stay deterministic so the model is Patch (and
Verification). Change Intelligence is skipped — the static ChangeManifest is
the seed.

    uv run --all-packages python scripts/run_live_patch.py

Workspace is kept under --scratch so the edits and viewer evidence survive.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.adk import (  # noqa: E402
    REASONING_MODEL,
    adk_unavailable_reason,
    adk_version,
    configure_vertex_environment,
    vertex_unavailable_reason,
)
from agents.context import RunContext  # noqa: E402
from agents.orchestrator import Orchestrator, VerticalSlice, binding_value  # noqa: E402
from agents.tools.credentials import RuntimeCredentialsInventory  # noqa: E402
from agents.trace import ToolTrace  # noqa: E402
from packages.providers.dotenv import apply_defaults, read_env_files  # noqa: E402
from packages.providers.google.config import load_config  # noqa: E402
from packages.providers.google.errors import GoogleProviderError  # noqa: E402
from packages.schemas.run_state import RunState  # noqa: E402
from sandbox.session import open_session  # noqa: E402

DEFAULT_FIXTURE: Final[Path] = REPO_ROOT / "demo" / "storygen"
DEFAULT_FEED_DIR: Final[Path] = REPO_ROOT / "demo" / "fixtures"
DEFAULT_MANIFEST: Final[Path] = REPO_ROOT / "agents" / "fixtures" / "change_manifest.gemini20.json"
DEFAULT_RUN_ID: Final[str] = "live-patch"

DEMO_SLICE: Final[VerticalSlice] = VerticalSlice(
    change_id="gemini20-flash-shutdown-2026-06-01",
    repo="amelia751/storygen",
    entrypoint="lib/gemini.ts",
    binding="MODEL",
    build_command="python3 generate.py",
    test_command="python3 -m unittest test_generate.py",
)


def _log(line: str) -> None:
    print(line, flush=True)


def _stage_fixture(session: object, fixture: Path) -> None:
    working = session.working_dir  # type: ignore[attr-defined]
    shutil.copytree(
        fixture,
        working,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "node_modules", ".next", ".sandbox-home", ".sandbox-tmp"
        ),
    )


async def _run(*, scratch: Path, fixture: Path, manifest: Path, run_id: str) -> int:
    session = open_session("local", root=scratch, run_id=run_id, retain=True)
    _stage_fixture(session, fixture)
    _log(f"workspace: {session.working_dir}")
    _log(f"task:      migrate {DEMO_SLICE.entrypoint} off retired Gemini 2.0 Flash")
    _log(f"manifest:  {manifest}")
    _log(f"model:     {REASONING_MODEL}")
    _log("")

    context = RunContext(
        run_id=run_id,
        repo_root=REPO_ROOT,
        feed_dir=DEFAULT_FEED_DIR,
        workspace_root=Path(session.working_dir),
        sandbox=session,
        credentials_inventory=RuntimeCredentialsInventory(
            bound=True,
            secret_names=("GEMINI_API_KEY",)
            if os.environ.get("PATCHAPI_VAULT_HAS_GEMINI") == "1"
            else (),
            gcp_connected=False,
            detail=(
                "storygen vault has GEMINI_API_KEY"
                if os.environ.get("PATCHAPI_VAULT_HAS_GEMINI") == "1"
                else "storygen vault is empty: no GEMINI_API_KEY and no GCP connection"
            ),
        ),
    )
    trace = ToolTrace(run_id=run_id, live=_log)
    orchestrator = Orchestrator(context, trace)

    try:
        base = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        base_sha = base.stdout.strip() if len(base.stdout.strip()) == 40 else "0" * 40
        result = await orchestrator.run_vertical_slice(
            DEMO_SLICE,
            base_sha=base_sha,
            deterministic=False,
            setup_deterministic=True,
            static_manifest=manifest,
        )
    finally:
        workspace = Path(session.working_dir)
        session.close()

    _log("")
    _log("stages:")
    for stage in result.stages:
        served = stage.turn.served_model if stage.turn else "(no model)"
        _log(f"  {stage.agent:<20} {stage.state:<18} {served:<28} {stage.detail}")
    _log(f"run state: {result.state}")
    if context.operator_requests:
        _log("operator hold:")
        for request in context.operator_requests:
            _log(
                f"  need={request.get('need')} names={request.get('names')} "
                f"agent={request.get('agent')} reason={request.get('reason')}"
            )
            _log(f"  message={request.get('message')}")
    elif result.state is RunState.WAITING_ON_OPERATOR:
        _log("operator hold: state is WAITING_ON_OPERATOR but no request was recorded")

    source = workspace / DEMO_SLICE.entrypoint
    if source.is_file():
        bound = binding_value(source.read_text(encoding="utf-8"), DEMO_SLICE.binding)
        _log(f"{DEMO_SLICE.binding} now binds {bound!r}")
    _log(f"workspace kept at {workspace}")
    return (
        0
        if result.state
        in {
            RunState.HUMAN_REQUIRED,
            RunState.PR_CREATED,
            RunState.WAITING_ON_OPERATOR,
        }
        else 1
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument(
        "--scratch",
        type=Path,
        default=None,
        help="parent directory for the sandbox (default: a temp dir that is kept)",
    )
    args = parser.parse_args(argv)

    reason = adk_unavailable_reason()
    if reason is not None:
        _log(f"cannot start: {reason}")
        return 2
    apply_defaults(read_env_files([REPO_ROOT / ".env", REPO_ROOT / ".env.example"]))
    try:
        config = load_config(base_dir=REPO_ROOT)
    except GoogleProviderError as exc:
        _log(f"cannot start: {exc}")
        return 2
    blocked = vertex_unavailable_reason(config)
    if blocked is not None:
        _log(f"cannot start: {blocked}")
        return 2
    applied = configure_vertex_environment(config)
    _log(f"google-adk:    {adk_version()}")
    _log(f"vertex:        project {applied['GOOGLE_CLOUD_PROJECT']} @ {config.location}")

    scratch = args.scratch or Path(tempfile.mkdtemp(prefix="patchapi-live-"))
    scratch.mkdir(parents=True, exist_ok=True)
    return asyncio.run(
        _run(scratch=scratch, fixture=args.fixture, manifest=args.manifest, run_id=args.run_id)
    )


if __name__ == "__main__":
    raise SystemExit(main())
