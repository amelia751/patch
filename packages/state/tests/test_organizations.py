from packages.state.organizations import (
    FALLBACK_NAME,
    first_name,
    organization_name,
    organization_slug,
)


def test_first_name_prefers_given_name() -> None:
    assert first_name(given_name="Anh", display_name="Lam Dao Que Anh") == "Anh"


def test_first_name_uses_display_name_token() -> None:
    assert first_name(display_name="Anh Lam") == "Anh"


def test_first_name_ignores_dotted_email_local() -> None:
    assert first_name(email="amelia.anh.lam@gmail.com") is None


def test_first_name_uses_simple_email_local() -> None:
    assert first_name(email="anh@example.com") == "Anh"


def test_organization_name_with_first_name() -> None:
    assert organization_name(given_name="Anh") == "Anh's Organization"


def test_organization_name_without_first_name() -> None:
    assert organization_name(email="amelia.anh.lam@gmail.com") == FALLBACK_NAME


def test_organization_slug_strips_apostrophe() -> None:
    assert organization_slug("Anh's Organization") == "anhs-organization"
