"""`PatchPlan` — what the Patch agent intends to change (roadmap §8.4).

The plan is declared before the diff is graded, so the independent verifier can
compare intent against the files a diff actually touched. Every attempt starts
from the same pinned `base_sha`.
"""

from typing import ClassVar, Self

from pydantic import Field, model_validator

from packages.schemas.base import VersionedContract
from packages.schemas.config import MAX_MIGRATION_SUMMARY_CHARS, MAX_PATCH_ATTEMPTS
from packages.schemas.fields import (
    AgentId,
    ChangeId,
    GitSha,
    NonEmptyLine,
    RepoFullName,
    RepoRelativePath,
    RunId,
    Sha256Hex,
)


class PatchPlan(VersionedContract):
    CONTRACT_NAME: ClassVar[str] = "patch_plan"

    run_id: RunId
    change_id: ChangeId
    repo: RepoFullName
    base_sha: GitSha
    attempt: int = Field(ge=1, le=MAX_PATCH_ATTEMPTS)
    author_agent_id: AgentId
    files_expected: list[RepoRelativePath] = Field(min_length=1)
    migration_summary: str = Field(min_length=1, max_length=MAX_MIGRATION_SUMMARY_CHARS)
    assumptions: list[NonEmptyLine] = Field(default_factory=list)
    verification_commands: list[NonEmptyLine] = Field(min_length=1)
    skill_id: NonEmptyLine | None = None
    skill_version: NonEmptyLine | None = None
    diff_sha256: Sha256Hex | None = None

    @model_validator(mode="after")
    def _check_coherent(self) -> Self:
        if len(set(self.files_expected)) != len(self.files_expected):
            raise ValueError("files_expected must not repeat a path")
        if (self.skill_id is None) != (self.skill_version is None):
            raise ValueError("skill_id and skill_version are recorded together or not at all")
        return self
