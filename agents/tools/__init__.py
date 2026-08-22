"""Tool construction, and the check that the allowlist describes reality.

`build_tools` is the only way an LlmAgent gets tools. It returns exactly the
functions named in that agent's allowlist. Policy and PR helpers are built
into the index so the orchestrator can call them as Python; they are not
granted to any LlmAgent.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.config import ADK_ATTACHED_TOOLS, AgentId, ToolName, tool_allowlist
from agents.context import RunContext
from agents.tools.change import build_provider_feed_tools
from agents.tools.impact import build_repo_inventory_tools
from agents.tools.index_lookup import build_index_lookup_tools
from agents.tools.patch import (
    build_computer_use_tools,
    build_migration_skill_tools,
    build_workspace_tools,
)
from agents.tools.policy import build_policy_tools
from agents.tools.pr import build_pull_request_tools
from agents.tools.results import ReasonCode, is_refusal, ok, refusal
from agents.tools.shared import build_shared_tools
from agents.tools.verification import build_evidence_tools

# Agent toolboxes first, then the two Python-stage helpers the orchestrator
# calls. A grant that is not in this union raises rather than becoming a
# function the model can name and never reach.
_BUILDERS: Final[tuple[Callable[[RunContext], list[Callable[..., Any]]], ...]] = (
    build_provider_feed_tools,
    build_index_lookup_tools,
    build_repo_inventory_tools,
    build_migration_skill_tools,
    build_workspace_tools,
    build_computer_use_tools,
    build_evidence_tools,
    build_policy_tools,
    build_pull_request_tools,
)


class UnimplementedToolError(RuntimeError):
    """An agent was granted a tool no builder produces."""


def build_tool_index(context: RunContext, agent: AgentId) -> dict[str, Callable[..., Any]]:
    """Every tool function this process can build, keyed by name."""
    index: dict[str, Callable[..., Any]] = {}
    for builder in _BUILDERS:
        for function in builder(context):
            index[function.__name__] = function
    for function in build_shared_tools(context, agent):
        index[function.__name__] = function
    return index


def build_tools(context: RunContext, agent: AgentId) -> list[Callable[..., Any]]:
    """Return the tool functions `agent` is permitted to call, in a stable order."""
    index = build_tool_index(context, agent)
    granted = sorted(tool_allowlist(agent))
    missing = [
        str(name) for name in granted if str(name) not in index and name not in ADK_ATTACHED_TOOLS
    ]
    if missing:
        raise UnimplementedToolError(
            f"agent {agent} is granted tools with no implementation: {', '.join(missing)}"
        )
    return [index[str(name)] for name in granted if name not in ADK_ATTACHED_TOOLS]


def implemented_tool_names(context: RunContext) -> frozenset[str]:
    """Names of every tool this package can build. Used by the coverage test."""
    return frozenset(build_tool_index(context, AgentId.ORCHESTRATOR)) | {
        str(name) for name in ADK_ATTACHED_TOOLS
    }


__all__ = [
    "ReasonCode",
    "ToolName",
    "UnimplementedToolError",
    "build_tool_index",
    "build_tools",
    "implemented_tool_names",
    "is_refusal",
    "ok",
    "refusal",
]
