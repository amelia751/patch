"""A linked GitHub account owns the console photo.

Google's hosted picture 403s in the dashboard (the Referer from Cloud Run and
localhost is refused). GitHub's public avatar URL does not. `/me` therefore
returns the GitHub photo whenever an identity is linked, even if an earlier
Google sign-in left its own URL on the row.
"""

from __future__ import annotations

from datetime import UTC, datetime

from packages.state.users import _profile, github_avatar_url


def _row(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "anh@example.test",
        "display_name": "Anh",
        "avatar_url": "https://lh3.googleusercontent.com/a/google-photo",
        "email_verified": True,
        "github_id": None,
        "github_username": None,
        "type": "personal",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "settings": {},
    }
    fields.update(overrides)
    return fields


def test_a_github_id_is_the_public_avatar() -> None:
    assert github_avatar_url(github_id=751, github_username="amelia751") == (
        "https://avatars.githubusercontent.com/u/751"
    )


def test_a_placeholder_id_falls_back_to_the_login() -> None:
    """`provider_user_id = '0'` is not a real GitHub account."""
    assert github_avatar_url(github_id=0, github_username="amelia751") == (
        "https://github.com/amelia751.png"
    )


def test_no_github_identity_means_no_github_avatar() -> None:
    assert github_avatar_url(github_id=None, github_username=None) is None
    assert github_avatar_url(github_id=None, github_username="  ") is None


def test_me_uses_the_github_photo_when_github_is_linked() -> None:
    profile = _profile(_row(github_id=751, github_username="amelia751"), github_app_installed=True)

    assert profile["avatar_url"] == "https://avatars.githubusercontent.com/u/751"


def test_me_keeps_the_google_photo_when_github_is_not_linked() -> None:
    profile = _profile(_row(), github_app_installed=False)

    assert profile["avatar_url"] == "https://lh3.googleusercontent.com/a/google-photo"
