"""GitHub OAuth URL construction, without contacting GitHub."""

from pathlib import Path

from packages.auth.config import IdentityPlatformConfig, load_config
from packages.auth.errors import AuthConfigurationError
from packages.auth.github_oauth import authorization_url, install_url


def test_authorization_url_includes_client_and_state() -> None:
    config = IdentityPlatformConfig(
        github_client_id="Iv1.example",
        github_client_secret="secret",
        github_redirect_uri="http://localhost:8080/api/auth/github/callback",
    )
    url = authorization_url(config, "state-token")
    assert url.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=Iv1.example" in url
    assert "state=state-token" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fapi%2Fauth%2Fgithub%2Fcallback" in url


def test_authorization_url_refuses_an_unconfigured_client() -> None:
    try:
        authorization_url(IdentityPlatformConfig(), "state")
    except AuthConfigurationError as exc:
        assert "github-app.json" in str(exc)
    else:
        raise AssertionError("expected AuthConfigurationError")


def test_install_url_uses_the_app_slug() -> None:
    config = IdentityPlatformConfig(github_app_slug="patchapi")
    assert install_url(config) == "https://github.com/apps/patchapi/installations/new"


def test_install_url_is_absent_without_a_slug() -> None:
    assert install_url(IdentityPlatformConfig()) is None


def test_load_config_reads_github_app_json(tmp_path: Path) -> None:
    (tmp_path / ".secrets").mkdir()
    (tmp_path / ".secrets/github-app.json").write_text(
        '{"app_id": 123, "client_id": "Iv1.test", "client_secret": "s", "app_slug": "patchapi"}'
    )

    config = load_config({}, base_dir=tmp_path)

    assert config.github_client_id == "Iv1.test"
    assert config.github_client_secret == "s"
    assert config.github_app_slug == "patchapi"
    assert config.github_app_id == "123"
    assert config.github_oauth_configured() is True


def test_public_repository_projects_the_import_list_fields() -> None:
    from packages.auth.github_oauth import public_repository

    projected = public_repository(
        {
            "id": 42,
            "name": "egaki",
            "full_name": "amelia751/egaki",
            "private": True,
            "language": "TypeScript",
            "stargazers_count": 3,
            "updated_at": "2026-08-12T00:00:00Z",
            "html_url": "https://github.com/amelia751/egaki",
            "permissions": {"admin": True},
        }
    )
    assert projected == {
        "id": 42,
        "name": "egaki",
        "full_name": "amelia751/egaki",
        "private": True,
        "language": "TypeScript",
        "stargazers_count": 3,
        "updated_at": "2026-08-12T00:00:00Z",
        "html_url": "https://github.com/amelia751/egaki",
    }
    assert "permissions" not in projected


def test_public_contents_entry_keeps_dirs_and_files() -> None:
    from packages.auth.github_oauth import public_contents_entry

    assert public_contents_entry({"name": "src", "type": "dir"}) == {
        "name": "src",
        "type": "dir",
    }
    assert public_contents_entry({"name": "README.md", "type": "file"}) == {
        "name": "README.md",
        "type": "file",
    }
    assert public_contents_entry({"name": "link", "type": "symlink"}) == {
        "name": "link",
        "type": "file",
    }
    assert public_contents_entry({"name": "", "type": "dir"}) is None
    assert public_contents_entry({"name": "x", "type": "unknown"}) is None
