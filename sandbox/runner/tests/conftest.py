"""Test fixtures for the sandbox runner.

`sandbox/` is a namespace package with no distribution of its own, so the
repository root is placed on `sys.path` here rather than by an install step.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PLANS_DIR = REPO_ROOT / "sandbox" / "runner" / "plans"
FIXTURE_DIR = REPO_ROOT / "sandbox" / "runner" / "testdata" / "image_service"


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture
def plans_dir():
    return PLANS_DIR


@pytest.fixture
def fixture_dir():
    return FIXTURE_DIR


@pytest.fixture
def sandbox_root(tmp_path):
    """A sandbox root outside the repository, as every real run requires."""

    root = tmp_path / "sandbox-root"
    root.mkdir()
    return root
