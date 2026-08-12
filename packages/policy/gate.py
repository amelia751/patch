"""The single entry point a run passes through before anything is written.

Roadmap §8.3: hard controls must not depend solely on an LLM. `evaluate_change`
is that control. It runs the deterministic gates in the order that fails
soonest — untrusted provider text first, then proposed edits — and returns one
verdict with every finding attached, so the dashboard can show what was
attempted alongside what stopped it.

The Policy & Risk agent may add findings on top of this evaluation. It cannot
subtract one: `combine` only ever escalates.
"""

from collections.abc import Iterable, Mapping

from packages.policy.config import POLICY_VERSION, REQUIRED_CHECKS
from packages.policy.decision import (
    PolicyEvaluation,
    PolicyFinding,
    PolicyOutcome,
    combine,
)
from packages.policy.injection import scan_untrusted_text
from packages.policy.paths import evaluate_paths, forbidden_globs


def evaluate_change(
    *,
    proposed_paths: Iterable[str] = (),
    untrusted_documents: Mapping[str, str] | None = None,
) -> PolicyEvaluation:
    """Clear a proposed change through every deterministic gate.

    `untrusted_documents` maps a source name (a changelog URL, a fixture path)
    to its raw text. Documents are scanned before paths so an injected
    instruction is reported as the cause even when it also produced a forbidden
    edit.
    """
    findings: list[PolicyFinding] = []

    for source, text in sorted((untrusted_documents or {}).items()):
        findings.extend(scan_untrusted_text(text, source=source).findings)

    paths = tuple(proposed_paths)
    if paths:
        findings.extend(evaluate_paths(paths).findings)

    return PolicyEvaluation(
        policy_version=POLICY_VERSION,
        outcome=combine(tuple(findings)),
        findings=tuple(findings),
    )


def decision_fields(evaluation: PolicyEvaluation) -> dict[str, object]:
    """Project an evaluation onto the fields of a `PolicyDecision` contract.

    Returned as plain data so this package stays free of a Pydantic dependency;
    the agent that emits the contract validates it. `auto_merge` is absent by
    construction — the contract types it as a constant `False`, and no policy
    document can express otherwise.
    """
    permitted = evaluation.outcome is PolicyOutcome.ALLOW
    return {
        "outcome": evaluation.outcome.value,
        "auto_patch": permitted,
        "auto_pr": permitted,
        "human_review_required": evaluation.outcome is not PolicyOutcome.ALLOW,
        "forbidden_globs": list(forbidden_globs()),
        "required_checks": list(REQUIRED_CHECKS),
        "rule_ids": sorted({finding.rule_id for finding in evaluation.findings}),
        "reason": _summarize(evaluation),
    }


def _summarize(evaluation: PolicyEvaluation) -> str:
    blocking = evaluation.blocking_findings
    if blocking:
        first = blocking[0]
        return f"{first.reason} (rule {first.rule_id}, matched {first.matched!r})"
    escalated = [f for f in evaluation.findings if f.outcome is PolicyOutcome.HUMAN_REQUIRED]
    if escalated:
        first = escalated[0]
        return f"{first.reason} (rule {first.rule_id})"
    return "All proposed edits and provider documents cleared the deterministic policy gate."
