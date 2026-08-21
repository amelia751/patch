"""Mint a short-lived GitHub App installation token for one fetch.

Hard constraint #8: this service never stores the App private key in git or
hands a token to an agent. The PEM arrives as a Cloud Run secret mount. The
token is written only to `PATCHAPI_GITHUB_INSTALLATION_TOKEN` for the process,
which `git.py` reads for a single `fetch` and never writes into `.git/config`.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import load_pem_private_key

log = logging.getLogger(__name__)

TOKEN_ENV: Final[str] = "PATCHAPI_GITHUB_INSTALLATION_TOKEN"
APP_ID_ENV: Final[str] = "GITHUB_APP_ID"
INSTALLATION_ID_ENV: Final[str] = "GITHUB_APP_INSTALLATION_ID"
PEM_PATH_ENV: Final[str] = "GITHUB_APP_PRIVATE_KEY_PATH"
API_BASE: Final[str] = os.getenv("GITHUB_API_BASE", "https://api.github.com").rstrip("/")

_JWT_LIFETIME_SECONDS: Final[int] = 540
_SKEW_SECONDS: Final[int] = 60

_cached_token: str | None = None
_cached_until: float = 0.0


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _app_jwt(app_id: str, pem: bytes) -> str:
    key = load_pem_private_key(pem, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise TypeError("the GitHub App private key must be an RSA key")
    issued_at = int(time.time()) - 60
    payload = {"iat": issued_at, "exp": issued_at + _JWT_LIFETIME_SECONDS, "iss": app_id}
    header = {"alg": "RS256", "typ": "JWT"}
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        for part in (header, payload)
    ).encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), SHA256())
    return f"{signing_input.decode('ascii')}.{_b64url(signature)}"


def _pem() -> bytes | None:
    path = os.environ.get(PEM_PATH_ENV, "").strip()
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        return None
    return file.read_bytes()


def _installation_id(app_jwt: str, repository: str | None) -> str | None:
    pinned = os.environ.get(INSTALLATION_ID_ENV, "").strip()
    if pinned:
        return pinned
    if not repository or "/" not in repository:
        return None
    owner, name = repository.split("/", 1)
    response = httpx.get(
        f"{API_BASE}/repos/{owner}/{name}/installation",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "patchapi-repo-indexer",
        },
        timeout=15.0,
    )
    if response.status_code != 200:
        log.warning(
            "could not resolve GitHub installation for %s (%s)",
            repository,
            response.status_code,
        )
        return None
    identifier = response.json().get("id")
    return str(identifier) if identifier is not None else None


def ensure_installation_token(*, repository: str | None = None) -> bool:
    """Put a usable installation token in the environment. Returns whether one is set."""
    global _cached_token, _cached_until
    existing = os.environ.get(TOKEN_ENV, "").strip()
    if existing and time.time() < _cached_until:
        return True
    if existing and _cached_token is None:
        return True

    now = time.time()
    if _cached_token and now < _cached_until:
        os.environ[TOKEN_ENV] = _cached_token
        return True

    app_id = os.environ.get(APP_ID_ENV, "").strip()
    pem = _pem()
    if not app_id or pem is None:
        return bool(os.environ.get(TOKEN_ENV, "").strip())

    try:
        jwt = _app_jwt(app_id, pem)
        installation = _installation_id(jwt, repository)
        if not installation:
            return False
        response = httpx.post(
            f"{API_BASE}/app/installations/{installation}/access_tokens",
            headers={
                "Authorization": f"Bearer {jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "patchapi-repo-indexer",
            },
            timeout=15.0,
        )
        if response.status_code != 201:
            log.warning("GitHub refused an installation token (HTTP %s)", response.status_code)
            return False
        body = response.json()
        token = str(body.get("token") or "")
        expires = body.get("expires_at")
        if not token:
            return False
        _cached_token = token
        if isinstance(expires, str):
            expiry = datetime.fromisoformat(expires.replace("Z", "+00:00")).astimezone(UTC)
            _cached_until = expiry.timestamp() - _SKEW_SECONDS
        else:
            _cached_until = now + 3000
        os.environ[TOKEN_ENV] = token
        return True
    except Exception as exc:
        log.warning("could not mint a GitHub installation token: %s", type(exc).__name__)
        return False
