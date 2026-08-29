"""The tool boundary refuses what it should and records everything."""

import json
from dataclasses import dataclass

from agents.config import AgentId, ToolName, tool_allowlist
from agents.guardrails import build_tool_guardrails
from agents.tools.results import is_refusal
from agents.trace import ToolStatus, ToolTrace, digest


@dataclass
class FakeTool:
    """Stands in for an ADK `BaseTool`; the callbacks only read `.name`."""

    name: str


def test_a_granted_tool_is_allowed_through(trace):
    before, _ = build_tool_guardrails(AgentId.CHANGE_INTELLIGENCE, trace)
    assert (
        before(tool=FakeTool(str(ToolName.LOAD_PROVIDER_NOTICE)), args={"change_id": "x"}) is None
    )
    assert len(trace) == 0


def test_a_tool_outside_the_allowlist_is_refused_without_running(trace):
    before, _ = build_tool_guardrails(AgentId.PATCH, trace)
    result = before(tool=FakeTool(str(ToolName.OPEN_PULL_REQUEST)), args={"title": "t"})

    assert result is not None
    assert result["status"] == "refused"
    assert result["reason_code"] == "policy_denied"
    assert len(trace.denied) == 1
    assert trace.denied[0].tool == str(ToolName.OPEN_PULL_REQUEST)


def test_a_denial_names_only_the_tools_the_agent_actually_has(trace):
    before, _ = build_tool_guardrails(AgentId.PATCH, trace)
    result = before(tool=FakeTool(str(ToolName.SCAN_REPOSITORY)), args={})

    assert set(result["permitted_tools"]) == {str(name) for name in tool_allowlist(AgentId.PATCH)}
    assert str(ToolName.SCAN_REPOSITORY) not in result["permitted_tools"]


def test_an_unknown_tool_is_refused(trace):
    before, _ = build_tool_guardrails(AgentId.IMPACT, trace)
    assert before(tool=FakeTool("exfiltrate_secrets"), args={})["status"] == "refused"


def test_the_tool_call_budget_stops_a_looping_turn(trace):
    before, after = build_tool_guardrails(AgentId.IMPACT, trace, max_calls=2)
    tool = FakeTool(str(ToolName.CLASSIFY_REPOSITORY_PATH))

    for index in range(2):
        args = {"path": f"src/{index}.ts"}
        assert before(tool=tool, args=args) is None
        after(tool=tool, args=args, tool_response={"status": "ok"})

    stopped = before(tool=tool, args={"path": "src/3.ts"})
    assert stopped["status"] == "refused"
    assert "budget" in stopped["message"]


def test_an_exhausted_turn_can_still_record_an_ending(trace):
    """The budget bounds work, not endings.

    The refusal above tells the agent to record HUMAN_REQUIRED. While that call
    was refused too, a Patch turn that spent its budget on a failed diff had no
    way to say so: it parked the run on a credential it already had, because
    asking was the only call left that did anything.
    """
    before, after = build_tool_guardrails(AgentId.IMPACT, trace, max_calls=1)
    work = FakeTool(str(ToolName.CLASSIFY_REPOSITORY_PATH))
    args = {"path": "src/0.ts"}
    assert before(tool=work, args=args) is None
    after(tool=work, args=args, tool_response={"status": "ok"})

    stopped = before(tool=work, args={"path": "src/1.ts"})
    assert stopped["status"] == "refused"
    # `agents.adk._drive` reads this shape to tell a refused long-running call
    # from a real operator hold. A refusal that stopped looking like one would
    # park the run again, silently.
    assert is_refusal(stopped)
    for ending in (ToolName.RECORD_HUMAN_REQUIRED, ToolName.RECORD_IMPACT_REPORT):
        assert before(tool=FakeTool(str(ending)), args={"reason": "stuck"}) is None


def test_repeating_a_search_that_already_answered_is_refused(trace):
    """A search whose arguments have not changed cannot return anything new.

    One Patch turn issued the same query twelve times at roughly 25s each.
    Two are allowed so a transient failure can be retried.
    """
    before, _ = build_tool_guardrails(AgentId.CHANGE_INTELLIGENCE, trace, max_identical=2)
    tool = FakeTool(str(ToolName.SEARCH_WEB))
    args = {"request": "gemini-3.1-flash-image"}

    assert before(tool=tool, args=dict(args)) is None
    assert before(tool=tool, args=dict(args)) is None
    looping = before(tool=tool, args=dict(args))
    assert looping["status"] == "refused"
    assert "will not change" in looping["message"]
    # A different question is still a different question.
    assert before(tool=tool, args={"request": "imagen-4.0-generate-001"}) is None


def test_rerunning_a_command_after_an_edit_is_not_a_loop(trace):
    """The Patch loop is edit, re-run, compare. Identical args are the point."""
    before, _ = build_tool_guardrails(AgentId.PATCH, trace, max_identical=2)
    tool = FakeTool(str(ToolName.RUN_COMMAND))
    for _ in range(5):
        assert before(tool=tool, args={"command": "python3 generate.py"}) is None


def test_a_completed_call_is_traced_with_a_result_digest(trace):
    before, after = build_tool_guardrails(AgentId.IMPACT, trace)
    tool = FakeTool(str(ToolName.CLASSIFY_REPOSITORY_PATH))
    args = {"path": "docs/README.md"}
    response = {"status": "ok", "usage_kind": "documentation_example"}

    before(tool=tool, args=args)
    after(tool=tool, args=args, tool_response=response)

    assert len(trace) == 1
    event = trace.events[0]
    assert event.agent is AgentId.IMPACT
    assert event.status is ToolStatus.OK
    assert event.result_digest == digest(response)
    assert event.argument_digest == digest(args)
    assert event.duration_ms >= 0.0


def test_a_tool_refusal_is_traced_as_a_refusal(trace):
    before, after = build_tool_guardrails(AgentId.CHANGE_INTELLIGENCE, trace)
    tool = FakeTool(str(ToolName.LOAD_PROVIDER_NOTICE))
    args = {"change_id": "nope"}
    response = {"status": "refused", "reason_code": "not_found", "message": "no such notice"}

    before(tool=tool, args=args)
    after(tool=tool, args=args, tool_response=response)

    assert trace.events[0].status is ToolStatus.REFUSED
    assert trace.events[0].detail == "no such notice"


def test_the_trace_serializes_to_ndjson(trace):
    before, after = build_tool_guardrails(AgentId.IMPACT, trace)
    tool = FakeTool(str(ToolName.CLASSIFY_REPOSITORY_PATH))
    before(tool=tool, args={"path": "a.ts"})
    after(tool=tool, args={"path": "a.ts"}, tool_response={"status": "ok"})

    lines = trace.to_ndjson().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["tool"] == "classify_repository_path"
    assert record["agent"] == "impact"
    assert record["status"] == "ok"
    assert record["fleet_version"]


def test_an_applied_patch_keeps_the_diff_for_the_console(trace):
    """The Edit card is drawn from this detail on the next flush, not the final artifact."""
    before, after = build_tool_guardrails(AgentId.PATCH, trace)
    tool = FakeTool(str(ToolName.APPLY_PATCH))
    diff = "--- a/lib/gemini.ts\n+++ b/lib/gemini.ts\n@@ -1 +1 @@\n-old\n+new\n"
    args = {"diff": diff}

    before(tool=tool, args=args)
    after(tool=tool, args=args, tool_response={"applied": True, "files": ["lib/gemini.ts"]})

    assert trace.events[0].detail == diff
    assert "applied" in trace.events[0].result_summary


def test_bulky_arguments_are_digested_not_copied_into_the_trace():
    trace = ToolTrace(run_id="run-digest")
    before, after = build_tool_guardrails(AgentId.CHANGE_INTELLIGENCE, trace)
    tool = FakeTool(str(ToolName.RECORD_CHANGE_MANIFEST))
    secretish = "x" * 5000
    args = {"change_id": "c", "rationale": secretish}

    before(tool=tool, args=args)
    after(tool=tool, args=args, tool_response={"status": "ok"})

    rendered = trace.events[0].to_record()["arguments"]["rationale"]
    assert secretish not in rendered
    assert "5000 chars" in rendered
