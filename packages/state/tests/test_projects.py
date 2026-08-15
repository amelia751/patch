"""Project helpers that do not need a database."""

from pathlib import Path

from packages.state.projects import full_name_from_repo_url

PROJECTS_PY = Path(__file__).resolve().parents[1] / "projects.py"


def test_full_name_from_https_git_url() -> None:
    assert (
        full_name_from_repo_url("https://github.com/amelia751/egaki.git") == "amelia751/egaki"
    )


def test_full_name_from_bare_owner_repo() -> None:
    assert full_name_from_repo_url("amelia751/egaki") == "amelia751/egaki"


def test_full_name_rejects_a_non_github_url() -> None:
    assert full_name_from_repo_url("https://gitlab.com/amelia751/egaki") is None


def test_add_repository_writes_the_same_workspace_row_as_import() -> None:
    """Add Repository used to insert only `project_repositories`.

    Import Project also writes `workspaces`. Without that second row the
    Codebase tab kept the first import and Configure had nothing to bind the
    new repo to — the add looked like it had failed.
    """
    source = PROJECTS_PY.read_text(encoding="utf-8")
    start = source.index("async def add_repository")
    body = source[start : start + 4500]
    assert "INSERT INTO workspaces" in body
    assert "repository_id" in body
