"""Descriptors are the only place a provider's detection surface is declared.

The properties worth pinning are the ones a second provider would otherwise
break: reads fail closed, a malformed descriptor is refused at load rather than
mid-scan, and the search intent changes when — and only when — what a scan
looks for changes.
"""

import json

import pytest
from pydantic import ValidationError

from packages.providers import registry, sdk
from packages.providers.descriptor import ProviderDescriptor, load_descriptor
from packages.providers.errors import DescriptorError, UnknownProviderError

GOOGLE = "google"
STRIPE = "stripe"


@pytest.fixture(autouse=True)
def _restore_registry():
    """Every test starts from the shipped descriptors and leaves them intact."""
    registry.reload_builtin()
    yield
    registry.reload_builtin()


def minimal(**overrides) -> dict:
    payload = {
        "descriptor_version": "1.0.0",
        "provider_id": "acme-cloud",
        "display_name": "Acme Cloud",
        "identifier_families": [{"name": "models", "pattern": r"acme-\d+"}],
        "watched_identifiers": {"retired": ["acme-1"]},
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- #
# The shipped descriptors
# --------------------------------------------------------------------------- #


def test_both_shipped_providers_are_registered():
    assert registry.known_providers() == (GOOGLE, STRIPE)


def test_every_shipped_descriptor_declares_something_to_look_for():
    """A descriptor with no patterns and no literals reports every tree clean."""
    for descriptor in registry.descriptors():
        assert descriptor.patterns() or descriptor.all_watched_identifiers()


def test_an_unregistered_provider_is_an_error_not_an_empty_answer():
    """Fail closed. An empty pattern set is byte-for-byte 'nothing is affected'."""
    with pytest.raises(UnknownProviderError, match="no provider descriptor registered"):
        registry.descriptor_for("not-a-provider")


def test_the_error_names_what_is_registered():
    with pytest.raises(UnknownProviderError, match="google, stripe"):
        registry.descriptor_for("not-a-provider")


# --------------------------------------------------------------------------- #
# Validation happens at load, not mid-scan
# --------------------------------------------------------------------------- #


def test_a_pattern_that_does_not_compile_is_refused_at_load():
    """A regex that fails during a query would degrade one repository to 'clean'."""
    with pytest.raises(ValidationError, match="does not compile"):
        load_descriptor(minimal(identifier_families=[{"name": "bad", "pattern": "acme-(["}]))


def test_a_descriptor_that_looks_for_nothing_is_refused():
    with pytest.raises(ValidationError, match="would search for nothing"):
        load_descriptor(minimal(identifier_families=[], watched_identifiers={}))


def test_an_unknown_package_ecosystem_is_refused():
    with pytest.raises(ValidationError, match="unknown package ecosystem"):
        load_descriptor(minimal(packages=[{"ecosystem": "cargo", "name": "acme"}]))


def test_a_descriptor_from_a_newer_producer_is_refused():
    with pytest.raises(ValidationError, match="unsupported descriptor version"):
        load_descriptor(minimal(descriptor_version="9.9.9"))


def test_a_malformed_document_names_the_file_it_came_from(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DescriptorError, match="broken.json"):
        registry.load_directory(tmp_path)


# --------------------------------------------------------------------------- #
# Search intent
# --------------------------------------------------------------------------- #


def test_search_intent_is_stable_for_an_unchanged_descriptor():
    descriptor = registry.descriptor_for(GOOGLE)
    assert descriptor.search_intent() == registry.descriptor_for(GOOGLE).search_intent()


def test_two_providers_never_share_a_search_intent():
    assert (
        registry.descriptor_for(GOOGLE).search_intent()
        != registry.descriptor_for(STRIPE).search_intent()
    )


def test_widening_a_watchlist_changes_the_search_intent():
    """This is what makes an already-indexed repository re-scan for one provider."""
    before = registry.descriptor_for(GOOGLE)
    widened = ProviderDescriptor.model_validate(
        before.model_dump() | {"watched_identifiers": {"extra": ["imagen-5.0-generate-001"]}}
    )
    assert widened.search_intent() != before.search_intent()


def test_a_pattern_that_is_declared_but_not_queried_stays_out_of_the_intent():
    """A retired family keeps naming old findings without re-scanning the fleet."""
    google = registry.descriptor_for(GOOGLE)
    assert google.pattern_named("gemini_20_family") not in google.patterns()


# --------------------------------------------------------------------------- #
# Onboarding a provider is data
# --------------------------------------------------------------------------- #


def test_a_descriptor_dropped_in_a_directory_onboards_a_provider(tmp_path):
    (tmp_path / "acme.json").write_text(json.dumps(minimal()), encoding="utf-8")

    registry.load_directory(tmp_path)

    assert registry.has_provider("acme-cloud")
    assert registry.descriptor_for("acme-cloud").patterns() == (r"acme-\d+",)


def test_a_registered_descriptor_supersedes_the_shipped_one():
    """A descriptor loaded from Postgres has to win over the one in the image."""
    replacement = load_descriptor(minimal(provider_id=GOOGLE, display_name="Google (widened)"))
    registry.register(replacement)

    assert registry.descriptor_for(GOOGLE).display_name == "Google (widened)"


def test_onboarding_a_provider_widens_the_watched_package_set(tmp_path):
    """The SDK map is a read of the registry, so a new descriptor is enough."""
    (tmp_path / "acme.json").write_text(
        json.dumps(minimal(packages=[{"ecosystem": "npm", "name": "@acme/sdk"}])),
        encoding="utf-8",
    )
    assert sdk.provider_for_package("npm", "@acme/sdk") is None

    registry.load_directory(tmp_path)

    assert sdk.provider_for_package("npm", "@acme/sdk") == "acme-cloud"


# --------------------------------------------------------------------------- #
# Identifier ownership
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("identifier", "provider"),
    [
        ("imagen-4.0-generate-001", GOOGLE),
        ("gemini-3.5-flash", GOOGLE),
        ("aiplatform.googleapis.com", GOOGLE),
        ("stripe.createSource", STRIPE),
        ("2026-03-25.dahlia", STRIPE),
        ("api.stripe.com", STRIPE),
    ],
)
def test_a_descriptor_claims_its_own_identifiers(identifier, provider):
    assert registry.provider_for_identifier(identifier) == provider


def test_an_identifier_nobody_declares_belongs_to_nobody():
    """Guessing an owner would send it to a surface that answers 404 for 'never heard of it'."""
    assert registry.provider_for_identifier("acme-widget-v1") is None
