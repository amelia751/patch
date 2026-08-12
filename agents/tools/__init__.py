"""Tool construction, and the check that the allowlist describes reality.

`build_tools` is the only way an agent gets tools. It returns exactly the
functions named in that agent's allowlist, so a grant in `agents.config` and a
capability in the running process cannot drift apart: a tool nobody granted is
never constructed, and a grant with no implementation raises here rather than
becoming a function the model can call and never reach.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.config import AgentId, ToolName, tool_allowlist
from agents.context import RunContext
from agents.tools.evidence import build_evidence_tools
from agents.tools.migration_skill import build_migration_skill_tools
from agents.tools.policy_gate import build_policy_tools
from agents.tools.provider_feed import build_provider_feed_tools
from agents.tools.pull_request import build_pull_request_tools
from agents.tools.repo_inventory import build_repo_inventory_tools
from agents.tools.results import ReasonCode, is_refusal, ok, refusal
from agents.tools.shared import build_shared_tools

# Every builder in the package. Each returns plain functions whose names are
# `ToolName` values; `build_tools` selects from the union by allowlist.
_BUILDERS: Final[tuple[Callable[[RunContext], list[Callable[..., Any]]], ...]] = (
    build_provider_feed_tools,
    build_repo_inventory_tools,
    build_policy_tools,
    build_migration_skill_tools,
    build_evidence_tools,
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
    missing = [str(name) for name in granted if str(name) not in index]
    if missing:
        raise UnimplementedToolError(
            f"agent {agent} is granted tools with no implementation: {', '.join(missing)}"
        )
    return [index[str(name)] for name in granted]


def implemented_tool_names(context: RunContext) -> frozenset[str]:
    """Names of every tool this package can build. Used by the coverage test."""
    return frozenset(build_tool_index(context, AgentId.ORCHESTRATOR))


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
