"""PR Agent — roadmap §8.6.

Intentionally boring. It receives a verified patch, renders an evidence summary,
and requests that the GitHub tool service open a pull request. It cannot merge,
cannot bypass a check, cannot alter branch protection, and cannot edit code —
none of those are in its allowlist, and the tool service that owns the GitHub
credential exposes no such capability either.

This agent is where PatchAPI stops.
"""

from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.specialist import build_specialist
from agents.trace import ToolTrace

AGENT: Final[AgentId] = AgentId.PR

DESCRIPTION: Final[str] = (
    "Renders the evidence-backed pull request body and requests creation through the "
    "narrow GitHub tool service. Cannot merge or edit code."
)

INSTRUCTION: Final[str] = """\
You are the PR agent. A verified patch has been produced. Your job is to make it
reviewable by a human, and then to stop.

1. Call render_pull_request_body. It builds the description from the contracts
   the other agents recorded, so you do not write the facts yourself.
2. Call open_pull_request with a title that names the provider change, the head
   branch, and the base branch.

Do not describe a check that did not run. Do not soften a failed check. Do not
suggest that anyone merge this, and do not ask for an exception to a review
requirement — the pull request exists so that normal CODEOWNERS review, branch
protection and CI apply exactly as they always do.

If the tool refuses because the GitHub capability is unavailable, report that
plainly. Nothing was opened, and saying otherwise would be a false claim in an
audit trail.
"""


def build_pr_agent(context: RunContext, trace: ToolTrace) -> Any:
    """Build the PR ADK agent."""
    return build_specialist(
        AGENT,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        context=context,
        trace=trace,
    )


__all__ = ["AGENT", "DESCRIPTION", "INSTRUCTION", "build_pr_agent"]
