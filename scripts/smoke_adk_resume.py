#!/usr/bin/env python
"""Does an agent turn that parked for the operator really resume?

The question this answers is not "does the run continue" — the run always
continued, by starting the turn over. It is whether the *turn* continues: does
the model pick up after the tool call it was waiting on, still holding the files
it read and the commands it ran, rather than paying for all of that again.

Resuming needs three things and this exercises all three against the real
stack, no doubles:

1. A resumable app. `is_resumable=True`, so ADK writes the agent state its
   runner needs to rehydrate an invocation.
2. A session that outlives the process. The remediation job exits when a run
   parks, so an in-memory session is a session that is gone. This uses the
   Postgres store the deployed runner uses.
3. The unanswered call. Resuming is sending a `FunctionResponse` carrying the
   id of the `FunctionCall` that paused the turn.

Point 2 is the one a single-process test cannot honestly check, so the runner
and the session service are both thrown away between the pause and the resume
and rebuilt from the database — which is what a second Cloud Run execution does.

    ./scripts/smoke_adk_resume.py

Exit 0 means a parked turn resumed and the model did not redo its earlier work.
Exit 3 means the environment could not answer (no Vertex, no database); that is
reported, not passed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final
from uuid import uuid4

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.adk import (  # noqa: E402
    adk_unavailable_reason,
    configure_vertex_environment,
    generate_content_config,
    new_session_service,
    resume_turn,
    run_turn,
    session_id_for,
    vertex_unavailable_reason,
)
from agents.config import REASONING_MODEL  # noqa: E402
from agents.sessions import session_dsn, undurable_reason  # noqa: E402
from agents.trace import ToolTrace  # noqa: E402
from packages.providers.google.config import load_config  # noqa: E402

EXIT_OK: Final[int] = 0
EXIT_FAILED: Final[int] = 1
EXIT_SKIPPED: Final[int] = 3

# What the fake tools record, so the resumed turn can be checked for repeating
# work instead of continuing it.
CALLS: list[str] = []

INSTRUCTION: Final[str] = """\
You are migrating one file. Work in this exact order and take one step at a
time.

1. Call read_entrypoint to see the file.
2. Call request_runtime_credentials because the migration needs a credential
   you do not have. Then stop and wait.
3. When the credential request comes back answered, call apply_migration once
   and then reply with the single word DONE.

Never call read_entrypoint more than once. If you have already read the file,
you already have its contents.
"""


def read_entrypoint() -> dict[str, str]:
    """Read the file being migrated."""
    CALLS.append("read_entrypoint")
    return {"status": "ok", "path": "lib/gemini.ts", "content": 'const MODEL = "gemini-2.0-flash";'}


def request_runtime_credentials(reason: str) -> dict[str, str]:
    """Ask the operator for a runtime credential. Pauses the turn."""
    CALLS.append("request_runtime_credentials")
    return {"status": "waiting_on_operator", "reason": reason}


def apply_migration(new_model: str) -> dict[str, str]:
    """Rewrite the binding to `new_model`."""
    CALLS.append("apply_migration")
    return {"status": "applied", "model": new_model}


def _agent() -> Any:
    from google.adk.agents import LlmAgent
    from google.adk.tools import LongRunningFunctionTool

    return LlmAgent(
        name="patch",
        model=REASONING_MODEL,
        description="Smoke agent for the operator-hold resume path.",
        instruction=INSTRUCTION,
        tools=[
            read_entrypoint,
            LongRunningFunctionTool(func=request_runtime_credentials),
            apply_migration,
        ],
        generate_content_config=generate_content_config(),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


async def _stored_events(app_name: str, session: str) -> int:
    """How many events the session store holds — proof the turn was persisted."""
    service = new_session_service()
    found = await service.get_session(
        app_name=app_name, user_id="patchapi-orchestrator", session_id=session
    )
    return 0 if found is None else len(found.events)


async def _run(app_name: str) -> int:
    run_id = f"smoke-{uuid4().hex[:12]}"
    trace = ToolTrace(run_id=run_id, live=lambda line: print(f"  {line}"))

    print("— turn one: run until the operator is asked ————————————————")
    # A fresh service per leg, as a process boundary gives.
    first = await run_turn(
        _agent(),
        "Migrate lib/gemini.ts off gemini-2.0-flash. Follow your instructions in order.",
        trace=trace,
        session_service=new_session_service(),
        app_name=app_name,
    )
    print(f"  paused={first.paused} tool={first.long_running_tool!r}")
    print(f"  session={first.session_id!r} call_id={first.pending_call_id!r}")
    print(f"  tools called: {CALLS}")

    if not first.paused:
        print("\nFAIL: the turn never parked, so there is nothing to resume.")
        return EXIT_FAILED
    if not first.resumable:
        print("\nFAIL: the turn parked but carried no session id or call id to answer.")
        return EXIT_FAILED
    if "read_entrypoint" not in CALLS:
        print("\nFAIL: the model parked without doing the work a resume is meant to preserve.")
        return EXIT_FAILED

    expected = session_id_for(run_id, "patch")
    if first.session_id != expected:
        print(f"\nFAIL: session id {first.session_id!r} is not the per-agent {expected!r}.")
        return EXIT_FAILED

    stored = await _stored_events(app_name, first.session_id)
    print(f"\n— the process ends here. {stored} event(s) are in Postgres, not in memory.")
    if stored == 0:
        print("FAIL: nothing was persisted, so a later execution has no turn to rejoin.")
        return EXIT_FAILED

    before = list(CALLS)
    CALLS.clear()

    print("\n— turn two: a new runner, a new session service, answer the call ————")
    second = await resume_turn(
        _agent(),
        call_id=first.pending_call_id,
        tool_name=str(first.long_running_tool),
        response={"status": "ok", "gcp_connected": True, "detail": "The operator connected GCP."},
        trace=trace,
        session_service=new_session_service(),
        app_name=app_name,
    )
    print(f"  invocation={second.invocation_id!r} paused={second.paused}")
    print(f"  reply: {second.final_text[:200]!r}")
    print(f"  tools called after the resume: {CALLS}")

    if second.errors:
        print(f"\nFAIL: the resumed turn errored: {second.errors}")
        return EXIT_FAILED
    if "read_entrypoint" in CALLS:
        print(
            "\nFAIL: the resumed turn read the file again. That is a replay, not a resume — "
            "the session history did not reach the model."
        )
        return EXIT_FAILED
    if "apply_migration" not in CALLS:
        print("\nFAIL: the resumed turn never got past the credential request.")
        return EXIT_FAILED

    print(
        f"\nOK: the turn parked at {before[-1]}, the process ended, and a new runner "
        "continued the same invocation — the file was not read a second time."
    )
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    unavailable = adk_unavailable_reason()
    if unavailable:
        print(f"SKIP: {unavailable}")
        return EXIT_SKIPPED
    undurable = undurable_reason()
    if undurable:
        print(f"SKIP: {undurable}")
        return EXIT_SKIPPED

    config = load_config(base_dir=REPO_ROOT)
    reason = vertex_unavailable_reason(config)
    if reason:
        print(f"SKIP: {reason}")
        return EXIT_SKIPPED
    applied = configure_vertex_environment(config)
    print(f"model    {REASONING_MODEL}")
    project = applied.get("GOOGLE_CLOUD_PROJECT")
    print(f"vertex   {project} / {applied.get('GOOGLE_CLOUD_LOCATION')}")
    print(f"sessions {session_dsn().split('@')[-1]} (schema adk)\n")

    app_name = f"patchapi-smoke-resume-{os.getpid()}"
    return asyncio.run(_run(app_name))


if __name__ == "__main__":
    raise SystemExit(main())
