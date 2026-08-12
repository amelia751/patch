"""`ImpactReport` — the Impact agent's verdict on one repository (roadmap §8.2)."""

from typing import ClassVar, Self

from pydantic import Field, model_validator

from packages.schemas.base import StrictModel, VersionedContract
from packages.schemas.config import MAX_FINDING_EXCERPT_CHARS
from packages.schemas.enums import MigrationCharacter, UsageKind
from packages.schemas.fields import (
    ChangeId,
    GitSha,
    Identifier,
    NonEmptyLine,
    RepoFullName,
    RepoRelativePath,
    RunId,
)

# Findings that execute. A repository whose only hits are documentation or dead
# code is affected, but not in the same way, and the two must stay separable.
RUNTIME_USAGE_KINDS: frozenset[UsageKind] = frozenset(
    {UsageKind.RUNTIME_SOURCE, UsageKind.CONFIGURATION}
)


class ImpactFinding(StrictModel):
    """One concrete occurrence of an affected identifier."""

    identifier: Identifier
    file: RepoRelativePath
    kind: UsageKind
    line: int | None = Field(default=None, ge=1)
    symbol: str | None = None
    excerpt: str | None = Field(default=None, max_length=MAX_FINDING_EXCERPT_CHARS)

    @property
    def is_runtime(self) -> bool:
        return self.kind in RUNTIME_USAGE_KINDS


class ImpactReport(VersionedContract):
    CONTRACT_NAME: ClassVar[str] = "impact_report"

    run_id: RunId
    change_id: ChangeId
    repo: RepoFullName
    base_sha: GitSha
    affected: bool
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[ImpactFinding] = Field(default_factory=list)
    migration_character: MigrationCharacter | None = None
    required_checks: list[NonEmptyLine] = Field(default_factory=list)
    owners: list[NonEmptyLine] = Field(default_factory=list)
    notes: str | None = None

    @model_validator(mode="after")
    def _check_coherent(self) -> Self:
        if self.affected and not self.findings:
            raise ValueError("an affected repository must carry at least one finding")
        if not self.affected and self.findings:
            raise ValueError("an unaffected repository must carry no findings")
        if self.affected and self.migration_character is None:
            raise ValueError("an affected repository must state a migration_character")
        if not self.affected and self.migration_character is not None:
            raise ValueError("an unaffected repository must not state a migration_character")
        if self.affected and not self.required_checks:
            raise ValueError("an affected repository must state the checks a patch has to pass")
        return self

    @property
    def runtime_findings(self) -> list[ImpactFinding]:
        """Findings in code that executes, as opposed to docs or examples."""
        return [finding for finding in self.findings if finding.is_runtime]

    @property
    def affected_files(self) -> list[str]:
        """Unique files carrying at least one finding, in first-seen order."""
        return list(dict.fromkeys(finding.file for finding in self.findings))
