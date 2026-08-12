"""Patch Agent — roadmap §8.4.

Plans a migration and produces a diff. It cannot open a pull request, cannot
allocate a sandbox, and cannot grade its own work — the allowlist grants it a
skill reader and a plan recorder, and nothing else.

Provider-specific knowledge lives in a skill package (roadmap §12.2) rather than
in this prompt, so adding Stripe or Twilio later means adding a skill, not
editing an agent.
"""

from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.specialist import build_specialist
from agents.trace import ToolTrace

AGENT: Final[AgentId] = AgentId.PATCH

DESCRIPTION: Final[str] = (
    "Plans a repository-specific migration from a provider skill and records a "
    "versioned PatchPlan. Holds no write, sandbox or GitHub capability."
)

INSTRUCTION: Final[str] = """\
You are the Patch agent. You plan a migration. You do not decide whether it is
allowed, you do not run it, and you do not judge whether it worked.

1. Call load_migration_skill for the provider skill named in your task. It holds
   the capability differences that make this migration more than a find and
   replace. Read it before planning.
2. Plan against the ImpactReport findings. Every file you intend to change must
   be listed in files_expected — a file you change without listing it is an
   unexpected change to the Verification agent, and that fails the run.
3. Call record_patch_plan with the summary, your assumptions, and the commands
   that must pass in the sandbox.

State every assumption. If the skill says an option on the retired API has no
equivalent on the replacement, that is not something to quietly drop: either the
plan handles it explicitly, or you call record_human_required.

Your work will be graded by a different agent that did not see this prompt.
Write the plan so that agent can check it.
"""


def build_patch_agent(context: RunContext, trace: ToolTrace) -> Any:
    """Build the Patch ADK agent."""
    return build_specialist(
        AGENT,
        description=DESCRIPTION,
        instruction=INSTRUCTION,
        context=context,
        trace=trace,
    )


__all__ = ["AGENT", "DESCRIPTION", "INSTRUCTION", "build_patch_agent"]
