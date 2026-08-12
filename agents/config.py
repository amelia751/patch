"""Pinned agent identities, model IDs, prompt versions and tool allowlists.

Roadmap §8 gives each agent one job. This module is where that separation is
declared as data rather than left to prose in a prompt: an agent's allowlist is
the set of tool names it may call, and `agents.guardrails` refuses everything
else before the tool function is entered. Patch cannot open a pull request
because `PATCH` does not name a pull-request tool, not because its instruction
asks it not to.

Nothing here is inlined at a call site. A model ID, a prompt version or a tool
grant changes by editing this file.
"""

from enum import StrEnum
from types import MappingProxyType
from typing import Final

from packages.providers.google.config import (
    DEFAULT_REASONING_MODEL,
    require_supported_reasoning_model,
)

# Bumped when the agent topology, a tool contract or an instruction changes in a
# way a stored trace should be readable against. Recorded on every trace event.
FLEET_VERSION: Final[str] = "1.0.0"

# Agent Registry (roadmap §12.1) discovers the fleet under this name.
FLEET_NAME: Final[str] = "patchapi-fleet"


class AgentId(StrEnum):
    """The orchestrator plus the six specialists of roadmap §8."""

    ORCHESTRATOR = "orchestrator"
    CHANGE_INTELLIGENCE = "change_intelligence"
    IMPACT = "impact"
    POLICY = "policy"
    PATCH = "patch"
    VERIFICATION = "verification"
    PR = "pr"


SPECIALISTS: Final[tuple[AgentId, ...]] = (
    AgentId.CHANGE_INTELLIGENCE,
    AgentId.IMPACT,
    AgentId.POLICY,
    AgentId.PATCH,
    AgentId.VERIFICATION,
    AgentId.PR,
)


class ToolName(StrEnum):
    """Every tool the fleet exposes.

    A tool absent from this enum cannot be granted, and `agents.tools` asserts
    that the functions it registers and this enum are the same set.
    """

    # Change Intelligence — provider feed, read-only, no repository access.
    LIST_PROVIDER_NOTICES = "list_provider_notices"
    LOAD_PROVIDER_NOTICE = "load_provider_notice"
    NORMALIZE_PROVIDER_NOTICE = "normalize_provider_notice"
    RECORD_CHANGE_MANIFEST = "record_change_manifest"

    # Impact — deterministic repository inventory, no provider fetch, no writes.
    SCAN_REPOSITORY = "scan_repository"
    CLASSIFY_REPOSITORY_PATH = "classify_repository_path"
    RECORD_IMPACT_REPORT = "record_impact_report"

    # Policy & Risk — deterministic gates.
    EVALUATE_POLICY = "evaluate_policy"
    LIST_FORBIDDEN_GLOBS = "list_forbidden_globs"
    RECORD_POLICY_DECISION = "record_policy_decision"

    # Patch — migration skill and a plan. No sandbox control, no GitHub.
    LOAD_MIGRATION_SKILL = "load_migration_skill"
    RECORD_PATCH_PLAN = "record_patch_plan"

    # Verification — sandbox evidence, read-only, independent of Patch.
    LIST_VERIFICATION_EVIDENCE = "list_verification_evidence"
    READ_VERIFICATION_EVIDENCE = "read_verification_evidence"
    RECORD_VERIFICATION_REPORT = "record_verification_report"

    # PR — render and request. Creation goes through the GitHub tool service.
    RENDER_PULL_REQUEST_BODY = "render_pull_request_body"
    OPEN_PULL_REQUEST = "open_pull_request"

    # Available to every agent: the fail-closed exit.
    RECORD_HUMAN_REQUIRED = "record_human_required"


# Granted to all seven agents. Roadmap §8 and CLAUDE.md constraint 10: an agent
# that cannot answer says so in structured form, and that path is always open.
SHARED_TOOLS: Final[frozenset[ToolName]] = frozenset({ToolName.RECORD_HUMAN_REQUIRED})

# Agent -> the tools it may call, beyond `SHARED_TOOLS`. The orchestrator holds
# none: it sequences specialists deterministically (roadmap §9) and is not an
# LLM that decides who does what.
_GRANTS: Final[dict[AgentId, frozenset[ToolName]]] = {
    AgentId.ORCHESTRATOR: frozenset(),
    AgentId.CHANGE_INTELLIGENCE: frozenset(
        {
            ToolName.LIST_PROVIDER_NOTICES,
            ToolName.LOAD_PROVIDER_NOTICE,
            ToolName.NORMALIZE_PROVIDER_NOTICE,
            ToolName.RECORD_CHANGE_MANIFEST,
        }
    ),
    AgentId.IMPACT: frozenset(
        {
            ToolName.SCAN_REPOSITORY,
            ToolName.CLASSIFY_REPOSITORY_PATH,
            ToolName.RECORD_IMPACT_REPORT,
        }
    ),
    AgentId.POLICY: frozenset(
        {
            ToolName.EVALUATE_POLICY,
            ToolName.LIST_FORBIDDEN_GLOBS,
            ToolName.RECORD_POLICY_DECISION,
        }
    ),
    AgentId.PATCH: frozenset(
        {
            ToolName.LOAD_MIGRATION_SKILL,
            ToolName.RECORD_PATCH_PLAN,
        }
    ),
    AgentId.VERIFICATION: frozenset(
        {
            ToolName.LIST_VERIFICATION_EVIDENCE,
            ToolName.READ_VERIFICATION_EVIDENCE,
            ToolName.RECORD_VERIFICATION_REPORT,
        }
    ),
    AgentId.PR: frozenset(
        {
            ToolName.RENDER_PULL_REQUEST_BODY,
            ToolName.OPEN_PULL_REQUEST,
        }
    ),
}

TOOL_ALLOWLISTS: Final[MappingProxyType[AgentId, frozenset[ToolName]]] = MappingProxyType(
    {agent: grants | SHARED_TOOLS for agent, grants in _GRANTS.items()}
)

# Instruction version per agent, recorded on trace events so a stored run can be
# replayed against the prompt that produced it. Bumping a prompt bumps this.
PROMPT_VERSIONS: Final[MappingProxyType[AgentId, str]] = MappingProxyType(
    dict.fromkeys(AgentId, "1.0.0")
)

# Reasoning model for every agent. One pin, inherited from the provider adapter
# so PatchAPI cannot drift from the generation the rules require.
REASONING_MODEL: Final[str] = require_supported_reasoning_model(DEFAULT_REASONING_MODEL)

# Deterministic decoding. These agents confirm and record structured facts; a
# sampled answer would make an audit trail irreproducible.
MODEL_TEMPERATURE: Final[float] = 0.0

# Gemini 3.x spends output tokens on thinking before it emits text or a function
# call, so a small cap yields an empty turn rather than a short one.
MAX_OUTPUT_TOKENS: Final[int] = 2048

# A turn that has not converged by here is stuck. The orchestrator fails closed
# rather than letting an agent loop on a tool it cannot satisfy.
MAX_TOOL_CALLS_PER_TURN: Final[int] = 12

# Longest untrusted provider excerpt handed to a model in one tool result.
# Provider text is data; a whole changelog in a prompt is an injection surface,
# not evidence.
MAX_UNTRUSTED_EXCERPT_CHARS: Final[int] = 6000

# Trace result digests are prefixes of a SHA-256 hex digest: long enough to pin
# a payload, short enough to read in a terminal and a dashboard cell.
TRACE_DIGEST_CHARS: Final[int] = 16

# ADK app name; also the Agent Runtime deployment name (roadmap §7.1).
APP_NAME: Final[str] = FLEET_NAME


def tool_allowlist(agent: AgentId) -> frozenset[ToolName]:
    """Return the tools `agent` may call. Unknown agents get nothing."""
    return TOOL_ALLOWLISTS.get(agent, SHARED_TOOLS)


def prompt_version(agent: AgentId) -> str:
    """Return the pinned instruction version for `agent`."""
    return PROMPT_VERSIONS[agent]
