"""The API usage inventory contract (roadmap §11.1).

One row per literal provider identifier occurrence, shaped to the
`provider_usages` table in `db/migrations/0007_provider_usages.sql` so
persisting an inventory is a column-for-column write rather than a translation.
The document carries no timestamp: two indexes of the same commit must
serialize identically, and when a row was first or last seen is the database's
business, not the scanner's.
"""

from typing import Annotated, Literal

from pydantic import Field

from packages.repo_scan.classify import UsageKind
from packages.schemas.base import StrictModel
from packages.schemas.fields import (
    GitSha,
    Identifier,
    ProviderId,
    RepoFullName,
    RepoRelativePath,
)
from patchapi_repo_indexer.config import (
    DETECTION_LAYER,
    INDEXER_VERSION,
    INVENTORY_VERSION,
    RUNTIME_USAGE_KINDS,
    SCANNER_VERSION,
    SCOPE_CHANGED_PATHS,
    SCOPE_FULL_TREE,
)

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]

# Longest excerpt an inventory row carries. Rows are pointers into a checkout,
# not a channel for shipping source into an agent prompt; the scanner already
# truncates, and this bound makes the contract say so too.
MAX_EXCERPT_CHARS = 240


class ApiUsageRecord(StrictModel):
    """One deterministic occurrence of a watched provider identifier."""

    provider: ProviderId
    identifier: Identifier
    # Set only when the hit describes a call shape or a model family rather than
    # a literal string. Layer A never fills it in; Layers B and C may.
    surface: str | None = None
    file_path: RepoRelativePath
    line_start: int = Field(ge=1)
    line_end: int | None = Field(default=None, ge=1)
    usage_kind: UsageKind
    detection_layer: Literal[DETECTION_LAYER] = DETECTION_LAYER
    confidence: Confidence
    excerpt: str = Field(max_length=MAX_EXCERPT_CHARS)

    @property
    def is_runtime(self) -> bool:
        """True when breakage here reaches production rather than a doc page."""
        return self.usage_kind in RUNTIME_USAGE_KINDS


class ApiUsageInventory(StrictModel):
    """Every watched identifier found in one repository at one commit.

    An inventory with no usages is a real answer — this repository does not use
    the watched identifiers — and is distinguishable from a failed scan because
    a failed scan raises instead of returning.
    """

    inventory_version: Literal[INVENTORY_VERSION] = INVENTORY_VERSION
    indexer_version: Literal[INDEXER_VERSION] = INDEXER_VERSION
    # The Layer A scanner build that produced the hits. Pinned separately from
    # the indexer: a scanner change can move findings without changing this
    # service.
    scanner_version: Literal[SCANNER_VERSION] = SCANNER_VERSION
    repository: RepoFullName
    # Branch the tree was read at. Defaults to `main` so Layer A inventories
    # produced before the indexer knew about branches still validate.
    branch: str = "main"
    observed_sha: GitSha
    provider: ProviderId
    watched_identifiers: tuple[Identifier, ...]
    # `changed_paths` inventories describe only the files a push touched, so a
    # consumer must not read one as the repository's complete usage.
    scope: Literal[SCOPE_FULL_TREE, SCOPE_CHANGED_PATHS]
    files_scanned: int = Field(ge=0)
    usages: tuple[ApiUsageRecord, ...] = ()

    @property
    def matched_identifiers(self) -> tuple[str, ...]:
        return tuple(sorted({usage.identifier for usage in self.usages}))

    @property
    def runtime_usages(self) -> tuple[ApiUsageRecord, ...]:
        return tuple(usage for usage in self.usages if usage.is_runtime)

    @property
    def is_empty(self) -> bool:
        return not self.usages
