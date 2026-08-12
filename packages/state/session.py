"""Signed session cookies for the console.

The cookie is HMAC-signed, not encrypted: it carries a user id, not a
credential. Identity Platform tokens never land here.
"""

from __future__ import annotations

import hmac
import os
import secrets
import time
from hashlib import sha256
from pathlib import Path
from typing import Final
from uuid import UUID

COOKIE_NAME: Final[str] = "access_token"
OAUTH_STATE_COOKIE: Final[str] = "oauth_state"
DEFAULT_SECRET_FILE: Final[str] = ".secrets/session_secret.txt"
TTL_SECONDS: Final[int] = 60 * 60 * 24 * 7
COOKIE_SECURE_VAR: Final[str] = "PATCHAPI_COOKIE_SECURE"


def cookie_kwargs(*, secure: bool | None = None) -> dict[str, str | bool]:
    """Cookie flags for the current deployment.

    Localhost is same-site across ports, so Lax + not-Secure is enough.
    Cloud Run puts the dashboard and the API on different `run.app` hosts
    (the suffix is on the public suffix list), so the browser treats the
    callback as cross-site: that requires Secure + SameSite=None.
    """
    if secure is None:
        raw = os.environ.get(COOKIE_SECURE_VAR, "").strip().lower()
        secure = raw in {"1", "true", "yes"}
    return {
        "httponly": True,
        "samesite": "none" if secure else "lax",
        "secure": secure,
        "path": "/",
    }


def load_session_secret(base_dir: Path | None = None) -> str:
    """Return the HMAC key, creating `.secrets/session_secret.txt` if needed."""
    root = Path.cwd() if base_dir is None else base_dir
    env = os.environ.get("PATCHAPI_SESSION_SECRET", "").strip()
    if env:
        return env
    path = root / DEFAULT_SECRET_FILE
    if path.is_file():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(32)
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
    return value


def issue(user_id: UUID, secret: str, *, now: int | None = None) -> str:
    """Return a cookie value bound to `user_id` until `TTL_SECONDS` from now."""
    expires = (now if now is not None else int(time.time())) + TTL_SECONDS
    payload = f"{user_id}:{expires}"
    signature = hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()
    return f"{payload}:{signature}"


def parse(token: str, secret: str, *, now: int | None = None) -> UUID | None:
    """Return the user id if the cookie is well-formed, signed, and unexpired."""
    parts = token.split(":")
    if len(parts) != 3:
        return None
    user_id_raw, expires_raw, signature = parts
    payload = f"{user_id_raw}:{expires_raw}"
    expected = hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        expires = int(expires_raw)
        user_id = UUID(user_id_raw)
    except (TypeError, ValueError):
        return None
    if expires < (now if now is not None else int(time.time())):
        return None
    return user_id
