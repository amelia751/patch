"""Google authorization-code flow for Continue with Google.

Identity Platform's google.com provider needs a Web OAuth client ID and secret.
Google does not let a service account create that client on a project that is
not in an organization; the values are read from `.secrets/google-oauth.json`
once a person has created the client in the Cloud Console.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlencode

import httpx

from packages.auth.config import (
    ADMIN_SCOPES,
    IdentityPlatformConfig,
    load_config,
)
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError

logger = logging.getLogger(__name__)

GOOGLE_AUTH_ENDPOINT: Final[str] = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT: Final[str] = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT: Final[str] = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_SCOPES: Final[str] = "openid email profile"

_IDP_CREATE = (
    "https://identitytoolkit.googleapis.com/admin/v2/projects/{project}"
    "/defaultSupportedIdpConfigs?idpId=google.com"
)
_IDP_PATCH = (
    "https://identitytoolkit.googleapis.com/admin/v2/projects/{project}"
    "/defaultSupportedIdpConfigs/google.com"
)


@dataclass(frozen=True)
class GoogleProfile:
    """What Google's userinfo endpoint returns for a signed-in account."""

    subject: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


def authorization_url(config: IdentityPlatformConfig, state: str) -> str:
    """Build the Google account-chooser URL the browser should navigate to."""
    if not config.google_oauth_configured():
        raise AuthConfigurationError(
            "Google OAuth client is not configured; write .secrets/google-oauth.json"
        )
    query = urlencode(
        {
            "client_id": config.google_client_id,
            "redirect_uri": config.google_redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_SCOPES,
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_AUTH_ENDPOINT}?{query}"


async def exchange_code(config: IdentityPlatformConfig, code: str) -> GoogleProfile:
    """Trade an authorization code for the Google profile of the signed-in user."""
    if not config.google_oauth_configured():
        raise AuthConfigurationError(
            "Google OAuth client is not configured; write .secrets/google-oauth.json"
        )
    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": config.google_client_id,
                    "client_secret": config.google_client_secret,
                    "redirect_uri": config.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise AuthUnavailableError("Google did not return an access token")
            userinfo = await client.get(
                GOOGLE_USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            userinfo.raise_for_status()
    except httpx.HTTPError as exc:
        raise AuthUnavailableError(f"could not reach Google OAuth: {exc}") from exc

    body: dict[str, Any] = userinfo.json()
    email = (body.get("email") or "").strip()
    subject = (body.get("sub") or "").strip()
    if not email or not subject:
        raise AuthUnavailableError("Google did not return an email and subject")
    return GoogleProfile(
        subject=subject,
        email=email,
        email_verified=bool(body.get("email_verified", False)),
        name=(body.get("name") or "").strip() or None,
        picture=(body.get("picture") or "").strip() or None,
    )


async def ensure_google_idp(config: IdentityPlatformConfig | None = None) -> bool:
    """Enable Identity Platform's google.com provider with this Web client.

    Returns False when the OAuth client is missing or the admin call fails.
    Google login can still complete via the authorization-code flow against
    Google directly; this only registers the same client with Identity Platform.
    """
    cfg = config if config is not None else load_config()
    if not cfg.google_oauth_configured() or not cfg.project:
        return False
    try:
        import google.auth
        import google.auth.transport.requests
        from google.oauth2 import service_account
    except ImportError:
        return False

    if cfg.credentials_path is not None and cfg.credentials_path.is_file():
        credentials = service_account.Credentials.from_service_account_file(
            str(cfg.credentials_path), scopes=list(ADMIN_SCOPES)
        )
    else:
        credentials, _ = google.auth.default(scopes=list(ADMIN_SCOPES))
    credentials.refresh(google.auth.transport.requests.Request())
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }
    payload = {
        "enabled": True,
        "clientId": cfg.google_client_id,
        "clientSecret": cfg.google_client_secret,
    }
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            created = await client.post(
                _IDP_CREATE.format(project=cfg.project),
                headers=headers,
                json=payload,
            )
            if created.status_code in {200, 201}:
                logger.info("Enabled Identity Platform google.com provider")
                return True
            if created.status_code == 409:
                patched = await client.patch(
                    _IDP_PATCH.format(project=cfg.project),
                    headers=headers,
                    json=payload,
                    params={"updateMask": "enabled,clientId,clientSecret"},
                )
                patched.raise_for_status()
                logger.info("Updated Identity Platform google.com provider")
                return True
            logger.warning(
                "Could not enable google.com IdP: status=%s body=%s",
                created.status_code,
                created.text[:200],
            )
            return False
    except httpx.HTTPError as exc:
        logger.warning("Could not enable google.com IdP: %s", exc)
        return False
