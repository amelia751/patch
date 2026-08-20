from datetime import date
from pathlib import Path

import pytest

from packages.state.providers import (
    ProviderStoreError,
    _parse_since_year,
    normalize_provider_slug,
    validate_provider_slug,
)

ROUTES_PY = Path(__file__).resolve().parents[1] / "provider_routes.py"


def test_since_year_is_stored_as_january_first() -> None:
    assert _parse_since_year("2008") == date(2008, 1, 1)


def test_since_year_may_be_blank() -> None:
    assert _parse_since_year("") is None
    assert _parse_since_year("  ") is None


def test_since_year_rejects_noise() -> None:
    with pytest.raises(ProviderStoreError, match="four-digit year"):
        _parse_since_year("08")


def test_slug_is_created_from_the_organization_name() -> None:
    assert normalize_provider_slug("Acme AI") == "acme-ai"
    assert normalize_provider_slug("Anh's Organization") == "anhs-organization"


def test_slug_follows_org_format_rules() -> None:
    assert validate_provider_slug("acme-ai") == "acme-ai"
    with pytest.raises(ProviderStoreError, match="3 characters"):
        validate_provider_slug("ai")
    with pytest.raises(ProviderStoreError, match="start and end"):
        validate_provider_slug("acme-")
    with pytest.raises(ProviderStoreError, match="consecutive hyphens"):
        validate_provider_slug("acme--ai")
    with pytest.raises(ProviderStoreError, match="reserved"):
        validate_provider_slug("google")


def test_check_slug_is_registered_before_slug_routes() -> None:
    source = ROUTES_PY.read_text(encoding="utf-8")
    assert source.index('@router.post("/check-slug")') < source.index('@router.get("/{slug}")')
    assert "provider_slug_available" in source
