"""Project helpers that do not need a database."""

from pathlib import Path

from packages.state.projects import full_name_from_repo_url

PROJECTS_PY = Path(__file__).resolve().parents[1] / "projects.py"
PROJECT_ROUTES_PY = Path(__file__).resolve().parents[1] / "project_routes.py"


def test_full_name_from_https_git_url() -> None:
    assert (
        full_name_from_repo_url("https://github.com/amelia751/egaki.git") == "amelia751/egaki"
    )


def test_full_name_from_bare_owner_repo() -> None:
    assert full_name_from_repo_url("amelia751/egaki") == "amelia751/egaki"


def test_full_name_rejects_a_non_github_url() -> None:
    assert full_name_from_repo_url("https://gitlab.com/amelia751/egaki") is None


def test_update_cloud_provider_writes_the_enum_column() -> None:
    """Configure → Connection calls PATCH /cloud-provider.

    Without this write the dialog looked like it saved and the tab stayed
    on 'No cloud connection'.
    """
    source = PROJECTS_PY.read_text(encoding="utf-8")
    start = source.index("async def update_project_cloud_provider")
    body = source[start : start + 1800]
    assert "SET cloud_provider = $3::cloud_provider" in body
    assert '{"aws", "gcp"}' in body or "('aws', 'gcp')" in body


def test_cloud_provider_route_is_a_patch() -> None:
    source = PROJECT_ROUTES_PY.read_text(encoding="utf-8")
    assert '@router.patch("/{project_id}/cloud-provider")' in source
    assert "update_project_cloud_provider" in source


def test_subscribe_kicks_off_a_findings_backfill() -> None:
    source = PROJECT_ROUTES_PY.read_text(encoding="utf-8")
    assert '@router.put("/{project_id}/providers/{slug}")' in source
    assert "backfill_project" in source
    assert '@router.get("/{project_id}/changes")' in source
    assert "inbox_payload" in source


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
