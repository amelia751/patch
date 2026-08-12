"""Pinned configuration for the repository indexer.

Every version string, confidence value and watched identifier lives here. A
call site asks this module for a watchlist; none of them names a model ID, so
changing what PatchAPI watches for is a deliberate edit to this file.
"""

from types import MappingProxyType
from typing import Final

from packages.repo_scan import SCANNER_VERSION
from packages.repo_scan.classify import UsageKind
from patchapi_repo_indexer.errors import UnknownProviderError

# Bumped when the inventory-building logic changes shape. Recorded on every
# inventory so a stored document can be traced to the indexer that wrote it.
INDEXER_VERSION: Final[str] = "1.0.0"

# Document version of the inventory contract itself. Consumers refuse a version
# they do not know rather than misread a document written by a newer producer.
INVENTORY_VERSION: Final[str] = "1.0.0"

# Mirrors the `detection_layer` enum in db/migrations/0001_types.sql. This
# indexer only ever produces Layer A findings: literal, non-model matches.
DETECTION_LAYER: Final[str] = "A_DETERMINISTIC"

# A literal string match is certain — the bytes are either in the file or they
# are not. Uncertainty in this pipeline belongs to the layers that reason, not
# to the layer that greps.
LITERAL_MATCH_CONFIDENCE: Final[float] = 1.0

# Scanning scope labels recorded on the inventory. Full-tree is the initial
# index of a checkout; changed-paths is the push-driven update of roadmap §11.2,
# which must not be mistaken for a complete picture of the repository.
SCOPE_FULL_TREE: Final[str] = "full_tree"
SCOPE_CHANGED_PATHS: Final[str] = "changed_paths"

DEFAULT_PROVIDER: Final[str] = "google"

# The Imagen 4 family retired by the pinned demo change. Kept in step with
# `demo/fixtures/google-imagen4-deprecation.json`; the fixture is the provider's
# claim, this is the list PatchAPI watches for by default when no manifest has
# been supplied.
IMAGEN_4_IDENTIFIERS: Final[tuple[str, ...]] = (
    "imagen-4.0-generate-001",
    "imagen-4.0-fast-generate-001",
    "imagen-4.0-ultra-generate-001",
)

WATCHLISTS: Final[MappingProxyType[str, tuple[str, ...]]] = MappingProxyType(
    {
        DEFAULT_PROVIDER: IMAGEN_4_IDENTIFIERS,
    }
)

# Usage kinds whose breakage takes production down, re-exported here so the
# inventory and the scanner cannot drift apart on what "runtime" means.
RUNTIME_USAGE_KINDS: Final[frozenset[UsageKind]] = frozenset(
    {UsageKind.RUNTIME_SOURCE, UsageKind.CONFIGURATION}
)

__all__ = [
    "DEFAULT_PROVIDER",
    "DETECTION_LAYER",
    "IMAGEN_4_IDENTIFIERS",
    "INDEXER_VERSION",
    "INVENTORY_VERSION",
    "LITERAL_MATCH_CONFIDENCE",
    "RUNTIME_USAGE_KINDS",
    "SCANNER_VERSION",
    "SCOPE_CHANGED_PATHS",
    "SCOPE_FULL_TREE",
    "WATCHLISTS",
    "watchlist_for",
]


def watchlist_for(provider: str) -> tuple[str, ...]:
    """Return the pinned identifiers watched for `provider`.

    Fails closed: an unknown provider is a configuration error, never an empty
    watchlist that would silently report a repository as unaffected.
    """
    try:
        return WATCHLISTS[provider]
    except KeyError as exc:
        known = ", ".join(sorted(WATCHLISTS))
        raise UnknownProviderError(
            f"no pinned watchlist for provider {provider!r}; known providers: {known}"
        ) from exc
