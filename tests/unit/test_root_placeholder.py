"""Root workspace smoke test.

Placeholder in the sense that no product code exists yet, but it still asserts
the two things the workspace contract depends on: the interpreter is pinned to
3.12, and every declared workspace member that exists on disk carries its own
`pyproject.toml` (a bare member directory breaks `uv sync` for the whole fleet).
"""

import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _root_config() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_interpreter_is_python_312():
    assert sys.version_info[:2] == (3, 12)


def test_workspace_declares_members():
    members = _root_config()["tool"]["uv"]["workspace"]["members"]
    assert "packages/schemas" in members
    assert "services/control_api" in members
    assert "agents" in members
    assert "db" in members


def test_existing_members_own_a_pyproject():
    members = _root_config()["tool"]["uv"]["workspace"]["members"]
    incomplete = [
        member
        for member in members
        if (REPO_ROOT / member).is_dir() and not (REPO_ROOT / member / "pyproject.toml").is_file()
    ]
    assert incomplete == [], f"workspace members missing pyproject.toml: {incomplete}"
