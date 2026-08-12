"""Installation authentication: a real RS256 JWT, a cached token, no leakage."""

import base64
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.hashes import SHA256
from patchapi_github_tools.auth import (
    InstallationAuthError,
    InstallationTokenProvider,
    build_app_jwt,
)
from patchapi_github_tools.config import APP_JWT_LIFETIME_SECONDS
from patchapi_github_tools.credentials import load_app_credentials

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _b64decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def test_app_jwt_verifies_against_the_public_key(app_env, private_key):
    credentials = load_app_credentials(app_env)
    token = build_app_jwt(credentials, now=NOW).reveal()
    header_segment, payload_segment, signature_segment = token.split(".")

    private_key.public_key().verify(
        _b64decode(signature_segment),
        f"{header_segment}.{payload_segment}".encode("ascii"),
        padding.PKCS1v15(),
        SHA256(),
    )

    assert json.loads(_b64decode(header_segment)) == {"alg": "RS256", "typ": "JWT"}
    payload = json.loads(_b64decode(payload_segment))
    assert payload["iss"] == "123456"
    # Backdated a minute against clock drift, and inside GitHub's 10-minute cap.
    assert payload["iat"] == int(NOW.timestamp()) - 60
    assert payload["exp"] - payload["iat"] == APP_JWT_LIFETIME_SECONDS
    assert payload["exp"] - int(NOW.timestamp()) < 600


def test_the_jwt_is_a_secret(app_env):
    credentials = load_app_credentials(app_env)
    assert repr(build_app_jwt(credentials, now=NOW)) == "<redacted>"


async def test_the_installation_token_is_minted_once_and_reused(app_env, fake_github):
    credentials = load_app_credentials(app_env)
    http = httpx.AsyncClient(transport=fake_github.transport())
    provider = InstallationTokenProvider(
        credentials, http=http, api_base="https://api.github.test", clock=lambda: NOW
    )

    header = await provider.authorization_header()
    assert header.startswith("Bearer ghs_")
    for _ in range(3):
        assert await provider.authorization_header() == header
    assert fake_github.token_mints == 1


async def test_an_expiring_token_is_replaced(app_env, fake_github):
    credentials = load_app_credentials(app_env)
    http = httpx.AsyncClient(transport=fake_github.transport())
    clock = {"now": datetime.now(UTC)}
    provider = InstallationTokenProvider(
        credentials, http=http, api_base="https://api.github.test", clock=lambda: clock["now"]
    )

    await provider.token()
    assert fake_github.token_mints == 1
    # Past the skew window the cached token is no longer usable.
    clock["now"] = clock["now"] + timedelta(minutes=61)
    await provider.token()
    assert fake_github.token_mints == 2


async def test_a_refused_mint_carries_no_credential_material(app_env):
    credentials = load_app_credentials(app_env)

    def refuse(request: httpx.Request) -> httpx.Response:
        # A hostile upstream that echoes the request back.
        return httpx.Response(401, json={"message": dict(request.headers)})

    http = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    provider = InstallationTokenProvider(
        credentials, http=http, api_base="https://api.github.test", clock=lambda: NOW
    )
    with pytest.raises(InstallationAuthError) as failure:
        await provider.token()
    message = str(failure.value)
    assert "HTTP 401" in message
    assert "Bearer" not in message
    assert "PRIVATE KEY" not in message
