"""Shared fixtures for the Google provider adapter tests."""

import warnings
from importlib.util import find_spec
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "golden"
REPO_ROOT = Path(__file__).resolve().parents[4]

# A bare `uv run pytest` at the repo root syncs only the workspace root, which
# installs neither this member nor Pydantic. Stand down with a warning that
# names the verifier which does install it, rather than breaking collection for
# every other tree.
collect_ignore_glob: list[str] = []
if find_spec("pydantic") is None:
    collect_ignore_glob = ["test_*.py"]
    warnings.warn(
        "packages/providers tests were not collected: pydantic is not installed in this "
        "environment. Run ./scripts/verify_packages_providers_google.sh (or "
        "`uv run --all-packages pytest packages/providers`).",
        stacklevel=1,
    )


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    return GOLDEN_DIR


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def demo_fixture_path(repo_root: Path) -> Path:
    """The pinned Google deprecation fixture the demo runs against."""
    return repo_root / "demo" / "fixtures" / "google-imagen4-deprecation.json"
