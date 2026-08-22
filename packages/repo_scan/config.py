"""Pinned limits and traversal rules for deterministic repository scanning.

Every bound the scanner depends on lives here so no call site inlines one and
so two runs of the same commit produce byte-identical inventories.
"""

from typing import Final

# Bumped whenever a scan of the same commit could return a different set of
# hits. Stored on every inventory, and read by the indexer to decide whether a
# shard written earlier can still be trusted.
SCANNER_VERSION: Final[str] = "1.1.0"

# Directories never descended into. Vendored dependencies and build output are
# not the customer's API usage, and scanning them makes the inventory unstable.
SKIP_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".next",
        "dist",
        "build",
        "target",
        "coverage",
        ".turbo",
        "vendor",
    }
)

# Extensions the scanner reads. An allowlist rather than a denylist: an unknown
# binary format should be skipped, not guessed at.
SCANNED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".go",
        ".rb",
        ".java",
        ".kt",
        ".rs",
        ".php",
        ".cs",
        ".sh",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".env",
        ".md",
        ".mdx",
        ".txt",
    }
)

# Files without a scanned extension that still carry configuration worth
# reading. `go.mod` is here for the dependency parser, which needs the manifest
# even though nothing in it looks like a model id.
SCANNED_FILENAMES: Final[frozenset[str]] = frozenset(
    {"Dockerfile", "Makefile", ".env", "go.mod"}
)

# A file larger than this is treated as generated or vendored. Reading it would
# cost more than the signal is worth and risks pulling a bundle into evidence.
MAX_FILE_BYTES: Final[int] = 1_000_000

# Longest excerpt attached to a hit. Hits are pointers into the repository, not
# a channel for shipping source code into an agent prompt.
MAX_EXCERPT_CHARS: Final[int] = 240
