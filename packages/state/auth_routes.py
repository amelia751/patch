"""Console auth HTTP surface: Google/GitHub OAuth and session reads.

Mounted by the wired control plane (`packages.state.serve`), not by the unwired
service, so the OpenAPI contract for health and `/v1/*` stays unchanged until
email routes exist.
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from packages.auth.config import load_config
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError
from packages.auth.github_oauth import (
    authorization_url as github_authorization_url,
    exchange_code as github_exchange_code,
    fetch_installation,
    find_installation_for_login,
    install_url,
)
from packages.auth.google_oauth import (
    authorization_url as google_authorization_url,
    exchange_code as google_exchange_code,
)
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
)

if TYPE_CHECKING:
    import asyncpg

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    """Use the host the browser actually called so the state cookie round-trips.

    `localhost` and `127.0.0.1` are different cookie sites. The OAuth client
    must list both callback URLs (README); this picks the one that matches
    the request.
    """
    incoming = str(request.base_url).rstrip("/") + path
    return incoming or fallback


def _github_redirect_uri(request: Request, fallback: str) -> str:
    return _oauth_callback_uri(request, "/api/auth/github/callback", fallback)


def _google_redirect_uri(request: Request, fallback: str) -> str:
    return _oauth_callback_uri(request, "/api/auth/google/callback", fallback)


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
