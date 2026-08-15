"""The Layer A inventory: what it must find, and what it must never invent."""

from pathlib import Path

import pytest
from patchapi_repo_indexer.config import (
    DETECTION_LAYER,
    GEMINI_20_IDENTIFIERS,
    IMAGEN_4_IDENTIFIERS,
    LITERAL_MATCH_CONFIDENCE,
    SCOPE_CHANGED_PATHS,
    SCOPE_FULL_TREE,
    watchlist_for,
)
from patchapi_repo_indexer.errors import ScanRootError, UnknownProviderError, UnsafePathError
from patchapi_repo_indexer.index import build_inventory
from patchapi_repo_indexer.models import ApiUsageInventory
from pydantic import ValidationError

from packages.repo_scan.classify import UsageKind

# The git null SHA: the fixture tree is not a checkout, so naming a real commit
# would be a fabricated provenance claim.
NULL_SHA = "0" * 40
FIXTURE_REPO_FULL_NAME = "patchapi-fixtures/repo-with-imagen"
RETIRED_MODEL = "imagen-4.0-generate-001"
RETIRED_FAST_MODEL = "imagen-4.0-fast-generate-001"


def index(root: Path, **overrides) -> ApiUsageInventory:
    kwargs = {
        "root": root,
        "repository": FIXTURE_REPO_FULL_NAME,
        "observed_sha": NULL_SHA,
    }
    kwargs.update(overrides)
    return build_inventory(**kwargs)


def test_finds_the_retired_imagen_identifier(fixture_repo):
    inventory = index(fixture_repo)

    assert RETIRED_MODEL in inventory.matched_identifiers
    assert not inventory.is_empty
    assert inventory.scope == SCOPE_FULL_TREE
    assert inventory.provider == "google"
    assert inventory.watched_identifiers == IMAGEN_4_IDENTIFIERS + GEMINI_20_IDENTIFIERS


def test_reports_the_runtime_call_site_with_its_line(fixture_repo):
    inventory = index(fixture_repo)

    runtime = [usage for usage in inventory.usages if usage.file_path == "src/image.ts"]
    assert len(runtime) == 1
    hit = runtime[0]
    assert hit.identifier == RETIRED_MODEL
    assert hit.usage_kind is UsageKind.RUNTIME_SOURCE
    assert hit.is_runtime
    assert hit.detection_layer == DETECTION_LAYER
    assert hit.confidence == LITERAL_MATCH_CONFIDENCE
    # The prefixed form is what the file contains; the identifier stays exact.
    assert "vertex/imagen-4.0-generate-001" in hit.excerpt
    source_line = (fixture_repo / "src" / "image.ts").read_text(encoding="utf-8").splitlines()
    assert RETIRED_MODEL in source_line[hit.line_start - 1]


def test_separates_runtime_usage_from_documentation(fixture_repo):
    inventory = index(fixture_repo)

    by_path = {usage.file_path: usage.usage_kind for usage in inventory.usages}
    assert by_path["README.md"] is UsageKind.DOCUMENTATION_EXAMPLE
    assert by_path["config/models.json"] is UsageKind.CONFIGURATION
    runtime_paths = {usage.file_path for usage in inventory.runtime_usages}
    assert runtime_paths == {"src/image.ts", "config/models.json"}


def test_finds_every_watched_family_member_present(fixture_repo):
    inventory = index(fixture_repo)

    assert set(inventory.matched_identifiers) == {RETIRED_MODEL, RETIRED_FAST_MODEL}


def test_skips_vendored_directories(fixture_repo):
    inventory = index(fixture_repo)

    assert all(not usage.file_path.startswith("vendor/") for usage in inventory.usages)


def test_empty_tree_yields_an_empty_inventory(empty_repo):
    inventory = index(empty_repo)

    assert inventory.is_empty
    assert inventory.usages == ()
    assert inventory.matched_identifiers == ()
    # The scan happened; it simply found nothing.
    assert inventory.files_scanned == 2


def test_directory_with_no_files_yields_an_empty_inventory(tmp_path):
    inventory = index(tmp_path)

    assert inventory.is_empty
    assert inventory.files_scanned == 0


def test_two_indexes_of_the_same_tree_are_identical(fixture_repo):
    first = index(fixture_repo)
    second = index(fixture_repo)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_changed_paths_narrow_the_scan_and_mark_it_partial(fixture_repo):
    inventory = index(fixture_repo, changed_paths=["src/image.ts"])

    assert inventory.scope == SCOPE_CHANGED_PATHS
    assert inventory.files_scanned == 1
    assert {usage.file_path for usage in inventory.usages} == {"src/image.ts"}


def test_changed_path_that_no_longer_exists_is_not_an_error(fixture_repo):
    inventory = index(fixture_repo, changed_paths=["src/deleted.ts"])

    assert inventory.is_empty
    assert inventory.files_scanned == 0


def test_changed_path_escaping_the_root_is_refused(fixture_repo):
    with pytest.raises(UnsafePathError):
        index(fixture_repo, changed_paths=["../../pyproject.toml"])


def test_explicit_identifiers_override_the_watchlist(fixture_repo):
    inventory = index(fixture_repo, identifiers=["gemini-3.5-flash"])

    assert inventory.watched_identifiers == ("gemini-3.5-flash",)
    assert inventory.matched_identifiers == ("gemini-3.5-flash",)


def test_empty_identifier_list_is_refused(fixture_repo):
    # "Search for nothing" must not be reachable by accident: it would report
    # every repository as unaffected.
    with pytest.raises(ValueError):
        index(fixture_repo, identifiers=[" "])


def test_unknown_provider_fails_closed(fixture_repo):
    with pytest.raises(UnknownProviderError):
        index(fixture_repo, provider="acme")


def test_watchlist_for_returns_the_pinned_imagen_and_gemini20_families():
    assert watchlist_for("google") == IMAGEN_4_IDENTIFIERS + GEMINI_20_IDENTIFIERS


def test_indexes_the_gemini20_hello_fixture():
    root = Path(__file__).resolve().parents[3] / "demo" / "gemini20-hello"
    inventory = index(root, repository="amelia751/gemini20-hello")

    assert "gemini-2.0-flash" in inventory.matched_identifiers
    runtime = [usage for usage in inventory.usages if usage.file_path == "generate.py"]
    assert runtime
    assert runtime[0].identifier == "gemini-2.0-flash"


def test_missing_root_is_an_error(tmp_path):
    with pytest.raises(ScanRootError):
        index(tmp_path / "not-here")


def test_file_as_root_is_an_error(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("imagen-4.0-generate-001\n", encoding="utf-8")
    with pytest.raises(ScanRootError):
        index(path)


def test_malformed_sha_is_refused(fixture_repo):
    with pytest.raises(ValidationError):
        index(fixture_repo, observed_sha="not-a-sha")


def test_inventory_round_trips_through_json(fixture_repo):
    inventory = index(fixture_repo)

    restored = ApiUsageInventory.model_validate_json(inventory.model_dump_json())

    assert restored == inventory


def test_inventory_rejects_an_unknown_field(fixture_repo):
    payload = index(fixture_repo).model_dump(mode="json")
    payload["remediation"] = "merge it yourself"

    with pytest.raises(ValidationError):
        ApiUsageInventory.model_validate(payload)
