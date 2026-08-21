"""The topology declared in config is the topology that exists."""

import pytest

from agents.config import (
    ADK_ATTACHED_TOOLS,
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


def test_the_four_specialists_are_the_roadmap_reasoning_agents():
    from agents.config import DETERMINISTIC_STAGES

    assert set(SPECIALISTS) == {
        AgentId.CHANGE_INTELLIGENCE,
        AgentId.IMPACT,
        AgentId.PATCH,
        AgentId.VERIFICATION,
    }
    assert set(DETERMINISTIC_STAGES) == {AgentId.POLICY, AgentId.PR}
    assert set(SPECIALISTS) | set(DETERMINISTIC_STAGES) | {AgentId.ORCHESTRATOR} == set(AgentId)


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
        # ...nor scan the repo as Impact; it works from the ImpactReport.
        (AgentId.PATCH, ToolName.SCAN_REPOSITORY),
        # Roadmap §8.6: the PR agent cannot edit code or re-decide policy.
        (AgentId.PR, ToolName.RECORD_PATCH_PLAN),
        (AgentId.PR, ToolName.APPLY_PATCH),
        (AgentId.PR, ToolName.RUN_COMMAND),
        (AgentId.PR, ToolName.COMPUTER_USE_STEP),
        (AgentId.PR, ToolName.RECORD_POLICY_DECISION),
        # Roadmap §8.5: verification does not author patches.
        (AgentId.VERIFICATION, ToolName.RECORD_PATCH_PLAN),
        (AgentId.VERIFICATION, ToolName.APPLY_PATCH),
        (AgentId.VERIFICATION, ToolName.RUN_COMMAND),
        (AgentId.VERIFICATION, ToolName.COMPUTER_USE_STEP),
        # Roadmap §8.1: Change Intelligence may not reach the workspace.
        (AgentId.CHANGE_INTELLIGENCE, ToolName.READ_FILE),
        (AgentId.CHANGE_INTELLIGENCE, ToolName.RUN_COMMAND),
        (AgentId.PATCH, ToolName.SEARCH_PROVIDER_WEB),
        (AgentId.VERIFICATION, ToolName.SEARCH_PROVIDER_WEB),
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
        expected = {str(tool) for tool in tool_allowlist(agent) if tool not in ADK_ATTACHED_TOOLS}
        assert names == expected


def test_tool_functions_are_documented(run_context):
    """ADK derives the model-visible tool description from the docstring."""
    for function in build_tools(run_context, AgentId.CHANGE_INTELLIGENCE):
        assert function.__doc__ and function.__doc__.strip()


def test_change_intelligence_holds_the_search_child_grant():
    assert ToolName.SEARCH_PROVIDER_WEB in tool_allowlist(AgentId.CHANGE_INTELLIGENCE)
    assert ToolName.SEARCH_PROVIDER_WEB in ADK_ATTACHED_TOOLS


def test_the_patch_agent_holds_the_debug_loop():
    granted = tool_allowlist(AgentId.PATCH)
    for name in (
        ToolName.READ_FILE,
        ToolName.LIST_DIR,
        ToolName.APPLY_PATCH,
        ToolName.RUN_COMMAND,
        ToolName.LOAD_MIGRATION_SKILL,
        ToolName.RECORD_PATCH_PLAN,
    ):
        assert name in granted
