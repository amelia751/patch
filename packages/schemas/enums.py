"""Closed vocabularies shared by the agent contracts.

Every enum is a `StrEnum` so a serialized contract stays readable JSON while a
consumer still gets a checked value rather than free prose.
"""

from enum import StrEnum


class ChangeType(StrEnum):
    """What a provider actually changed."""

    MODEL_RETIREMENT = "model_retirement"
    ENDPOINT_REMOVAL = "endpoint_removal"
    API_DEPRECATION = "api_deprecation"
    BREAKING_CHANGE = "breaking_change"
    PARAMETER_CHANGE = "parameter_change"
    AUTH_CHANGE = "auth_change"
    BEHAVIOR_CHANGE = "behavior_change"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TrustClassification(StrEnum):
    """Provenance of the text a contract was derived from.

    Provider material is data, never instructions, and stays labelled as such
    all the way through the pipeline.
    """

    UNTRUSTED_PROVIDER_INPUT = "untrusted_provider_input"
    INTERNAL_ANALYSIS = "internal_analysis"


class UsageKind(StrEnum):
    """How an affected identifier appears in a repository.

    Roadmap §8.2: a docs-only hit must not be treated like a runtime hit.
    """

    RUNTIME_SOURCE = "runtime_source"
    CONFIGURATION = "configuration"
    TEST = "test"
    EXAMPLE = "example"
    DOCUMENTATION_EXAMPLE = "documentation_example"
    DEAD_CODE = "dead_code"


class MigrationCharacter(StrEnum):
    """How much reasoning the migration needs.

    `SEMANTIC` means the replacement has a different request surface, so a
    model-ID string rewrite would be wrong.
    """

    MECHANICAL = "mechanical"
    SEMANTIC = "semantic"
    UNSUPPORTED = "unsupported"


class RiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyOutcome(StrEnum):
    """Deterministic verdict of the Policy & Risk agent."""

    ALLOW = "allow"
    HUMAN_REQUIRED = "human_required"
    BLOCKED = "blocked"


class CheckOutcome(StrEnum):
    """Result of one verification check.

    `SKIP` means the check was not attempted; `INCONCLUSIVE` means it ran but
    produced no usable signal. Neither may be read as success.
    """

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    INCONCLUSIVE = "inconclusive"


class Verdict(StrEnum):
    """Overall judgement of the independent Verification agent."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


class EvidenceKind(StrEnum):
    BUILD_LOG = "build_log"
    TEST_LOG = "test_log"
    LIVE_API_ARTIFACT = "live_api_artifact"
    DIFF = "diff"
    SOURCE_SNAPSHOT = "source_snapshot"
    SANDBOX_LOG = "sandbox_log"
