"""Resolved Identity Platform configuration.

The Web API key is not a secret in the way a service-account key is — Firebase
embeds it in shipped client bundles, and the browser needs it too. It still
resolves from `.secrets/` here rather than being inlined, so that one file is
the single place a key is rotated for both the browser and the control plane.

Three sources are read in falling priority so a deployment can supply the key
however it already supplies configuration, without this package caring which:

1. `PATCHAPI_IDENTITY_API_KEY` — what Cloud Run and CI set.
2. `.secrets/identity_platform_api_key.txt` — the key alone, no parsing.
3. `.secrets/identity-platform.json` — the Firebase web-config blob.

The admin credential is different in kind and is never resolved here: it stays
a service-account key referenced by `GOOGLE_APPLICATION_CREDENTIALS`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from packages.auth.errors import AuthConfigurationError

ENV_API_KEY: Final[str] = "PATCHAPI_IDENTITY_API_KEY"
ENV_API_KEY_FILE: Final[str] = "PATCHAPI_IDENTITY_API_KEY_FILE"
ENV_CONFIG_FILE: Final[str] = "PATCHAPI_IDENTITY_CONFIG"
ENV_PROJECT: Final[str] = "GCP_PROJECT"
ENV_CREDENTIALS: Final[str] = "GOOGLE_APPLICATION_CREDENTIALS"
ENV_ACTION_URL: Final[str] = "PATCHAPI_IDENTITY_ACTION_URL"
ENV_GOOGLE_OAUTH: Final[str] = "PATCHAPI_GOOGLE_OAUTH"
ENV_GOOGLE_CLIENT_ID: Final[str] = "PATCHAPI_GOOGLE_OAUTH_CLIENT_ID"
ENV_GOOGLE_CLIENT_SECRET: Final[str] = "PATCHAPI_GOOGLE_OAUTH_CLIENT_SECRET"
ENV_GOOGLE_REDIRECT: Final[str] = "PATCHAPI_GOOGLE_OAUTH_REDIRECT_URI"
ENV_GITHUB_APP: Final[str] = "PATCHAPI_GITHUB_APP"
ENV_GITHUB_CLIENT_ID: Final[str] = "PATCHAPI_GITHUB_OAUTH_CLIENT_ID"
ENV_GITHUB_CLIENT_SECRET: Final[str] = "PATCHAPI_GITHUB_OAUTH_CLIENT_SECRET"
ENV_GITHUB_REDIRECT: Final[str] = "PATCHAPI_GITHUB_OAUTH_REDIRECT_URI"
ENV_GITHUB_APP_ID: Final[str] = "GITHUB_APP_ID"
ENV_GITHUB_PRIVATE_KEY: Final[str] = "GITHUB_APP_PRIVATE_KEY_PATH"
ENV_FRONTEND_ORIGIN: Final[str] = "PATCHAPI_FRONTEND_ORIGIN"

DEFAULT_API_KEY_FILE: Final[str] = ".secrets/identity_platform_api_key.txt"
DEFAULT_CONFIG_FILE: Final[str] = ".secrets/identity-platform.json"
DEFAULT_GOOGLE_OAUTH_FILE: Final[str] = ".secrets/google-oauth.json"
DEFAULT_GOOGLE_REDIRECT: Final[str] = "http://localhost:8080/api/auth/google/callback"
DEFAULT_GITHUB_APP_FILE: Final[str] = ".secrets/github-app.json"
DEFAULT_GITHUB_REDIRECT: Final[str] = "http://localhost:8080/api/auth/github/callback"
DEFAULT_GITHUB_PRIVATE_KEY: Final[str] = ".secrets/github-app.pem"
DEFAULT_FRONTEND_ORIGIN: Final[str] = "http://localhost:3000"

# Where Google's verification and reset emails send the browser back to. The
# host must also be listed in the project's authorized domains, or Identity
# Platform refuses to mint the link at all.
DEFAULT_ACTION_URL: Final[str] = "http://localhost:3000/auth/action"

IDENTITY_TOOLKIT_BASE: Final[str] = "https://identitytoolkit.googleapis.com/v1"
SECURE_TOKEN_URL: Final[str] = "https://securetoken.googleapis.com/v1/token"

# Admin calls authenticate as the service account, not with the API key.
ADMIN_SCOPES: Final[tuple[str, ...]] = ("https://www.googleapis.com/auth/cloud-platform",)

DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0


@dataclass(frozen=True)
class IdentityPlatformConfig:
    """Everything one Identity Platform session needs.

    `api_key` stays optional so an offline test can build a config and assert
    on `is_configured()` without a key present anywhere on the machine.
    """

    api_key: str | None = None
    project: str | None = None
    auth_domain: str | None = None
    credentials_path: Path | None = None
    action_url: str = DEFAULT_ACTION_URL
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = DEFAULT_GOOGLE_REDIRECT
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_redirect_uri: str = DEFAULT_GITHUB_REDIRECT
    github_app_slug: str | None = None
    github_app_id: str | None = None
    github_private_key_path: Path | None = None
    frontend_origin: str = DEFAULT_FRONTEND_ORIGIN
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def is_configured(self) -> bool:
        """Whether a live call can be attempted at all."""
        return bool(self.api_key and self.project)

    def google_oauth_configured(self) -> bool:
        """Whether Continue with Google can start an authorization-code flow."""
        return bool(self.google_client_id and self.google_client_secret)

    def github_oauth_configured(self) -> bool:
        """Whether Continue with GitHub can start the App's user-to-server flow."""
        return bool(self.github_client_id and self.github_client_secret)

    def github_app_jwt_configured(self) -> bool:
        """Whether the App private key can look up installations (no user token)."""
        return bool(
            self.github_app_id
            and self.github_private_key_path is not None
            and self.github_private_key_path.is_file()
        )

    def require_api_key(self) -> str:
        if not self.api_key:
            raise AuthConfigurationError(
                f"no Identity Platform API key; set {ENV_API_KEY} or write "
                f"{DEFAULT_API_KEY_FILE} (see .env.example)"
            )
        return self.api_key

    def require_project(self) -> str:
        if not self.project:
            raise AuthConfigurationError(
                f"no GCP project configured; set {ENV_PROJECT} (see .env.example)"
            )
        return self.project

    def url(self, method: str) -> str:
        """Key-authenticated Identity Toolkit endpoint for `method`."""
        return f"{IDENTITY_TOOLKIT_BASE}/accounts:{method}?key={self.require_api_key()}"

    def admin_url(self, path: str) -> str:
        """Service-account-authenticated endpoint under this project."""
        return f"{IDENTITY_TOOLKIT_BASE}/projects/{self.require_project()}/{path}"


def _read_api_key_file(path: Path) -> str | None:
    """Read a key-only file, tolerating the trailing newline a shell redirect adds."""
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def _read_web_config(path: Path) -> Mapping[str, str]:
    """Parse the Firebase web-config blob, treating a malformed file as absent.

    A half-written config should not take down every sign-in with a traceback;
    `is_configured()` reporting False produces a far more actionable failure.
    """
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _text(value: object) -> str:
    """Stringify a JSON field, including numeric ids from GitHub's App blob."""
    if value is None:
        return ""
    return str(value).strip()


def load_config(
    environ: Mapping[str, str] | None = None,
    *,
    base_dir: Path | None = None,
) -> IdentityPlatformConfig:
    """Build a config from the environment and `.secrets/`.

    `base_dir` is what the relative paths in `.env.example` resolve against, so
    a process started from anywhere still finds the repository's `.secrets/`.
    """
    env = os.environ if environ is None else environ
    root = Path.cwd() if base_dir is None else base_dir

    def _resolve(raw: str) -> Path:
        candidate = Path(raw).expanduser()
        return candidate if candidate.is_absolute() else (root / candidate)

    web_config = _read_web_config(
        _resolve(env.get(ENV_CONFIG_FILE, "").strip() or DEFAULT_CONFIG_FILE)
    )

    api_key = env.get(ENV_API_KEY, "").strip() or None
    if api_key is None:
        api_key = _read_api_key_file(
            _resolve(env.get(ENV_API_KEY_FILE, "").strip() or DEFAULT_API_KEY_FILE)
        )
    if api_key is None:
        api_key = (web_config.get("apiKey") or "").strip() or None

    project = (
        env.get(ENV_PROJECT, "").strip() or (web_config.get("projectId") or "").strip() or None
    )

    auth_domain = (web_config.get("authDomain") or "").strip() or None
    if auth_domain is None and project:
        auth_domain = f"{project}.firebaseapp.com"

    raw_credentials = env.get(ENV_CREDENTIALS, "").strip()

    google_file = _read_web_config(
        _resolve(env.get(ENV_GOOGLE_OAUTH, "").strip() or DEFAULT_GOOGLE_OAUTH_FILE)
    )
    # Google's console download nests credentials under `web`.
    google_web = google_file.get("web") if isinstance(google_file.get("web"), dict) else {}
    google_client_id = (
        env.get(ENV_GOOGLE_CLIENT_ID, "").strip()
        or (google_file.get("client_id") or google_file.get("clientId") or "").strip()
        or (google_web.get("client_id") or "").strip()
        or None
    )
    google_client_secret = (
        env.get(ENV_GOOGLE_CLIENT_SECRET, "").strip()
        or (google_file.get("client_secret") or google_file.get("clientSecret") or "").strip()
        or (google_web.get("client_secret") or "").strip()
        or None
    )

    github_file = _read_web_config(
        _resolve(env.get(ENV_GITHUB_APP, "").strip() or DEFAULT_GITHUB_APP_FILE)
    )
    github_client_id = (
        env.get(ENV_GITHUB_CLIENT_ID, "").strip()
        or _text(github_file.get("client_id") or github_file.get("clientId"))
        or None
    )
    github_client_secret = (
        env.get(ENV_GITHUB_CLIENT_SECRET, "").strip()
        or _text(github_file.get("client_secret") or github_file.get("clientSecret"))
        or None
    )
    github_app_slug = _text(github_file.get("app_slug") or github_file.get("slug")) or None
    github_app_id = (
        env.get(ENV_GITHUB_APP_ID, "").strip()
        or _text(github_file.get("app_id") or github_file.get("appId"))
        or None
    )
    raw_pem = env.get(ENV_GITHUB_PRIVATE_KEY, "").strip() or DEFAULT_GITHUB_PRIVATE_KEY
    github_private_key_path = _resolve(raw_pem)

    return IdentityPlatformConfig(
        api_key=api_key,
        project=project,
        auth_domain=auth_domain,
        credentials_path=_resolve(raw_credentials) if raw_credentials else None,
        action_url=env.get(ENV_ACTION_URL, "").strip() or DEFAULT_ACTION_URL,
        google_client_id=google_client_id,
        google_client_secret=google_client_secret,
        google_redirect_uri=env.get(ENV_GOOGLE_REDIRECT, "").strip() or DEFAULT_GOOGLE_REDIRECT,
        github_client_id=github_client_id,
        github_client_secret=github_client_secret,
        github_redirect_uri=env.get(ENV_GITHUB_REDIRECT, "").strip() or DEFAULT_GITHUB_REDIRECT,
        github_app_slug=github_app_slug,
        github_app_id=github_app_id,
        github_private_key_path=github_private_key_path,
        frontend_origin=env.get(ENV_FRONTEND_ORIGIN, "").strip() or DEFAULT_FRONTEND_ORIGIN,
    )
