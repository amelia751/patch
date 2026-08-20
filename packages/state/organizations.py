"""Personal organization name stored on the user row.

The dashboard breadcrumb is one personal org per user. The name is derived
once from the sign-in profile and then kept in `users.settings`.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING
from uuid import UUID

from packages.state.pool import StateUnavailableError

if TYPE_CHECKING:
    import asyncpg

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def first_name(
    *,
    given_name: str | None = None,
    display_name: str | None = None,
) -> str:
    """First name from Google given_name, or the first word of the signup name."""
    for raw in (given_name, display_name):
        token = _name_token(raw)
        if token:
            return token
    raise ValueError("first name is required")


def organization_name(
    *,
    given_name: str | None = None,
    display_name: str | None = None,
) -> str:
    """Always '{First}'s Organization' — email, Google, and GitHub all collect a name."""
    return f"{first_name(given_name=given_name, display_name=display_name)}'s Organization"


def organization_slug(name: str) -> str:
    cleaned = _SLUG_STRIP.sub("-", name.lower().replace("'", "")).strip("-")
    return cleaned or "organization"


def personal_organization(user_id: UUID, name: str, slug: str) -> dict[str, str]:
    return {
        "id": str(user_id),
        "name": name,
        "slug": slug,
        "type": "personal",
        "role": "owner",
    }


async def read_personal_organization(
    pool: asyncpg.Pool,
    user_id: UUID,
    *,
    given_name: str | None = None,
) -> dict[str, str]:
    """Return the personal org, writing the derived name on first read."""
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT display_name, email, settings
                FROM users
                WHERE id = $1
                """,
                user_id,
            )
            if row is None:
                raise StateUnavailableError("user not found")
            settings = row["settings"] if isinstance(row["settings"], dict) else {}
            name = (settings.get("organization_name") or "").strip()
            slug = (settings.get("organization_slug") or "").strip()
            if not name:
                name = organization_name(
                    given_name=given_name,
                    display_name=row["display_name"],
                )
                slug = organization_slug(name)
                merged = {**settings, "organization_name": name, "organization_slug": slug}
                await connection.execute(
                    """
                    UPDATE users
                    SET settings = $2::jsonb, updated_at = now()
                    WHERE id = $1
                    """,
                    user_id,
                    json.dumps(merged),
                )
            elif not slug:
                slug = organization_slug(name)
            return personal_organization(user_id, name, slug)
    except StateUnavailableError:
        raise
    except Exception as exc:
        raise StateUnavailableError(
            f"could not load organization: {type(exc).__name__}"
        ) from exc


async def update_personal_organization(
    pool: asyncpg.Pool,
    user_id: UUID,
    *,
    name: str | None = None,
    slug: str | None = None,
) -> dict[str, str]:
    """Rename the personal org. Empty names are refused."""
    current = await read_personal_organization(pool, user_id)
    next_name = (name or current["name"]).strip()
    if not next_name:
        raise ValueError("organization name is required")
    next_slug = organization_slug((slug or current["slug"] or next_name).strip())
    try:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT settings FROM users WHERE id = $1", user_id
            )
            if row is None:
                raise StateUnavailableError("user not found")
            settings = row["settings"] if isinstance(row["settings"], dict) else {}
            merged = {
                **settings,
                "organization_name": next_name,
                "organization_slug": next_slug,
            }
            await connection.execute(
                """
                UPDATE users
                SET settings = $2::jsonb, updated_at = now()
                WHERE id = $1
                """,
                user_id,
                json.dumps(merged),
            )
        return personal_organization(user_id, next_name, next_slug)
    except StateUnavailableError:
        raise
    except Exception as exc:
        raise StateUnavailableError(
            f"could not update organization: {type(exc).__name__}"
        ) from exc


def _name_token(raw: str | None) -> str | None:
    if not raw:
        return None
    token = raw.strip().split()[0] if raw.strip() else ""
    if not token:
        return None
    return token[0].upper() + token[1:]
