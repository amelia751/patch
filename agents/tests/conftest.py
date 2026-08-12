"""Shared fixtures for the agent-layer tests."""

import warnings
from importlib.util import find_spec
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# A bare `uv run pytest` at the repository root syncs only the workspace root,
# which installs neither this member nor Pydantic. Stand down with a warning
# naming the verifier that does install it, rather than breaking collection for
# every other tree.
collect_ignore_glob: list[str] = []
if find_spec("pydantic") is None:
    collect_ignore_glob = ["test_*.py"]
    warnings.warn(
        "agents tests were not collected: pydantic is not installed in this environment. "
        "Run ./scripts/verify_agents_adk.sh (or `uv run --all-packages pytest agents`).",
        stacklevel=1,
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def feed_dir(repo_root: Path) -> Path:
    """Where the pinned Google deprecation fixture lives."""
    return repo_root / "demo" / "fixtures"


@pytest.fixture
def run_context(repo_root: Path, feed_dir: Path):
    from agents.context import RunContext

    return RunContext(run_id="run-test-0001", repo_root=repo_root, feed_dir=feed_dir)


@pytest.fixture
def trace():
    from agents.trace import ToolTrace

    return ToolTrace(run_id="run-test-0001")
