"""Console auth HTTP surface: `/api/auth/google` and session reads.

Mounted by the wired control plane (`packages.state.serve`), not by the unwired
service, so the OpenAPI contract for health and `/v1/*` stays unchanged until
email and GitHub routes exist.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from packages.auth.config import load_config
from packages.auth.errors import AuthConfigurationError, AuthUnavailableError
from packages.auth.google_oauth import authorization_url, exchange_code
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
from packages.state.users import read_user, upsert_google_user

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


@router.get("/google")
async def google_start(response: Response) -> JSONResponse:
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
    body = JSONResponse({"auth_url": authorization_url(config, state)})
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
        profile = await exchange_code(config, code)
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
