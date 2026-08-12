"""Google OAuth URL construction, without contacting Google."""

from packages.auth.config import IdentityPlatformConfig
from packages.auth.errors import AuthConfigurationError
from packages.auth.google_oauth import authorization_url


def test_authorization_url_includes_client_and_state() -> None:
    config = IdentityPlatformConfig(
        google_client_id="client.apps.googleusercontent.com",
        google_client_secret="secret",
        google_redirect_uri="http://localhost:8080/api/auth/google/callback",
    )
    url = authorization_url(config, "state-token")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=client.apps.googleusercontent.com" in url
    assert "state=state-token" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fapi%2Fauth%2Fgoogle%2Fcallback" in url


def test_authorization_url_refuses_an_unconfigured_client() -> None:
    try:
        authorization_url(IdentityPlatformConfig(), "state")
    except AuthConfigurationError as exc:
        assert "google-oauth.json" in str(exc)
    else:
        raise AssertionError("expected AuthConfigurationError")
