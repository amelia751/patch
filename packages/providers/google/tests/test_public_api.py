"""The adapter's public surface stays in step with what it advertises."""

import pytest

import packages.providers.google as google_provider


def test_all_matches_the_export_table():
    assert sorted(google_provider.__all__) == sorted(google_provider._EXPORTS)


def test_every_exported_name_resolves():
    unresolved = [name for name in google_provider.__all__ if not hasattr(google_provider, name)]
    assert unresolved == []


def test_an_unknown_name_raises_attribute_error():
    missing = "definitely_not_exported"
    with pytest.raises(AttributeError, match=missing):
        getattr(google_provider, missing)
