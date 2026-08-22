"""SDK inventory: the provider's client library, read from the manifest."""

import json
from pathlib import Path

from patchapi_repo_indexer.index import build_inventory_literal
from patchapi_repo_indexer.models import ApiUsageInventory

from packages.repo_scan.classify import UsageKind

NULL_SHA = "0" * 40
REPOSITORY = "patchapi-fixtures/repo-with-manifests"


def index(root: Path) -> ApiUsageInventory:
    return build_inventory_literal(
        root=root, repository=REPOSITORY, observed_sha=NULL_SHA, provider="google"
    )


def _tree(root: Path) -> Path:
    (root / "package.json").write_text(
        json.dumps({"dependencies": {"@google/genai": "^1.4.0", "next": "15.0.0"}}, indent=2),
        encoding="utf-8",
    )
    (root / "requirements.txt").write_text(
        "google-generativeai==0.8.3\nfastapi>=0.115\n", encoding="utf-8"
    )
    (root / "app").mkdir()
    (root / "app" / "main.py").write_text('MODEL = "imagen-4.0-generate-001"\n', encoding="utf-8")
    return root


def test_the_provider_sdk_is_inventory_alongside_the_model_id(tmp_path):
    """A call site names the model but never the SDK version; the manifest names
    the version but never the model. Both are needed to see the whole break."""
    inventory = index(_tree(tmp_path))

    assert set(inventory.matched_identifiers) == {
        "imagen-4.0-generate-001",
        "npm:@google/genai",
        "pypi:google-generativeai",
    }


def test_a_dependency_that_is_nobody_watched_package_is_left_out(tmp_path):
    """PatchAPI is not a dependency updater. `next` and `fastapi` break nothing
    a subscribed provider is responsible for."""
    identifiers = set(index(_tree(tmp_path)).matched_identifiers)

    assert not {item for item in identifiers if "next" in item or "fastapi" in item}


def test_the_pinned_constraint_is_the_evidence(tmp_path):
    usage = next(
        item for item in index(_tree(tmp_path)).usages if item.identifier == "npm:@google/genai"
    )

    assert usage.file_path == "package.json"
    assert usage.excerpt == '"@google/genai": "^1.4.0",'
    assert usage.usage_kind is UsageKind.CONFIGURATION


def test_vendored_manifests_are_not_the_customers_dependencies(tmp_path):
    _tree(tmp_path)
    vendored = tmp_path / "node_modules" / "someone-else"
    vendored.mkdir(parents=True)
    (vendored / "package.json").write_text(
        json.dumps({"dependencies": {"@google/genai": "^0.1.0"}}), encoding="utf-8"
    )

    paths = {usage.file_path for usage in index(tmp_path).usages}

    assert not any(path.startswith("node_modules/") for path in paths)
