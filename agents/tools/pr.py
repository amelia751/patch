"""PR tools: render an evidence summary, then request creation. Nothing else.

Roadmap §8.6 wants this agent boring, and CLAUDE.md constraint 3 says PatchAPI
stops at the pull request. Both are enforced structurally rather than by
instruction: the body is rendered from contracts other agents recorded, and the
only write tool refuses unless an independent `VerificationReport` with a PASS
verdict exists.

`open_pull_request` never holds a GitHub credential. It hands a request to the
narrow GitHub tool service (roadmap §7.3), which owns the App key and exposes no
merge, admin, secret or branch-protection capability. Until that service is
configured for a deployment the tool returns `CAPABILITY_NOT_AVAILABLE` — the
run stops with a rendered body a human can use, and no PR is claimed.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.tools.results import ReasonCode, ok, refusal
from packages.schemas.change_manifest import ChangeManifest
from packages.schemas.impact_report import ImpactReport
from packages.schemas.patch_plan import PatchPlan
from packages.schemas.policy_decision import PolicyDecision
from packages.schemas.verification_report import VerificationReport

AGENT: Final[AgentId] = AgentId.PR

# The closing section of every PatchAPI pull request. Fixed text: the automation
# boundary is a property of the product, not a sentence a model composes.
AUTOMATION_BOUNDARY: Final[str] = (
    "PatchAPI did not merge this pull request and cannot. "
    "Normal CODEOWNERS review, branch protection and CI apply unchanged."
)


def _checklist(report: VerificationReport) -> list[str]:
    marks = {"pass": "✅", "fail": "❌", "skip": "⏭️", "inconclusive": "❓"}
    return [f"- {marks[str(outcome)]} {name}" for name, outcome in report.checks.items()]


def _render_body(
    manifest: ChangeManifest,
    impact: ImpactReport,
    decision: PolicyDecision,
    plan: PatchPlan,
    report: VerificationReport,
) -> str:
    retired = ", ".join(f"`{identifier}`" for identifier in manifest.affected_identifiers)
    effective = manifest.effective_at.isoformat() if manifest.effective_at else "unstated"
    usage = "\n".join(f"- `{finding.file}` — {finding.kind}" for finding in impact.findings[:20])
    evidence = "\n".join(f"- {ref.uri}" for ref in report.evidence)
    return "\n".join(
        [
            "## PatchAPI migration",
            "",
            "### Why",
            f"{manifest.provider} is retiring {retired}, effective {effective}.",
            f"Source: {manifest.source_urls[0]}",
            "",
            "### Affected usage",
            usage or "- (no findings recorded)",
            "",
            "### Migration",
            plan.migration_summary,
            "",
            "### Verification",
            *_checklist(report),
            f"- independent verifier: `{report.verifier_agent_id}`",
            "",
            "### Risk",
            f"{decision.risk} — {decision.reason}",
            "",
            "### Evidence",
            evidence or "- (none recorded)",
            f"- run ID: `{report.run_id}`",
            "",
            "### Automation boundary",
            AUTOMATION_BOUNDARY,
        ]
    )


def build_pull_request_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Build the PR tool set bound to `context`."""

    def render_pull_request_body() -> dict[str, Any]:
        """Render the pull-request body from what the other agents recorded.

        Takes no arguments on purpose: every fact in the body comes from a
        committed contract, so the description cannot claim a check that did
        not run. Call this before open_pull_request.
        """
        required = {
            "change_manifest": ChangeManifest,
            "impact_report": ImpactReport,
            "policy_decision": PolicyDecision,
            "patch_plan": PatchPlan,
            "verification_report": VerificationReport,
        }
        missing = [
            name for name, model in required.items() if not isinstance(context.output(name), model)
        ]
        if missing:
            return refusal(
                ReasonCode.STAGE_NOT_READY,
                "a pull request body needs every upstream contract; "
                f"not recorded: {', '.join(missing)}",
            )
        body = _render_body(
            context.output("change_manifest"),
            context.output("impact_report"),
            context.output("policy_decision"),
            context.output("patch_plan"),
            context.output("verification_report"),
        )
        return ok(body=body, characters=len(body))

    def open_pull_request(title: str, head_branch: str, base_branch: str) -> dict[str, Any]:
        """Ask the GitHub tool service to open the pull request.

        Refused unless an independent verification passed and policy permitted
        a pull request. This tool cannot merge, change branch protection, or
        touch CI configuration, and it never sees a GitHub credential.
        """
        report = context.output("verification_report")
        decision = context.output("policy_decision")
        if not isinstance(report, VerificationReport) or not report.permits_pull_request:
            verdict = str(report.verdict) if isinstance(report, VerificationReport) else "absent"
            return refusal(
                ReasonCode.POLICY_DENIED,
                f"independent verification did not pass (verdict: {verdict}); no pull request",
            )
        if not isinstance(decision, PolicyDecision) or not decision.auto_pr:
            return refusal(
                ReasonCode.POLICY_DENIED,
                "policy did not permit an automated pull request for this run",
            )
        return refusal(
            ReasonCode.CAPABILITY_NOT_AVAILABLE,
            "the GitHub tool service is not configured in this deployment, so no pull "
            "request was opened. Use the rendered body; nothing was written to GitHub.",
            requested_title=title.strip(),
            requested_head=head_branch.strip(),
            requested_base=base_branch.strip(),
        )

    return [render_pull_request_body, open_pull_request]


__all__ = ["AGENT", "AUTOMATION_BOUNDARY", "build_pull_request_tools"]
