"""The Patch agent's plan contract.

Migration knowledge is not here and is not in the Patch prompt. It lives in the
packages under `skills/`, which ADK's `SkillToolset` exposes to the model
directly (`agents.adk`). Nothing in PatchAPI decides which package applies:
the model reads the metadata ADK injects and loads what the change needs.

Workspace edits and allowlisted commands live in `agents.tools.patch.workspace`.
This module does not write a file, allocate a sandbox, or open a pull request.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.tools.results import ReasonCode, ok, refusal
from packages.schemas.patch_plan import PatchPlan

CONTRACT: Final[str] = "patch_plan"
AGENT: Final[AgentId] = AgentId.PATCH


def build_patch_plan_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Build the Patch plan tool bound to `context`."""

    def record_patch_plan(
        change_id: str,
        repo: str,
        base_sha: str,
        attempt: int,
        files_expected: list[str],
        migration_summary: str,
        assumptions: list[str],
        verification_commands: list[str],
        skill_id: str,
        skill_version: str,
    ) -> dict[str, Any]:
        """Commit this run's PatchPlan.

        List every file you intend to change, summarise the migration, state
        the assumptions a reviewer would need to check, and give the commands
        that must pass in the sandbox. A file you do not list here and then
        change is an unexpected file to the Verification agent.

        `skill_id` and `skill_version` name the skill whose method you
        followed, as `load_skill` reported them. Leave both empty if you
        followed none; naming one you did not read is a false provenance.
        """
        try:
            plan = PatchPlan(
                run_id=context.run_id,
                change_id=change_id,
                repo=repo,
                base_sha=base_sha,
                attempt=attempt,
                author_agent_id=str(AGENT),
                files_expected=[path for path in files_expected if path.strip()],
                migration_summary=migration_summary,
                assumptions=[line for line in assumptions if line.strip()],
                verification_commands=[line for line in verification_commands if line.strip()],
                skill_id=skill_id or None,
                skill_version=skill_version or None,
            )
        except ValueError as exc:
            return refusal(ReasonCode.INVALID_CONTRACT, str(exc))

        context.record(CONTRACT, AGENT, plan)
        return ok(
            recorded=CONTRACT,
            schema_version=plan.schema_version,
            attempt=plan.attempt,
            files_expected=list(plan.files_expected),
        )

    return [record_patch_plan]


__all__ = ["AGENT", "CONTRACT", "build_patch_plan_tools"]
