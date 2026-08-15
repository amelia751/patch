"""The fleet constructs, and it constructs with the properties it claims.

These need google-adk installed but no credentials: building an `LlmAgent` does
not call a model. That makes them the cheapest place to catch a topology
regression — a specialist that can transfer to a peer, or one wired to a model
outside the pinned generation.
"""

import pytest

from agents.adk import PREAMBLE, adk_unavailable_reason
from agents.config import (
    DETERMINISTIC_STAGES,
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
        assert agent.model == REASONING_MODEL


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


def test_each_agent_holds_exactly_its_allowlist(fleet):
    for agent_id, agent in fleet.items():
        assert {tool.__name__ for tool in agent.tools} == {
            str(name) for name in tool_allowlist(agent_id)
        }


def test_tool_policy_is_stated_in_the_instruction_not_in_provider_data(fleet):
    for agent in fleet.values():
        assert agent.instruction.startswith(PREAMBLE)
        assert "record_human_required" in agent.instruction


def test_the_prompt_version_is_visible_on_the_agent(fleet):
    for agent_id, agent in fleet.items():
        assert f"prompt v{prompt_version(agent_id)}" in agent.description


def test_decoding_is_deterministic(fleet):
    for agent in fleet.values():
        assert agent.generate_content_config.temperature == 0.0


def test_the_orchestrator_starts_in_received(run_context, trace):
    from agents.orchestrator import Orchestrator
    from packages.schemas.run_state import RunState

    orchestrator = Orchestrator(run_context, trace)
    assert orchestrator.state is RunState.RECEIVED
    assert orchestrator.agent(AgentId.PATCH).name == "patch"
    assert AgentId.PR not in orchestrator.fleet
