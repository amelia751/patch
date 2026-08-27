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

import json
import os
import urllib.error
import urllib.request
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
GITHUB_TOOLS_URL_ENV: Final[str] = "PATCHAPI_GITHUB_TOOLS_URL"
PR_AGENT_IDENTITY: Final[str] = "patchapi.pr"
_HTTP_TIMEOUT_SECONDS: Final[float] = 30.0

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


def github_tools_base_url() -> str:
    """Configured GitHub tool service origin, or empty when none is wired."""
    return os.environ.get(GITHUB_TOOLS_URL_ENV, "").strip().rstrip("/")


def _service_identity(audience: str) -> str:
    """Google-signed ID token proving which service account is calling.

    The GitHub tool service is deployed private, so the caller has to be a
    named service account rather than anyone who learns the URL. This is the
    only credential the agent side ever handles, and it grants nothing beyond
    "you may ask the tool service"; the GitHub App key stays on the other side.

    Returns empty off Google infrastructure, where a private service is not
    reachable anyway and the caller should hear that as a refusal.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.id_token import fetch_id_token

        return str(fetch_id_token(Request(), audience))
    except Exception:
        # Absent ADC is a deployment fact, not a bug. The caller turns the
        # resulting 403 into a refusal that names the tool service.
        return ""


def invoke_github_capability(
    capability: str,
    *,
    run_id: str,
    arguments: dict[str, Any],
    agent: str = PR_AGENT_IDENTITY,
) -> dict[str, Any]:
    """POST one capability to the GitHub tool service. Never holds a token."""
    base = github_tools_base_url()
    if not base:
        return refusal(
            ReasonCode.CAPABILITY_NOT_AVAILABLE,
            "the GitHub tool service is not configured in this deployment, so no "
            "GitHub write was attempted.",
            capability=capability,
        )
    headers = {
        "Content-Type": "application/json",
        "X-PatchAPI-Agent": agent,
        "X-PatchAPI-Run-Id": run_id,
    }
    token = _service_identity(base)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base}/v1/capabilities/{capability}",
        data=json.dumps(arguments).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        return refusal(
            ReasonCode.CAPABILITY_NOT_AVAILABLE,
            f"GitHub tool service refused {capability} ({exc.code}): {body}",
            capability=capability,
        )
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return refusal(
            ReasonCode.CAPABILITY_NOT_AVAILABLE,
            f"GitHub tool service could not be reached for {capability}: {exc}",
            capability=capability,
        )
    if not isinstance(payload, dict):
        return refusal(
            ReasonCode.INVALID_CONTRACT,
            f"GitHub tool service returned a non-object for {capability}",
        )
    return ok(capability=capability, result=payload.get("result", payload))


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
        risk = str(decision.risk)
        if risk == "critical":
            risk = "high"
        impact = context.output("impact_report")
        plan = context.output("patch_plan")
        usage = (
            [f"{finding.file} — {finding.kind}" for finding in impact.findings]
            if isinstance(impact, ImpactReport)
            else []
        )
        migration = [plan.migration_summary] if isinstance(plan, PatchPlan) else []
        manifest = context.output("change_manifest")
        why = (
            plan.migration_summary
            if isinstance(plan, PatchPlan) and plan.migration_summary.strip()
            else decision.reason
        )
        if isinstance(manifest, ChangeManifest) and manifest.affected_identifiers:
            retired = ", ".join(f"`{item}`" for item in manifest.affected_identifiers[:4])
            if not why or "deterministic slice" in why.lower():
                why = f"{manifest.provider} is retiring {retired}."
        evidence = {
            "why": why,
            "affected_usage": usage,
            "migration": migration,
            "verification": [
                {
                    "name": name,
                    "passed": str(outcome) in {"pass", "skip"},
                    "detail": None if str(outcome) == "pass" else str(outcome),
                }
                for name, outcome in report.checks.items()
            ],
            "risk_level": risk if risk in {"low", "medium", "high"} else "medium",
            "risk_rationale": decision.reason,
            "evidence_links": [ref.uri for ref in report.evidence],
            "trace_id": context.run_id,
        }
        return invoke_github_capability(
            "open_pull_request",
            run_id=context.run_id,
            arguments={
                "repo": report.repo,
                "head_branch": head_branch.strip(),
                "base_branch": base_branch.strip(),
                "title": title.strip(),
                "base_sha": report.base_sha,
                "run_id": context.run_id,
                "evidence": evidence,
            },
        )

    return [render_pull_request_body, open_pull_request]


__all__ = [
    "AGENT",
    "AUTOMATION_BOUNDARY",
    "GITHUB_TOOLS_URL_ENV",
    "build_pull_request_tools",
    "github_tools_base_url",
    "invoke_github_capability",
]
