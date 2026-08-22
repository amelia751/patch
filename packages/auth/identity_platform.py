"""Identity Platform (GCIP) authentication, shaped to the caller's existing contract.

This replaces an AWS Cognito client method-for-method so the control plane's
auth routes did not have to change. Two vocabulary differences are absorbed
here rather than being pushed up into routing:

* **One bearer credential, not two.** Cognito issues an access token and an ID
  token with different audiences. Identity Platform issues one ID token that is
  both. `AuthTokens.access_token` and `.id_token` therefore carry the same
  string, and callers that stored "the access token" keep working.
* **`code` means an `oobCode`.** Cognito emailed a six-digit code the user
  retyped. Identity Platform emails a link carrying an opaque out-of-band code,
  so the code arrives from a redirect rather than a keyboard. Every method that
  took a `code` still takes one; it is simply longer and machine-supplied.

Provider error strings are translated into the sentences the sign-in form
already displays. Nothing here logs a token, an `oobCode`, or a password: on
failure only the mapped message and the HTTP status travel onward.
"""

from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import httpx

from packages.auth.config import (
    ADMIN_SCOPES,
    SECURE_TOKEN_URL,
    IdentityPlatformConfig,
    load_config,
)
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError

logger = logging.getLogger(__name__)

# Identity Platform reports failures as a bare token in `error.message`, at
# times suffixed with a colon and detail (`WEAK_PASSWORD : Password should...`).
# Anything absent from this table becomes a generic message: an unmapped
# provider string is not something a person signing in can act on.
_ERROR_MESSAGES: Final[dict[str, str]] = {
    "EMAIL_EXISTS": "An account with this email already exists",
    "EMAIL_NOT_FOUND": "No account found with this email",
    "INVALID_EMAIL": "That email address is not valid",
    "INVALID_PASSWORD": "Incorrect email or password",
    "INVALID_LOGIN_CREDENTIALS": "Incorrect email or password",
    "MISSING_PASSWORD": "Please enter your password",
    "USER_DISABLED": "This account has been disabled",
    "OPERATION_NOT_ALLOWED": "Email and password sign-in is not enabled for this project",
    "PASSWORD_LOGIN_DISABLED": "Email and password sign-in is not enabled for this project",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Please try again later.",
    "INVALID_OOB_CODE": "That verification link is not valid. Please request a new one.",
    "EXPIRED_OOB_CODE": "That verification link has expired. Please request a new one.",
    "INVALID_ID_TOKEN": "Invalid or expired token",
    "TOKEN_EXPIRED": "Invalid or expired token",
    "USER_NOT_FOUND": "Invalid or expired token",
    "INVALID_REFRESH_TOKEN": "Your session has expired. Please sign in again.",
    "TOKEN_REVOKED": "Your session has expired. Please sign in again.",
}

_WEAK_PASSWORD: Final[str] = "WEAK_PASSWORD"
_GENERIC_FAILURE: Final[str] = "Authentication failed. Please try again."


@dataclass
class AuthTokens:
    """Field-compatible with the Cognito token bundle it replaces."""

    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


@dataclass
class AuthUser:
    """Field-compatible with the Cognito user record it replaces.

    `sub` carries Identity Platform's `localId`, which plays the same role: a
    stable provider-side identifier the local user row is keyed against.
    """

    sub: str
    email: str
    email_verified: bool
    name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _translate(provider_message: str) -> str:
    """Map a provider error token onto a sentence worth showing a person."""
    token = provider_message.split(":", 1)[0].strip()
    if token == _WEAK_PASSWORD:
        detail = provider_message.split(":", 1)[1].strip() if ":" in provider_message else ""
        return (
            f"Password does not meet requirements: {detail}"
            if detail
            else ("Password does not meet requirements")
        )
    return _ERROR_MESSAGES.get(token, _GENERIC_FAILURE)


class IdentityPlatformService:
    """Email/password identity backed by Google Cloud Identity Platform."""

    def __init__(self, config: IdentityPlatformConfig | None = None) -> None:
        self._config = config if config is not None else load_config()

    @property
    def config(self) -> IdentityPlatformConfig:
        return self._config

    def is_configured(self) -> bool:
        """Whether an API key and project are both resolvable."""
        return self._config.is_configured()

    # -- transport ---------------------------------------------------------

    async def _post(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        bearer: str | None = None,
        form: bool = False,
    ) -> dict[str, Any]:
        """POST to Identity Platform, raising `ValueError` with a mapped message.

        A transport failure raises `AuthUnavailableError` rather than any of the
        credential messages: "we could not reach Google" and "your password is
        wrong" must never look the same to the person retyping it.
        """
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.post(
                    url,
                    data=payload if form else None,
                    json=None if form else payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise AuthUnavailableError(f"could not reach Identity Platform: {exc}") from exc

        if response.status_code >= 400:
            try:
                provider_message = response.json().get("error", {}).get("message", "")
            except ValueError:
                provider_message = ""
            logger.warning(
                "Identity Platform rejected a request: status=%s code=%s",
                response.status_code,
                provider_message.split(":", 1)[0].strip() or "(unparsed)",
            )
            raise ValueError(_translate(provider_message))

        return response.json()

    async def _admin_token(self) -> str:
        """Mint a service-account bearer for the admin-only endpoints.

        google-auth is imported lazily so that importing this module — and thus
        collecting the offline tests — never requires the library to be present.
        """
        try:
            import google.auth
            import google.auth.transport.requests
            from google.oauth2 import service_account
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise AuthConfigurationError("google-auth is not installed") from exc

        key_path = self._config.credentials_path
        if key_path is not None:
            if not key_path.is_file():
                raise AuthConfigurationError(
                    f"GOOGLE_APPLICATION_CREDENTIALS points at {key_path}, which does not exist"
                )
            credentials = service_account.Credentials.from_service_account_file(
                str(key_path), scopes=list(ADMIN_SCOPES)
            )
        else:
            credentials, _ = google.auth.default(scopes=list(ADMIN_SCOPES))

        credentials.refresh(google.auth.transport.requests.Request())
        return str(credentials.token)

    # -- registration ------------------------------------------------------

    async def sign_up(self, email: str, password: str, display_name: str) -> dict:
        """Register a user and return the same shape the Cognito client did.

        `confirmed` is always False: the account is immediately usable, but the
        email behind it is unverified until the emailed link is followed, and
        the caller keys its "show the verification prompt" decision off this.
        """
        if not self.is_configured():
            raise AuthConfigurationError("Identity Platform not configured")

        data = await self._post(
            self._config.url("signUp"),
            {
                "email": email,
                "password": password,
                "displayName": display_name,
                "returnSecureToken": True,
            },
        )
        return {
            "user_sub": data.get("localId", ""),
            "id_token": data.get("idToken", ""),
            "confirmed": False,
            "delivery": {"AttributeName": "email"},
        }

    async def confirm_sign_up(self, email: str, code: str) -> bool:
        """Apply an emailed verification code.

        `email` is unused: an `oobCode` already identifies the account it was
        minted for, and trusting a caller-supplied address instead would let one
        account's link mark another address verified. It stays in the signature
        so the calling route did not have to change.
        """
        await self._post(self._config.url("update"), {"oobCode": code})
        return True

    async def admin_confirm_sign_up(self, email: str) -> bool:
        """No-op retained for call-site compatibility.

        Cognito blocked sign-in until an account was confirmed, so the caller
        admin-confirmed every new user to keep them usable. Identity Platform
        has no such gate — an unverified user can already sign in — so there is
        nothing to do, and reporting success is accurate rather than a stub.
        """
        return True

    async def create_oauth_user(self, email: str, display_name: str) -> bool:
        """Create a password-less account for a user who arrived via OAuth.

        Gives that user a route to email/password sign-in later through the
        reset flow. Returns False when the account already exists, and on any
        other failure: an OAuth sign-in must not fail because this did.
        """
        if not self.is_configured():
            raise AuthConfigurationError("Identity Platform not configured")

        alphabet = string.ascii_letters + string.digits + "!@#$%"
        placeholder = "".join(secrets.choice(alphabet) for _ in range(32))

        try:
            await self._post(
                self._config.admin_url("accounts"),
                {
                    "email": email,
                    "password": placeholder,
                    "displayName": display_name,
                    "emailVerified": True,
                },
                bearer=await self._admin_token(),
            )
        except (ValueError, AuthConfigurationError, AuthUnavailableError) as exc:
            logger.info("Could not pre-create an Identity Platform user for %s: %s", email, exc)
            return False
        return True

    # -- verification and reset -------------------------------------------

    async def resend_confirmation_code(self, email: str) -> dict:
        """Unsupported by address alone; the caller's session path handles this.

        Identity Platform will only issue a verification link against a signed-in
        ID token, so there is no address-only equivalent. Raising keeps the
        caller's existing fallback honest instead of reporting a mail that was
        never sent.
        """
        raise ValueError("Please sign in again to resend the verification email")

    async def send_email_verification_code(self, access_token: str) -> dict:
        """Have Google email a verification link for the signed-in account."""
        data = await self._post(
            self._config.url("sendOobCode"),
            {
                "requestType": "VERIFY_EMAIL",
                "idToken": access_token,
                "continueUrl": self._config.continue_url("verifyEmail"),
            },
        )
        return {"delivery": {"AttributeName": "email", "Destination": data.get("email", "")}}

    async def verify_email_attribute(self, access_token: str, code: str) -> bool:
        """Apply a verification code for a signed-in user.

        `access_token` is unused for the same reason `confirm_sign_up` ignores
        `email`: the `oobCode` is already bound to one account.
        """
        await self._post(self._config.url("update"), {"oobCode": code})
        return True

    async def forgot_password(self, email: str) -> dict:
        """Have Google email a password-reset link.

        An unknown address reports success. Distinguishing it here would turn
        the reset form into an oracle for which emails hold accounts.
        """
        if not self.is_configured():
            raise AuthConfigurationError("Identity Platform not configured")

        try:
            await self._post(
                self._config.url("sendOobCode"),
                {
                    "requestType": "PASSWORD_RESET",
                    "email": email,
                    "continueUrl": self._config.continue_url("resetPassword"),
                },
            )
        except ValueError as exc:
            if str(exc) == _ERROR_MESSAGES["EMAIL_NOT_FOUND"]:
                logger.info("Password reset requested for an unknown address")
                return {"delivery": {"AttributeName": "email"}}
            raise
        return {"delivery": {"AttributeName": "email"}}

    async def inspect_reset_code(self, code: str) -> str:
        """Return the address a reset code is bound to, without consuming it.

        Identity Platform answers `resetPassword` with only an `oobCode` by
        naming the account. The page uses that to show who the form is for.
        """
        data = await self._post(self._config.url("resetPassword"), {"oobCode": code})
        email = (data.get("email") or "").strip()
        if not email:
            raise ValueError(_ERROR_MESSAGES["INVALID_OOB_CODE"])
        return email

    async def confirm_forgot_password(self, email: str, code: str, new_password: str) -> bool:
        """Complete a reset with the emailed code and a new password."""
        await self._post(
            self._config.url("resetPassword"),
            {"oobCode": code, "newPassword": new_password},
        )
        return True

    # -- session -----------------------------------------------------------

    async def sign_in(self, email: str, password: str) -> AuthTokens:
        """Exchange an email and password for a token bundle."""
        if not self.is_configured():
            raise AuthConfigurationError("Identity Platform not configured")

        data = await self._post(
            self._config.url("signInWithPassword"),
            {"email": email, "password": password, "returnSecureToken": True},
        )
        token = data["idToken"]
        return AuthTokens(
            access_token=token,
            id_token=token,
            refresh_token=data["refreshToken"],
            expires_in=int(data.get("expiresIn", 3600)),
        )

    async def get_user(self, access_token: str) -> AuthUser:
        """Resolve the account behind a token."""
        data = await self._post(self._config.url("lookup"), {"idToken": access_token})
        users = data.get("users") or []
        if not users:
            raise ValueError("Invalid or expired token")

        user = users[0]
        return AuthUser(
            sub=user.get("localId", ""),
            email=user.get("email", ""),
            # Absent means unverified; the API omits the field rather than
            # sending false, so a truthiness test would silently invert here.
            email_verified=bool(user.get("emailVerified", False)),
            name=user.get("displayName") or None,
        )

    async def refresh_tokens(self, refresh_token: str) -> AuthTokens:
        """Trade a refresh token for a fresh bundle.

        Identity Platform may rotate the refresh token, so the response's value
        is returned rather than the one passed in — Cognito never rotated, and
        echoing the old token back would hand the caller a dead credential.
        """
        if not self.is_configured():
            raise AuthConfigurationError("Identity Platform not configured")

        data = await self._post(
            SECURE_TOKEN_URL + f"?key={self._config.require_api_key()}",
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            form=True,
        )
        token = data["id_token"]
        return AuthTokens(
            access_token=token,
            id_token=token,
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=int(data.get("expires_in", 3600)),
        )

    async def sign_out(self, access_token: str) -> bool:
        """Best-effort global sign-out.

        Never raises: the caller clears its own session regardless, and a user
        who clicked "log out" should not see an error for a revocation that is
        already unreachable.
        """
        try:
            user = await self.get_user(access_token)
            await self._post(
                self._config.admin_url("accounts:update"),
                {"localId": user.sub, "validSince": str(int(datetime.now().timestamp()))},
                bearer=await self._admin_token(),
            )
        except (ValueError, AuthConfigurationError, AuthUnavailableError, KeyError) as exc:
            logger.info("Could not revoke Identity Platform refresh tokens: %s", exc)
            return False
        return True


_identity_service: IdentityPlatformService | None = None


def get_identity_service() -> IdentityPlatformService:
    """Return the process-wide Identity Platform client."""
    global _identity_service
    if _identity_service is None:
        _identity_service = IdentityPlatformService()
    return _identity_service


def reset_identity_service() -> None:
    """Drop the cached client so a test can rebuild it against fresh config."""
    global _identity_service
    _identity_service = None
