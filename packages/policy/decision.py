"""The vocabulary and result types of the deterministic policy gate.

Roadmap §8.3 fixes the enforcement hierarchy: hard blocks outrank org policy,
which outranks semantic governance, which outranks anything an agent suggests.
`RuleTier` encodes that order, and `combine` applies it — a lower tier can never
soften a decision a higher one already made.

`PolicyOutcome`'s wire strings mirror `packages.schemas.enums.PolicyOutcome`.
The schemas package is not imported here: this gate has to keep working in an
environment where nothing but the standard library is installed, because it is
the thing that says no. `packages/policy/tests/test_policy.py` asserts the two
vocabularies have not drifted apart whenever both are importable.
"""

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Any, Final


class PolicyOutcome(StrEnum):
    ALLOW = "allow"
    HUMAN_REQUIRED = "human_required"
    BLOCKED = "blocked"


class RuleTier(IntEnum):
    """Authority of a rule. Lower value wins.

    `SEMANTIC_GOVERNANCE` and `AGENT_SUGGESTION` exist so a probabilistic
    verdict has a place to sit that is structurally incapable of overriding a
    deterministic one. Google's own documentation notes semantic governance is
    probabilistic; it is defence in depth, never the only barrier.
    """

    HARD_BLOCK = 1
    ORG_POLICY = 2
    SEMANTIC_GOVERNANCE = 3
    AGENT_SUGGESTION = 4


# Severity order used when several findings disagree. Independent of tier: a
# tier decides who may speak, this decides what the worst thing said was.
_OUTCOME_SEVERITY: Final[dict[PolicyOutcome, int]] = {
    PolicyOutcome.ALLOW: 0,
    PolicyOutcome.HUMAN_REQUIRED: 1,
    PolicyOutcome.BLOCKED: 2,
}


@dataclass(frozen=True, slots=True)
class Rule:
    """One deterministic rule: what it matches and what that means."""

    rule_id: str
    tier: RuleTier
    outcome: PolicyOutcome
    reason: str
    patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PolicyFinding:
    """A rule fired against a specific subject.

    `subject` is the path or the source of the untrusted text; `matched` is the
    literal pattern or phrase that fired, so a denial can be shown to a human
    without re-running the gate.
    """

    rule_id: str
    tier: RuleTier
    outcome: PolicyOutcome
    reason: str
    subject: str
    matched: str

    def to_audit_record(self) -> dict[str, Any]:
        """A flat, JSON-safe record for the audit log and the dashboard.

        Denials are visible by construction: what was attempted and what
        stopped it are both fields, not prose in a log line.
        """
        return {
            "rule_id": self.rule_id,
            "tier": self.tier.name.lower(),
            "outcome": self.outcome.value,
            "reason": self.reason,
            "attempted": self.subject,
            "matched": self.matched,
        }


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    """The gate's verdict over a whole set of subjects."""

    policy_version: str
    outcome: PolicyOutcome
    findings: tuple[PolicyFinding, ...] = field(default=())

    @property
    def permits_patching(self) -> bool:
        return self.outcome is PolicyOutcome.ALLOW

    @property
    def blocking_findings(self) -> tuple[PolicyFinding, ...]:
        return tuple(f for f in self.findings if f.outcome is PolicyOutcome.BLOCKED)

    def to_audit_records(self) -> list[dict[str, Any]]:
        return [finding.to_audit_record() for finding in self.findings]


def combine(findings: tuple[PolicyFinding, ...]) -> PolicyOutcome:
    """Fold findings into one outcome under the enforcement hierarchy.

    The hierarchy is expressed as a ratchet rather than a precedence lookup: a
    finding may only escalate the verdict, never relax one another finding has
    already reached. That is what makes the tiers safe to mix — a probabilistic
    semantic-governance verdict can add a `HUMAN_REQUIRED`, but no tier below
    `HARD_BLOCK` can talk a `BLOCKED` back down to `ALLOW`.

    An empty set of findings is not an approval: a gate that evaluated nothing
    has cleared nothing, so callers get `HUMAN_REQUIRED`.
    """
    if not findings:
        return PolicyOutcome.HUMAN_REQUIRED
    return max(findings, key=lambda finding: _OUTCOME_SEVERITY[finding.outcome]).outcome
