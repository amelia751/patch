"""`VerificationReport` — the independent verifier's judgement (roadmap §8.5).

Two constraints are enforced structurally rather than left to a prompt:

* the verifier must not be the agent that wrote the patch, and
* `PASS` is only expressible when a real proof ran: either the local
  build and tests passed, or a live provider resolve passed. Skip on the
  unused side is allowed. No unexpected file, retired identifiers gone,
  evidence exists.

A run that skipped every proof (no local gate and no live resolve) is
`INCONCLUSIVE`, never `PASS`.
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
            if failed:
                raise ValueError(
                    f"verdict PASS forbids a failed check; failed: {', '.join(failed)}"
                )
            if self.policy is not CheckOutcome.PASS:
                raise ValueError("verdict PASS requires policy to pass")
            local_ok = self.build is CheckOutcome.PASS and self.tests is CheckOutcome.PASS
            live_ok = self.live_api is CheckOutcome.PASS
            if not local_ok and not live_ok:
                raise ValueError(
                    "verdict PASS requires a green local gate or a live provider resolve"
                )
            for name, outcome in (
                ("build", self.build),
                ("tests", self.tests),
                ("live_api", self.live_api),
            ):
                if outcome not in {CheckOutcome.PASS, CheckOutcome.SKIP}:
                    raise ValueError(f"verdict PASS cannot record {name} as {outcome}")
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
