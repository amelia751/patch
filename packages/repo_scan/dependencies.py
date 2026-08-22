"""What a checkout declares it depends on, read from the manifest that pins it.

Layer A finds a model id because the id is a literal in the source. An SDK is
not: `client.models.generate_content(...)` names no version, and the thing that
breaks when a major ships is the constraint in `package.json`, three directories
away from the call. So the manifest is its own inventory.

Parsing is structural rather than regex over the whole file — a dependency table
is machine-written and a regex would read a URL in a comment as a package. The
line number is then recovered by locating the name in the text, because a
finding without a line is not evidence a reviewer can check.

Nothing here knows which packages matter. This module answers "what does this
tree depend on"; deciding which of those belong to a watched provider is the
caller's job.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Final

from packages.repo_scan.config import MAX_EXCERPT_CHARS

NPM: Final[str] = "npm"
PYPI: Final[str] = "pypi"
GO: Final[str] = "go"

PACKAGE_JSON: Final[str] = "package.json"
PYPROJECT_TOML: Final[str] = "pyproject.toml"
GO_MOD: Final[str] = "go.mod"
REQUIREMENTS_PREFIX: Final[str] = "requirements"

_NPM_SECTIONS: Final[tuple[str, ...]] = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)

# `google-genai[aiohttp] >= 1.2, <2  # comment` -> name, then everything else.
_PEP508: Final[re.Pattern[str]] = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*(.*)$")

# A requirements line that configures pip rather than naming a package.
_PIP_DIRECTIVE: Final[tuple[str, ...]] = ("-r", "-c", "-e", "--", "#", "git+", "http:", "https:")

_GO_REQUIRE: Final[re.Pattern[str]] = re.compile(r"^\s*([\w.\-/]+\.[\w.\-/]+)\s+(v[\w.\-+]+)")


@dataclass(frozen=True, slots=True)
class DependencyHit:
    """One declared dependency, and the line of the manifest that declares it."""

    ecosystem: str
    name: str
    constraint: str
    path: str
    line_number: int
    excerpt: str


def is_manifest(filename: str) -> bool:
    """True for a file this module knows how to read."""
    if filename in {PACKAGE_JSON, PYPROJECT_TOML, GO_MOD}:
        return True
    return filename.startswith(REQUIREMENTS_PREFIX) and filename.endswith(".txt")


def _locate(text: str, name: str) -> tuple[int, str]:
    """The first line naming `name`, as a number and the text of the line.

    A structural parse knows the dependency is there but not where. Falling back
    to line 1 keeps the hit rather than dropping a real dependency over a
    cosmetic field.
    """
    for offset, line in enumerate(text.splitlines(), start=1):
        if name in line:
            return offset, line.strip()[:MAX_EXCERPT_CHARS]
    return 1, ""


def _npm_dependencies(payload: Any) -> Iterator[tuple[str, str]]:
    if not isinstance(payload, dict):
        return
    for section in _NPM_SECTIONS:
        table = payload.get(section)
        if not isinstance(table, dict):
            continue
        for name, constraint in table.items():
            if isinstance(name, str) and isinstance(constraint, str) and name.strip():
                yield name.strip(), constraint.strip()


def _pep508_entries(entries: Any) -> Iterator[tuple[str, str]]:
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, str):
            continue
        match = _PEP508.match(entry)
        if not match:
            continue
        name = match.group(1).strip()
        if name:
            yield name, match.group(2).strip()


def _pyproject_dependencies(payload: Any) -> Iterator[tuple[str, str]]:
    if not isinstance(payload, dict):
        return
    project = payload.get("project")
    if isinstance(project, dict):
        yield from _pep508_entries(project.get("dependencies"))
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for group in optional.values():
                yield from _pep508_entries(group)
    tool = payload.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    table = poetry.get("dependencies") if isinstance(poetry, dict) else None
    if isinstance(table, dict):
        for name, constraint in table.items():
            if not isinstance(name, str) or not name.strip() or name.strip() == "python":
                continue
            # Poetry allows a table for extras and markers; the version is one key.
            if isinstance(constraint, dict):
                constraint = str(constraint.get("version") or "")
            yield name.strip(), str(constraint).strip()


def _requirements_dependencies(text: str) -> Iterator[tuple[str, str, int, str]]:
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(_PIP_DIRECTIVE):
            continue
        match = _PEP508.match(line)
        if not match:
            continue
        name = match.group(1).strip()
        if name:
            yield name, match.group(2).strip(), line_number, line[:MAX_EXCERPT_CHARS]


def _go_dependencies(text: str) -> Iterator[tuple[str, str, int, str]]:
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("//", 1)[0].strip()
        if not line or line.startswith(("module ", "go ", "require (", ")")):
            continue
        match = _GO_REQUIRE.match(line.removeprefix("require "))
        if match:
            yield match.group(1), match.group(2), line_number, line[:MAX_EXCERPT_CHARS]


def parse_manifest(text: str, *, path: str) -> list[DependencyHit]:
    """Every dependency `path` declares, or nothing when it cannot be parsed.

    A malformed manifest yields no hits rather than an exception: one unreadable
    file in a monorepo must not fail the whole index.
    """
    filename = path.rsplit("/", 1)[-1]
    hits: list[DependencyHit] = []

    if filename == PACKAGE_JSON:
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return []
        pairs = list(_npm_dependencies(payload))
        ecosystem = NPM
    elif filename == PYPROJECT_TOML:
        try:
            payload = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, ValueError):
            return []
        pairs = list(_pyproject_dependencies(payload))
        ecosystem = PYPI
    elif filename.startswith(REQUIREMENTS_PREFIX) and filename.endswith(".txt"):
        return [
            DependencyHit(PYPI, name, constraint, path, line_number, excerpt)
            for name, constraint, line_number, excerpt in _requirements_dependencies(text)
        ]
    elif filename == GO_MOD:
        return [
            DependencyHit(GO, name, constraint, path, line_number, excerpt)
            for name, constraint, line_number, excerpt in _go_dependencies(text)
        ]
    else:
        return []

    seen: set[str] = set()
    for name, constraint in pairs:
        if name in seen:
            continue
        seen.add(name)
        line_number, excerpt = _locate(text, name)
        hits.append(DependencyHit(ecosystem, name, constraint, path, line_number, excerpt))
    return hits


__all__ = [
    "GO",
    "GO_MOD",
    "NPM",
    "PACKAGE_JSON",
    "PYPI",
    "PYPROJECT_TOML",
    "DependencyHit",
    "is_manifest",
    "parse_manifest",
]
