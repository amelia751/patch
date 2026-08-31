"""The Patch debug loop end to end, with no model in it.

`PATCHAPI_PATCH_LOOP_DETERMINISTIC` exists so the halves of the slice that are
not the model — isolation, containment, the state machine, and the orchestrator's
independent re-check — can be exercised without Vertex. That is exactly what
these tests use it for. They prove the loop by reading the workspace and the
exit codes, never by reading a summary of what happened.
"""

import asyncio
import os
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
from agents.orchestrator import Orchestrator, VerticalSlice, binding_value  # noqa: E402
from agents.tools.patch.workspace import build_workspace_tools  # noqa: E402
from agents.tools.pr import GITHUB_TOOLS_URL_ENV  # noqa: E402
from agents.tools.results import is_refusal  # noqa: E402
from agents.trace import ToolStatus, ToolTrace  # noqa: E402
from packages.schemas.run_state import RunState  # noqa: E402
from sandbox.session import LocalSession  # noqa: E402

# A pinned tree, not the developer's HEAD: a contract that names a base_sha has
# to name a fixed one for the test to be reproducible.
BASE_SHA = "87e77dc54ac81ac573916db0ec6ceb97474902b0"

RETIRED = "gemini-2.0-flash"
REPLACEMENT = "gemini-3.5-flash"

# Demo trees, not product constants. The remediator builds a VerticalSlice
# from the ChangeManifest and the checkout; these fixtures only pin the
# deterministic tests to one known layout.
GEMINI20_SLICE = VerticalSlice(
    change_id="gemini20-flash-shutdown-2026-06-01",
    repo="amelia751/storygen",
    entrypoint="lib/gemini.ts",
    binding="MODEL",
    build_command="python3 generate.py",
    test_command="python3 -m unittest test_generate.py",
)
LIVE_PROOF_SLICE = VerticalSlice(
    change_id="imagen4-retirement-2026-08-17",
    repo="amelia751/storygen",
    entrypoint="lib/gemini.ts",
    binding="IMAGE_MODEL",
    build_command="",
    test_command="",
)


@pytest.fixture(autouse=True)
def _no_live_github_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests prove the workspace, not a live pull request."""
    monkeypatch.delenv(GITHUB_TOOLS_URL_ENV, raising=False)
    os.environ.pop(GITHUB_TOOLS_URL_ENV, None)


@pytest.fixture
def session(tmp_path: Path, repo_root: Path):
    """A local sandbox session holding a copy of the pinned fixture.

    The fixture is copied, never opened in place. A loop that edited
    `demo/storygen` would leave the next run's red state already green.
    """
    opened = LocalSession(root=tmp_path, run_id="run-patch-loop")
    shutil.copytree(
        repo_root / "demo" / "storygen",
        opened.working_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules", ".next"),
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
    assert binding_value(session.read_file("lib/gemini.ts"), "MODEL") == RETIRED


def test_the_deterministic_loop_migrates_the_workspace(sandboxed_context, session, repo_root):
    orchestrator = Orchestrator(sandboxed_context, ToolTrace(run_id="run-patch-loop"))
    manifest = repo_root / "agents" / "fixtures" / "change_manifest.gemini20.json"

    result = asyncio.run(
        orchestrator.run_vertical_slice(
            GEMINI20_SLICE,
            base_sha=BASE_SHA,
            deterministic=True,
            static_manifest=manifest,
        )
    )

    assert result.reached_testing, result.detail
    assert result.state in {RunState.HUMAN_REQUIRED, RunState.PR_CREATED, RunState.VERIFYING}

    # The claim is checked against the workspace, not against the run's own
    # report of the workspace.
    source = session.read_file(GEMINI20_SLICE.entrypoint)
    assert binding_value(source, "MODEL") == REPLACEMENT
    assert session.execute(["python3", "generate.py"], 60).exit_code == 0
    assert session.execute(["python3", "-m", "unittest", "test_generate.py"], 60).exit_code == 0
    assert (session.working_dir / "viewer" / "model.json").is_file()
    assert (session.working_dir / ".patchapi-ui" / "screenshot.png").is_file()


def test_the_deterministic_loop_records_every_contract(sandboxed_context):
    orchestrator = Orchestrator(sandboxed_context, ToolTrace(run_id="run-patch-loop"))
    asyncio.run(
        orchestrator.run_vertical_slice(GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=True)
    )

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
    report = sandboxed_context.output("verification_report")
    assert report is not None
    assert str(report.verdict) == "pass"
    # No GitHub tool service in this environment: nothing was opened.
    assert sandboxed_context.output("verification_report").permits_pull_request


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
        result = asyncio.run(
            orchestrator.run_vertical_slice(GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=True)
        )

    assert result.state is RunState.UNAFFECTED
    assert context.output("policy_decision") is None
    assert context.output("patch_plan") is None


def test_the_trace_shows_the_whole_chain(sandboxed_context):
    trace = ToolTrace(run_id="run-patch-loop")
    orchestrator = Orchestrator(sandboxed_context, trace)
    asyncio.run(
        orchestrator.run_vertical_slice(GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=True)
    )

    called = [event.tool for event in trace]
    assert called.index("scan_repository") < called.index("evaluate_policy")
    assert called.index("evaluate_policy") < called.index("apply_patch")
    assert called.index("apply_patch") < called.index("run_command")
    assert called.index("run_command") < called.index("computer_use_step")
    assert called.index("computer_use_step") < called.index("record_verification_report")
    assert not trace.denied
    assert all(
        event.agent is not AgentId.PATCH for event in trace if event.tool == "open_pull_request"
    )


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


@pytest.mark.asyncio
async def test_the_patch_stage_parks_when_the_agent_requests_a_secret(
    sandboxed_context, repo_root, monkeypatch
):
    """The model decides a live check needs a key; the run waits, it does not fail closed."""
    from agents.adk import TurnResult
    from agents.tools.credentials import build_credentials_tools

    orchestrator = Orchestrator(sandboxed_context, ToolTrace(run_id="run-patch-loop"))
    orchestrator.seed_static_manifest(
        repo_root / "agents" / "fixtures" / "change_manifest.gemini20.json"
    )
    await orchestrator.run_impact(GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=True)
    await orchestrator.run_policy(GEMINI20_SLICE, deterministic=True)

    async def _paused_turn(*_args, **_kwargs):
        tools = {
            fn.__name__: fn for fn in build_credentials_tools(sandboxed_context, AgentId.PATCH)
        }
        tools["request_runtime_credentials"](
            need="secret",
            names=["GEMINI_API_KEY"],
            reason="lib/gemini.ts live call reads GEMINI_API_KEY",
        )
        return TurnResult(
            agent="patch",
            final_text="",
            model_versions=(),
            event_count=1,
            trace=orchestrator.trace,
            paused=True,
            long_running_tool="request_runtime_credentials",
        )

    monkeypatch.setattr("agents.orchestrator.run_turn", _paused_turn)
    result = await orchestrator.run_patch(GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=False)

    assert result.state is RunState.WAITING_ON_OPERATOR
    assert sandboxed_context.waiting_on_operator
    assert not sandboxed_context.stopped_for_human
    assert "GEMINI_API_KEY" in result.detail

    resumed = orchestrator.resume_after_operator()
    assert resumed is RunState.PATCHING
    assert not sandboxed_context.waiting_on_operator


IMAGE_RETIRED = "imagen-4.0-generate-001"
IMAGE_REPLACEMENT = "gemini-3.1-flash-image"


@pytest.mark.asyncio
async def test_imagen_parks_before_a_model_turn_when_the_key_is_missing(
    sandboxed_context, repo_root, monkeypatch
):
    """Imagen has no local gate. Missing credentials pause the run; they do not fail it."""
    called = {"turn": False}

    async def _must_not_run(*_args, **_kwargs):
        called["turn"] = True
        raise AssertionError("the patch model must not run before the operator hold")

    monkeypatch.setattr("agents.orchestrator.run_turn", _must_not_run)
    orchestrator = Orchestrator(sandboxed_context, ToolTrace(run_id="run-patch-loop"))
    orchestrator.seed_static_manifest(
        repo_root / "agents" / "fixtures" / "change_manifest.imagen4.json"
    )
    await orchestrator.run_impact(LIVE_PROOF_SLICE, base_sha=BASE_SHA, deterministic=True)
    await orchestrator.run_policy(LIVE_PROOF_SLICE, deterministic=True)
    result = await orchestrator.run_patch(LIVE_PROOF_SLICE, base_sha=BASE_SHA, deterministic=False)

    assert not called["turn"]
    assert result.state is RunState.WAITING_ON_OPERATOR
    assert sandboxed_context.waiting_on_operator
    assert not sandboxed_context.stopped_for_human
    assert "GEMINI_API_KEY" in result.detail
    assert binding_value(sandboxed_context.sandbox.read_file("lib/gemini.ts"), "MODEL") == RETIRED
    assert (
        binding_value(sandboxed_context.sandbox.read_file("lib/gemini.ts"), "IMAGE_MODEL")
        == IMAGE_RETIRED
    )


@pytest.mark.asyncio
async def test_imagen_continues_after_the_operator_connects_gcp(
    sandboxed_context, repo_root, feed_dir, monkeypatch
):
    """Continue after Connect GCP is a new execution that must not park again."""
    from agents.adk import TurnResult
    from agents.context import RunContext
    from agents.tools.credentials import RuntimeCredentialsInventory

    parked = Orchestrator(sandboxed_context, ToolTrace(run_id="run-park"))
    parked.seed_static_manifest(
        repo_root / "agents" / "fixtures" / "change_manifest.imagen4.json"
    )
    await parked.run_impact(LIVE_PROOF_SLICE, base_sha=BASE_SHA, deterministic=True)
    await parked.run_policy(LIVE_PROOF_SLICE, deterministic=True)
    held = await parked.run_patch(LIVE_PROOF_SLICE, base_sha=BASE_SHA, deterministic=False)
    assert held.state is RunState.WAITING_ON_OPERATOR

    # A Cloud Run job exits on the hold. Continue starts a new process with
    # the connection the operator just stored, not the in-memory ADK session.
    resumed_context = RunContext(
        run_id="run-resume",
        repo_root=repo_root,
        feed_dir=feed_dir,
        workspace_root=sandboxed_context.workspace_root,
        sandbox=sandboxed_context.sandbox,
        credentials_inventory=RuntimeCredentialsInventory(bound=True, gcp_connected=True),
    )
    called = {"turn": False}

    async def _empty_turn(*_args, **_kwargs):
        called["turn"] = True
        return TurnResult(
            agent="patch",
            final_text="",
            model_versions=(),
            event_count=1,
            trace=ToolTrace(run_id="run-resume"),
            paused=False,
        )

    monkeypatch.setattr("agents.orchestrator.run_turn", _empty_turn)
    resumed = Orchestrator(resumed_context, ToolTrace(run_id="run-resume"))
    resumed.seed_static_manifest(
        repo_root / "agents" / "fixtures" / "change_manifest.imagen4.json"
    )
    await resumed.run_impact(LIVE_PROOF_SLICE, base_sha=BASE_SHA, deterministic=True)
    await resumed.run_policy(LIVE_PROOF_SLICE, deterministic=True)
    result = await resumed.run_patch(LIVE_PROOF_SLICE, base_sha=BASE_SHA, deterministic=False)

    assert called["turn"]
    assert result.state is RunState.TESTING, result.detail
    assert not resumed_context.waiting_on_operator
    assert (
        binding_value(sandboxed_context.sandbox.read_file("lib/gemini.ts"), "IMAGE_MODEL")
        == IMAGE_REPLACEMENT
    )


@pytest.mark.asyncio
async def test_a_resumed_tree_does_not_start_a_second_patch_turn(
    sandboxed_context, session, repo_root, monkeypatch
):
    """A hold after apply_patch must not send the model around the loop again."""
    from agents.tools.credentials import RuntimeCredentialsInventory

    sandboxed_context.credentials_inventory = RuntimeCredentialsInventory(
        bound=True, gcp_connected=True
    )
    first = Orchestrator(sandboxed_context, ToolTrace(run_id="run-first"))
    first.seed_static_manifest(
        repo_root / "agents" / "fixtures" / "change_manifest.gemini20.json"
    )
    await first.run_impact(GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=True)
    await first.run_policy(GEMINI20_SLICE, deterministic=True)
    landed = await first.run_patch(GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=True)
    assert landed.state is RunState.TESTING
    assert binding_value(session.read_file(GEMINI20_SLICE.entrypoint), "MODEL") == REPLACEMENT

    async def _must_not_run(*_args, **_kwargs):
        raise AssertionError("the patch model must not start a second loop")

    monkeypatch.setattr("agents.orchestrator.run_turn", _must_not_run)
    again = Orchestrator(sandboxed_context, ToolTrace(run_id="run-resume"))
    again.seed_static_manifest(
        repo_root / "agents" / "fixtures" / "change_manifest.gemini20.json"
    )
    await again.run_impact(GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=True)
    await again.run_policy(GEMINI20_SLICE, deterministic=True)
    result = await again.run_patch(
        GEMINI20_SLICE, base_sha=BASE_SHA, deterministic=False, skip_turn=True
    )

    assert result.state is RunState.TESTING, result.detail
    assert binding_value(session.read_file(GEMINI20_SLICE.entrypoint), "MODEL") == REPLACEMENT


def test_imagen_rewrites_image_model_without_running_generate_py(
    sandboxed_context, session, repo_root
):
    from agents.tools.credentials import RuntimeCredentialsInventory

    sandboxed_context.credentials_inventory = RuntimeCredentialsInventory(
        secret_names=("GEMINI_API_KEY",),
        gcp_connected=True,
    )
    orchestrator = Orchestrator(sandboxed_context, ToolTrace(run_id="run-imagen"))
    orchestrator.seed_static_manifest(
        repo_root / "agents" / "fixtures" / "change_manifest.imagen4.json"
    )
    asyncio.run(orchestrator.run_impact(LIVE_PROOF_SLICE, base_sha=BASE_SHA, deterministic=True))
    asyncio.run(orchestrator.run_policy(LIVE_PROOF_SLICE, deterministic=True))
    result = asyncio.run(
        orchestrator.run_patch(LIVE_PROOF_SLICE, base_sha=BASE_SHA, deterministic=True)
    )

    assert result.state is RunState.TESTING, result.detail
    source = session.read_file("lib/gemini.ts")
    assert binding_value(source, "IMAGE_MODEL") == IMAGE_REPLACEMENT
    assert binding_value(source, "MODEL") == RETIRED
    # generate.py still fails: it is the Gemini 2.0 gate, not this change.
    assert session.execute(["python3", "generate.py"], 60).exit_code == 1
