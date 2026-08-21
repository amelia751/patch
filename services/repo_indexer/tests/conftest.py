"""Trees the indexer tests run against."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_REPO = REPO_ROOT / "tests" / "fixtures" / "repo_with_imagen"


@pytest.fixture(scope="session")
def fixture_repo() -> Path:
    assert FIXTURE_REPO.is_dir(), f"fixture tree is missing: {FIXTURE_REPO}"
    return FIXTURE_REPO


@pytest.fixture
def empty_repo(tmp_path: Path) -> Path:
    """A checkout with files but no watched identifier in any of them."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text(
        'export const MODEL = "text-embedding-004";\n', encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# nothing to migrate\n", encoding="utf-8")
    return tmp_path
