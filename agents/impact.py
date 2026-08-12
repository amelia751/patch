"""Impact Agent — roadmap §8.2.

Decides whether a repository is actually affected by a change, and how. It reads
the checkout through a deterministic scanner and never opens a network
connection: the provider's side of the story arrives as an already-normalized
`ChangeManifest`, not as text this agent fetches.

Roadmap §8.2's own emphasis is the distinction this agent exists to make — a
documentation example that mentions a retired model is not the same finding as a
runtime call to it.
"""

from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.specialist import build_specialist
from agents.trace import ToolTrace

AGENT: Final[AgentId] = AgentId.IMPACT

DESCRIPTION: Final[str] = (
    "Determines whether a repository is affected by a normalized provider change, "
    "which files are involved, and whether the migration is mechanical or semantic."
)

INSTRUCTION: Final[str] = """\
You are the Impact agent. You judge what a provider change means for one
repository checkout.

1. Call scan_repository with the retired identifiers from the ChangeManifest.
   The scan is the inventory; you do not name files it did not find.
2. Read the usage kind on each hit. A runtime_source or configuration hit means
   the repository is affected. Documentation, examples and tests alone are a
   weaker signal — say so in your confidence and your notes rather than
   treating them as equivalent.
3. Decide the migration character. "mechanical" means the replacement is a
   drop-in and only the identifier string changes. "semantic" means the
   replacement has a different request surface, so a string rewrite would be
   wrong. "unsupported" means the replacement cannot do what this code needs.
   When the manifest says a semantic migration is required, do not report
   mechanical.
4. Call record_impact_report with your judgement, the checks that must pass, and
   a short note naming the strongest evidence.

If the scan finds nothing, report affected=false. That is a complete, useful
answer, not a failure.
"""


def build_impact_agent(context: RunContext, trace: ToolTrace) -> Any:
    """Build the Impact ADK agent."""
    return build_specialist(
        AGENT,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        context=context,
        trace=trace,
    )


__all__ = ["AGENT", "DESCRIPTION", "INSTRUCTION", "build_impact_agent"]
