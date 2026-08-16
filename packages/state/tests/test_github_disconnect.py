"""GitHub disconnect drops the install row and the identity."""

from pathlib import Path

USERS_PY = Path(__file__).resolve().parents[1] / "users.py"
GITHUB_ROUTES_PY = Path(__file__).resolve().parents[1] / "github_routes.py"


def test_delete_github_connection_removes_install_and_identity() -> None:
    """`/me` re-binds an install when a GitHub identity remains.

    Disconnect must delete both `github_connections` and the github
    `user_identities` row so the header stays unlinked.
    """
    source = USERS_PY.read_text(encoding="utf-8")
    start = source.index("async def delete_github_connection")
    body = source[start : start + 1800]
    assert "DELETE FROM github_connections" in body
    assert "DELETE FROM user_identities" in body
    assert "provider = 'github'" in body


def test_disconnect_route_is_a_delete_on_connection() -> None:
    source = GITHUB_ROUTES_PY.read_text(encoding="utf-8")
    assert '@router.delete("/connection")' in source
    assert "delete_github_connection" in source
