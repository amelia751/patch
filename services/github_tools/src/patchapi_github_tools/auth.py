"""GitHub App installation authentication.

Two short-lived credentials, neither of which leaves this module in readable
form: an RS256 JWT proving we are the App, exchanged for an installation token
scoped to the one installation the App is installed on (roadmap §14).

The JWT is assembled here rather than through a JWT library: the payload is
three claims, `cryptography` is already a workspace dependency, and adding a
signing library would widen the credential-handling surface for no gain.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from patchapi_github_tools.config import (
    APP_JWT_LIFETIME_SECONDS,
    GITHUB_API_VERSION,
    INSTALLATION_TOKEN_SKEW_SECONDS,
    USER_AGENT,
)
from patchapi_github_tools.credentials import AppCredentials, Secret

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def build_app_jwt(credentials: AppCredentials, *, now: datetime) -> Secret:
    """Sign the App-level JWT GitHub accepts in place of a token.

    `iat` is backdated by a minute because GitHub rejects a JWT issued in its
    own future, and the two clocks are not the same clock.
    """
    key = load_pem_private_key(credentials.private_key_pem.reveal().encode("utf-8"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError("the GitHub App private key must be an RSA key")

    issued_at = int(now.timestamp()) - 60
    payload = {
        "iat": issued_at,
        "exp": issued_at + APP_JWT_LIFETIME_SECONDS,
        "iss": credentials.app_id,
    }
    header = {"alg": "RS256", "typ": "JWT"}
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        for part in (header, payload)
    ).encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), SHA256())
    return Secret(f"{signing_input.decode('ascii')}.{_b64url(signature)}")


@dataclass(frozen=True, slots=True)
class InstallationToken:
    token: Secret
    expires_at: datetime

    def is_usable(self, now: datetime) -> bool:
        return now < self.expires_at - timedelta(seconds=INSTALLATION_TOKEN_SKEW_SECONDS)

    def __repr__(self) -> str:
        return f"InstallationToken(expires_at={self.expires_at.isoformat()})"


class InstallationTokenProvider:
    """Mints and caches the installation token used by every GitHub call.

    The token stays in this object. Callers get an `Authorization` header value
    from `authorization_header`; nothing hands back a bare string that could be
    logged or forwarded into a prompt.
    """

    def __init__(
        self,
        credentials: AppCredentials,
        *,
        http: httpx.AsyncClient,
        api_base: str,
        clock: Clock = _utcnow,
    ) -> None:
        self._credentials = credentials
        self._http = http
        self._api_base = api_base.rstrip("/")
        self._clock = clock
        self._cached: InstallationToken | None = None
        self._lock = asyncio.Lock()

    @property
    def installation_id(self) -> str:
        return self._credentials.installation_id

    async def token(self) -> Secret:
        """Return a usable installation token, minting one if needed."""
        async with self._lock:
            now = self._clock()
            if self._cached is not None and self._cached.is_usable(now):
                return self._cached.token
            self._cached = await self._mint(now)
            return self._cached.token

    async def authorization_header(self) -> str:
        return f"Bearer {(await self.token()).reveal()}"

    async def _mint(self, now: datetime) -> InstallationToken:
        app_jwt = build_app_jwt(self._credentials, now=now)
        installation = self._credentials.installation_id
        url = f"{self._api_base}/app/installations/{installation}/access_tokens"
        response = await self._http.post(
            url,
            headers={
                "Authorization": f"Bearer {app_jwt.reveal()}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "User-Agent": USER_AGENT,
            },
        )
        if response.status_code != httpx.codes.CREATED:
            # The body may echo request headers; only the status crosses this
            # boundary so a failure cannot leak the JWT it was sent with.
            raise InstallationAuthError(
                f"GitHub refused the installation token request (HTTP {response.status_code})"
            )
        body = response.json()
        return InstallationToken(
            token=Secret(body["token"]),
            expires_at=datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00")),
        )


class InstallationAuthError(RuntimeError):
    """The installation token could not be minted. Carries no credential material."""
