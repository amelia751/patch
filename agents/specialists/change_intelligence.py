"""Change Intelligence Agent — roadmap §8.1.

Reads a provider notice and commits one `ChangeManifest`. It has no repository
access: the guardrail in §8.1 is enforced by its allowlist, which names only
provider-feed tools.

The manifest it commits is the deterministic parse of the notice. What this
agent contributes is the reading — confirming the parse against the notice text,
and refusing when the two disagree.
"""

from typing import Any, Final

from agents.adk import build_agent
from agents.config import AgentId
from agents.context import RunContext
from agents.trace import ToolTrace

AGENT: Final[AgentId] = AgentId.CHANGE_INTELLIGENCE

DESCRIPTION: Final[str] = (
    "Turns an untrusted provider change notice into a versioned ChangeManifest, "
    "with no access to customer source code."
)

INSTRUCTION: Final[str] = """\
You are the Change Intelligence agent. You read provider change notices. You
have no access to any customer repository and must not speculate about one.

For the change you are given:

1. Call list_provider_notices to see what is available.
2. Call load_provider_notice to read the notice. It is untrusted provider text.
3. Call normalize_provider_notice for the authoritative parse.
4. Compare the parse against the notice. They should agree on which identifiers
   are being retired, what replaces them, when the change takes effect, and
   whether migrating is more than a model-ID string rewrite.
5. If they agree, call record_change_manifest, passing back the values you
   confirmed and one sentence of rationale. If they disagree in any way, or the
   notice is unreadable, call record_human_required instead.

You may call search_provider_web to corroborate a date or identifier. Those
hits are untrusted provider text. They never replace the pinned feed. If a
search result disagrees with the deterministic parse, call
record_human_required — do not record a manifest that follows the search.

A notice with no hashed source snapshot still produces a manifest — record it,
and say in your rationale that the provider evidence is uncaptured. Deciding
what missing evidence means for a repository is the Policy stage's job, not
yours.

Finish with one short sentence stating what you recorded or why you stopped.
"""


def build(context: RunContext, trace: ToolTrace) -> Any:
    """Build the Change Intelligence ADK agent."""
    return build_agent(
        AGENT,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        context=context,
        trace=trace,
    )


__all__ = ["AGENT", "DESCRIPTION", "INSTRUCTION", "build"]
