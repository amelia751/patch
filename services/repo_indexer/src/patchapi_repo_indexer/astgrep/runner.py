"""Run ast-grep rules over Layer A candidates (repo-indexer.md §5.3).

Layer B answers a question Layer A cannot: is this line a call site, or is it
prose that happens to contain a model ID? It is a precision layer, so its
absence costs ranking, never recall — a missing binary skips Layer B and the
Layer A findings stand.

`ast-grep scan --json=stream` emits one JSON object per line, so a large result
set is consumed as it arrives instead of buffered whole.
"""

import json
import logging
import shutil
import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from patchapi_repo_indexer.config import ASTGREP_RULE_DIR
from patchapi_repo_indexer.errors import AstGrepRuleError

log = logging.getLogger(__name__)

AST_GREP_BINARY: Final[str] = "ast-grep"

# Rules ship with the service so the sandbox and the indexer match a call site
# with the same file (repo-indexer.md §7.5). One subdirectory per provider,
# named by that provider's descriptor: running every provider's rules against
# every candidate would confirm a Stripe finding with a Google rule and put
# cross-provider noise in front of a reviewer.
DEFAULT_RULE_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "rules"

RULE_SUFFIXES: Final[tuple[str, ...]] = (".yml", ".yaml")

SCAN_TIMEOUT_SECONDS: Final[int] = 300

# ast-grep is handed candidate files, not a tree, so the list is short in the
# normal case. The batch bound exists for the pathological push that touches
# thousands of files and would otherwise exceed the argument limit.
MAX_FILES_PER_INVOCATION: Final[int] = 200

_STDERR_TAIL_CHARS: Final[int] = 500


@dataclass(frozen=True, slots=True)
class StructuralMatch:
    """One rule match, located by repo-relative path and line range."""

    rule_id: str
    path: str
    line_start: int
    line_end: int
    text: str


def available() -> bool:
    """True when the ast-grep binary is on PATH."""
    return shutil.which(AST_GREP_BINARY) is not None


def rule_root() -> Path:
    """The directory holding every provider's rule subdirectory."""
    return Path(ASTGREP_RULE_DIR) if ASTGREP_RULE_DIR else DEFAULT_RULE_DIR


def configured_rule_dir(provider: str) -> Path | None:
    """The rules for `provider`, or `None` when it ships none.

    `None` rather than an error. Layer B is precision: a provider whose call
    shapes nobody has written rules for still gets its Layer A findings, just
    unconfirmed. Raising here would turn "we have not written those rules yet"
    into a failed index.
    """
    from packages.providers import registry

    candidate = rule_root() / registry.descriptor_for(provider).namespace
    return candidate if candidate.is_dir() else None


def rule_files(directory: Path) -> tuple[Path, ...]:
    """Return the rule files in `directory`, sorted.

    A missing directory is a configuration error rather than an empty rule set:
    silently running no rules would report every candidate as unconfirmed.
    """
    if not directory.is_dir():
        raise AstGrepRuleError(f"ast-grep rule directory does not exist: {directory}")
    found = tuple(
        sorted(path for path in directory.iterdir() if path.suffix.lower() in RULE_SUFFIXES)
    )
    if not found:
        raise AstGrepRuleError(f"ast-grep rule directory holds no rules: {directory}")
    return found


def _parse_stream(stdout: str, rule_id: str) -> Iterator[StructuralMatch]:
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        path = entry.get("file")
        span = entry.get("range") or {}
        start = span.get("start") or {}
        end = span.get("end") or {}
        if not isinstance(path, str) or not isinstance(start.get("line"), int):
            continue
        # ast-grep reports 0-based lines; the inventory is 1-based everywhere.
        line_start = start["line"] + 1
        line_end = end["line"] + 1 if isinstance(end.get("line"), int) else line_start
        yield StructuralMatch(
            rule_id=entry.get("ruleId") or rule_id,
            path=Path(path).as_posix(),
            line_start=line_start,
            line_end=line_end,
            text=entry.get("text") or "",
        )


def _run_rule(binary: str, rule: Path, batch: Sequence[Path], root: Path) -> list[StructuralMatch]:
    command = [
        binary,
        "scan",
        "--rule",
        str(rule),
        "--json=stream",
        *(str(path) for path in batch),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=SCAN_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise AstGrepRuleError(f"ast-grep failed to run rule {rule.name}: {exc}") from exc

    matches = list(_parse_stream(completed.stdout, rule.stem))
    if completed.returncode != 0 and not matches:
        tail = (completed.stderr or "").strip()[-_STDERR_TAIL_CHARS:]
        raise AstGrepRuleError(f"ast-grep rejected rule {rule.name}: {tail}")
    return matches


def scan_files(rule_dir: Path, files: Sequence[Path], root: Path) -> list[StructuralMatch]:
    """Confirm which of `files` structurally match the rules in `rule_dir`.

    Returns an empty list when ast-grep is not installed: Layer B sharpens Layer
    A, and a repository must not be reported differently because a binary is
    missing from the image.

    Paths are reported relative to `root`, so a match lines up with an inventory
    row without the caller re-deriving the repository layout.
    """
    binary = shutil.which(AST_GREP_BINARY)
    if binary is None:
        log.info("ast-grep is not installed; skipping Layer B structural confirmation")
        return []
    if not files:
        return []

    relative: list[Path] = []
    for candidate in files:
        try:
            relative.append(Path(candidate).resolve().relative_to(root.resolve()))
        except ValueError:
            # A candidate outside the scanned tree is not this scan's business.
            continue

    matches: list[StructuralMatch] = []
    for rule in rule_files(rule_dir):
        for offset in range(0, len(relative), MAX_FILES_PER_INVOCATION):
            batch = relative[offset : offset + MAX_FILES_PER_INVOCATION]
            matches.extend(_run_rule(binary, rule, batch, root))

    matches.sort(key=lambda match: (match.path, match.line_start, match.rule_id))
    return matches


__all__ = [
    "AST_GREP_BINARY",
    "DEFAULT_RULE_DIR",
    "MAX_FILES_PER_INVOCATION",
    "RULE_SUFFIXES",
    "SCAN_TIMEOUT_SECONDS",
    "StructuralMatch",
    "available",
    "configured_rule_dir",
    "rule_files",
    "rule_root",
    "scan_files",
]
