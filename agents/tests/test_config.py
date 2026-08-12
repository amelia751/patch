"""The topology declared in config is the topology that exists."""

import pytest

from agents.config import (
    MAX_TOOL_CALLS_PER_TURN,
    MODEL_TEMPERATURE,
    REASONING_MODEL,
    SHARED_TOOLS,
    SPECIALISTS,
    TOOL_ALLOWLISTS,
    AgentId,
    ToolName,
    prompt_version,
    tool_allowlist,
)
from agents.tools import build_tools, implemented_tool_names
from packages.providers.google.config import (
    MINIMUM_REASONING_GENERATION,
    parse_gemini_generation,
    require_supported_reasoning_model,
)


def test_reasoning_model_meets_the_pinned_generation():
    assert require_supported_reasoning_model(REASONING_MODEL) == REASONING_MODEL
    assert parse_gemini_generation(REASONING_MODEL) >= MINIMUM_REASONING_GENERATION


def test_decoding_is_deterministic():
    assert MODEL_TEMPERATURE == 0.0
    assert MAX_TOOL_CALLS_PER_TURN > 0


def test_every_agent_has_an_allowlist_and_a_prompt_version():
    for agent in AgentId:
        assert agent in TOOL_ALLOWLISTS
        assert prompt_version(agent)


def test_the_six_specialists_are_the_roadmap_six():
    assert set(SPECIALISTS) == set(AgentId) - {AgentId.ORCHESTRATOR}
    assert len(SPECIALISTS) == 6


def test_every_agent_can_stop_for_a_human():
    for agent in AgentId:
        assert ToolName.RECORD_HUMAN_REQUIRED in tool_allowlist(agent)
    assert SHARED_TOOLS == frozenset({ToolName.RECORD_HUMAN_REQUIRED})


@pytest.mark.parametrize(
    ("agent", "forbidden"),
    [
        # Roadmap §8.1: Change Intelligence may not reach repository source.
        (AgentId.CHANGE_INTELLIGENCE, ToolName.SCAN_REPOSITORY),
        # Roadmap §8.4: the Patch agent cannot open a pull request...
        (AgentId.PATCH, ToolName.OPEN_PULL_REQUEST),
        # ...nor grade its own work.
        (AgentId.PATCH, ToolName.RECORD_VERIFICATION_REPORT),
        # Roadmap §8.6: the PR agent cannot edit code or re-decide policy.
        (AgentId.PR, ToolName.RECORD_PATCH_PLAN),
        (AgentId.PR, ToolName.RECORD_POLICY_DECISION),
        # Roadmap §8.5: verification does not author patches.
        (AgentId.VERIFICATION, ToolName.RECORD_PATCH_PLAN),
        # The orchestrator is code, not a supervisor agent with capabilities.
        (AgentId.ORCHESTRATOR, ToolName.OPEN_PULL_REQUEST),
    ],
)
def test_separation_of_duties(agent, forbidden):
    assert forbidden not in tool_allowlist(agent)


def test_every_granted_tool_is_implemented(run_context):
    implemented = implemented_tool_names(run_context)
    for agent in AgentId:
        granted = {str(name) for name in tool_allowlist(agent)}
        assert granted <= implemented, f"{agent} is granted an unimplemented tool"


def test_every_implemented_tool_is_named_in_the_enum(run_context):
    assert implemented_tool_names(run_context) == {str(name) for name in ToolName}


def test_build_tools_returns_exactly_the_allowlist(run_context):
    for agent in AgentId:
        names = {function.__name__ for function in build_tools(run_context, agent)}
        assert names == {str(tool) for tool in tool_allowlist(agent)}


def test_tool_functions_are_documented(run_context):
    """ADK derives the model-visible tool description from the docstring."""
    for function in build_tools(run_context, AgentId.CHANGE_INTELLIGENCE):
        assert function.__doc__ and function.__doc__.strip()
