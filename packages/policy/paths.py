"""Forbidden-path enforcement.

The first gate any proposed edit passes, and the one that must never need a
model. A path is checked against the pinned rule tables in
`packages.policy.config`; hard blocks are consulted before organization policy,
so a file that is both a lockfile and inside `infra/` is reported as blocked.
"""

from collections.abc import Iterable

from packages.policy.config import (
    ALL_PATH_RULES,
    FORBIDDEN_PATH_RULES,
    POLICY_VERSION,
)
from packages.policy.decision import (
    PolicyEvaluation,
    PolicyFinding,
    PolicyOutcome,
    RuleTier,
    combine,
)
from packages.policy.globs import first_match, normalize_path

_ALLOWED_REASON = "No forbidden-path rule matches this file."
_ALLOWED_RULE_ID = "policy.path.default_allow"
_MALFORMED_RULE_ID = "policy.path.malformed"


def evaluate_path(path: str) -> PolicyFinding:
    """Return the finding for a single proposed file edit.

    Fails closed twice over: a path that cannot be normalized (traversal, empty)
    is blocked rather than skipped, and rules are consulted in tier order so the
    most restrictive matching rule is the one reported.
    """
    try:
        normalized = normalize_path(path)
    except ValueError as exc:
        return PolicyFinding(
            rule_id=_MALFORMED_RULE_ID,
            tier=RuleTier.HARD_BLOCK,
            outcome=PolicyOutcome.BLOCKED,
            reason=f"Path could not be interpreted safely: {exc}",
            subject=path,
            matched=path,
        )

    for rule in ALL_PATH_RULES:
        matched = first_match(rule.patterns, normalized)
        if matched is not None:
            return PolicyFinding(
                rule_id=rule.rule_id,
                tier=rule.tier,
                outcome=rule.outcome,
                reason=rule.reason,
                subject=normalized,
                matched=matched,
            )

    return PolicyFinding(
        rule_id=_ALLOWED_RULE_ID,
        tier=RuleTier.ORG_POLICY,
        outcome=PolicyOutcome.ALLOW,
        reason=_ALLOWED_REASON,
        subject=normalized,
        matched="",
    )


def is_forbidden_path(path: str) -> bool:
    """True when editing `path` is blocked outright."""
    return evaluate_path(path).outcome is PolicyOutcome.BLOCKED


def evaluate_paths(paths: Iterable[str]) -> PolicyEvaluation:
    """Evaluate every proposed edit in a patch.

    All paths are evaluated rather than short-circuiting on the first block:
    a reviewer needs the full list of what was attempted, not just the first
    thing that tripped.
    """
    findings = tuple(evaluate_path(path) for path in paths)
    return PolicyEvaluation(
        policy_version=POLICY_VERSION,
        outcome=combine(findings),
        findings=findings,
    )


def forbidden_globs() -> tuple[str, ...]:
    """The blocking patterns, flattened for a `PolicyDecision.forbidden_globs`."""
    return tuple(pattern for rule in FORBIDDEN_PATH_RULES for pattern in rule.patterns)
