"""`VerificationReport` — the independent verifier's judgement (roadmap §8.5).

Two constraints are enforced structurally rather than left to a prompt:

* the verifier must not be the agent that wrote the patch, and
* `PASS` is only expressible when every required check passed, no unexpected
  file was touched, the retired identifiers are gone, and evidence exists.

A live check that could not run yields `INCONCLUSIVE`, never `PASS`.
"""

from typing import ClassVar, Self

from pydantic import Field, model_validator

from packages.schemas.base import VersionedContract
from packages.schemas.enums import CheckOutcome, Verdict
from packages.schemas.evidence import EvidenceRef
from packages.schemas.fields import (
    AgentId,
    ChangeId,
    GitSha,
    HexDigest,
    RepoFullName,
    RepoRelativePath,
    RunId,
)


class VerificationReport(VersionedContract):
    CONTRACT_NAME: ClassVar[str] = "verification_report"

    run_id: RunId
    change_id: ChangeId
    repo: RepoFullName
    base_sha: GitSha
    patched_sha_or_diff_hash: HexDigest
    verdict: Verdict
    build: CheckOutcome
    tests: CheckOutcome
    live_api: CheckOutcome
    policy: CheckOutcome
    deprecated_identifiers_absent: bool
    unexpected_files: list[RepoRelativePath] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    patch_agent_id: AgentId
    verifier_agent_id: AgentId
    notes: str | None = None

    @property
    def checks(self) -> dict[str, CheckOutcome]:
        return {
            "build": self.build,
            "tests": self.tests,
            "live_api": self.live_api,
            "policy": self.policy,
        }

    @model_validator(mode="after")
    def _check_independent_and_consistent(self) -> Self:
        if self.patch_agent_id == self.verifier_agent_id:
            raise ValueError(
                "verification must be independent: "
                f"{self.verifier_agent_id!r} also produced the patch"
            )

        failed = [name for name, outcome in self.checks.items() if outcome is CheckOutcome.FAIL]

        if self.verdict is Verdict.PASS:
            not_passed = [
                name for name, outcome in self.checks.items() if outcome is not CheckOutcome.PASS
            ]
            if not_passed:
                raise ValueError(
                    "verdict PASS requires every check to pass; "
                    f"not passing: {', '.join(not_passed)}"
                )
            if self.unexpected_files:
                raise ValueError("verdict PASS requires no unexpected file changes")
            if not self.deprecated_identifiers_absent:
                raise ValueError(
                    "verdict PASS requires the retired identifiers to be gone from the "
                    "exercised path"
                )
            if not self.evidence:
                raise ValueError("verdict PASS requires at least one piece of evidence")

        if self.verdict is Verdict.INCONCLUSIVE and failed:
            raise ValueError(
                f"a failed check is a FAIL verdict, not INCONCLUSIVE; failed: {', '.join(failed)}"
            )

        return self

    @property
    def permits_pull_request(self) -> bool:
        """Only an unambiguous PASS lets the PR agent proceed."""
        return self.verdict is Verdict.PASS
