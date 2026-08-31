"""The notice path, exercised by a provider nobody wrote a module for.

`packages/providers/google/tests` already covers the schema's refusals in depth.
What is proven here is narrower and is the whole point of the descriptor work:
a real change from a provider with no Python of its own — no adapter subclass,
no branch in the normalizer, only a descriptor and a JSON document — becomes a
`ChangeManifest` with verifiable evidence.

The fixture is Stripe's 2026-03-25.dahlia removal of the deprecated Payment
Intents, Setup Intents and Sources methods from Stripe.js, and `pages/` holds
the published page it cites, captured and hashed.
"""

from datetime import date
from pathlib import Path

import pytest

from packages.providers.notice import load_notice_file, manifest_from_notice_file
from packages.schemas.enums import ChangeType, Severity, TrustClassification

GOLDEN = Path(__file__).resolve().parent / "golden"
STRIPE_NOTICE = GOLDEN / "stripe-legacy-stripejs-removal.json"


@pytest.fixture(scope="module")
def manifest():
    return manifest_from_notice_file(STRIPE_NOTICE)


def test_a_provider_with_no_module_of_its_own_still_normalizes(manifest):
    assert manifest.provider == "stripe"
    assert manifest.change_id == "stripe-remove-legacy-stripejs-methods-2026-03-25"
    assert manifest.change_type is ChangeType.ENDPOINT_REMOVAL
    assert manifest.effective_at == date(2026, 3, 25)
    assert manifest.trust is TrustClassification.UNTRUSTED_PROVIDER_INPUT


def test_severity_comes_from_the_pinned_table_not_the_provider(manifest):
    """Stripe does not get to call its own change low-severity."""
    assert manifest.severity is Severity.CRITICAL


def test_every_removed_method_is_carried_into_the_manifest(manifest):
    assert set(manifest.affected_identifiers) == {
        "stripe.handleCardPayment",
        "stripe.confirmPaymentIntent",
        "stripe.handleFpxPayment",
        "stripe.handleCardSetup",
        "stripe.confirmSetupIntent",
        "stripe.createSource",
        "stripe.retrieveSource",
    }


def test_a_change_with_no_single_successor_declares_none(manifest):
    """Seven identifiers, three replacements. Naming one would be a wrong answer."""
    assert manifest.recommended_replacement is None
    assert manifest.semantic_migration_required is True


def test_only_the_replacement_family_becomes_a_migration_constraint(manifest):
    """The descriptor names which family describes the replacement; nothing reads key names."""
    joined = " ".join(manifest.migration_constraints)

    assert "confirmCardPayment" in joined
    assert "no Stripe.js replacement" in joined
    assert "throw at call time" not in joined, "the retired surface is implied by the identifiers"


def test_the_cited_page_is_captured_and_rehashes_to_what_the_notice_recorded(manifest):
    """The evidence gate is provider-neutral: a real Stripe page passes it."""
    assert manifest.has_verifiable_evidence is True

    (snapshot,) = manifest.source_snapshots
    assert str(snapshot.source_url).endswith("remove-legacy-stripejs-methods.md")
    assert snapshot.media_type == "text/markdown"


def test_the_captured_page_is_the_one_the_notice_cites():
    """Guards the fixture itself: a re-captured page must be re-hashed."""
    notice = load_notice_file(STRIPE_NOTICE)
    page = (STRIPE_NOTICE.parent / notice.source_snapshot.path).read_text(encoding="utf-8")

    for identifier in notice.affected_identifiers:
        method = identifier.removeprefix("stripe.")
        assert f"`{method}`" in page, f"{method} is not named on the page the notice cites"
