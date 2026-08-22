"""Versioned Pydantic contracts for PatchAPI agent and service I/O.

Runtime code passes these models, never untyped dicts. Contract versions are
pinned in `packages.schemas.config` so no call site inlines one.

Names are resolved on first access rather than imported eagerly. Importing this
package must not require Pydantic to be installed: a bare `pytest` at the repo
root collects every tree using the workspace-root environment, which does not
install workspace members, and an eager import here would abort collection for
all of them. `./scripts/verify_packages_schemas.sh` runs the tests in an
environment that does have the dependency.
"""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - resolved statically, never at runtime
    from packages.schemas.base import StrictModel, VersionedContract
    from packages.schemas.change_manifest import ChangeManifest, IdentifierReplacement
    from packages.schemas.config import (
        ALLOWED_EVIDENCE_URI_SCHEMES,
        CONTRACT_VERSIONS,
        MAX_FINDING_EXCERPT_CHARS,
        MAX_MIGRATION_SUMMARY_CHARS,
        MAX_PATCH_ATTEMPTS,
        UnknownContractError,
        contract_version,
    )
    from packages.schemas.enums import (
        ChangeType,
        CheckOutcome,
        EvidenceKind,
        MigrationCharacter,
        PolicyOutcome,
        RiskTier,
        Severity,
        TrustClassification,
        UsageKind,
        Verdict,
    )
    from packages.schemas.evidence import EvidenceRef, SourceSnapshot
    from packages.schemas.impact_report import (
        RUNTIME_USAGE_KINDS,
        ImpactFinding,
        ImpactReport,
    )
    from packages.schemas.patch_plan import PatchPlan
    from packages.schemas.policy_decision import PolicyDecision
    from packages.schemas.run_state import (
        ALLOWED_RUN_STATE_TRANSITIONS,
        TERMINAL_RUN_STATES,
        IllegalRunStateTransitionError,
        RunState,
        assert_transition,
        can_transition,
        is_terminal,
    )
    from packages.schemas.verification_report import VerificationReport

_EXPORTS: dict[str, str] = {
    "ALLOWED_EVIDENCE_URI_SCHEMES": "config",
    "ALLOWED_RUN_STATE_TRANSITIONS": "run_state",
    "CONTRACT_VERSIONS": "config",
    "MAX_FINDING_EXCERPT_CHARS": "config",
    "MAX_MIGRATION_SUMMARY_CHARS": "config",
    "MAX_PATCH_ATTEMPTS": "config",
    "RUNTIME_USAGE_KINDS": "impact_report",
    "TERMINAL_RUN_STATES": "run_state",
    "ChangeManifest": "change_manifest",
    "ChangeType": "enums",
    "CheckOutcome": "enums",
    "EvidenceKind": "enums",
    "EvidenceRef": "evidence",
    "IdentifierReplacement": "change_manifest",
    "IllegalRunStateTransitionError": "run_state",
    "ImpactFinding": "impact_report",
    "ImpactReport": "impact_report",
    "MigrationCharacter": "enums",
    "PatchPlan": "patch_plan",
    "PolicyDecision": "policy_decision",
    "PolicyOutcome": "enums",
    "RiskTier": "enums",
    "RunState": "run_state",
    "Severity": "enums",
    "SourceSnapshot": "evidence",
    "StrictModel": "base",
    "TrustClassification": "enums",
    "UnknownContractError": "config",
    "UsageKind": "enums",
    "Verdict": "enums",
    "VerificationReport": "verification_report",
    "VersionedContract": "base",
    "assert_transition": "run_state",
    "can_transition": "run_state",
    "contract_version": "config",
    "is_terminal": "run_state",
}

# Spelled out rather than derived from `_EXPORTS` so the public surface is
# readable statically. A test asserts the two stay in step.
__all__ = [
    "ALLOWED_EVIDENCE_URI_SCHEMES",
    "ALLOWED_RUN_STATE_TRANSITIONS",
    "CONTRACT_VERSIONS",
    "MAX_FINDING_EXCERPT_CHARS",
    "MAX_MIGRATION_SUMMARY_CHARS",
    "MAX_PATCH_ATTEMPTS",
    "RUNTIME_USAGE_KINDS",
    "TERMINAL_RUN_STATES",
    "ChangeManifest",
    "ChangeType",
    "CheckOutcome",
    "EvidenceKind",
    "EvidenceRef",
    "IdentifierReplacement",
    "IllegalRunStateTransitionError",
    "ImpactFinding",
    "ImpactReport",
    "MigrationCharacter",
    "PatchPlan",
    "PolicyDecision",
    "PolicyOutcome",
    "RiskTier",
    "RunState",
    "Severity",
    "SourceSnapshot",
    "StrictModel",
    "TrustClassification",
    "UnknownContractError",
    "UsageKind",
    "Verdict",
    "VerificationReport",
    "VersionedContract",
    "assert_transition",
    "can_transition",
    "contract_version",
    "is_terminal",
]


def __getattr__(name: str) -> Any:
    """Load the submodule that owns `name`, then cache the binding."""
    try:
        submodule = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(f"{__name__}.{submodule}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
