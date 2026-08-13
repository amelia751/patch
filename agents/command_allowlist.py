"""The commands the Patch agent may propose. Everything else is refused.

Roadmap §8.4: `run_command` driven by a model that has read untrusted provider
text is arbitrary code execution unless something bounds it. The agent proposes;
only these argv shapes execute. Matching is on the split argv, never on a
shell string, so `pnpm install --frozen-lockfile; curl …` cannot sneak through
as a suffix of an allowed command.

`cat` / `ls` / `grep` are omitted on purpose. `read_file` and `list_dir` cover
inspection without giving the model a second, less-bounded read path.
"""

from dataclasses import dataclass
from typing import Final

from packages.policy.globs import normalize_path


@dataclass(frozen=True)
class AllowedCommand:
    """One argv shape the Patch agent may run, and how long it may take."""

    argv: tuple[str, ...]
    timeout_seconds: int
    reason: str


# Exact matches. Order is the audit order: the first match is the one named.
_EXACT: Final[tuple[AllowedCommand, ...]] = (
    AllowedCommand(
        argv=("pnpm", "install", "--frozen-lockfile"),
        timeout_seconds=900,
        reason="install workspace dependencies from the lockfile",
    ),
    AllowedCommand(
        argv=("node", "--version"),
        timeout_seconds=10,
        reason="confirm the Node toolchain",
    ),
    AllowedCommand(
        argv=("python3", "--version"),
        timeout_seconds=10,
        reason="confirm the Python toolchain",
    ),
    AllowedCommand(
        argv=("python", "--version"),
        timeout_seconds=10,
        reason="confirm the Python toolchain",
    ),
)


class CommandNotAllowedError(ValueError):
    """The proposed argv is not on the allowlist."""


def _safe_relative(path: str) -> str:
    """Return `path` if it is a single relative path with no traversal."""
    if not path or path.startswith("-") or path.startswith("/"):
        raise CommandNotAllowedError(f"path {path!r} is not a safe relative path")
    try:
        return normalize_path(path)
    except ValueError as exc:
        raise CommandNotAllowedError(str(exc)) from exc


def match_command(argv: list[str]) -> AllowedCommand:
    """Return the allowlist entry for `argv`, or raise `CommandNotAllowedError`."""
    if not argv:
        raise CommandNotAllowedError("empty command")

    exact = tuple(argv)
    for rule in _EXACT:
        if exact == rule.argv:
            return rule

    # pnpm --dir <rel> build
    if len(argv) == 4 and argv[0] == "pnpm" and argv[1] == "--dir" and argv[3] == "build":
        _safe_relative(argv[2])
        return AllowedCommand(
            argv=tuple(argv),
            timeout_seconds=300,
            reason="build one package in the workspace",
        )

    # pnpm --dir <rel> test
    # pnpm --dir <rel> test -- <rel>
    if len(argv) in {4, 6} and argv[0] == "pnpm" and argv[1] == "--dir" and argv[3] == "test":
        _safe_relative(argv[2])
        if len(argv) == 6:
            if argv[4] != "--":
                raise CommandNotAllowedError("extra pnpm test arguments must be '-- <test-path>'")
            _safe_relative(argv[5])
        return AllowedCommand(
            argv=tuple(argv),
            timeout_seconds=300,
            reason="run one package's tests in the workspace",
        )

    raise CommandNotAllowedError(f"command {argv!r} is not on the Patch agent allowlist")


__all__ = ["AllowedCommand", "CommandNotAllowedError", "match_command"]
