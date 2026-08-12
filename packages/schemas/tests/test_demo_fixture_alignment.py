"""The golden manifest and the demo provider fixture describe the same change.

`demo/fixtures/` is owned by the demo tree, so this test does not parse it as a
contract — normalizing provider evidence is the provider adapter's job. It only
asserts the pinned facts have not drifted apart between the two trees.
"""

import json

import pytest

from packages.schemas import ChangeManifest

DEMO_FIXTURE = "demo/fixtures/google-imagen4-deprecation.json"


@pytest.fixture
def demo_fixture(repo_root):
    path = repo_root / DEMO_FIXTURE
    if not path.exists():
        pytest.skip(f"{DEMO_FIXTURE} not present in this checkout")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def golden_manifest(load_golden):
    return ChangeManifest.model_validate(load_golden("change_manifest.imagen4.json"))


def test_pinned_facts_agree(demo_fixture, golden_manifest):
    assert golden_manifest.provider == demo_fixture["provider"]
    assert golden_manifest.change_id == demo_fixture["change_id"]
    assert golden_manifest.change_type.value == demo_fixture["change_type"]
    assert golden_manifest.effective_at.isoformat() == demo_fixture["effective_at"]
    assert golden_manifest.affected_identifiers == demo_fixture["affected_identifiers"]
    assert golden_manifest.recommended_replacement == demo_fixture["recommended_replacement"]


def test_source_urls_agree(demo_fixture, golden_manifest):
    manifest_urls = {str(url).rstrip("/") for url in golden_manifest.source_urls}
    fixture_urls = {url.rstrip("/") for url in demo_fixture["source_urls"]}

    assert manifest_urls == fixture_urls
