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
FLEET_VERSION: Final[str] = "1.7.0"

# Agent Registry (roadmap §12.1) discovers the fleet under this name.
FLEET_NAME: Final[str] = "patchapi-fleet"


class AgentId(StrEnum):
    """The orchestrator, four reasoning agents, and two Python stage names."""

    ORCHESTRATOR = "orchestrator"
    CHANGE_INTELLIGENCE = "change_intelligence"
    IMPACT = "impact"
    POLICY = "policy"
    PATCH = "patch"
    VERIFICATION = "verification"
    PR = "pr"


# Roadmap §8: four LlmAgents. POLICY and PR stay as stage / trace names.
SPECIALISTS: Final[tuple[AgentId, ...]] = (
    AgentId.CHANGE_INTELLIGENCE,
    AgentId.IMPACT,
    AgentId.PATCH,
    AgentId.VERIFICATION,
)

DETERMINISTIC_STAGES: Final[tuple[AgentId, ...]] = (AgentId.POLICY, AgentId.PR)


class ToolName(StrEnum):
    """Every tool the fleet exposes.

    A tool absent from this enum cannot be granted, and `agents.tools` asserts
    that the functions it registers and this enum are the same set.
    """

    # Change Intelligence — provider feed plus the project index (read-only).
    LIST_PROVIDER_NOTICES = "list_provider_notices"
    LOAD_PROVIDER_NOTICE = "load_provider_notice"
    NORMALIZE_PROVIDER_NOTICE = "normalize_provider_notice"
    RECORD_CHANGE_MANIFEST = "record_change_manifest"
    LIVE_IDENTIFIER = "live_identifier"
    SEARCH_WEB = "search_web"
    SEARCH_INDEX = "search_index"

    # Impact — deterministic repository inventory, no provider fetch, no writes.
    SCAN_REPOSITORY = "scan_repository"
    LOOKUP_INDEX_USAGES = "lookup_index_usages"
    CLASSIFY_REPOSITORY_PATH = "classify_repository_path"
    RECORD_IMPACT_REPORT = "record_impact_report"

    # Policy & Risk — deterministic gates.
    EVALUATE_POLICY = "evaluate_policy"
    LIST_FORBIDDEN_GLOBS = "list_forbidden_globs"
    RECORD_POLICY_DECISION = "record_policy_decision"

    # Patch — skill, plan, and the sandbox debug loop. No sandbox
    # allocation, no GitHub. Roadmap §8.4.
    LOAD_MIGRATION_SKILL = "load_migration_skill"
    RECORD_PATCH_PLAN = "record_patch_plan"
    READ_FILE = "read_file"
    LIST_DIR = "list_dir"
    APPLY_PATCH = "apply_patch"
    RUN_COMMAND = "run_command"
    COMPUTER_USE_STEP = "computer_use_step"

    # Verification — sandbox evidence, read-only, independent of Patch.
    LIST_VERIFICATION_EVIDENCE = "list_verification_evidence"
    READ_VERIFICATION_EVIDENCE = "read_verification_evidence"
    RECORD_VERIFICATION_REPORT = "record_verification_report"

    # PR — render and request. Creation goes through the GitHub tool service.
    RENDER_PULL_REQUEST_BODY = "render_pull_request_body"
    OPEN_PULL_REQUEST = "open_pull_request"

    # Available to every agent: the fail-closed exit.
    RECORD_HUMAN_REQUIRED = "record_human_required"

    # Patch / Verification — inspect vault names, then pause for the operator.
    LIST_RUNTIME_CREDENTIALS = "list_runtime_credentials"
    REQUEST_RUNTIME_CREDENTIALS = "request_runtime_credentials"


# Granted to every AgentId, including the two Python stages. Roadmap §8 and
# CLAUDE.md constraint 10: stopping is always an available structured action.
SHARED_TOOLS: Final[frozenset[ToolName]] = frozenset({ToolName.RECORD_HUMAN_REQUIRED})

# The tool-call budget bounds work; it must never bound an ending. Refusing
# these alongside the rest told an exhausted agent to record HUMAN_REQUIRED and
# then refused that call too, so the turn could only die without a verdict.
TURN_ENDING_TOOLS: Final[frozenset[ToolName]] = frozenset(
    {
        ToolName.RECORD_HUMAN_REQUIRED,
        ToolName.RECORD_CHANGE_MANIFEST,
        ToolName.RECORD_IMPACT_REPORT,
        ToolName.RECORD_POLICY_DECISION,
        ToolName.RECORD_PATCH_PLAN,
        ToolName.RECORD_VERIFICATION_REPORT,
    }
)

# Tools whose answer cannot change during a turn, so repeating the same
# arguments cannot tell the agent anything it does not already have. Asking
# twice is a retry; asking a third time is a loop, and one Patch turn spent
# minutes re-issuing an identical search before its budget ran out.
#
# Deliberately narrow. `run_command` and `read_file` are how the Patch loop
# sees the effect of an edit, so an identical call there is the point.
REPEATED_CALL_IS_A_LOOP: Final[frozenset[ToolName]] = frozenset(
    {
        ToolName.SEARCH_WEB,
        ToolName.LOAD_MIGRATION_SKILL,
        ToolName.LIST_VERIFICATION_EVIDENCE,
        ToolName.LIST_RUNTIME_CREDENTIALS,
    }
)

# How many identical calls to one of those tools a turn may make.
MAX_IDENTICAL_CALLS: Final[int] = 2

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
            ToolName.LIVE_IDENTIFIER,
            ToolName.SEARCH_WEB,
            ToolName.LOOKUP_INDEX_USAGES,
            ToolName.SEARCH_INDEX,
            ToolName.READ_FILE,
            ToolName.LIST_DIR,
        }
    ),
    AgentId.IMPACT: frozenset(
        {
            ToolName.SCAN_REPOSITORY,
            ToolName.LOOKUP_INDEX_USAGES,
            ToolName.SEARCH_INDEX,
            ToolName.CLASSIFY_REPOSITORY_PATH,
            ToolName.RECORD_IMPACT_REPORT,
            ToolName.SEARCH_WEB,
        }
    ),
    AgentId.POLICY: frozenset(),
    AgentId.PATCH: frozenset(
        {
            ToolName.LOAD_MIGRATION_SKILL,
            ToolName.RECORD_PATCH_PLAN,
            ToolName.READ_FILE,
            ToolName.LIST_DIR,
            ToolName.APPLY_PATCH,
            ToolName.RUN_COMMAND,
            ToolName.COMPUTER_USE_STEP,
            ToolName.SEARCH_WEB,
            ToolName.LIST_RUNTIME_CREDENTIALS,
            ToolName.REQUEST_RUNTIME_CREDENTIALS,
        }
    ),
    AgentId.VERIFICATION: frozenset(
        {
            ToolName.LIST_VERIFICATION_EVIDENCE,
            ToolName.READ_VERIFICATION_EVIDENCE,
            ToolName.RECORD_VERIFICATION_REPORT,
            ToolName.SEARCH_WEB,
            ToolName.LIST_RUNTIME_CREDENTIALS,
            ToolName.REQUEST_RUNTIME_CREDENTIALS,
        }
    ),
    AgentId.PR: frozenset(),
}

TOOL_ALLOWLISTS: Final[MappingProxyType[AgentId, frozenset[ToolName]]] = MappingProxyType(
    {agent: grants | SHARED_TOOLS for agent, grants in _GRANTS.items()}
)

# Built in `adk.py` as an AgentTool child, not as a Python function. `build_tools`
# does not construct these; the grant still names them so the guardrail can.
ADK_ATTACHED_TOOLS: Final[frozenset[ToolName]] = frozenset({ToolName.SEARCH_WEB})

# Instruction version per agent, recorded on trace events so a stored run can be
# replayed against the prompt that produced it. Bumping a prompt bumps this.
PROMPT_VERSIONS: Final[MappingProxyType[AgentId, str]] = MappingProxyType(
    {
        **dict.fromkeys(AgentId, "1.1.0"),
        AgentId.CHANGE_INTELLIGENCE: "1.4.0",
        AgentId.PATCH: "1.6.0",
        AgentId.VERIFICATION: "1.4.0",
    }
)

# Reasoning model for every agent. One pin, inherited from the provider adapter
# so PatchAPI cannot drift from the generation the rules require.
REASONING_MODEL: Final[str] = require_supported_reasoning_model(DEFAULT_REASONING_MODEL)

# Google's documented setting for this generation. Greedy decoding is what makes
# Gemini 3 repeat itself: at 0.0 a Patch turn re-issued one identical web search
# a dozen times until its budget ran out. It bought no reproducibility either —
# what a run can be audited from is the trace and the evidence, and those depend
# on the sandbox, the provider, and the search index, none of which are fixed.
# https://ai.google.dev/gemini-api/docs/prompting-strategies
MODEL_TEMPERATURE: Final[float] = 1.0

# Gemini 3.x spends output tokens on thinking before it emits text or a function
# call, so a small cap yields an empty turn rather than a short one.
MAX_OUTPUT_TOKENS: Final[int] = 4096

# A turn that has not converged by here is stuck. The orchestrator fails closed
# rather than letting an agent loop on a tool it cannot satisfy. The Patch
# debug loop (inspect → edit → run) needs more than a single-shot confirm, and a
# multi-file semantic migration spends most of this on reading before it edits:
# a Patch turn that loads a skill, reads a dozen files, searches, runs a
# baseline, patches, and re-runs is working, not looping.
MAX_TOOL_CALLS_PER_TURN: Final[int] = 40

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
