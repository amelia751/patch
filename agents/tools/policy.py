"""Policy & Risk tools: the deterministic gate, then a recorded decision.

Roadmap §8.3 fixes the enforcement hierarchy, and this module is where an agent
meets it. `evaluate_policy` runs `packages.policy`, which decides with pinned
rules and the standard library. `record_policy_decision` then takes the
*outcome* from that evaluation, not from the agent: the model supplies a risk
tier and a reason, and the permission fields — `auto_patch`, `auto_pr`,
`human_review_required` — are derived. An agent can escalate by recording
HUMAN_REQUIRED; it has no expressible way to soften a denial.
"""

from collections.abc import Callable
from typing import Any, Final

from agents.config import AgentId
from agents.context import RunContext
from agents.tools.results import ReasonCode, ok, refusal
from packages.policy.config import POLICY_VERSION
from packages.policy.gate import decision_fields, evaluate_change
from packages.policy.paths import forbidden_globs
from packages.schemas.change_manifest import ChangeManifest
from packages.schemas.policy_decision import PolicyDecision

CONTRACT: Final[str] = "policy_decision"
AGENT: Final[AgentId] = AgentId.POLICY


def build_policy_tools(context: RunContext) -> list[Callable[..., Any]]:
    """Build the Policy & Risk tool set bound to `context`."""

    evaluated: dict[str, Any] = {}

    def list_forbidden_globs() -> dict[str, Any]:
        """List the path patterns no PatchAPI run may edit.

        Deterministic and non-negotiable. A migration that needs one of these
        paths is a HUMAN_REQUIRED run, not a policy exception to argue for.
        """
        return ok(policy_version=POLICY_VERSION, forbidden_globs=list(forbidden_globs()))

    def evaluate_policy(proposed_paths: list[str]) -> dict[str, Any]:
        """Clear a set of proposed file edits through the deterministic gate.

        Returns the outcome and every rule that fired. Run this before
        recording a decision; the recorded outcome comes from here.
        """
        evaluation = evaluate_change(proposed_paths=[p for p in proposed_paths if p.strip()])
        evaluated["evaluation"] = evaluation
        return ok(
            policy_version=evaluation.policy_version,
            outcome=str(evaluation.outcome),
            findings=[finding.to_audit_record() for finding in evaluation.findings],
        )

    def record_policy_decision(
        change_id: str,
        repo: str,
        risk: str,
        reason: str,
        escalate_to_human: bool,
    ) -> dict[str, Any]:
        """Commit this run's PolicyDecision.

        The outcome and the auto_patch / auto_pr permissions come from the
        deterministic evaluation, not from you. Supply the risk tier ("low",
        "medium", "high", "critical") and one sentence of reasoning. Set
        escalate_to_human when something the rules cannot see makes this
        unsafe — it can only tighten the verdict, never loosen it.
        """
        evaluation = evaluated.get("evaluation")
        if evaluation is None:
            return refusal(
                ReasonCode.STAGE_NOT_READY,
                "call evaluate_policy before recording a policy decision",
            )

        fields = decision_fields(evaluation)
        manifest = context.output("change_manifest")

        # An unproven provider claim is not grounds for touching customer code
        # (roadmap §8.1). This is checked here rather than trusted to the model.
        evidence_missing = (
            isinstance(manifest, ChangeManifest) and not manifest.has_verifiable_evidence
        )
        if evidence_missing or escalate_to_human:
            if fields["outcome"] == "allow":
                fields["outcome"] = "human_required"
            fields["auto_patch"] = False
            fields["auto_pr"] = False
            fields["human_review_required"] = True
            if evidence_missing:
                fields["reason"] = (
                    "No hashed provider snapshot backs this change; PatchAPI fails closed "
                    "on unverifiable provider evidence."
                )
                fields["rule_ids"] = sorted({*fields["rule_ids"], "evidence.snapshot_required"})

        stated_reason = (
            fields["reason"] if evidence_missing else (reason.strip() or fields["reason"])
        )
        try:
            decision = PolicyDecision(
                run_id=context.run_id,
                change_id=change_id,
                repo=repo,
                risk=risk,
                reason=stated_reason,
                outcome=fields["outcome"],
                auto_patch=fields["auto_patch"],
                auto_pr=fields["auto_pr"],
                human_review_required=fields["human_review_required"],
                forbidden_globs=fields["forbidden_globs"],
                required_checks=fields["required_checks"],
                rule_ids=fields["rule_ids"] or ["policy.gate.clear"],
            )
        except ValueError as exc:
            return refusal(ReasonCode.INVALID_CONTRACT, str(exc))

        context.record(CONTRACT, AGENT, decision)
        return ok(
            recorded=CONTRACT,
            schema_version=decision.schema_version,
            outcome=str(decision.outcome),
            auto_patch=decision.auto_patch,
            human_review_required=decision.human_review_required,
        )

    return [list_forbidden_globs, evaluate_policy, record_policy_decision]


__all__ = ["AGENT", "CONTRACT", "build_policy_tools"]
