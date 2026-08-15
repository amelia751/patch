"""The tool boundary refuses what it should and records everything."""

import json
from dataclasses import dataclass

from agents.config import AgentId, ToolName, tool_allowlist
from agents.guardrails import build_tool_guardrails
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
