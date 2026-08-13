"""Zoekt integration — Layer A as an index rather than a walk (repo-indexer.md §5.2).

Split three ways so the failure modes stay separable: `shard` owns the on-disk
index lifecycle, `query` owns the read path, and `patterns` owns the versioned
regexes. A caller that cannot reach any of them gets `ZoektUnavailableError` and
degrades to the literal scanner; it never gets an empty result.
"""

from patchapi_repo_indexer.zoekt.patterns import (
    GOOGLE_IMAGEN_FAMILY,
    GOOGLE_IMAGEN_PREVIEW,
    PATTERNS_VERSION,
    match_identifiers,
    patterns_for,
)
from patchapi_repo_indexer.zoekt.query import (
    ZoektMatch,
    repository_file_count,
    search,
    search_shards,
)
from patchapi_repo_indexer.zoekt.shard import (
    ShardInfo,
    ShardRef,
    delta_index,
    index_repository,
    shard_info,
    shard_path_for,
)

__all__ = [
    "GOOGLE_IMAGEN_FAMILY",
    "GOOGLE_IMAGEN_PREVIEW",
    "PATTERNS_VERSION",
    "ShardInfo",
    "ShardRef",
    "ZoektMatch",
    "delta_index",
    "index_repository",
    "match_identifiers",
    "patterns_for",
    "repository_file_count",
    "search",
    "search_shards",
    "shard_info",
    "shard_path_for",
]
