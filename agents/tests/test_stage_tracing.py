"""The trace is the run's reasoning chain, and it carries identifiers only.

Two claims are under test here. That a remediation arrives at a trace backend as
one readable chain — a run span with a stage under it for every stage that
executed, each naming the run it belongs to. And that nothing else rides along:
a trace is exported to a third party, so every attribute on it has to be a
pinned key holding an identifier, a count, or an enum value.

The spans are read back from an in-memory exporter rather than asserted against
the call sites, because the call sites are exactly what could be wrong.
"""

import asyncio
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.context import RunContext  # noqa: E402
from agents.observe import (  # noqa: E402
    EVENT_MEMORY_NOT_RECORDED,
    EVENT_MEMORY_UNAVAILABLE,
    PINNED_ATTRIBUTES,
    SPAN_RUN,
)
from agents.orchestrator import Orchestrator, VerticalSlice  # noqa: E402
from agents.trace import ToolTrace  # noqa: E402
from packages.observability.config import (  # noqa: E402
    ATTR_ATTEMPT,
    ATTR_BASE_SHA,
    ATTR_CHANGE_ID,
    ATTR_MODEL_ID,
    ATTR_POLICY_OUTCOME,
    ATTR_REPO,
    ATTR_RUN_ID,
    SPAN_IMPACT,
    SPAN_PATCH,
    SPAN_POLICY,
    SPAN_SANDBOX,
    SPAN_VERIFICATION,
)
from packages.schemas.run_state import RunState  # noqa: E402
from sandbox.session import LocalSession  # noqa: E402

BASE_SHA = "87e77dc54ac81ac573916db0ec6ceb97474902b0"

SLICE = VerticalSlice(
    change_id="gemini20-flash-shutdown-2026-06-01",
    repo="amelia751/storygen",
    skill_id="google_gemini20_migration",
    entrypoint="lib/gemini.ts",
    binding="MODEL",
    build_command="python3 generate.py",
    test_command="python3 -m unittest test_generate.py",
)

MANIFEST = REPO_ROOT / "agents" / "fixtures" / "change_manifest.gemini20.json"


@pytest.fixture(scope="session")
def exporter():
    """An in-memory exporter on the process's tracer provider.

    Attached to whatever provider is installed rather than insisting on its own:
    OpenTelemetry ignores a second global provider, so a test that demanded one
    would silently record nothing if anything else got there first.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    sink = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(sink))
    return sink


@pytest.fixture(autouse=True)
def _no_memory_bank(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing in this suite reaches a network, including a configured engine."""
    for name in (
        "PATCHAPI_MEMORY_BANK_ENGINE",
        "PATCHAPI_MEMORY_BANK_LOCATION",
        "PATCHAPI_MEMORY_BANK_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fresh_run(tmp_path: Path, repo_root: Path, feed_dir: Path):
    """A factory for independent runs over their own copy of the fixture tree.

    Independent on purpose: a `RunContext` accumulates what its run recorded, so
    two remediations sharing one would have the second read the first's endings.
    """
    opened: list[LocalSession] = []

    def build(name: str) -> RunContext:
        session = LocalSession(root=tmp_path / name, run_id=name)
        opened.append(session)
        shutil.copytree(
            repo_root / "demo" / "storygen",
            session.working_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules", ".next"),
        )
        return RunContext(
            run_id=name,
            repo_root=repo_root,
            feed_dir=feed_dir,
            workspace_root=session.working_dir,
            sandbox=session,
        )

    yield build
    for session in opened:
        session.close()


@pytest.fixture
def context(fresh_run) -> RunContext:
    return fresh_run("run-traced")


@pytest.fixture
def spans(exporter, context):
    """The spans one deterministic remediation produced, keyed by name."""
    exporter.clear()
    orchestrator = Orchestrator(context, ToolTrace(run_id=context.run_id), attempt=2)
    result = asyncio.run(
        orchestrator.run_vertical_slice(
            SLICE, base_sha=BASE_SHA, deterministic=True, static_manifest=MANIFEST
        )
    )
    assert result.reached_testing, result.detail
    return {span.name: span for span in exporter.get_finished_spans()}


def test_every_stage_that_ran_is_in_the_trace(spans):
    for name in (
        SPAN_RUN,
        SPAN_IMPACT,
        SPAN_POLICY,
        SPAN_PATCH,
        SPAN_SANDBOX,
        SPAN_VERIFICATION,
    ):
        assert name in spans, f"{name} did not reach the exporter"


def test_a_stage_span_carries_the_run_identity(spans):
    for name in (SPAN_IMPACT, SPAN_POLICY, SPAN_PATCH, SPAN_VERIFICATION):
        attributes = dict(spans[name].attributes or {})
        assert attributes[ATTR_RUN_ID] == "run-traced"
        assert attributes[ATTR_REPO] == SLICE.repo
        assert attributes[ATTR_CHANGE_ID] == SLICE.change_id
        assert attributes[ATTR_ATTEMPT] == 2
    assert dict(spans[SPAN_IMPACT].attributes)[ATTR_BASE_SHA] == BASE_SHA


def test_the_run_is_one_trace_and_the_stages_hang_from_it(spans):
    """Without a parent, one remediation reaches the backend as seven traces."""
    run = spans[SPAN_RUN]
    assert run.parent is None
    for name in (SPAN_IMPACT, SPAN_POLICY, SPAN_PATCH, SPAN_VERIFICATION):
        stage = spans[name]
        assert stage.context.trace_id == run.context.trace_id
        assert stage.parent is not None
        assert stage.parent.span_id == run.context.span_id
    # The sandbox check runs inside the patch stage, and the trace says so.
    assert spans[SPAN_SANDBOX].parent.span_id == spans[SPAN_PATCH].context.span_id


def test_the_policy_stage_records_the_outcome_that_explains_the_run(spans):
    assert dict(spans[SPAN_POLICY].attributes)[ATTR_POLICY_OUTCOME] == "allow"


def test_no_attribute_uses_a_key_nobody_pinned(spans):
    for name, span in spans.items():
        unpinned = set(dict(span.attributes or {})) - PINNED_ATTRIBUTES
        assert not unpinned, f"{name} carries unpinned attributes {sorted(unpinned)}"


def test_no_attribute_carries_untrusted_text(spans):
    """A trace leaves the trust boundary, so prose must not be able to ride on one.

    Checked two ways: the manifest's own words do not appear anywhere in the
    exported attributes, and no attribute value contains whitespace at all —
    which is what makes the first true for text nobody thought to look for.
    """
    manifest = MANIFEST.read_text(encoding="utf-8")
    words = {word for word in manifest.split() if len(word) > 12}
    assert words, "the fixture should contain long words to look for"

    for name, span in spans.items():
        for key, value in dict(span.attributes or {}).items():
            if isinstance(value, int):
                continue
            assert " " not in str(value), f"{name}.{key} carries prose: {value!r}"
            for word in words:
                assert word not in str(value), f"{name}.{key} leaked {word!r}"


def test_a_run_with_no_model_in_it_does_not_name_one(spans):
    """The deterministic slice is a claim about who decided. The trace keeps it."""
    for name in (SPAN_IMPACT, SPAN_POLICY, SPAN_PATCH, SPAN_VERIFICATION):
        assert ATTR_MODEL_ID not in dict(spans[name].attributes or {})


def test_a_run_with_no_institutional_context_says_so_on_the_span(spans):
    """Not a `ToolTrace` row — no agent acted. The span is where it belongs.

    The distinction the event preserves is between "the Memory Bank said this
    repository has no history" and "there was no Memory Bank", which a silent
    span would collapse.
    """
    events = [event.name for event in spans[SPAN_RUN].events]

    assert EVENT_MEMORY_UNAVAILABLE in events
    assert EVENT_MEMORY_NOT_RECORDED in events


@pytest.mark.asyncio
async def test_a_span_opened_inside_a_stage_nests_under_it(exporter, context):
    """The reason for the stage spans: ADK's own spans attach to what is current.

    ADK is not driven here — a stub standing where `run_turn` is called opens a
    span the way ADK's instrumentation does. What is under test is that the
    stage span survives the `await`, which is what decides whether a model call
    lands under its stage or at the root of the trace.
    """
    from opentelemetry import trace as otel

    from agents.adk import TurnResult

    exporter.clear()
    orchestrator = Orchestrator(context, ToolTrace(run_id=context.run_id))
    orchestrator.seed_static_manifest(MANIFEST)

    async def _turn_that_traces(agent, prompt, **_kwargs):
        await asyncio.sleep(0)
        with otel.get_tracer("gcp.vertex.agent").start_as_current_span("call_llm"):
            await asyncio.sleep(0)
        orchestrator._impact_deterministically(
            context.output("change_manifest"), SLICE, base_sha=BASE_SHA
        )
        return TurnResult(
            agent=agent.name,
            final_text="",
            model_versions=("gemini-3.5-flash",),
            event_count=1,
            trace=orchestrator.trace,
        )

    import agents.orchestrator as module

    original = module.run_turn
    module.run_turn = _turn_that_traces
    try:
        await orchestrator.run_impact(SLICE, base_sha=BASE_SHA, deterministic=False)
    finally:
        module.run_turn = original

    finished = {span.name: span for span in exporter.get_finished_spans()}
    assert finished["call_llm"].parent.span_id == finished[SPAN_IMPACT].context.span_id
    # And the served model, not the requested one, is what the stage reports.
    assert dict(finished[SPAN_IMPACT].attributes)[ATTR_MODEL_ID] == "gemini-3.5-flash"


def test_two_attempts_at_one_run_are_distinguishable(exporter, fresh_run):
    exporter.clear()
    for attempt in (1, 7):
        context = fresh_run(f"run-attempt-{attempt}")
        orchestrator = Orchestrator(context, ToolTrace(run_id=context.run_id), attempt=attempt)
        asyncio.run(
            orchestrator.run_vertical_slice(
                SLICE, base_sha=BASE_SHA, deterministic=True, static_manifest=MANIFEST
            )
        )

    attempts = [
        dict(span.attributes or {})[ATTR_ATTEMPT]
        for span in exporter.get_finished_spans()
        if span.name == SPAN_RUN
    ]
    assert attempts == [1, 7]


def test_a_broken_tracer_does_not_fail_a_run(context, monkeypatch):
    """Tracing is never the reason a remediation does not happen."""

    def _explode(*_args, **_kwargs):
        raise RuntimeError("the tracer provider is on fire")

    monkeypatch.setattr("packages.observability.span", _explode)
    orchestrator = Orchestrator(context, ToolTrace(run_id=context.run_id))
    result = asyncio.run(
        orchestrator.run_vertical_slice(
            SLICE, base_sha=BASE_SHA, deterministic=True, static_manifest=MANIFEST
        )
    )

    assert result.reached_testing, result.detail
    assert orchestrator.state is not RunState.FAILED
