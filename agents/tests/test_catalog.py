"""The published catalog is derived from the fleet, not authored alongside it.

These assertions are the reason `agents/catalog.py` exists: if a card could
claim a version or a skill the code does not have, the registry entry would be
marketing. No network — the cards are built from configuration only.
"""

import asyncio
import json
from pathlib import Path

import pytest

from agents.catalog import (
    ADK_TOOL_DESCRIPTIONS,
    AGENT_TITLES,
    PIPELINE_STAGES,
    SEARCH_WEB_DESCRIPTION,
    agent_card,
    agent_description,
    agent_skills,
    catalog_tools,
    fleet_cards,
    mcp_tool_spec,
)
from agents.config import (
    ADK_ATTACHED_TOOLS,
    FLEET_NAME,
    SPECIALISTS,
    AgentId,
    ToolName,
    prompt_version,
    tool_allowlist,
)
from packages.platform.config import (
    A2A_PROTOCOL_VERSION,
    PROTOCOL_BINDING_JSONRPC,
    RegistryConfig,
)

CONFIG = RegistryConfig(project="patch-test", a2a_base_url="https://agents.example.invalid")


def test_every_agent_id_has_a_card():
    cards = fleet_cards(config=CONFIG)

    assert len(cards) == len(AgentId)
    assert {agent for agent, _, _ in cards} == set(AgentId)


@pytest.mark.parametrize("agent", list(AgentId))
def test_card_version_is_the_pinned_prompt_version(agent):
    assert agent_card(agent, config=CONFIG)["version"] == prompt_version(agent)


@pytest.mark.parametrize("agent", list(AgentId))
def test_card_url_is_the_agents_own_a2a_path(agent):
    card = agent_card(agent, config=CONFIG)

    assert card["url"] == f"https://agents.example.invalid/a2a/{agent.value}"
    assert card["preferredTransport"] == PROTOCOL_BINDING_JSONRPC
    assert card["protocolVersion"] == A2A_PROTOCOL_VERSION


@pytest.mark.parametrize("agent", list(SPECIALISTS))
def test_a_reasoning_agents_skills_are_exactly_its_tool_grant(agent):
    ids = {skill["id"] for skill in agent_skills(agent)}

    assert ids == {str(tool) for tool in tool_allowlist(agent)}


def test_revoking_a_grant_would_remove_the_skill():
    patch_ids = {skill["id"] for skill in agent_skills(AgentId.PATCH)}
    verification_ids = {skill["id"] for skill in agent_skills(AgentId.VERIFICATION)}

    # The two halves of constraint 6: the author holds the sandbox edit tools,
    # the grader holds the evidence tools, and neither holds the other's.
    assert str(ToolName.APPLY_PATCH) in patch_ids
    assert str(ToolName.APPLY_PATCH) not in verification_ids
    assert str(ToolName.RECORD_VERIFICATION_REPORT) in verification_ids
    assert str(ToolName.RECORD_VERIFICATION_REPORT) not in patch_ids


def test_no_card_advertises_a_pull_request_tool_it_cannot_call():
    for agent in AgentId:
        if agent is AgentId.PR:
            continue
        ids = {skill["id"] for skill in agent_skills(agent)}
        assert str(ToolName.OPEN_PULL_REQUEST) not in ids


def test_the_deterministic_stages_publish_their_stage_helpers():
    policy_ids = {skill["id"] for skill in agent_skills(AgentId.POLICY)}
    pr_ids = {skill["id"] for skill in agent_skills(AgentId.PR)}

    assert str(ToolName.EVALUATE_POLICY) in policy_ids
    assert str(ToolName.RECORD_POLICY_DECISION) in policy_ids
    assert str(ToolName.OPEN_PULL_REQUEST) in pr_ids
    assert str(ToolName.RENDER_PULL_REQUEST_BODY) in pr_ids


def test_the_orchestrator_publishes_the_pipeline_it_sequences():
    ids = [skill["id"] for skill in agent_skills(AgentId.ORCHESTRATOR)]

    assert ids[: len(PIPELINE_STAGES)] == [f"stage_{stage.value}" for stage in PIPELINE_STAGES]
    assert AgentId.ORCHESTRATOR not in PIPELINE_STAGES


@pytest.mark.parametrize("agent", list(AgentId))
def test_every_skill_carries_a_description_and_the_fleet_tag(agent):
    for skill in agent_skills(agent):
        assert skill["description"].strip()
        assert FLEET_NAME in skill["tags"]
        assert str(agent) in skill["tags"]


def test_a_tool_skill_description_is_the_docstring_the_model_is_shown():
    (skill,) = [
        skill for skill in agent_skills(AgentId.PATCH) if skill["id"] == str(ToolName.APPLY_PATCH)
    ]

    from agents.context import RunContext
    from agents.tools import build_tool_index

    index = build_tool_index(
        RunContext(run_id="t", repo_root=Path("."), feed_dir=Path(".")), AgentId.PATCH
    )
    docstring = index[str(ToolName.APPLY_PATCH)].__doc__ or ""

    assert skill["description"] == " ".join(docstring.split("\n\n")[0].split())


def test_every_adk_attached_tool_keeps_its_pinned_description():
    """These are built by ADK, so there is no docstring for the catalog to read."""
    published = {skill["id"]: skill["description"] for skill in agent_skills(AgentId.PATCH)}

    for tool in ADK_ATTACHED_TOOLS & tool_allowlist(AgentId.PATCH):
        assert published[str(tool)] == ADK_TOOL_DESCRIPTIONS[tool]
    assert published[str(ToolName.SEARCH_WEB)] == SEARCH_WEB_DESCRIPTION


def test_the_pinned_skill_tool_descriptions_still_match_adk():
    """The catalog pins ADK's prose. An ADK upgrade that reworded it is drift."""
    pytest.importorskip("google.adk")
    from agents.adk import build_skill_toolset, repo_root
    from agents.config import SKILL_TOOLS

    toolset = build_skill_toolset(repo_root() / "skills")
    live = {tool.name: tool.description for tool in asyncio.run(toolset.get_tools(None))}

    for tool in SKILL_TOOLS:
        assert live[str(tool)] == ADK_TOOL_DESCRIPTIONS[tool]


@pytest.mark.parametrize("agent", list(AgentId))
def test_descriptions_are_single_line_prose(agent):
    description = agent_description(agent)

    assert description.strip()
    assert "\n" not in description


@pytest.mark.parametrize("agent", list(AgentId))
def test_titles_are_pinned_for_every_agent(agent):
    assert AGENT_TITLES[agent].startswith("PatchAPI")
    assert agent_card(agent, config=CONFIG)["name"] == AGENT_TITLES[agent]


def test_cards_never_claim_streaming_the_runtime_does_not_have():
    for agent in AgentId:
        capabilities = agent_card(agent, config=CONFIG)["capabilities"]
        assert capabilities == {"streaming": False, "pushNotifications": False}


def test_catalog_tools_are_sorted_and_unique():
    for agent in AgentId:
        tools = catalog_tools(agent)
        assert list(tools) == sorted(set(tools))


def test_the_mcp_tool_spec_covers_every_implemented_tool():
    names = {tool["name"] for tool in mcp_tool_spec()}

    assert names == {str(tool) for tool in ToolName}
    assert all(tool["description"].strip() for tool in mcp_tool_spec())


def test_a_card_stays_within_the_registry_ten_kilobyte_spec_limit():
    for agent in AgentId:
        payload = json.dumps(agent_card(agent, config=CONFIG))
        assert len(payload.encode("utf-8")) < 10_240, agent
