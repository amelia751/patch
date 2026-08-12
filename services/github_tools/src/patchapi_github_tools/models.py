"""Argument and result contracts for the capability surface.

Validation here is part of the security boundary, not input hygiene. Three
constraints are worth naming because they cannot be recovered later:

* every write targets a branch under `PATCH_BRANCH_PREFIX`, so the service is
  structurally unable to commit to `main` even if an agent asks it to;
* commits and branch creation pin a full 40-character SHA, never a moving ref;
* a pull request cannot be opened without the evidence §8.6 requires, so the
  body is rendered from data rather than accepted as free text.
"""

from __future__ import annotations

import re
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.github import RepositoryRef

# Writes are confined to branches this prefix identifies as PatchAPI's own.
PATCH_BRANCH_PREFIX: Final[str] = "patchapi/"

_SHA_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{40}$")

RepoName = Annotated[str, Field(min_length=3, max_length=140, examples=["amelia751/egaki"])]
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class CapabilityArgs(BaseModel):
    """Base for every capability's arguments."""

    # Unknown keys are a contract mismatch: silently dropping one would let a
    # caller believe it constrained an operation that ignored the constraint.
    model_config = ConfigDict(extra="forbid", frozen=True)

    repo: RepoName

    @field_validator("repo")
    @classmethod
    def _validate_repo(cls, value: str) -> str:
        # Reuse the shared reference type so the service and the agents agree
        # on what a repository name may contain.
        return RepositoryRef.parse(value).full_name

    @property
    def repository(self) -> RepositoryRef:
        return RepositoryRef.parse(self.repo)


class _PatchBranchArgs(CapabilityArgs):
    branch: str = Field(min_length=len(PATCH_BRANCH_PREFIX) + 1, max_length=255)

    @field_validator("branch")
    @classmethod
    def _validate_branch(cls, value: str) -> str:
        if not value.startswith(PATCH_BRANCH_PREFIX):
            raise ValueError(f"write targets must live under {PATCH_BRANCH_PREFIX!r}")
        if ".." in value or value.endswith("/") or value.endswith(".lock"):
            raise ValueError(f"invalid branch name: {value!r}")
        return value


class GetRepositoryMetadataArgs(CapabilityArgs):
    pass


class GetFileArgs(CapabilityArgs):
    path: str = Field(min_length=1, max_length=4096)
    ref: Sha


class ListTreeArgs(CapabilityArgs):
    sha: Sha
    recursive: bool = True


class GetCommitArgs(CapabilityArgs):
    sha: Sha


class GetPullRequestArgs(CapabilityArgs):
    number: int = Field(ge=1)


class GetChecksArgs(CapabilityArgs):
    ref: Sha


class CreatePatchBranchArgs(_PatchBranchArgs):
    base_sha: Sha


class PatchFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1, max_length=4096)
    content: str

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if value.startswith("/") or ".." in value.split("/"):
            raise ValueError(f"patch paths are repository-relative: {value!r}")
        return value


class CommitVerifiedPatchArgs(_PatchBranchArgs):
    message: str = Field(min_length=1, max_length=4096)
    files: list[PatchFile] = Field(min_length=1)
    # The commit is rejected if the branch has moved since verification, so a
    # patch verified against one tree is never committed onto another.
    expected_head_sha: Sha


class VerificationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=200)
    passed: bool
    detail: str | None = Field(default=None, max_length=500)


class PullRequestEvidence(BaseModel):
    """The evidence a PatchAPI pull request must carry (roadmap §8.6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    why: str = Field(min_length=1, max_length=2000)
    affected_usage: list[str] = Field(min_length=1)
    migration: list[str] = Field(min_length=1)
    verification: list[VerificationCheck] = Field(min_length=1)
    risk_level: Literal["low", "medium", "high"]
    risk_rationale: str = Field(min_length=1, max_length=1000)
    evidence_links: list[str] = Field(default_factory=list)
    trace_id: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _require_independent_verification(self) -> PullRequestEvidence:
        # Roadmap §8.6 and CLAUDE.md §6: the patch author does not grade its own
        # work. A PR whose evidence records a failed or missing independent pass
        # is refused here, not caught by a reviewer.
        if any(not check.passed for check in self.verification):
            failed = ", ".join(check.name for check in self.verification if not check.passed)
            raise ValueError(f"every verification check must pass before a PR is opened: {failed}")
        return self


class OpenPullRequestArgs(CapabilityArgs):
    head_branch: str = Field(min_length=len(PATCH_BRANCH_PREFIX) + 1, max_length=255)
    base_branch: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=256)
    base_sha: Sha
    run_id: str = Field(min_length=1, max_length=200)
    evidence: PullRequestEvidence
    draft: bool = False

    @field_validator("head_branch")
    @classmethod
    def _validate_head(cls, value: str) -> str:
        if not value.startswith(PATCH_BRANCH_PREFIX):
            raise ValueError(f"pull requests may only be opened from {PATCH_BRANCH_PREFIX!r}")
        return value

    @model_validator(mode="after")
    def _distinct_branches(self) -> OpenPullRequestArgs:
        if self.head_branch == self.base_branch:
            raise ValueError("head_branch and base_branch must differ")
        return self


class AddPrCommentArgs(CapabilityArgs):
    number: int = Field(ge=1)
    body: str = Field(min_length=1, max_length=60_000)


def is_full_sha(value: str) -> bool:
    return bool(_SHA_RE.match(value))
