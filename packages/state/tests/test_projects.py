"""Project helpers that do not need a database."""

from packages.state.projects import full_name_from_repo_url


def test_full_name_from_https_git_url() -> None:
    assert (
        full_name_from_repo_url("https://github.com/amelia751/egaki.git") == "amelia751/egaki"
    )


def test_full_name_from_bare_owner_repo() -> None:
    assert full_name_from_repo_url("amelia751/egaki") == "amelia751/egaki"


def test_full_name_rejects_a_non_github_url() -> None:
    assert full_name_from_repo_url("https://gitlab.com/amelia751/egaki") is None
