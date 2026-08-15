"""The Patch debug loop end to end, with no model in it.

`PATCHAPI_PATCH_LOOP_DETERMINISTIC` exists so the halves of the slice that are
not the model — isolation, containment, the state machine, and the orchestrator's
independent re-check — can be exercised without Vertex. That is exactly what
these tests use it for. They prove the loop by reading the workspace and the
exit codes, never by reading a summary of what happened.
"""

import asyncio
import shutil
import sys
from pathlib import Path

import pytest

# `sandbox/` is a namespace package with no distribution of its own, so the
# repository root goes on `sys.path` here rather than by an install step —
# the same arrangement `sandbox/tests` uses.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.config import AgentId, ToolName, tool_allowlist  # noqa: E402
from agents.context import RunContext  # noqa: E402
from agents.guardrails import build_tool_guardrails  # noqa: E402
from agents.orchestrator import GEMINI20_SLICE, Orchestrator, binding_value  # noqa: E402
from agents.tools.results import is_refusal  # noqa: E402
from agents.tools.workspace import build_workspace_tools  # noqa: E402
from agents.trace import ToolStatus, ToolTrace  # noqa: E402
from packages.schemas.run_state import RunState  # noqa: E402
from sandbox.session import LocalSession  # noqa: E402

# A pinned tree, not the developer's HEAD: a contract that names a base_sha has
# to name a fixed one for the test to be reproducible.
BASE_SHA = "87e77dc54ac81ac573916db0ec6ceb97474902b0"

RETIRED = "gemini-2.0-flash"
REPLACEMENT = "gemini-3.5-flash"


@pytest.fixture
def session(tmp_path: Path, repo_root: Path):
    """A local sandbox session holding a copy of the pinned fixture.

    The fixture is copied, never opened in place. A loop that edited
    `demo/gemini20-hello` would leave the next run's red state already green.
    """
    opened = LocalSession(root=tmp_path, run_id="run-patch-loop")
    shutil.copytree(
        repo_root / "demo" / "gemini20-hello",
        opened.working_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    yield opened
    opened.close()


@pytest.fixture
def sandboxed_context(session, repo_root: Path, feed_dir: Path) -> RunContext:
    return RunContext(
        run_id="run-patch-loop",
        repo_root=repo_root,
        feed_dir=feed_dir,
        workspace_root=session.working_dir,
        sandbox=session,
    )


def test_the_fixture_starts_red(session):
    """Without this the green assertions below would prove nothing."""
    assert session.execute(["python3", "generate.py"], 60).exit_code == 1
    assert binding_value(session.read_file("generate.py"), "MODEL") == RETIRED


def test_the_deterministic_loop_migrates_the_workspace(sandboxed_context, session):
    orchestrator = Orchestrator(sandboxed_context, ToolTrace(run_id="run-patch-loop"))

    result = asyncio.run(orchestrator.run_vertical_slice(base_sha=BASE_SHA, deterministic=True))

    assert result.state is RunState.TESTING, result.detail
    assert result.reached_testing

    # The claim is checked against the workspace, not against the run's own
    # report of the workspace.
    source = session.read_file(GEMINI20_SLICE.entrypoint)
    assert binding_value(source, "MODEL") == REPLACEMENT
    assert session.execute(["python3", "generate.py"], 60).exit_code == 0
    assert session.execute(["python3", "-m", "unittest", "test_generate.py"], 60).exit_code == 0


def test_the_deterministic_loop_records_every_contract(sandboxed_context):
    orchestrator = Orchestrator(sandboxed_context, ToolTrace(run_id="run-patch-loop"))
    asyncio.run(orchestrator.run_vertical_slice(base_sha=BASE_SHA, deterministic=True))

    manifest = sandboxed_context.output("change_manifest")
    report = sandboxed_context.output("impact_report")
    decision = sandboxed_context.output("policy_decision")
    plan = sandboxed_context.output("patch_plan")

    assert manifest.change_id == GEMINI20_SLICE.change_id
    # The pinned fixture carries a hashed snapshot, so Policy has evidence to
    # clear and does not have to fail closed on an unverifiable provider claim.
    assert manifest.has_verifiable_evidence is True
    assert RETIRED in {finding.identifier for finding in report.findings}
    assert decision.auto_patch is True
    assert plan.files_expected == [GEMINI20_SLICE.entrypoint]
    # Stopping at TESTING is the point: no verification report, and no PR.
    assert sandboxed_context.output("verification_report") is None
    assert not sandboxed_context.stopped_for_human


def test_an_unaffected_workspace_stops_before_policy(tmp_path, repo_root, feed_dir):
    """A repository the scan clears is UNAFFECTED, not a no-op patch run."""
    with LocalSession(root=tmp_path, run_id="run-clean") as clean:
        clean.write_file("generate.py", f'MODEL = "{REPLACEMENT}"\n')
        context = RunContext(
            run_id="run-clean",
            repo_root=repo_root,
            feed_dir=feed_dir,
            workspace_root=clean.working_dir,
            sandbox=clean,
        )
        orchestrator = Orchestrator(context, ToolTrace(run_id="run-clean"))
        result = asyncio.run(orchestrator.run_vertical_slice(base_sha=BASE_SHA, deterministic=True))

    assert result.state is RunState.UNAFFECTED
    assert context.output("policy_decision") is None
    assert context.output("patch_plan") is None


def test_the_trace_shows_the_whole_chain(sandboxed_context):
    trace = ToolTrace(run_id="run-patch-loop")
    orchestrator = Orchestrator(sandboxed_context, trace)
    asyncio.run(orchestrator.run_vertical_slice(base_sha=BASE_SHA, deterministic=True))

    called = [event.tool for event in trace]
    assert called.index("scan_repository") < called.index("evaluate_policy")
    assert called.index("evaluate_policy") < called.index("apply_patch")
    assert called.index("apply_patch") < called.index("run_command")
    assert not trace.denied
    assert "open_pull_request" not in called


def test_the_patch_agent_cannot_open_a_pull_request():
    """The grant, and the barrier that holds even if the grant were widened."""
    assert ToolName.OPEN_PULL_REQUEST not in tool_allowlist(AgentId.PATCH)

    trace = ToolTrace(run_id="run-patch-guard")
    before_tool, _ = build_tool_guardrails(AgentId.PATCH, trace)

    class _Tool:
        name = "open_pull_request"

    denial = before_tool(tool=_Tool(), args={"title": "Migrate off Gemini 2.0"})
    assert is_refusal(denial)
    assert denial["reason_code"] == "policy_denied"
    assert trace.events[-1].status is ToolStatus.DENIED


def test_workspace_tools_execute_through_the_session(sandboxed_context, session):
    """Containment is enforced here, before anything reaches the session."""
    tools = {function.__name__: function for function in build_workspace_tools(sandboxed_context)}

    listed = tools["list_dir"](".")
    assert {"name": "generate.py", "kind": "file"} in listed["entries"]

    read = tools["read_file"]("generate.py")
    assert RETIRED in read["content"]

    ran = tools["run_command"]("python3 generate.py")
    assert ran["exit_code"] == 1

    escape = tools["read_file"]("../generate.py")
    assert is_refusal(escape)
    assert escape["reason_code"] == "out_of_scope"

    off_allowlist = tools["run_command"]("python3 -c 'print(1)'")
    assert is_refusal(off_allowlist)
    assert off_allowlist["reason_code"] == "policy_denied"
    # Nothing ran: the workspace is exactly as the fixture left it.
    assert session.execute(["python3", "generate.py"], 60).exit_code == 1
