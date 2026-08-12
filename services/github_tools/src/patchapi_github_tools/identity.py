"""Which agent may exercise which capability.

The allowlist in `packages.github` says what the service could ever expose.
This module is the second, narrower gate: what each named caller may ask for.
The two are deliberately separate — widening one does not widen the other.

Grants follow the agent contracts in roadmap §8. In particular the Change
Intelligence Agent handles untrusted provider material and is listed here with
no grants at all, so a request from it is a recorded refusal rather than an
unrecognised caller.
"""

from collections.abc import Mapping
from typing import Final

from packages.github import Capability

CHANGE_INTELLIGENCE: Final[str] = "patchapi.change_intelligence"
IMPACT: Final[str] = "patchapi.impact"
PATCH: Final[str] = "patchapi.patch"
VERIFICATION: Final[str] = "patchapi.verification"
PR: Final[str] = "patchapi.pr"
REPO_INDEXER: Final[str] = "patchapi.repo_indexer"
ORCHESTRATOR: Final[str] = "patchapi.orchestrator"

_READ_ONLY: Final[frozenset[Capability]] = frozenset(
    {
        Capability.GET_REPOSITORY_METADATA,
        Capability.GET_FILE,
        Capability.LIST_TREE,
        Capability.GET_COMMIT,
        Capability.GET_PULL_REQUEST,
        Capability.GET_CHECKS,
    }
)

AGENT_GRANTS: Final[Mapping[str, frozenset[Capability]]] = {
    # Roadmap §8.1: may not access GitHub source code.
    CHANGE_INTELLIGENCE: frozenset(),
    IMPACT: _READ_ONLY,
    REPO_INDEXER: _READ_ONLY,
    # The Patch Agent proposes edits; the sandbox applies them. It never writes
    # to GitHub itself (roadmap §14).
    PATCH: _READ_ONLY,
    VERIFICATION: _READ_ONLY,
    # Roadmap §8.6: the only writer, and only branch / commit / PR / comment.
    PR: _READ_ONLY
    | {
        Capability.CREATE_PATCH_BRANCH,
        Capability.COMMIT_VERIFIED_PATCH,
        Capability.OPEN_PULL_REQUEST,
        Capability.ADD_PR_COMMENT,
    },
    # The orchestrator reads run-relevant state to make routing decisions; it
    # delegates every write to the PR Agent.
    ORCHESTRATOR: _READ_ONLY,
}


def is_known_agent(agent: str) -> bool:
    return agent in AGENT_GRANTS


def granted_capabilities(agent: str) -> frozenset[Capability]:
    """Return the capabilities `agent` holds; empty for an unknown caller."""
    return AGENT_GRANTS.get(agent, frozenset())


def has_grant(agent: str, capability: Capability) -> bool:
    return capability in granted_capabilities(agent)
