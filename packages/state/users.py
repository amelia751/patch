"""Console user rows: what `/api/auth/me` returns.

Writes belong here because Google sign-in creates the profile the dashboard
renders. Passwords and Google tokens never touch these queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from packages.auth.google_oauth import GoogleProfile
from packages.state.pool import StateUnavailableError

if TYPE_CHECKING:
    import asyncpg


def _profile(row: Any, *, github_app_installed: bool) -> dict[str, Any]:
    settings = row["settings"] if isinstance(row["settings"], dict) else {}
    created = row["created_at"]
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "avatar_url": row["avatar_url"],
        "email_verified": bool(row["email_verified"]),
        "github_id": int(row["github_id"]) if row["github_id"] is not None else None,
        "github_username": row["github_username"],
        "github_app_installed": github_app_installed,
        "type": row["type"],
        "created_at": created.isoformat() if created is not None else None,
        "settings": settings,
    }


async def upsert_google_user(pool: asyncpg.Pool, profile: GoogleProfile) -> dict[str, Any]:
    """Insert or update the console user for a Google sign-in, then return `/me`."""
    display_name = profile.name or profile.email.split("@", 1)[0]
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO users (
                        email, display_name, avatar_url, email_verified, type, settings
                    )
                    VALUES ($1, $2, $3, $4, 'personal', '{}'::jsonb)
                    ON CONFLICT (email) DO UPDATE
                    SET display_name = EXCLUDED.display_name,
                        avatar_url = COALESCE(EXCLUDED.avatar_url, users.avatar_url),
                        email_verified = users.email_verified OR EXCLUDED.email_verified,
                        updated_at = now()
                    RETURNING id, email, display_name, avatar_url, email_verified,
                              type, settings, created_at
                    """,
                    profile.email,
                    display_name,
                    profile.picture,
                    profile.email_verified,
                )
                await connection.execute(
                    """
                    INSERT INTO user_identities (
                        user_id, provider, provider_user_id, username, email
                    )
                    VALUES ($1, 'google', $2, $3, $4)
                    ON CONFLICT (provider, provider_user_id) DO UPDATE
                    SET email = EXCLUDED.email, username = EXCLUDED.username
                    """,
                    row["id"],
                    profile.subject,
                    display_name,
                    profile.email,
                )
            return await read_user(pool, row["id"])
    except Exception as exc:
        raise StateUnavailableError(f"could not persist Google user: {type(exc).__name__}") from exc


async def read_user(pool: asyncpg.Pool, user_id: UUID) -> dict[str, Any] | None:
    """Return the `/me` payload, or None if the id is unknown."""
    try:
        row = await pool.fetchrow(
            """
            SELECT
                u.id,
                u.email,
                u.display_name,
                u.avatar_url,
                u.email_verified,
                u.type::text AS type,
                u.settings,
                u.created_at,
                (
                    SELECT i.provider_user_id
                    FROM user_identities i
                    WHERE i.user_id = u.id AND i.provider = 'github'
                ) AS github_id,
                (
                    SELECT i.username
                    FROM user_identities i
                    WHERE i.user_id = u.id AND i.provider = 'github'
                ) AS github_username,
                EXISTS (
                    SELECT 1 FROM github_connections c
                    WHERE c.user_id = u.id AND c.suspended_at IS NULL
                ) AS github_app_installed
            FROM users u
            WHERE u.id = $1
            """,
            user_id,
        )
    except Exception as exc:
        raise StateUnavailableError(f"could not read user: {type(exc).__name__}") from exc
    if row is None:
        return None
    github_id = row["github_id"]
    try:
        github_id_int = int(github_id) if github_id not in (None, "") else None
    except (TypeError, ValueError):
        github_id_int = None
    # fetchrow keys are used via mapping; rebuild with parsed github_id.
    mapped = dict(row)
    mapped["github_id"] = github_id_int
    return _profile(mapped, github_app_installed=bool(row["github_app_installed"]))
