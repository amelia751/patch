"""The control plane must never execute repository code (roadmap §7.2).

That constraint is only worth stating if something enforces it, so this walks
the service source and fails on any construct that could run code the process
did not ship with. Patches execute in the sandbox; this service routes HTTP.
"""

import ast
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "patchapi_control_api"

FORBIDDEN_MODULES = frozenset(
    {
        "ctypes",
        "importlib",
        "marshal",
        "multiprocessing",
        "pickle",
        "pty",
        "runpy",
        "shlex",
        "subprocess",
    }
)

FORBIDDEN_BUILTINS = frozenset({"compile", "eval", "exec", "__import__"})

# `os` is allowed for environment reads; these members are how it becomes an
# execution surface.
FORBIDDEN_OS_MEMBERS = frozenset(
    {
        "execl",
        "execle",
        "execlp",
        "execv",
        "execve",
        "execvp",
        "fork",
        "popen",
        "posix_spawn",
        "spawnl",
        "spawnv",
        "system",
    }
)


def _source_files() -> list[Path]:
    files = sorted(SOURCE_ROOT.rglob("*.py"))
    assert files, f"no service source found under {SOURCE_ROOT}"
    return files


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_module_cannot_execute_foreign_code(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in FORBIDDEN_MODULES, f"{path.name} imports {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in FORBIDDEN_MODULES, f"{path.name} imports from {node.module}"
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in FORBIDDEN_BUILTINS, f"{path.name} calls {func.id}()"
            elif isinstance(func, ast.Attribute):
                assert func.attr not in FORBIDDEN_OS_MEMBERS, f"{path.name} calls .{func.attr}()"
