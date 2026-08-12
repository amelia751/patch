"""PatchAPI repository indexer.

Maintains the API usage inventory (roadmap §11) so impact analysis is an index
lookup rather than a fleet-wide clone-and-grep. Deterministic by construction:
no model runs in this service.
"""

from patchapi_repo_indexer.config import (
    DEFAULT_PROVIDER,
    INDEXER_VERSION,
    INVENTORY_VERSION,
    watchlist_for,
)
from patchapi_repo_indexer.errors import (
    IndexerError,
    ScanRootError,
    UnknownProviderError,
    UnsafePathError,
)
from patchapi_repo_indexer.index import build_inventory
from patchapi_repo_indexer.models import ApiUsageInventory, ApiUsageRecord

__all__ = [
    "DEFAULT_PROVIDER",
    "INDEXER_VERSION",
    "INVENTORY_VERSION",
    "ApiUsageInventory",
    "ApiUsageRecord",
    "IndexerError",
    "ScanRootError",
    "UnknownProviderError",
    "UnsafePathError",
    "build_inventory",
    "watchlist_for",
]
