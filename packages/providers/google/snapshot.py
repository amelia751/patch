"""Hashed captures of official provider pages.

Hashing a captured page has nothing Google-specific about it, so the
implementation lives in `packages.providers.snapshot`. This module re-exports
it under the path the Google adapter and its verifier already import.
"""

from packages.providers.snapshot import (
    sha256_file,
    sha256_hex,
    snapshot_from_file,
    snapshot_matches_file,
)

__all__ = [
    "sha256_file",
    "sha256_hex",
    "snapshot_from_file",
    "snapshot_matches_file",
]
