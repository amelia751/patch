"""OAuth callback host selection, without contacting Google or GitHub."""

from starlette.requests import Request

from packages.state.auth_routes import _oauth_callback_uri

_GITHUB = "/api/auth/github/callback"
_HTTPS = "https://patchapi-api-913371146929.us-central1.run.app/api/auth/github/callback"
_LOCAL = "http://localhost:8080/api/auth/github/callback"


def _request(url: str, *, forwarded_proto: str | None = None) -> Request:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_proto:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode()))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": parsed.scheme,
            "path": parsed.path or "/",
            "raw_path": (parsed.path or "/").encode(),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 123),
            "server": (parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)),
        }
    )


def test_https_fallback_wins_over_http_container_url() -> None:
    request = _request("http://patchapi-api-913371146929.us-central1.run.app/")
    assert _oauth_callback_uri(request, _GITHUB, _HTTPS) == _HTTPS


def test_localhost_follows_the_browser_host() -> None:
    request = _request("http://127.0.0.1:8080/")
    assert _oauth_callback_uri(request, _GITHUB, _LOCAL) == (
        "http://127.0.0.1:8080/api/auth/github/callback"
    )


def test_forwarded_proto_upgrades_http_when_fallback_is_local() -> None:
    request = _request("http://127.0.0.1:8080/", forwarded_proto="https")
    assert _oauth_callback_uri(request, _GITHUB, _LOCAL) == (
        "https://127.0.0.1:8080/api/auth/github/callback"
    )
