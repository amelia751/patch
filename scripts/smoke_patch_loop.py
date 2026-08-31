"""Live proof that the Patch debug loop migrates a workspace inside a session.

    uv run --all-packages python scripts/smoke_patch_loop.py

What it does, in order: copy the pinned `demo/storygen` fixture into a
disposable sandbox session outside the repository, seed the pinned Gemini 2.0
shutdown manifest, scan, clear the deterministic policy gate, then run one real
Patch turn on Vertex Gemini that has to make `python3 generate.py` exit 0.

Three outcomes, and only three. `PASS` means the copied entry point no longer
binds a retired model identifier *and* the two commands exit 0 when this script
re-runs them itself, after the run. `SKIP` means ADK, credentials or the
requested sandbox transport is genuinely absent, and is the only case where no
model was called. `FAIL` means the loop ran and did not converge.

Nothing here writes to `demo/`: the fixture is copied, and the copy is what the
agent edits. `--deterministic` (or PATCHAPI_PATCH_LOOP_DETERMINISTIC=1) proves
the isolation and state-machine halves with no model in the loop; it is not a
fallback the live path degrades into.
"""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # The script lives in scripts/, so the repository root is not on sys.path
    # when it is invoked by path. Every other entry point is a module.
    sys.path.insert(0, str(REPO_ROOT))

from agents.adk import (  # noqa: E402
    REASONING_MODEL,
    adk_unavailable_reason,
    adk_version,
    configure_vertex_environment,
    vertex_unavailable_reason,
)
from agents.context import RunContext  # noqa: E402
from agents.orchestrator import (  # noqa: E402
    DETERMINISTIC_ENV_VAR,
    Orchestrator,
    VerticalSlice,
    binding_value,
)
from agents.trace import ToolTrace  # noqa: E402
from packages.providers.dotenv import apply_defaults, read_env_files  # noqa: E402
from packages.providers.google.config import load_config  # noqa: E402
from packages.providers.google.errors import GoogleProviderError  # noqa: E402
from packages.schemas.run_state import RunState  # noqa: E402
from sandbox.session import SandboxUnavailableError, open_session  # noqa: E402

EXIT_PASS: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_SKIP: Final[int] = 3

DEFAULT_FIXTURE: Final[Path] = REPO_ROOT / "demo" / "storygen"
DEFAULT_FEED_DIR: Final[Path] = REPO_ROOT / "demo" / "fixtures"
DEFAULT_MANIFEST: Final[Path] = REPO_ROOT / "agents" / "fixtures" / "change_manifest.gemini20.json"
DEFAULT_RUN_ID: Final[str] = "smoke-patch-loop"

# This script exercises the demo fixture. Production remediations build the
# slice from the change record and the checkout, via slices.decide().
DEMO_SLICE: Final[VerticalSlice] = VerticalSlice(
    change_id="gemini20-flash-shutdown-2026-06-01",
    repo="amelia751/storygen",
    entrypoint="lib/gemini.ts",
    binding="MODEL",
    build_command="python3 generate.py",
    test_command="python3 -m unittest test_generate.py",
)

# Compiled artefacts of a previous local run are not part of the fixture and
# would let a stale module answer the check the loop is supposed to prove.
_NOT_FIXTURE: Final[tuple[str, ...]] = (
    "__pycache__",
    "*.pyc",
    "node_modules",
    ".next",
    ".sandbox-home",
    ".sandbox-tmp",
)


def _apply_repo_pins() -> None:
    """Layer the repository's non-secret pins under the real environment."""
    apply_defaults(read_env_files([REPO_ROOT / ".env", REPO_ROOT / ".env.example"]))


def _base_sha(repo: str, *, require_remote: bool = False) -> str:
    """The commit a GitHub write must pin.

    A pull request on `amelia751/storygen` has to start from that repository's
    HEAD. The PatchAPI checkout SHA is only a stand-in for isolated runs.
    """
    remote = subprocess.run(
        ["gh", "api", f"repos/{repo}/commits/HEAD", "--jq", ".sha"],
        capture_output=True,
        text=True,
        check=False,
    )
    sha = remote.stdout.strip()
    if remote.returncode == 0 and len(sha) == 40:
        return sha
    if require_remote:
        raise RuntimeError(
            f"could not read HEAD for {repo}: {(remote.stderr or remote.stdout).strip()}"
        )
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip()


def _session_kwargs(kind: str, scratch: Path, run_id: str) -> dict[str, Any]:
    """Constructor arguments for the requested transport.

    Both transports keep their scratch under `scratch`, which is outside the
    repository, so nothing a session writes can land in the checkout.
    """
    if kind == "local":
        return {"root": scratch, "run_id": run_id}
    return {"run_id": run_id, "scratch_root": scratch}


def _is_fixture_file(path: Path) -> bool:
    return path.is_file() and not any(
        part == "__pycache__" or part.endswith(".pyc") for part in path.parts
    )


def _stage_fixture(session: Any, fixture: Path) -> None:
    """Copy the pinned fixture into the session workspace. Never the reverse.

    A local session exposes a real directory, so the copy is a `copytree`. A
    remote one does not, and the files go over the session's own write path —
    the only channel a sandbox has.
    """
    working = session.working_dir
    if isinstance(working, Path):
        shutil.copytree(
            fixture,
            working,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(*_NOT_FIXTURE),
        )
        return
    for path in sorted(fixture.rglob("*")):
        if _is_fixture_file(path):
            session.write_file(
                path.relative_to(fixture).as_posix(), path.read_text(encoding="utf-8")
            )


def _recheck(session: Any, slice_: VerticalSlice) -> tuple[bool, str]:
    """Re-run the pinned checks in the workspace, independently of the run.

    The orchestrator already ran these. Running them again here is the point:
    this script's exit code must depend on the workspace, not on a value the
    orchestrator computed and could have computed wrongly.
    """
    for command in (slice_.build_command, slice_.test_command):
        result = session.execute(command.split(), 300)
        if result.exit_code != 0:
            tail = (result.stderr or result.stdout).strip()[-400:]
            return False, f"{command!r} exited {result.exit_code} after the run: {tail}"
    return True, "both pinned checks exited 0 in the session workspace"


async def _run(
    session: Any,
    slice_: VerticalSlice,
    *,
    run_id: str,
    feed_dir: Path,
    static_manifest: Path | None,
    deterministic: bool,
    trace_out: Path | None,
    open_pr: bool,
) -> tuple[int, str]:
    context = RunContext(
        run_id=run_id,
        repo_root=REPO_ROOT,
        feed_dir=feed_dir,
        workspace_root=Path(session.working_dir) if isinstance(session.working_dir, Path) else None,
        sandbox=session,
    )
    trace = ToolTrace(run_id=run_id)
    orchestrator = Orchestrator(context, trace)

    mode = "deterministic (no model)" if deterministic else f"live on {REASONING_MODEL}"
    print(f"\nrunning the {slice_.change_id!r} slice — {mode}")
    print(f"workspace:      {session.working_dir}")

    result = await orchestrator.run_vertical_slice(
        slice_,
        base_sha=_base_sha(slice_.repo, require_remote=open_pr),
        deterministic=deterministic,
        static_manifest=static_manifest,
    )

    print(f"\ntool trace ({len(trace)} calls, run {run_id}):")
    print(trace.render() or "  (no tool calls)")
    if trace_out is not None:
        trace_out.parent.mkdir(parents=True, exist_ok=True)
        trace_out.write_text(trace.to_ndjson(), encoding="utf-8")
        print(f"  trace written to {trace_out}")

    print("\nstages:")
    for stage in result.stages:
        served = stage.turn.served_model if stage.turn else "(no model)"
        print(f"  {stage.agent:<20} {stage.state:<18} {served:<24} {stage.detail}")
    print(f"\nrun state:      {result.state}")

    report = context.output("verification_report")
    if context.human_required:
        reasons = "; ".join(entry["reason"] for entry in context.human_required)
        github_only = all(
            "GitHub tool service" in entry["reason"] or "not configured" in entry["reason"]
            for entry in context.human_required
        )
        if open_pr or not (
            github_only and report is not None and getattr(report, "permits_pull_request", False)
        ):
            return EXIT_FAIL, f"the run stopped for a human on the pinned fixture: {reasons}"
    if trace.denied:
        denied = ", ".join(event.tool for event in trace.denied)
        return EXIT_FAIL, f"an agent attempted tools outside its allowlist: {denied}"
    if not result.reached_testing:
        return EXIT_FAIL, f"the slice ended {result.state}: {result.detail}"
    if report is None or not getattr(report, "permits_pull_request", False):
        return EXIT_FAIL, "independent verification did not pass; no pull request was earned"

    source = session.read_file(slice_.entrypoint)
    binding = binding_value(source, slice_.binding)
    manifest = context.output("change_manifest")
    if binding is None:
        return EXIT_FAIL, f"{slice_.entrypoint} no longer assigns {slice_.binding}"
    if binding in manifest.affected_identifiers:
        return EXIT_FAIL, f"{slice_.entrypoint} still binds {slice_.binding} to {binding!r}"

    passed, detail = _recheck(session, slice_)
    if not passed:
        return EXIT_FAIL, detail
    if open_pr:
        if result.state is not RunState.PR_CREATED:
            return EXIT_FAIL, f"no pull request was opened ({result.state}: {result.detail})"
        url = ""
        for stage in reversed(result.stages):
            output = stage.output
            if not isinstance(output, dict):
                continue
            payload = output.get("result") if isinstance(output.get("result"), dict) else output
            if isinstance(payload, dict) and payload.get("html_url"):
                url = str(payload["html_url"])
                break
        extra = f" pull request {url}" if url else " pull request opened"
        return EXIT_PASS, f"{slice_.binding} now binds {binding!r}; {detail};{extra}"
    return EXIT_PASS, f"{slice_.binding} now binds {binding!r}; {detail}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--feed-dir", type=Path, default=DEFAULT_FEED_DIR)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="static ChangeManifest JSON (skips the provider crawl)",
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--sandbox", choices=("local", "gke"), default="local")
    parser.add_argument(
        "--deterministic",
        action="store_true",
        default=os.environ.get(DETERMINISTIC_ENV_VAR) == "1",
        help="apply the pinned rewrite without calling a model",
    )
    parser.add_argument(
        "--trace-out",
        type=Path,
        default=None,
        help="write the tool trace as NDJSON to this path",
    )
    parser.add_argument(
        "--open-pr",
        action="store_true",
        help="require github-tools and open the storygen pull request",
    )
    args = parser.parse_args(argv)

    if not args.fixture.is_dir():
        print(f"FAIL: no fixture directory at {args.fixture}")
        return EXIT_FAIL

    if args.open_pr and not os.environ.get("PATCHAPI_GITHUB_TOOLS_URL", "").strip():
        print("FAIL: --open-pr needs PATCHAPI_GITHUB_TOOLS_URL pointing at github-tools")
        return EXIT_FAIL

    if not args.deterministic:
        reason = adk_unavailable_reason()
        if reason is not None:
            print(f"SKIP: {reason}")
            return EXIT_SKIP
        _apply_repo_pins()
        try:
            config = load_config(base_dir=REPO_ROOT)
        except GoogleProviderError as exc:
            print(f"FAIL: {exc}")
            return EXIT_FAIL
        reason = vertex_unavailable_reason(config)
        if reason is not None:
            print(f"SKIP: {reason}")
            return EXIT_SKIP
        applied = configure_vertex_environment(config)
        print(f"google-adk:     {adk_version()}")
        print(f"reasoning pin:  {REASONING_MODEL}")
        print(f"vertex:         project {applied['GOOGLE_CLOUD_PROJECT']} @ {config.location}")

    # Outside the repository, so a run that escapes its workspace cannot land in
    # the checkout, and so `demo/` is never edited in place.
    scratch = Path(tempfile.mkdtemp(prefix="patchapi-patch-loop-"))
    try:
        try:
            kwargs = _session_kwargs(args.sandbox, scratch, args.run_id)
            session = open_session(args.sandbox, **kwargs)
        except SandboxUnavailableError as exc:
            print(f"SKIP: the {args.sandbox} sandbox is unavailable: {exc}")
            return EXIT_SKIP
        except (ImportError, TypeError) as exc:
            print(f"SKIP: the {args.sandbox} sandbox transport is not wired here: {exc}")
            return EXIT_SKIP

        try:
            _stage_fixture(session, args.fixture)
            code, message = asyncio.run(
                _run(
                    session,
                    DEMO_SLICE,
                    run_id=args.run_id,
                    feed_dir=args.feed_dir,
                    static_manifest=args.manifest if args.manifest.is_file() else None,
                    deterministic=args.deterministic,
                    trace_out=args.trace_out,
                    open_pr=args.open_pr,
                )
            )
        # A failed run is a FAIL line and an exit code, not a traceback: this is
        # a verification entry point, and its contract is the three outcomes.
        except Exception as exc:
            print(f"FAIL: the patch loop raised {type(exc).__name__}: {exc}")
            return EXIT_FAIL
        finally:
            session.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    print(f"\n{'PASS' if code == EXIT_PASS else 'FAIL'}: {message}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
