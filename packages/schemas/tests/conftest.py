"""Shared fixtures for the schema tests."""

import json
import warnings
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"
REPO_ROOT = Path(__file__).resolve().parents[3]

# A bare `uv run pytest` at the repo root syncs only the workspace root, which
# does not install this member or its Pydantic dependency. Rather than break
# every other tree's collection, stand down with a warning that names the
# verifier which does install it.
collect_ignore_glob: list[str] = []
if find_spec("pydantic") is None:
    collect_ignore_glob = ["test_*.py"]
    warnings.warn(
        "packages/schemas tests were not collected: pydantic is not installed in this "
        "environment. Run ./scripts/verify_packages_schemas.sh (or "
        "`uv run --all-packages pytest packages/schemas`).",
        stacklevel=1,
    )


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    return GOLDEN_DIR


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def load_golden() -> Callable[[str], dict[str, Any]]:
    """Return a loader for a golden document, decoded fresh on every call."""

    def _load(name: str) -> dict[str, Any]:
        return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))

    return _load
