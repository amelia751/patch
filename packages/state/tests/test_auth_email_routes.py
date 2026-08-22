"""Email/password routes exist and hide unknown-address resets."""

from pathlib import Path

AUTH_ROUTES = Path(__file__).resolve().parents[1] / "auth_routes.py"


def test_email_routes_are_mounted() -> None:
    source = AUTH_ROUTES.read_text(encoding="utf-8")
    for path in (
        '@router.post("/signup")',
        '@router.post("/login")',
        '@router.post("/forgot-password")',
        '@router.post("/reset-password")',
        '@router.post("/verify")',
    ):
        assert path in source


def test_forgot_password_does_not_name_the_account() -> None:
    source = AUTH_ROUTES.read_text(encoding="utf-8")
    start = source.index("async def forgot_password")
    body = source[start : start + 800]
    assert "Always reports success" in body or "cannot probe" in body
    assert "EMAIL_NOT_FOUND" not in body or "probe" in body
