"""Errors raised by the indexer.

Each one names a precondition the indexer refuses to guess at. An indexer that
returns an empty inventory because it could not read the tree looks exactly
like a repository that is not affected, so these are raised rather than logged.
"""


class IndexerError(Exception):
    """Base class for every indexer failure."""


class UnknownProviderError(IndexerError):
    """No watchlist is pinned for the requested provider."""


class ScanRootError(IndexerError):
    """The requested scan root is missing or is not a directory."""


class UnsafePathError(IndexerError):
    """A supplied path escapes the scan root."""
