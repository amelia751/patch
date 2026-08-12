"""`PolicyDecision` — deterministic authority over what a run may do (roadmap §8.3).

The decision is produced by rules, not by a model's opinion, and it is the
object every later stage checks itself against. `auto_merge` is typed as a
constant `False`: PatchAPI stops at the pull request, and no policy document can
express otherwise.
"""

from typing import ClassVar, Literal, Self

from pydantic import Field, model_validator

from packages.schemas.base import VersionedContract
from packages.schemas.enums import PolicyOutcome, RiskTier
from packages.schemas.fields import (
    ChangeId,
    GlobPattern,
    NonEmptyLine,
    RepoFullName,
    RunId,
)


class PolicyDecision(VersionedContract):
    CONTRACT_NAME: ClassVar[str] = "policy_decision"

    run_id: RunId
    change_id: ChangeId
    repo: RepoFullName
    risk: RiskTier
    outcome: PolicyOutcome
    auto_patch: bool
    auto_pr: bool
    auto_merge: Literal[False] = False
    human_review_required: bool
    forbidden_globs: list[GlobPattern] = Field(min_length=1)
    required_checks: list[NonEmptyLine] = Field(min_length=1)
    rule_ids: list[NonEmptyLine] = Field(min_length=1)
    reason: NonEmptyLine

    @model_validator(mode="after")
    def _check_outcome_consistent(self) -> Self:
        if self.outcome is PolicyOutcome.BLOCKED and (self.auto_patch or self.auto_pr):
            raise ValueError("a BLOCKED decision must not permit patching or PR creation")
        if self.outcome is PolicyOutcome.HUMAN_REQUIRED:
            if self.auto_patch or self.auto_pr:
                raise ValueError("a HUMAN_REQUIRED decision is analysis-only: no patching, no PR")
            if not self.human_review_required:
                raise ValueError("a HUMAN_REQUIRED decision must set human_review_required")
        if self.auto_pr and not self.auto_patch:
            raise ValueError("auto_pr without auto_patch has nothing to open a PR for")
        return self

    @property
    def permits_patching(self) -> bool:
        return self.outcome is PolicyOutcome.ALLOW and self.auto_patch
