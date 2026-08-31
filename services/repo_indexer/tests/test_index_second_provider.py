"""Index a tree for a provider that exists only as a descriptor.

`test_index.py` proves the Layer A contract against Google. This file proves the
same contract holds for Stripe, which has no module, no adapter subclass and no
branch anywhere in the indexer — only `packages/providers/descriptors/stripe.json`
and a rule directory. If onboarding a provider is data rather than a deploy,
these assertions are the evidence.

The findings are Stripe's 2026-03-25.dahlia removal of the deprecated Payment
Intents, Setup Intents and Sources methods from Stripe.js.
"""

from pathlib import Path

import pytest
from patchapi_repo_indexer.astgrep.runner import available
from patchapi_repo_indexer.config import SCOPE_FULL_TREE, watchlist_for
from patchapi_repo_indexer.errors import UnknownProviderError
from patchapi_repo_indexer.index import _confirm_structurally, build_inventory
from patchapi_repo_indexer.models import ApiUsageInventory
from patchapi_repo_indexer.zoekt.patterns import patterns_for

from packages.repo_scan.classify import UsageKind

NULL_SHA = "0" * 40
FIXTURE_REPO_FULL_NAME = "patchapi-fixtures/repo-with-stripe"
REMOVED_CARD_PAYMENT = "stripe.handleCardPayment"
REMOVED_CARD_SETUP = "stripe.handleCardSetup"

needs_ast_grep = pytest.mark.skipif(not available(), reason="ast-grep is not installed")


def index(root: Path, **overrides) -> ApiUsageInventory:
    kwargs = {
        "root": root,
        "repository": FIXTURE_REPO_FULL_NAME,
        "observed_sha": NULL_SHA,
        "provider": "stripe",
    }
    kwargs.update(overrides)
    return build_inventory(**kwargs)


def test_the_watchlist_resolves_for_a_provider_with_no_module():
    watched = watchlist_for("stripe")

    assert REMOVED_CARD_PAYMENT in watched
    assert "stripe.retrieveSource" in watched
    assert len(watched) == len(set(watched)), "a duplicated literal double-reports a finding"
    assert watched == watchlist_for("stripe"), "the watchlist must be stable across calls"


def test_an_unregistered_provider_is_still_an_error_not_an_empty_watchlist():
    """Fail closed survives generalization. An empty watchlist looks like good news."""
    with pytest.raises(UnknownProviderError):
        watchlist_for("acme-payments")


def test_each_provider_searches_for_its_own_thing():
    google = patterns_for("google")
    stripe = patterns_for("stripe")

    assert not set(google) & set(stripe)
    assert any("googleapis" in pattern for pattern in google)
    assert any("stripe" in pattern for pattern in stripe)


def test_finds_the_removed_stripejs_methods(stripe_fixture_repo):
    inventory = index(stripe_fixture_repo)

    assert not inventory.is_empty
    assert inventory.provider == "stripe"
    assert inventory.scope == SCOPE_FULL_TREE
    assert {REMOVED_CARD_PAYMENT, REMOVED_CARD_SETUP} <= set(inventory.matched_identifiers)


def test_reports_the_runtime_call_site_with_its_line(stripe_fixture_repo):
    inventory = index(stripe_fixture_repo)

    runtime = [usage for usage in inventory.usages if usage.file_path == "src/checkout.ts"]
    hit = next(usage for usage in runtime if usage.identifier == REMOVED_CARD_PAYMENT)

    assert hit.usage_kind is UsageKind.RUNTIME_SOURCE
    assert hit.is_runtime
    source = (stripe_fixture_repo / "src" / "checkout.ts").read_text(encoding="utf-8").splitlines()
    assert REMOVED_CARD_PAYMENT in source[hit.line_start - 1]


def test_separates_runtime_usage_from_documentation(stripe_fixture_repo):
    inventory = index(stripe_fixture_repo)

    by_path = {usage.file_path: usage.usage_kind for usage in inventory.usages}
    assert by_path["README.md"] is UsageKind.DOCUMENTATION_EXAMPLE
    assert by_path["src/checkout.ts"] is UsageKind.RUNTIME_SOURCE


def test_a_vendored_copy_is_not_the_customers_code(stripe_fixture_repo):
    inventory = index(stripe_fixture_repo)

    assert not [usage for usage in inventory.usages if usage.file_path.startswith("vendor/")]


def test_a_same_named_helper_is_not_reported(stripe_fixture_repo):
    """The watched identifier carries its receiver, so `attachments.createSource` misses."""
    inventory = index(stripe_fixture_repo)

    assert not [usage for usage in inventory.usages if usage.file_path == "src/uploads.ts"]


def test_a_file_with_nothing_in_it_yields_no_finding(stripe_fixture_repo):
    inventory = index(stripe_fixture_repo)

    assert not [usage for usage in inventory.usages if usage.file_path == "src/unrelated.ts"]


@needs_ast_grep
def test_layer_b_confirms_the_call_site_with_stripes_own_rule(stripe_fixture_repo):
    """Layer B runs on the Zoekt path, so it is exercised on the Layer A rows directly."""
    records = index(stripe_fixture_repo).usages
    confirmed = _confirm_structurally(stripe_fixture_repo, records, "stripe")

    by_path = {
        (usage.file_path, usage.line_start): usage.surface for usage in confirmed if usage.surface
    }
    assert by_path == {
        ("config/stripe.json", 2): "stripe-api-version-pin",
        ("src/checkout.ts", 9): "stripe-legacy-stripejs-call",
        ("src/checkout.ts", 13): "stripe-legacy-stripejs-call",
    }


@needs_ast_grep
def test_the_prose_mention_is_never_confirmed(stripe_fixture_repo):
    """A README that names the method is documentation, not a call that throws."""
    records = index(stripe_fixture_repo).usages
    confirmed = _confirm_structurally(stripe_fixture_repo, records, "stripe")

    assert not [usage for usage in confirmed if usage.file_path == "README.md" and usage.surface]


@needs_ast_grep
def test_no_google_rule_confirms_a_stripe_finding(stripe_fixture_repo):
    """Cross-provider confirmation would name a call shape the finding is not."""
    records = index(stripe_fixture_repo).usages
    confirmed = _confirm_structurally(stripe_fixture_repo, records, "google")

    assert not [usage.surface for usage in confirmed if usage.surface]
