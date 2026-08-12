"""Classify where in a repository a hit was found.

Roadmap §8.2: a docs-only hit must not be treated like a runtime hit. The
classification is derived from the path alone, deterministically, before any
model sees the finding — so the cheap signal is trustworthy even when the
expensive one is not.

The vocabulary mirrors `packages.schemas.enums.UsageKind`; the values are the
wire strings, and `packages/repo_scan/tests/test_scan.py` asserts they have not
drifted apart whenever the schemas package is importable.
"""

import posixpath
import re
from enum import StrEnum
from typing import Final


class UsageKind(StrEnum):
    RUNTIME_SOURCE = "runtime_source"
    CONFIGURATION = "configuration"
    TEST = "test"
    EXAMPLE = "example"
    DOCUMENTATION_EXAMPLE = "documentation_example"
    DEAD_CODE = "dead_code"


_TEST_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {"test", "tests", "__tests__", "spec", "e2e", "testdata", "fixtures"}
)
_EXAMPLE_DIRECTORIES: Final[frozenset[str]] = frozenset(
    {"example", "examples", "demo", "demos", "samples", "sample"}
)
_DOC_DIRECTORIES: Final[frozenset[str]] = frozenset({"doc", "docs", "documentation", "website"})

_TEST_FILENAME_RE: Final[re.Pattern[str]] = re.compile(
    r"(^test_|_test\.|\.test\.|\.spec\.|Test\.|Spec\.)"
)

_DOC_EXTENSIONS: Final[frozenset[str]] = frozenset({".md", ".mdx", ".txt", ".rst"})
_CONFIG_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".cfg"}
)


def classify_path(path: str) -> UsageKind:
    """Return the usage kind implied by `path`.

    Tests and examples are checked before documentation and configuration: a
    JSON fixture under `tests/` is a test, not configuration.
    """
    parts = [segment for segment in path.replace("\\", "/").split("/") if segment not in ("", ".")]
    directories = {segment.lower() for segment in parts[:-1]}
    filename = parts[-1] if parts else path
    extension = posixpath.splitext(filename)[1].lower()

    if directories & _TEST_DIRECTORIES or _TEST_FILENAME_RE.search(filename):
        return UsageKind.TEST
    if directories & _EXAMPLE_DIRECTORIES:
        return UsageKind.EXAMPLE
    if directories & _DOC_DIRECTORIES or extension in _DOC_EXTENSIONS:
        return UsageKind.DOCUMENTATION_EXAMPLE
    if extension in _CONFIG_EXTENSIONS or filename.startswith(".env"):
        return UsageKind.CONFIGURATION
    return UsageKind.RUNTIME_SOURCE


# Kinds whose breakage takes production down. Anything outside this set still
# gets reported, but it must not on its own justify an urgent migration.
RUNTIME_USAGE_KINDS: Final[frozenset[UsageKind]] = frozenset(
    {UsageKind.RUNTIME_SOURCE, UsageKind.CONFIGURATION}
)
