"""Pinned configuration for the repository indexer.

Every version string and confidence value lives here. What PatchAPI *watches
for* does not: identifiers and family patterns belong to a provider, so they
live in that provider's descriptor (`packages/providers/descriptors/`) and this
module reads them through the registry. Onboarding a provider is a descriptor,
not an edit to this file.

The reads still fail closed. An unknown provider raises `UnknownProviderError`
rather than yielding an empty watchlist, because a scan that looks for nothing
reports every repository as clean.
"""

import os
from collections.abc import Mapping
from typing import Final

from packages.providers import registry
from packages.providers.errors import UnknownProviderError as RegistryUnknownProviderError
from packages.repo_scan import SCANNER_VERSION
from packages.repo_scan.classify import UsageKind
from patchapi_repo_indexer.errors import UnknownProviderError

# Bumped when the inventory-building logic changes shape, including when the
# query patterns change what a search returns. Recorded on every inventory, so a
# stored document can be traced to the indexer that wrote it and a shard from an
# older extractor is re-indexed rather than believed.
INDEXER_VERSION: Final[str] = "1.5.0"

# Document version of the inventory contract itself. Consumers refuse a version
# they do not know rather than misread a document written by a newer producer.
INVENTORY_VERSION: Final[str] = "1.0.0"

# Mirrors the `detection_layer` enum in db/migrations/0007_provider_usages.sql.
# This indexer only ever produces Layer A findings: literal, non-model matches.
DETECTION_LAYER: Final[str] = "A_DETERMINISTIC"
DETECTION_LAYERS: Final[tuple[str, ...]] = (
    "A_DETERMINISTIC",
    "B_STRUCTURAL",
    "C_SEMANTIC",
    "D_TYPE_PRECISE",
)

# A literal string match is certain — the bytes are either in the file or they
# are not. Uncertainty in this pipeline belongs to the layers that reason, not
# to the layer that greps.
LITERAL_MATCH_CONFIDENCE: Final[float] = 1.0

# Scanning scope labels recorded on the inventory. Full-tree is the initial
# index of a checkout; changed-paths is the push-driven update of roadmap §11.2,
# which must not be mistaken for a complete picture of the repository.
SCOPE_FULL_TREE: Final[str] = "full_tree"
SCOPE_CHANGED_PATHS: Final[str] = "changed_paths"

INDEX_BACKEND: Final[str] = os.getenv("PATCHAPI_INDEX_BACKEND", "zoekt")
LAYER_B_CONFIDENCE: Final[float] = 0.9
ZOEKT_INDEX_DIR: Final[str] = os.getenv("PATCHAPI_ZOEKT_INDEX_DIR", "/tmp/patchapi-zoekt")
ZOEKT_WEBSERVER_URL: Final[str] = os.getenv("PATCHAPI_ZOEKT_WEBSERVER_URL", "http://127.0.0.1:6070")
ASTGREP_RULE_DIR: Final[str] = os.getenv("PATCHAPI_ASTGREP_RULE_DIR", "")
INDEXER_WORKDIR: Final[str] = os.getenv("PATCHAPI_INDEXER_WORKDIR", "/tmp/patchapi-index-work")
PUBSUB_PROJECT: Final[str] = os.getenv(
    "GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "patch-505223")
)
PUBSUB_TOPIC_PREFIX: Final[str] = os.getenv("PATCHAPI_PUBSUB_TOPIC_PREFIX", "patchapi-dev")

# The provider a caller means when it names none. Still Google, because that is
# the provider the demo subscribes to; it is a default rather than the only
# option, and `providers_for_target` resolves the real set from what a project
# subscribed to.
DEFAULT_PROVIDER: Final[str] = "google"


def _google_group(name: str) -> tuple[str, ...]:
    """One pinned identifier group from Google's descriptor.

    These names are re-exported because stored findings, the demo's expected
    results and several tests refer to a family by name. The values come from
    the descriptor so there is one place to widen a watchlist.
    """
    return registry.descriptor_for(DEFAULT_PROVIDER).identifier_group(name)


# The Imagen 4 family retired by the pinned demo change. Kept in step with
# `demo/fixtures/google-imagen4-deprecation.json`; the fixture is the provider's
# claim, the descriptor is the list PatchAPI watches for by default when no
# manifest has been supplied.
IMAGEN_4_IDENTIFIERS: Final[tuple[str, ...]] = _google_group("imagen_4")

# The Gemini 2.0 Flash family retired 2026-06-01. Kept in step with
# `demo/fixtures/google-gemini20-deprecation.json`. Without these, importing
# `storygen` indexes as ready with 0 usages and the Codebase tab looks
# like the add failed.
GEMINI_20_IDENTIFIERS: Final[tuple[str, ...]] = _google_group("gemini_20")

GEMINI_IMAGE_IDENTIFIERS: Final[tuple[str, ...]] = _google_group("gemini_image")

VERTEX_IMAGEN_IDENTIFIERS: Final[tuple[str, ...]] = _google_group("vertex_imagen")

FALSE_POSITIVE_IDENTIFIERS: Final[tuple[str, ...]] = _google_group("false_positive")

GOOGLE_WATCHED_IDENTIFIERS: Final[tuple[str, ...]] = registry.descriptor_for(
    DEFAULT_PROVIDER
).all_watched_identifiers()

# Usage kinds whose breakage takes production down, re-exported here so the
# inventory and the scanner cannot drift apart on what "runtime" means.
RUNTIME_USAGE_KINDS: Final[frozenset[UsageKind]] = frozenset(
    {UsageKind.RUNTIME_SOURCE, UsageKind.CONFIGURATION}
)

__all__ = [
    "ASTGREP_RULE_DIR",
    "DEFAULT_PROVIDER",
    "DETECTION_LAYER",
    "DETECTION_LAYERS",
    "FALSE_POSITIVE_IDENTIFIERS",
    "GEMINI_20_IDENTIFIERS",
    "GEMINI_IMAGE_IDENTIFIERS",
    "GOOGLE_WATCHED_IDENTIFIERS",
    "IMAGEN_4_IDENTIFIERS",
    "INDEXER_VERSION",
    "INDEXER_WORKDIR",
    "INDEX_BACKEND",
    "INVENTORY_VERSION",
    "LAYER_B_CONFIDENCE",
    "LITERAL_MATCH_CONFIDENCE",
    "PUBSUB_PROJECT",
    "PUBSUB_TOPIC_PREFIX",
    "RUNTIME_USAGE_KINDS",
    "SCANNER_VERSION",
    "SCOPE_CHANGED_PATHS",
    "SCOPE_FULL_TREE",
    "VERTEX_IMAGEN_IDENTIFIERS",
    "ZOEKT_INDEX_DIR",
    "ZOEKT_WEBSERVER_URL",
    "watchlist_for",
    "watchlists",
]


def watchlist_for(provider: str) -> tuple[str, ...]:
    """Return the pinned identifiers watched for `provider`.

    Fails closed: an unregistered provider is a configuration error, never an
    empty watchlist that would silently report a repository as unaffected.
    """
    try:
        return registry.descriptor_for(provider).all_watched_identifiers()
    except RegistryUnknownProviderError as exc:
        raise UnknownProviderError(str(exc)) from exc


def watchlists() -> Mapping[str, tuple[str, ...]]:
    """Every registered provider's pinned identifiers, by slug.

    A live read of the registry rather than a module constant: a descriptor
    loaded from Postgres after startup has to widen what a scan looks for
    without a redeploy, which is the whole point of descriptors being data.
    """
    return {
        descriptor.provider_id: descriptor.all_watched_identifiers()
        for descriptor in registry.descriptors()
    }
