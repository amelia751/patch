"""Patch tools: the provider migration skill, and a plan.

Roadmap §12.2 keeps the Patch agent generic and puts provider knowledge in a
skill package. `load_migration_skill` reads that package from disk; it does not
fetch it, and it does not reach a provider.

Workspace edits and allowlisted commands live in `agents.tools.patch.workspace`.
This module does not write a file, allocate a sandbox, or open a pull request.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.config import MAX_UNTRUSTED_EXCERPT_CHARS, AgentId
from agents.context import PathOutsideRootError, RunContext, resolve_within
from agents.tools.results import ReasonCode, ok, refusal
from packages.schemas.patch_plan import PatchPlan

CONTRACT: Final[str] = "patch_plan"
AGENT: Final[AgentId] = AgentId.PATCH

SKILLS_DIRNAME: Final[str] = "skills"
SKILL_ENTRYPOINT: Final[str] = "SKILL.md"


def build_migration_skill_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Build the Patch tool set bound to `context`."""

    def load_migration_skill(skill_id: str) -> dict[str, Any]:
        """Load a provider migration skill by directory name.

        The skill states the affected identifiers, the replacement, and the
        capability differences that make a string rewrite wrong. Read it before
        planning; do not rely on recalled provider knowledge.
        """
        skills_root = context.repo_root / SKILLS_DIRNAME
        if not skills_root.is_dir():
            return refusal(ReasonCode.NOT_FOUND, f"no skills directory at {skills_root}")
        try:
            skill_dir = resolve_within(skills_root, skill_id)
        except PathOutsideRootError as exc:
            return refusal(ReasonCode.OUT_OF_SCOPE, str(exc))

        entrypoint = skill_dir / SKILL_ENTRYPOINT
        if not entrypoint.is_file():
            available = sorted(
                path.name for path in skills_root.iterdir() if (path / SKILL_ENTRYPOINT).is_file()
            )
            return refusal(
                ReasonCode.NOT_FOUND,
                f"no {SKILL_ENTRYPOINT} for skill {skill_id!r}",
                available=available,
            )

        text = entrypoint.read_text(encoding="utf-8")
        return ok(
            skill_id=skill_id,
            path=str(entrypoint.relative_to(context.repo_root)),
            truncated=len(text) > MAX_UNTRUSTED_EXCERPT_CHARS,
            content=text[:MAX_UNTRUSTED_EXCERPT_CHARS],
        )

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

    return [load_migration_skill, record_patch_plan]


__all__ = ["AGENT", "CONTRACT", "build_migration_skill_tools"]
