from datetime import date

import pytest

from packages.state.providers import ProviderStoreError, _parse_since_year


def test_since_year_is_stored_as_january_first() -> None:
    assert _parse_since_year("2008") == date(2008, 1, 1)


def test_since_year_may_be_blank() -> None:
    assert _parse_since_year("") is None
    assert _parse_since_year("  ") is None


def test_since_year_rejects_noise() -> None:
    with pytest.raises(ProviderStoreError, match="four-digit year"):
        _parse_since_year("08")
