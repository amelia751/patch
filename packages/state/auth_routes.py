"""Console auth HTTP surface: email/password, Google/GitHub OAuth, sessions."""

from __future__ import annotations

import secrets
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from packages.auth.config import load_config
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError
from packages.auth.github_oauth import (
    authorization_url as github_authorization_url,
)
from packages.auth.github_oauth import (
    exchange_code as github_exchange_code,
)
from packages.auth.github_oauth import (
    fetch_installation,
    find_installation_for_login,
    install_url,
)
from packages.auth.google_oauth import (
    authorization_url as google_authorization_url,
)
from packages.auth.google_oauth import (
    exchange_code as google_exchange_code,
)
from packages.auth.identity_platform import get_identity_service
from packages.state.pool import StateUnavailableError
from packages.state.session import (
    COOKIE_NAME,
    OAUTH_STATE_COOKIE,
    TTL_SECONDS,
    cookie_kwargs,
    issue,
    load_session_secret,
    parse,
)
from packages.state.users import (
    find_user_id_by_github_login,
    read_user,
    record_github_installation,
    upsert_github_user,
    upsert_google_user,
    upsert_password_user,
)

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/auth", tags=["auth"])


class _EmailBody(BaseModel):
    email: str = Field(min_length=3)


class _PasswordBody(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class _SignupBody(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    display_name: str = ""


class _ResetBody(BaseModel):
    code: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
    email: str = ""


class _VerifyBody(BaseModel):
    code: str = Field(min_length=1)
    email: str = ""


def _auth_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, AuthConfigurationError):
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "identity_platform",
                "detail": str(exc),
            },
            status_code=503,
        )
    if isinstance(exc, AuthUnavailableError):
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "identity_platform",
                "detail": str(exc),
            },
            status_code=503,
        )
    return JSONResponse({"detail": str(exc)}, status_code=400)


def _pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "postgres_pool", None)
    if pool is None:
        raise StateUnavailableError("no connection pool; the service has not completed startup")
    return pool


def _set_session(response: Response, token: str) -> None:
    response.set_cookie(COOKIE_NAME, token, max_age=TTL_SECONDS, **cookie_kwargs())


def _session_user_id(request: Request) -> UUID | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    return parse(raw, load_session_secret())


async def _bind_github_installation(
    pool,
    *,
    user: dict | None,
    installation_id: str | None,
) -> dict | None:
    """Attach a GitHub App installation using the App JWT, not a user token."""
    config = load_config()
    try:
        found = None
        if installation_id:
            found = await fetch_installation(config, installation_id)
        elif user and user.get("github_username") and not user.get("github_app_installed"):
            found = await find_installation_for_login(config, user["github_username"])
        if found is None:
            return user
        ident, login, account_type = found
        user_id = UUID(user["id"]) if user else await find_user_id_by_github_login(pool, login)
        if user_id is None:
            return user
        return await record_github_installation(
            pool,
            user_id,
            installation_id=ident,
            account_login=login,
            account_type=account_type,
        )
    except (AuthConfigurationError, AuthUnavailableError, StateUnavailableError):
        return user


def _oauth_callback_uri(request: Request, path: str, fallback: str) -> str:
    """Pick the callback URI the OAuth client actually registered.

    Cloud Run terminates TLS and Starlette sees `http://` on the container.
    GitHub and Google require the exact https URI in the client. When the
    configured fallback is already https, use it.

    Locally the fallback is `http://localhost:8080/...`. `localhost` and
    `127.0.0.1` are different cookie sites, so that path still follows the
    host the browser called.
    """
    if fallback.startswith("https://"):
        return fallback
    incoming = str(request.base_url).rstrip("/") + path
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    if proto == "https" and incoming.startswith("http://"):
        incoming = "https://" + incoming[len("http://") :]
    return incoming or fallback


def _github_redirect_uri(request: Request, fallback: str) -> str:
    return _oauth_callback_uri(request, "/api/auth/github/callback", fallback)


def _google_redirect_uri(request: Request, fallback: str) -> str:
    return _oauth_callback_uri(request, "/api/auth/google/callback", fallback)


@router.post("/signup")
async def signup(request: Request, body: _SignupBody) -> JSONResponse:
    """Register an email/password account. Google emails the verification link."""
    identity = get_identity_service()
    try:
        created = await identity.sign_up(
            body.email.strip(), body.password, body.display_name.strip()
        )
        token = created.get("id_token") or ""
        if token:
            try:
                await identity.send_email_verification_code(token)
            except (ValueError, AuthUnavailableError):
                pass
        user = await upsert_password_user(
            _pool(request),
            email=body.email.strip().lower(),
            display_name=body.display_name.strip(),
            identity_platform_uid=str(created.get("user_sub") or ""),
            email_verified=False,
        )
    except (AuthConfigurationError, AuthUnavailableError, StateUnavailableError, ValueError) as exc:
        return _auth_error(exc)
    return JSONResponse(
        {
            "ok": True,
            "confirmed": False,
            "user": user,
            "message": "Check your email for a verification link.",
        }
    )


@router.post("/login")
async def login(request: Request, body: _PasswordBody) -> JSONResponse:
    """Exchange email and password for a console session cookie."""
    identity = get_identity_service()
    try:
        tokens = await identity.sign_in(body.email.strip(), body.password)
        profile = await identity.get_user(tokens.id_token)
        user = await upsert_password_user(
            _pool(request),
            email=profile.email,
            display_name=profile.name or "",
            identity_platform_uid=profile.sub,
            email_verified=profile.email_verified,
        )
    except (AuthConfigurationError, AuthUnavailableError, StateUnavailableError, ValueError) as exc:
        return _auth_error(exc)
    session = issue(UUID(user["id"]), load_session_secret())
    body_out = JSONResponse({"ok": True, "access_token": session, "user": user})
    _set_session(body_out, session)
    return body_out


@router.post("/forgot-password")
async def forgot_password(body: _EmailBody) -> JSONResponse:
    """Ask Identity Platform to email a password-reset link.

    Always reports success so the form cannot probe which addresses exist.
    """
    identity = get_identity_service()
    try:
        await identity.forgot_password(body.email.strip())
    except (AuthConfigurationError, AuthUnavailableError) as exc:
        return _auth_error(exc)
    except ValueError as exc:
        return _auth_error(exc)
    return JSONResponse({"ok": True})


@router.post("/reset-password")
async def reset_password(body: _ResetBody) -> JSONResponse:
    """Complete a reset with the `oobCode` from the emailed link."""
    identity = get_identity_service()
    try:
        await identity.confirm_forgot_password(
            body.email.strip(), body.code.strip(), body.new_password
        )
    except (AuthConfigurationError, AuthUnavailableError, ValueError) as exc:
        return _auth_error(exc)
    return JSONResponse({"ok": True})


@router.post("/verify")
async def verify_email(body: _VerifyBody) -> JSONResponse:
    """Apply the `oobCode` from a verification link."""
    identity = get_identity_service()
    try:
        await identity.confirm_sign_up(body.email.strip(), body.code.strip())
    except (AuthConfigurationError, AuthUnavailableError, ValueError) as exc:
        return _auth_error(exc)
    return JSONResponse({"ok": True})


@router.post("/resend-code")
async def resend_code(body: _EmailBody) -> JSONResponse:
    """Re-send a password-reset link. Verification resend needs a signed-in session."""
    identity = get_identity_service()
    try:
        await identity.forgot_password(body.email.strip())
    except (AuthConfigurationError, AuthUnavailableError, ValueError) as exc:
        return _auth_error(exc)
    return JSONResponse({"ok": True})


@router.get("/google")
async def google_start(request: Request, response: Response) -> JSONResponse:
    """Return the Google authorization URL the dashboard navigates to."""
    config = load_config()
    if not config.google_oauth_configured():
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "google_oauth",
                "reason": (
                    "Create a Web OAuth client in the Cloud Console and write "
                    "client_id/client_secret to .secrets/google-oauth.json. "
                    "Google does not allow a service account to create that "
                    "client on a project that is not in an organization."
                ),
            },
            status_code=503,
        )
    state = secrets.token_urlsafe(24)
    bound = replace(
        config, google_redirect_uri=_google_redirect_uri(request, config.google_redirect_uri)
    )
    body = JSONResponse({"auth_url": google_authorization_url(bound, state)})
    body.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, **cookie_kwargs())
    return body


@router.get("/google/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None):
    """Finish Google sign-in and send the browser back to the dashboard."""
    config = load_config()
    frontend = config.frontend_origin.rstrip("/")
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not state or not expected_state or state != expected_state:
        return RedirectResponse(f"{frontend}/?auth=error&message=invalid_state")
    try:
        bound = replace(
            config, google_redirect_uri=_google_redirect_uri(request, config.google_redirect_uri)
        )
        profile = await google_exchange_code(bound, code)
        user = await upsert_google_user(_pool(request), profile)
        try:
            await get_identity_service().create_oauth_user(
                profile.email, profile.name or profile.email
            )
        except (AuthConfigurationError, AuthUnavailableError, ValueError):
            pass
    except (AuthConfigurationError, AuthUnavailableError, StateUnavailableError, ValueError):
        return RedirectResponse(f"{frontend}/?auth=error&message=google_sign_in_failed")
    token = issue(UUID(user["id"]), load_session_secret())
    redirect = RedirectResponse(
        f"{frontend}/?auth=success&provider=google&email={profile.email}"
    )
    _set_session(redirect, token)
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return redirect


@router.get("/github")
async def github_start(request: Request, response: Response) -> JSONResponse:
    """Return the GitHub App authorize URL the dashboard navigates to."""
    config = load_config()
    if not config.github_oauth_configured():
        return JSONResponse(
            {
                "error": "dependency_unavailable",
                "dependency": "github_oauth",
                "reason": (
                    "Create the PatchAPI GitHub App and write client_id/"
                    "client_secret to .secrets/github-app.json (see README.md)."
                ),
            },
            status_code=503,
        )
    state = secrets.token_urlsafe(24)
    bound = replace(
        config, github_redirect_uri=_github_redirect_uri(request, config.github_redirect_uri)
    )
    body = JSONResponse({"auth_url": github_authorization_url(bound, state)})
    body.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, **cookie_kwargs())
    return body


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    installation_id: str | None = None,
    error: str | None = None,
):
    """Finish GitHub sign-in; send the browser to App install when still needed."""
    config = load_config()
    frontend = config.frontend_origin.rstrip("/")
    if error:
        return RedirectResponse(f"{frontend}/?auth=error&message=github_denied")
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not code or not state or not expected_state or state != expected_state:
        return RedirectResponse(f"{frontend}/?auth=error&message=invalid_state")
    try:
        bound = replace(
            config, github_redirect_uri=_github_redirect_uri(request, config.github_redirect_uri)
        )
        profile = await github_exchange_code(
            bound, code, installation_id=(installation_id or "").strip() or None
        )
        user = await upsert_github_user(
            _pool(request), profile, existing_user_id=_session_user_id(request)
        )
    except ValueError:
        return RedirectResponse(f"{frontend}/?auth=error&message=github_already_linked")
    except (AuthConfigurationError, AuthUnavailableError, StateUnavailableError):
        return RedirectResponse(f"{frontend}/?auth=error&message=github_sign_in_failed")
    token = issue(UUID(user["id"]), load_session_secret())
    next_url = f"{frontend}/?auth=success&provider=github"
    if not user.get("github_app_installed"):
        app_install = install_url(config)
        if app_install is not None:
            next_url = app_install
    redirect = RedirectResponse(next_url)
    _set_session(redirect, token)
    redirect.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    return redirect


@router.get("/github/setup")
async def github_setup(
    request: Request,
    installation_id: str | None = None,
    setup_action: str | None = None,
):
    """Record the App installation GitHub redirects to after install/update."""
    config = load_config()
    frontend = config.frontend_origin.rstrip("/")
    ident = (installation_id or "").strip()
    if not ident:
        return RedirectResponse(f"{frontend}/?auth=error&message=github_setup_failed")
    user = None
    user_id = _session_user_id(request)
    try:
        if user_id is not None:
            user = await read_user(_pool(request), user_id)
        user = await _bind_github_installation(
            _pool(request), user=user, installation_id=ident
        )
    except StateUnavailableError:
        return RedirectResponse(f"{frontend}/?auth=error&message=github_setup_failed")
    if user is None or not user.get("github_app_installed"):
        return RedirectResponse(f"{frontend}/?auth=error&message=github_setup_failed")
    action = (setup_action or "install").strip() or "install"
    return RedirectResponse(f"{frontend}/?auth=success&provider=github&setup={action}")


@router.get("/me")
async def me(request: Request) -> JSONResponse:
    """Return the signed-in console user, or 401."""
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            raw = auth[7:].strip()
    if not raw:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    user_id = parse(raw, load_session_secret())
    if user_id is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    try:
        user = await read_user(_pool(request), user_id)
        if user is not None and user.get("github_username") and not user.get("github_app_installed"):
            user = await _bind_github_installation(
                _pool(request), user=user, installation_id=None
            ) or user
    except StateUnavailableError as exc:
        return JSONResponse(
            {"error": "dependency_unavailable", "dependency": "postgres", "reason": str(exc)},
            status_code=503,
        )
    if user is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return JSONResponse(user)


@router.post("/logout")
async def logout() -> JSONResponse:
    body = JSONResponse({"ok": True})
    body.delete_cookie(COOKIE_NAME, path="/")
    return body
