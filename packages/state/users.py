"""Console user rows: what `/api/auth/me` returns.

Writes belong here because Google sign-in creates the profile the dashboard
renders. Passwords and Google tokens never touch these queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from packages.auth.github_oauth import GitHubProfile
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


async def upsert_github_user(
    pool: asyncpg.Pool,
    profile: GitHubProfile,
    *,
    existing_user_id: UUID | None = None,
) -> dict[str, Any]:
    """Insert or link the console user for a GitHub sign-in, then return `/me`.

    Tokens never land here. A GitHub identity already bound to a different user
    is refused rather than merged.
    """
    display_name = profile.name or profile.login
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                bound = await connection.fetchrow(
                    """
                    SELECT user_id FROM user_identities
                    WHERE provider = 'github' AND provider_user_id = $1
                    """,
                    profile.subject,
                )
                if bound is not None:
                    owner = bound["user_id"]
                    if existing_user_id is not None and owner != existing_user_id:
                        raise ValueError("That GitHub account is already linked to another user")
                    user_id = owner
                elif existing_user_id is not None:
                    user_id = existing_user_id
                else:
                    row = await connection.fetchrow(
                        """
                        INSERT INTO users (
                            email, display_name, avatar_url, email_verified, type, settings
                        )
                        VALUES ($1, $2, $3, $4, 'personal', '{}'::jsonb)
                        ON CONFLICT (email) DO UPDATE
                        SET display_name = COALESCE(NULLIF(users.display_name, ''), EXCLUDED.display_name),
                            avatar_url = COALESCE(users.avatar_url, EXCLUDED.avatar_url),
                            email_verified = users.email_verified OR EXCLUDED.email_verified,
                            updated_at = now()
                        RETURNING id
                        """,
                        profile.email,
                        display_name,
                        profile.avatar_url,
                        profile.email_verified,
                    )
                    user_id = row["id"]
                await connection.execute(
                    """
                    INSERT INTO user_identities (
                        user_id, provider, provider_user_id, username, email
                    )
                    VALUES ($1, 'github', $2, $3, $4)
                    ON CONFLICT (provider, provider_user_id) DO UPDATE
                    SET username = EXCLUDED.username, email = EXCLUDED.email
                    """,
                    user_id,
                    profile.subject,
                    profile.login,
                    profile.email,
                )
                await connection.execute(
                    """
                    UPDATE users
                    SET display_name = COALESCE(NULLIF($2, ''), display_name),
                        avatar_url = COALESCE($3, avatar_url),
                        updated_at = now()
                    WHERE id = $1
                    """,
                    user_id,
                    display_name,
                    profile.avatar_url,
                )
                if profile.installation_id:
                    await _upsert_installation(
                        connection,
                        user_id,
                        installation_id=profile.installation_id,
                        account_login=profile.account_login or profile.login,
                        account_type=profile.account_type or "User",
                    )
            return await read_user(pool, user_id)
    except ValueError:
        raise
    except Exception as exc:
        raise StateUnavailableError(
            f"could not persist GitHub user: {type(exc).__name__}"
        ) from exc


async def record_github_installation(
    pool: asyncpg.Pool,
    user_id: UUID,
    *,
    installation_id: str,
    account_login: str,
    account_type: str = "User",
) -> dict[str, Any]:
    """Bind a GitHub App installation to the signed-in user. No tokens."""
    kind = account_type if account_type in {"User", "Organization"} else "User"
    try:
        async with pool.acquire() as connection:
            await _upsert_installation(
                connection,
                user_id,
                installation_id=installation_id,
                account_login=account_login,
                account_type=kind,
            )
        return await read_user(pool, user_id)
    except Exception as exc:
        raise StateUnavailableError(
            f"could not persist GitHub installation: {type(exc).__name__}"
        ) from exc


async def _upsert_installation(
    connection: asyncpg.Connection,
    user_id: UUID,
    *,
    installation_id: str,
    account_login: str,
    account_type: str,
) -> None:
    await connection.execute(
        """
        INSERT INTO github_connections (
            user_id, installation_id, account_login, account_type
        )
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE
        SET installation_id = EXCLUDED.installation_id,
            account_login = EXCLUDED.account_login,
            account_type = EXCLUDED.account_type,
            suspended_at = NULL,
            updated_at = now()
        """,
        user_id,
        installation_id,
        account_login,
        account_type,
    )


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


async def find_user_id_by_github_login(pool: asyncpg.Pool, login: str) -> UUID | None:
    """Return the console user who linked this GitHub login, if any."""
    wanted = login.strip()
    if not wanted:
        return None
    try:
        row = await pool.fetchrow(
            """
            SELECT user_id FROM user_identities
            WHERE provider = 'github' AND lower(username) = lower($1)
            ORDER BY (provider_user_id = '0') ASC, created_at DESC
            LIMIT 1
            """,
            wanted,
        )
    except Exception as exc:
        raise StateUnavailableError(
            f"could not look up GitHub login: {type(exc).__name__}"
        ) from exc
    return row["user_id"] if row is not None else None


async def delete_github_connection(pool: asyncpg.Pool, user_id: UUID) -> dict[str, Any] | None:
    """Drop the App install and GitHub identity. Does not touch GitHub.com.

    The identity must go too: `/me` re-binds an install when `github_username`
    is set and no `github_connections` row exists.
    """
    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchval(
                    """
                    DELETE FROM github_connections
                    WHERE user_id = $1
                    RETURNING user_id
                    """,
                    user_id,
                )
                if row is None:
                    return None
                await connection.execute(
                    """
                    DELETE FROM user_identities
                    WHERE user_id = $1 AND provider = 'github'
                    """,
                    user_id,
                )
        return await read_user(pool, user_id)
    except Exception as exc:
        raise StateUnavailableError(
            f"could not disconnect GitHub: {type(exc).__name__}"
        ) from exc


async def read_github_connection(pool: asyncpg.Pool, user_id: UUID) -> dict[str, Any] | None:
    """Return the GitHub App installation bound to this user, if any."""
    try:
        row = await pool.fetchrow(
            """
            SELECT installation_id, account_login, account_type
            FROM github_connections
            WHERE user_id = $1 AND suspended_at IS NULL
            """,
            user_id,
        )
    except Exception as exc:
        raise StateUnavailableError(
            f"could not read GitHub connection: {type(exc).__name__}"
        ) from exc
    if row is None:
        return None
    return {
        "installation_id": row["installation_id"],
        "account_login": row["account_login"],
        "account_type": row["account_type"],
    }
