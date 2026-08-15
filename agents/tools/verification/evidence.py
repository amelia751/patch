"""Verification tools: read sandbox evidence, then grade it.

Roadmap §8.5 — verification is independent of patch generation, so nothing here
can produce or amend a patch. The Verification agent reads artifacts the sandbox
wrote and returns a verdict, and `VerificationReport` itself refuses a report
whose verifier is the agent that authored the patch.

Evidence is read from a root the run was given. There is no tool that reads an
arbitrary path: a verifier that could wander the filesystem could grade a build
log that belongs to a different run.
"""

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from agents.config import MAX_UNTRUSTED_EXCERPT_CHARS, AgentId
from agents.context import PathOutsideRootError, RunContext, resolve_within
from agents.tools.results import ReasonCode, ok, refusal
from packages.schemas.evidence import EvidenceRef
from packages.schemas.patch_plan import PatchPlan
from packages.schemas.verification_report import VerificationReport

CONTRACT: Final[str] = "verification_report"
AGENT: Final[AgentId] = AgentId.VERIFICATION

# Log tails are what diagnose a failure; a whole build log is not evidence a
# model needs in context when the artifact itself is hashed and stored.
MAX_EVIDENCE_CHARS: Final[int] = MAX_UNTRUSTED_EXCERPT_CHARS


def _relative_files(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def build_evidence_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Build the Verification tool set bound to `context`."""

    def list_verification_evidence() -> dict[str, Any]:
        """List the artifacts the sandbox produced for this run.

        Build logs, test logs, diffs and any live-API artifact. Read what you
        need from this list; there is no other way to reach a file.
        """
        root = context.evidence_root
        if root is None:
            return refusal(
                ReasonCode.STAGE_NOT_READY,
                "this run has no sandbox evidence yet; nothing has been verified",
            )
        if not root.is_dir():
            return refusal(ReasonCode.NOT_FOUND, f"evidence root {root} does not exist")
        return ok(evidence_root=str(root), files=_relative_files(root))

    def read_verification_evidence(name: str) -> dict[str, Any]:
        """Read one artifact by its name from the evidence listing.

        Returns the tail of the file plus its SHA-256, so a quoted line can be
        traced back to bytes a reviewer can re-hash.
        """
        root = context.evidence_root
        if root is None:
            return refusal(ReasonCode.STAGE_NOT_READY, "this run has no sandbox evidence yet")
        try:
            path = resolve_within(root, name)
        except PathOutsideRootError as exc:
            return refusal(ReasonCode.OUT_OF_SCOPE, str(exc))
        if not path.is_file():
            return refusal(
                ReasonCode.NOT_FOUND,
                f"no artifact named {name!r}",
                available=_relative_files(root),
            )

        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        return ok(
            name=name,
            uri=path.as_uri(),
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            truncated=len(text) > MAX_EVIDENCE_CHARS,
            content=text[-MAX_EVIDENCE_CHARS:],
        )

    def record_verification_report(
        change_id: str,
        repo: str,
        base_sha: str,
        patched_sha_or_diff_hash: str,
        verdict: str,
        build: str,
        tests: str,
        live_api: str,
        policy: str,
        deprecated_identifiers_absent: bool,
        unexpected_files: list[str],
        evidence_uris: list[str],
        notes: str,
    ) -> dict[str, Any]:
        """Commit this run's VerificationReport. You have veto power.

        Each check is "pass", "fail", "skip" or "inconclusive"; a check you did
        not run is "skip", never "pass". The verdict is "pass", "fail" or
        "inconclusive", and "pass" is rejected unless every check passed, no
        unexpected file changed, the retired identifiers are gone, and at least
        one artifact backs it.
        """
        plan = context.output("patch_plan")
        patch_author = (
            str(plan.author_agent_id) if isinstance(plan, PatchPlan) else str(AgentId.PATCH)
        )
        try:
            report = VerificationReport(
                run_id=context.run_id,
                change_id=change_id,
                repo=repo,
                base_sha=base_sha,
                patched_sha_or_diff_hash=patched_sha_or_diff_hash,
                verdict=verdict,
                build=build,
                tests=tests,
                live_api=live_api,
                policy=policy,
                deprecated_identifiers_absent=deprecated_identifiers_absent,
                unexpected_files=[path for path in unexpected_files if path.strip()],
                evidence=[
                    EvidenceRef(kind="sandbox_log", uri=uri) for uri in evidence_uris if uri.strip()
                ],
                patch_agent_id=patch_author,
                verifier_agent_id=str(AGENT),
                notes=notes or None,
            )
        except ValueError as exc:
            return refusal(ReasonCode.INVALID_CONTRACT, str(exc))

        context.record(CONTRACT, AGENT, report)
        return ok(
            recorded=CONTRACT,
            schema_version=report.schema_version,
            verdict=str(report.verdict),
            permits_pull_request=report.permits_pull_request,
        )

    return [
        list_verification_evidence,
        read_verification_evidence,
        record_verification_report,
    ]


__all__ = ["AGENT", "CONTRACT", "MAX_EVIDENCE_CHARS", "build_evidence_tools"]
