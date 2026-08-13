"""Pinned event vocabulary and payload limits.

The topic names are the ones in `roadmap.md` §10.4 and are a closed set: a
publisher that cannot name its topic here has invented a workflow step nobody
subscribes to.
"""

from enum import StrEnum
from typing import Final

ENVELOPE_VERSION: Final[str] = "1.0.0"


class EventType(StrEnum):
    """Every event PatchAPI publishes, one per Pub/Sub topic (roadmap §10.4)."""

    PROVIDER_CHANGE_DETECTED = "provider-change-detected"
    CHANGE_NORMALIZED = "change-normalized"
    REPO_IMPACT_REQUESTED = "repo-impact-requested"
    REPO_AFFECTED = "repo-affected"
    PATCH_REQUESTED = "patch-requested"
    SANDBOX_COMPLETE = "sandbox-complete"
    VERIFICATION_REQUESTED = "verification-requested"
    PR_REQUESTED = "pr-requested"
    POLICY_DENIED = "policy-denied"
    REPO_PUSH = "repo-push"
    PROJECT_REPO_ADDED = "project-repo-added"
    PROJECT_REPO_REMOVED = "project-repo-removed"
    INDEX_UPDATED = "index-updated"


class TrustLevel(StrEnum):
    """Provenance of the material an event refers to.

    Mirrors `packages.schemas.enums.TrustClassification`. An event derived from
    provider material stays labelled as untrusted all the way down the pipeline,
    so a subscriber cannot lose track of where the text came from.
    """

    UNTRUSTED_PROVIDER_INPUT = "untrusted_provider_input"
    INTERNAL_ANALYSIS = "internal_analysis"


# Messages carry IDs and URIs, not repository source code (roadmap §10.4).
# These bounds are what makes that rule enforceable rather than aspirational.
MAX_PAYLOAD_VALUE_CHARS: Final[int] = 2_048
MAX_PAYLOAD_KEYS: Final[int] = 32
MAX_PAYLOAD_BYTES: Final[int] = 64_000

# Payload values are scalars or flat lists of scalars. A nested structure is
# how source code gets smuggled into an event.
ALLOWED_PAYLOAD_SCALARS: Final[tuple[type, ...]] = (str, int, float, bool, type(None))
