"""The one tool every agent holds: the fail-closed exit.

CLAUDE.md constraint 10 — ambiguity ends a run, it does not get resolved by
guessing. That only works if stopping is always an available, structured action;
an agent with no way to say "I cannot answer this" will answer anyway.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.config import MAX_UNTRUSTED_EXCERPT_CHARS, AgentId
from agents.context import RunContext
from agents.tools.results import ok


def build_shared_tools(context: RunContext, agent: AgentId) -> list[Callable[..., Any]]:
    """Build the tools granted to every agent, bound to `context`."""

    def record_human_required(reason: str) -> dict[str, Any]:
        """Stop this run and hand it to a human, giving the reason.

        Use this whenever you cannot proceed honestly: the provider evidence is
        missing or unverifiable, the notice contradicts the parsed change, a
        capability you need is unavailable, or the migration is ambiguous. This
        is a correct outcome, not a failure — never guess instead.
        """
        entry = {
            "agent": str(agent),
            "reason": reason.strip()[:MAX_UNTRUSTED_EXCERPT_CHARS],
        }
        context.human_required.append(entry)
        return ok(recorded="human_required", **entry)

    return [record_human_required]


AGENT_AGNOSTIC: Final[tuple[str, ...]] = ("record_human_required",)

__all__ = ["AGENT_AGNOSTIC", "build_shared_tools"]
