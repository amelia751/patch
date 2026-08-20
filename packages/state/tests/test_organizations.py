import pytest

from packages.state.organizations import first_name, organization_name, organization_slug


def test_first_name_prefers_given_name() -> None:
    assert first_name(given_name="Anh", display_name="Lam Dao Que Anh") == "Anh"


def test_first_name_uses_display_name_token() -> None:
    assert first_name(display_name="Anh Lam") == "Anh"


def test_first_name_uses_signup_first_name() -> None:
    assert first_name(display_name="Anh") == "Anh"


def test_first_name_requires_a_name() -> None:
    with pytest.raises(ValueError, match="first name is required"):
        first_name()


def test_organization_name_is_always_possessive() -> None:
    assert organization_name(given_name="Anh") == "Anh's Organization"
    assert organization_name(display_name="Alex Chen") == "Alex's Organization"


def test_organization_slug_strips_apostrophe() -> None:
    assert organization_slug("Anh's Organization") == "anhs-organization"
