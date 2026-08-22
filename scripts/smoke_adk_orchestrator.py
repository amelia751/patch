"""Live proof that the ADK fleet runs and produces a `ChangeManifest`.

    uv run --all-packages python scripts/smoke_adk_orchestrator.py

What it does, in order: construct the four reasoning agents, then run one real Change
Intelligence turn against the pinned Google deprecation fixture on Vertex Gemini,
then print the tool trace and validate what the agent recorded.

Three outcomes, and only three. `PASS` means Google answered, the served model
was at or above the pinned generation, and the agent committed a manifest that
validates as `ChangeManifest`. `SKIP` means ADK or credentials are genuinely
absent, and is the only case where no model was called. `FAIL` means the turn
ran and did not satisfy the assertions. There is no path that prints `PASS`
without a response from Google — the manifest is read out of the run context,
which only a tool call can write.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # The script lives in scripts/, so the repository root is not on sys.path
    # when it is invoked by path. Every other entry point is a module.
    sys.path.insert(0, str(REPO_ROOT))

from agents.adk import (  # noqa: E402
    adk_unavailable_reason,
    adk_version,
    configure_vertex_environment,
    vertex_unavailable_reason,
)
from agents.config import (  # noqa: E402
    FLEET_NAME,
    FLEET_VERSION,
    REASONING_MODEL,
    SPECIALISTS,
    AgentId,
    tool_allowlist,
)
from agents.context import RunContext  # noqa: E402
from agents.trace import ToolTrace  # noqa: E402
from packages.providers.dotenv import apply_defaults, read_env_files  # noqa: E402
from packages.providers.google.config import (  # noqa: E402
    MINIMUM_REASONING_GENERATION,
    load_config,
    parse_gemini_generation,
)
from packages.providers.google.errors import GoogleProviderError  # noqa: E402
from packages.schemas.change_manifest import ChangeManifest  # noqa: E402

EXIT_PASS: Final[int] = 0
EXIT_FAIL: Final[int] = 1
EXIT_SKIP: Final[int] = 3

DEFAULT_CHANGE_ID: Final[str] = "imagen4-retirement-2026-08-17"
DEFAULT_FEED_DIR: Final[Path] = REPO_ROOT / "demo" / "fixtures"
DEFAULT_RUN_ID: Final[str] = "smoke-adk-orchestrator"
DEFAULT_DSN_FILE: Final[Path] = REPO_ROOT / ".secrets" / "database-url-proxy.txt"


async def _load_index(project: str, dsn: str) -> tuple[list[dict], str]:
    """Inventory rows for `project`, so the index tools are not reading an empty list."""
    import asyncpg

    from packages.state.index_inventory import index_summary, load_index_usages

    connection = await asyncpg.connect(dsn)
    try:
        row = await connection.fetchrow(
            "SELECT id FROM projects WHERE name = $1 OR id::text = $1", project
        )
        if row is None:
            return [], f"no project named {project!r}"
        project_id = row["id"]
        usages = await load_index_usages(connection, project_id)
        summary = await index_summary(connection, project_id)
    finally:
        await connection.close()
    note = (
        f"{summary['rows']} rows, {summary['repositories']} repos, "
        f"{summary['identifiers']} identifiers"
    )
    return usages, note


def _apply_repo_pins() -> None:
    """Layer the repository's non-secret pins under the real environment.

    `.env` wins over `.env.example`, and anything already exported wins over
    both, so a bare shell behaves like a configured one without overriding an
    operator.
    """
    apply_defaults(read_env_files([REPO_ROOT / ".env", REPO_ROOT / ".env.example"]))


def _print_topology(fleet: dict[AgentId, object]) -> None:
    print(f"\nfleet {FLEET_NAME} v{FLEET_VERSION} — {len(fleet)} specialists")
    for agent_id in SPECIALISTS:
        tools = ", ".join(sorted(str(name) for name in tool_allowlist(agent_id)))
        print(f"  {agent_id:<20} {REASONING_MODEL}")
        print(f"  {'':<20} tools: {tools}")


async def _publish(manifest: ChangeManifest, dsn: str) -> str:
    """Land a recorded manifest on the Releases tab and reclassify."""
    import asyncpg

    from packages.state.discovery import record_manifest_release

    payload = json.loads(manifest.model_dump_json())
    connection = await asyncpg.connect(dsn)
    try:
        if await record_manifest_release(connection, payload):
            return f"published {manifest.change_id} as a release"
        return f"{manifest.change_id} is already covered by an existing release"
    finally:
        await connection.close()


async def _run(
    change_id: str,
    feed_dir: Path,
    run_id: str,
    trace_out: Path | None,
    project: str | None,
    dsn: str | None,
    publish: bool,
) -> tuple[int, str]:
    from agents.orchestrator import Orchestrator

    context = RunContext(run_id=run_id, repo_root=REPO_ROOT, feed_dir=feed_dir)
    if project and dsn:
        usages, note = await _load_index(project, dsn)
        context.index_usages = usages
        context.project_id = project
        print(f"index:          {project} — {note}")
    trace = ToolTrace(run_id=run_id)
    orchestrator = Orchestrator(context, trace)

    _print_topology(orchestrator.fleet)

    print(f"\nrunning change_intelligence on {change_id!r} (fixture dir {feed_dir})")
    result = await orchestrator.run_change_intelligence(change_id)

    print(f"\ntool trace ({len(trace)} calls, run {run_id}):")
    print(trace.render() or "  (no tool calls)")
    if trace_out is not None:
        trace_out.parent.mkdir(parents=True, exist_ok=True)
        trace_out.write_text(trace.to_ndjson(), encoding="utf-8")
        print(f"  trace written to {trace_out}")

    print(f"\nrun state:      {result.state}")
    print(f"served model:   {result.turn.served_model or '(none reported)'}")
    print(f"adk events:     {result.turn.event_count}")
    if result.turn.errors:
        print(f"model errors:   {'; '.join(result.turn.errors)}")
    print(f"final message:  {result.turn.final_text[:300] or '(empty)'}")

    if result.human_required:
        reasons = "; ".join(entry["reason"] for entry in result.human_required)
        return EXIT_FAIL, f"the agent stopped for a human on the golden fixture: {reasons}"

    if not result.completed:
        return EXIT_FAIL, "the turn recorded no ChangeManifest"

    manifest = result.output
    if not isinstance(manifest, ChangeManifest):
        return EXIT_FAIL, f"recorded output is a {type(manifest).__name__}, not a ChangeManifest"

    # Re-validate from JSON: what the run produced has to survive the same
    # round trip a stored contract goes through.
    reloaded = ChangeManifest.model_validate_json(manifest.model_dump_json())
    print("\nChangeManifest:")
    print(json.dumps(json.loads(reloaded.model_dump_json()), indent=2, sort_keys=True))

    served = result.turn.served_model
    if not served:
        return EXIT_FAIL, "Vertex reported no model identity; the model that answered is unproven"
    try:
        generation = parse_gemini_generation(served)
    except GoogleProviderError as exc:
        return EXIT_FAIL, str(exc)
    if generation < MINIMUM_REASONING_GENERATION:
        minimum = ".".join(str(part) for part in MINIMUM_REASONING_GENERATION)
        return EXIT_FAIL, f"served model {served} is older than the pinned minimum {minimum}"

    if trace.denied:
        denied = ", ".join(event.tool for event in trace.denied)
        return EXIT_FAIL, f"the agent attempted tools outside its allowlist: {denied}"
    if not trace.calls("record_change_manifest"):
        return EXIT_FAIL, "no record_change_manifest call in the trace"

    if publish and dsn:
        print(f"\nreleases: {await _publish(reloaded, dsn)}")

    return EXIT_PASS, f"{served} produced a valid ChangeManifest for {manifest.change_id}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--change-id", default=DEFAULT_CHANGE_ID)
    parser.add_argument("--feed-dir", type=Path, default=DEFAULT_FEED_DIR)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument(
        "--trace-out",
        type=Path,
        default=None,
        help="write the tool trace as NDJSON to this path",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="project name or id whose repo index the agent may read",
    )
    parser.add_argument(
        "--dsn-file",
        type=Path,
        default=DEFAULT_DSN_FILE,
        help="file holding the Postgres DSN used with --project",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="write the recorded manifest to the Releases tab and reclassify",
    )
    args = parser.parse_args(argv)

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

    print(f"google-adk:     {adk_version()}")
    print(f"reasoning pin:  {REASONING_MODEL}")
    applied = configure_vertex_environment(config)
    print(f"vertex:         project {applied['GOOGLE_CLOUD_PROJECT']} @ {config.location}")

    dsn = None
    if args.project or args.publish:
        if not args.dsn_file.is_file():
            print(f"FAIL: --project/--publish need a DSN; {args.dsn_file} does not exist")
            return EXIT_FAIL
        dsn = args.dsn_file.read_text(encoding="utf-8").strip()

    try:
        code, message = asyncio.run(
            _run(
                args.change_id,
                args.feed_dir,
                args.run_id,
                args.trace_out,
                args.project,
                dsn,
                args.publish,
            )
        )
    # A failed run is a FAIL line and an exit code, not a traceback: this is a
    # verification entry point, and its contract is the three outcomes.
    except Exception as exc:
        print(f"FAIL: the agent run raised {type(exc).__name__}: {exc}")
        return EXIT_FAIL

    print(f"\n{'PASS' if code == EXIT_PASS else 'FAIL'}: {message}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
