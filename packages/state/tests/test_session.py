"""Signed session cookies, without a browser."""

from uuid import UUID

from packages.state.session import cookie_kwargs, issue, parse


def test_round_trip() -> None:
    user_id = UUID("5eedda7a-0001-4000-8000-000000000001")
    token = issue(user_id, "secret", now=1_000)
    assert parse(token, "secret", now=1_000) == user_id


def test_wrong_secret_is_rejected() -> None:
    user_id = UUID("5eedda7a-0001-4000-8000-000000000001")
    token = issue(user_id, "secret", now=1_000)
    assert parse(token, "other", now=1_000) is None


def test_local_cookies_are_lax_and_not_secure() -> None:
    flags = cookie_kwargs(secure=False)
    assert flags["samesite"] == "lax"
    assert flags["secure"] is False


def test_https_cookies_are_none_and_secure() -> None:
    flags = cookie_kwargs(secure=True)
    assert flags["samesite"] == "none"
    assert flags["secure"] is True


def test_expired_token_is_rejected() -> None:
    user_id = UUID("5eedda7a-0001-4000-8000-000000000001")
    token = issue(user_id, "secret", now=1_000)
    assert parse(token, "secret", now=1_000 + 60 * 60 * 24 * 8) is None
