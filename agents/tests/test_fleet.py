"""The fleet constructs, and it constructs with the properties it claims.

These need google-adk installed but no credentials: building an `LlmAgent` does
not call a model. That makes them the cheapest place to catch a topology
regression — a specialist that can transfer to a peer, or one wired to a model
outside the pinned generation.
"""

import asyncio

import pytest

from agents.adk import PREAMBLE, adk_unavailable_reason
from agents.config import (
    DETERMINISTIC_STAGES,
    MODEL_RETRY_ATTEMPTS,
    MODEL_TEMPERATURE,
    REASONING_MODEL,
    SPECIALISTS,
    AgentId,
    prompt_version,
    tool_allowlist,
)

pytestmark = pytest.mark.skipif(
    adk_unavailable_reason() is not None,
    reason=adk_unavailable_reason() or "",
)


@pytest.fixture
def fleet(run_context, trace):
    from agents.orchestrator import build_fleet

    return build_fleet(run_context, trace)


def test_the_four_reasoning_agents_construct(fleet):
    assert set(fleet) == set(SPECIALISTS)
    assert AgentId.POLICY not in fleet
    assert AgentId.PR not in fleet


def test_policy_and_pr_are_stage_names_not_llm_agents():
    assert DETERMINISTIC_STAGES == (AgentId.POLICY, AgentId.PR)
    assert set(DETERMINISTIC_STAGES).isdisjoint(SPECIALISTS)


def test_every_agent_runs_the_pinned_model(fleet):
    for agent in fleet.values():
        assert agent.model.model == REASONING_MODEL


def test_every_agent_rides_out_a_busy_region(fleet):
    """A 503 from one overloaded call must not end a run mid-migration.

    ADK's default is no retry at all, and two hosted runs died on a transient
    503 after staging a sandbox and reading the repository.
    """
    for agent in fleet.values():
        retry = agent.model.retry_options

        assert retry is not None
        assert retry.attempts == MODEL_RETRY_ATTEMPTS
        assert 503 in (retry.http_status_codes or [])
        # A 400 or a 403 is a request no amount of waiting fixes.
        assert not {code for code in retry.http_status_codes or [] if code < 429}


def test_no_specialist_can_hand_work_to_another(fleet):
    """Roadmap §9: the sequence is a state machine, not a model's choice."""
    for agent in fleet.values():
        assert agent.disallow_transfer_to_parent is True
        assert agent.disallow_transfer_to_peers is True
        assert not agent.sub_agents


def test_every_tool_call_passes_through_the_guardrails(fleet):
    for agent in fleet.values():
        assert agent.before_tool_callback
        assert agent.after_tool_callback


def _tool_names(agent) -> set[str]:
    """Every tool the model is offered, with toolsets expanded.

    ADK lets an agent hold a `BaseToolset` alongside plain functions, and the
    skill toolset is one. Reading only the top level would let a toolset smuggle
    in a tool the allowlist never granted.
    """
    from google.adk.tools.base_toolset import BaseToolset

    names: set[str] = set()
    for tool in agent.tools:
        if isinstance(tool, BaseToolset):
            names.update(item.name for item in asyncio.run(tool.get_tools(None)))
        else:
            names.add(getattr(tool, "__name__", None) or tool.name)
    return names


def test_each_agent_holds_exactly_its_allowlist(fleet):
    for agent_id, agent in fleet.items():
        assert _tool_names(agent) == {str(name) for name in tool_allowlist(agent_id)}


def test_request_runtime_credentials_is_a_long_running_tool(fleet):
    """ADK pauses the runner when the model asks the operator for a secret."""
    from agents.config import ToolName

    for agent_id in (AgentId.PATCH, AgentId.VERIFICATION):
        tool = next(
            item
            for item in fleet[agent_id].tools
            if (getattr(item, "__name__", None) or item.name)
            == str(ToolName.REQUEST_RUNTIME_CREDENTIALS)
        )
        assert getattr(tool, "is_long_running", False) is True
    change_names = {
        getattr(item, "__name__", None) or item.name
        for item in fleet[AgentId.CHANGE_INTELLIGENCE].tools
    }
    assert str(ToolName.REQUEST_RUNTIME_CREDENTIALS) not in change_names


def test_tool_policy_is_stated_in_the_instruction_not_in_provider_data(fleet):
    for agent in fleet.values():
        assert agent.instruction.startswith(PREAMBLE)
        assert "record_human_required" in agent.instruction


def test_no_prompt_names_a_provider_secret(fleet):
    """Roadmap §12.2: which env var a migration needs is skill knowledge.

    Naming them here means onboarding Stripe edits an agent instead of adding a
    skill, and it lets a prompt disagree with the skill about what proof needs.
    """
    for agent_id, agent in fleet.items():
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"):
            assert name not in agent.instruction, f"{agent_id} hardcodes {name}"


def test_the_patch_prompt_ends_on_its_constraints(fleet):
    """Gemini 3 drops negative constraints that appear too early in a long prompt.

    Google's prompting guidance for this generation is to end-load them, so the
    honesty rules live after the steps rather than inside step 3 where the last
    run's skipped live check went unreported.
    """
    instruction = fleet[AgentId.PATCH].instruction
    assert instruction.index("## Constraints") > instruction.index("## Steps")
    tail = instruction[instruction.index("## Constraints") :]
    assert "Never report a check you did not run" in tail


def test_a_web_search_does_not_end_the_turn_that_asked_for_it():
    """ADK treats a `skip_summarization` response as the agent's final response.

    With it on, the corroboration never reached the model that asked and the
    caller's remaining obligation went unrecorded: the Verification agent
    searched, its turn ended there, and no VerificationReport was ever written.
    """
    from google.adk.events.event import Event
    from google.adk.events.event_actions import EventActions

    from agents.adk import _search_web_tool

    assert _search_web_tool().skip_summarization is False
    # Why it has to stay false, asserted against ADK rather than described.
    ended = Event(author="patch", actions=EventActions(skip_summarization=True))
    assert ended.is_final_response()


def test_the_prompt_version_is_visible_on_the_agent(fleet):
    for agent_id, agent in fleet.items():
        assert f"prompt v{prompt_version(agent_id)}" in agent.description


def test_every_agent_decodes_at_the_pinned_temperature(fleet):
    for agent in fleet.values():
        assert agent.generate_content_config.temperature == MODEL_TEMPERATURE


def test_the_orchestrator_starts_in_received(run_context, trace):
    from agents.orchestrator import Orchestrator
    from packages.schemas.run_state import RunState

    orchestrator = Orchestrator(run_context, trace)
    assert orchestrator.state is RunState.RECEIVED
    assert orchestrator.agent(AgentId.PATCH).name == "patch"
    assert AgentId.PR not in orchestrator.fleet
