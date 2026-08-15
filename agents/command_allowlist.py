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


# The only interpreter that may be handed a script. `python` is absent
# deliberately: the exact `python --version` probe below is a toolchain check,
# and a second name that can execute a file doubles the shape to reason about.
_SCRIPT_INTERPRETER: Final[str] = "python3"

_PYTHON_SUFFIX: Final[str] = ".py"


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


def _safe_python_file(path: str) -> str:
    """Return `path` if it is a relative `.py` file inside the workspace.

    The suffix check is what separates a script argument from a module or an
    interpreter flag: `-c`, `-m`, and `http.server` all fail here, so the only
    thing `python3` can be pointed at is a file the workspace already contains.
    """
    cleaned = _safe_relative(path)
    if not cleaned.endswith(_PYTHON_SUFFIX):
        raise CommandNotAllowedError(f"{path!r} is not a {_PYTHON_SUFFIX} file in the workspace")
    return cleaned


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

    # python3 <script.py>
    if len(argv) == 2 and argv[0] == _SCRIPT_INTERPRETER:
        _safe_python_file(argv[1])
        return AllowedCommand(
            argv=tuple(argv),
            timeout_seconds=120,
            reason="run one Python entry point in the workspace",
        )

    # python3 -m unittest <test.py>
    if (
        len(argv) == 4
        and argv[0] == _SCRIPT_INTERPRETER
        and argv[1] == "-m"
        and argv[2] == "unittest"
    ):
        _safe_python_file(argv[3])
        return AllowedCommand(
            argv=tuple(argv),
            timeout_seconds=300,
            reason="run one unittest module in the workspace",
        )

    raise CommandNotAllowedError(f"command {argv!r} is not on the Patch agent allowlist")


__all__ = ["AllowedCommand", "CommandNotAllowedError", "match_command"]
