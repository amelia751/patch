"""Pinned span and attribute names.

A trace is evidence in this product: the demo shows the agent topology from it,
and an audit answers "what did the run actually do" from it. Names therefore
live here rather than at call sites, so renaming one is a single visible change
and a dashboard query cannot quietly stop matching.
"""

from typing import Final

TRACING_SCHEMA_VERSION: Final[str] = "1.0.0"

DEFAULT_SERVICE_NAME: Final[str] = "patchapi"

# One span per pipeline stage (roadmap §8), named so a trace reads as the run.
SPAN_CHANGE_INTELLIGENCE: Final[str] = "patchapi.change_intelligence"
SPAN_IMPACT: Final[str] = "patchapi.impact"
SPAN_POLICY: Final[str] = "patchapi.policy"
SPAN_PATCH: Final[str] = "patchapi.patch"
SPAN_SANDBOX: Final[str] = "patchapi.sandbox"
SPAN_VERIFICATION: Final[str] = "patchapi.verification"
SPAN_PULL_REQUEST: Final[str] = "patchapi.pull_request"

# Attribute keys. Prefixed to avoid colliding with OpenTelemetry semantic
# conventions, which own the unprefixed namespace.
ATTR_RUN_ID: Final[str] = "patchapi.run_id"
ATTR_CHANGE_ID: Final[str] = "patchapi.change_id"
ATTR_REPO: Final[str] = "patchapi.repo"
ATTR_BASE_SHA: Final[str] = "patchapi.base_sha"
ATTR_POLICY_OUTCOME: Final[str] = "patchapi.policy_outcome"
ATTR_TRUST: Final[str] = "patchapi.trust"
ATTR_MODEL_ID: Final[str] = "patchapi.model_id"
ATTR_ATTEMPT: Final[str] = "patchapi.attempt"
