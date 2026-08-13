"""The fail-soft property (repo-indexer.md §7.1): a dead index still answers.

These tests must run on a machine with no Zoekt installed, because that is the
condition they describe. Nothing here is skipped.
"""

import logging
from pathlib import Path

import pytest
from patchapi_repo_indexer import index as index_module
from patchapi_repo_indexer.config import SCOPE_CHANGED_PATHS, SCOPE_FULL_TREE
from patchapi_repo_indexer.errors import (
    ScanRootError,
    ShardCorruptError,
    UnknownProviderError,
    UnsafePathError,
    ZoektUnavailableError,
)
from patchapi_repo_indexer.index import build_inventory, build_inventory_literal

NULL_SHA = "0" * 40
FIXTURE_REPO_FULL_NAME = "patchapi-fixtures/repo-with-imagen"
RETIRED_MODEL = "imagen-4.0-generate-001"


def index(root: Path, **overrides) -> object:
    kwargs = {"root": root, "repository": FIXTURE_REPO_FULL_NAME, "observed_sha": NULL_SHA}
    kwargs.update(overrides)
    return build_inventory(**kwargs)


@pytest.fixture
def zoekt_backend(monkeypatch):
    """Select the indexed backend regardless of the ambient environment."""
    monkeypatch.setattr(index_module, "INDEX_BACKEND", "zoekt")


@pytest.fixture
def zoekt_down(monkeypatch, zoekt_backend):
    """Make the shard step raise the way a missing binary does."""

    def unavailable(*args, **kwargs):
        raise ZoektUnavailableError("zoekt-git-index is not on PATH")

    monkeypatch.setattr(index_module.zoekt_shard, "index_repository", unavailable)
    monkeypatch.setattr(index_module.zoekt_shard, "delta_index", unavailable)


@pytest.fixture
def shard_corrupt(monkeypatch, zoekt_backend):
    def corrupt(*args, **kwargs):
        raise ShardCorruptError("shard file 0.zoekt is 12 bytes: truncated, not empty")

    monkeypatch.setattr(index_module.zoekt_shard, "index_repository", corrupt)
    monkeypatch.setattr(index_module.zoekt_shard, "delta_index", corrupt)


def test_zoekt_down_yields_the_literal_inventory(fixture_repo, zoekt_down):
    inventory = index(fixture_repo)

    assert inventory == build_inventory_literal(
        root=fixture_repo, repository=FIXTURE_REPO_FULL_NAME, observed_sha=NULL_SHA
    )
    assert RETIRED_MODEL in inventory.matched_identifiers
    assert inventory.scope == SCOPE_FULL_TREE


def test_zoekt_down_is_not_an_exception(fixture_repo, zoekt_down):
    # The degradation is the point: the caller sees findings, not a failure.
    assert not index(fixture_repo).is_empty


def test_fallback_is_logged_as_a_warning(fixture_repo, zoekt_down, caplog):
    with caplog.at_level(logging.WARNING, logger="patchapi_repo_indexer.index"):
        index(fixture_repo)

    warnings = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert warnings, "a silent fallback is indistinguishable from a healthy index"
    message = warnings[0].getMessage()
    assert "falling back to literal scan" in message
    assert FIXTURE_REPO_FULL_NAME in message


def test_corrupt_shard_falls_back_rather_than_reporting_clean(fixture_repo, shard_corrupt):
    inventory = index(fixture_repo)

    assert RETIRED_MODEL in inventory.matched_identifiers
    assert inventory.files_scanned > 0


def test_fallback_preserves_the_changed_paths_scope(fixture_repo, zoekt_down):
    inventory = index(fixture_repo, changed_paths=["src/image.ts"])

    assert inventory.scope == SCOPE_CHANGED_PATHS
    assert inventory.files_scanned == 1
    assert {usage.file_path for usage in inventory.usages} == {"src/image.ts"}


def test_fallback_result_is_deterministic(fixture_repo, zoekt_down):
    assert index(fixture_repo).model_dump_json() == index(fixture_repo).model_dump_json()


def test_unknown_provider_still_fails_closed(fixture_repo, zoekt_down):
    # Falling back must not soften a refusal: an unknown provider has no
    # watchlist on either backend, and an empty scan would report every
    # repository as unaffected.
    with pytest.raises(UnknownProviderError):
        index(fixture_repo, provider="acme")


def test_unsafe_changed_path_still_refused(fixture_repo, zoekt_down):
    with pytest.raises(UnsafePathError):
        index(fixture_repo, changed_paths=["../../pyproject.toml"])


def test_missing_root_still_fails(tmp_path, zoekt_down):
    with pytest.raises(ScanRootError):
        index(tmp_path / "not-here")


def test_literal_backend_never_touches_zoekt(fixture_repo, monkeypatch):
    monkeypatch.setattr(index_module, "INDEX_BACKEND", "literal")

    def explode(*args, **kwargs):
        raise AssertionError("the literal backend must not build a shard")

    monkeypatch.setattr(index_module.zoekt_shard, "index_repository", explode)

    assert RETIRED_MODEL in index(fixture_repo).matched_identifiers


def test_a_healthy_index_answers_from_the_shard(fixture_repo, monkeypatch, zoekt_backend):
    """The other side of the fallback: what the indexed backend returns when up.

    The identifier here is not on the pinned watchlist. Catching it is the
    recall the index buys, and the reason a fallback is a degradation rather
    than an equivalent.
    """
    line = '  model: "imagen-5.0-ultra-generate-004",'

    class Shard:
        ref = index_module.zoekt_shard.ShardRef(FIXTURE_REPO_FULL_NAME, "main")

    monkeypatch.setattr(
        index_module.zoekt_shard, "index_repository", lambda *args, **kwargs: Shard()
    )
    monkeypatch.setattr(
        index_module.zoekt_query,
        "search_shards",
        lambda *args, **kwargs: [
            index_module.zoekt_query.ZoektMatch(
                repository=FIXTURE_REPO_FULL_NAME,
                branch="main",
                path="src/image.ts",
                line_number=4,
                line=line,
                matched_text="imagen-5.0-ultra-generate-004",
            )
        ],
    )
    monkeypatch.setattr(
        index_module.zoekt_query, "repository_file_count", lambda *args, **kwargs: 484
    )

    inventory = index(fixture_repo)

    assert inventory.matched_identifiers == ("imagen-5.0-ultra-generate-004",)
    assert inventory.files_scanned == 484
    usage = inventory.usages[0]
    assert usage.file_path == "src/image.ts"
    assert usage.line_start == 4
    assert usage.excerpt == line.strip()
    # `watched_identifiers` still records what was asked for, so a reviewer can
    # tell a pinned identifier from a family member the pattern caught.
    assert "imagen-5.0-ultra-generate-004" not in inventory.watched_identifiers


def test_the_indexed_backend_honours_the_changed_paths_scope(
    fixture_repo, monkeypatch, zoekt_backend
):
    class Shard:
        ref = index_module.zoekt_shard.ShardRef(FIXTURE_REPO_FULL_NAME, "main")

    monkeypatch.setattr(index_module.zoekt_shard, "delta_index", lambda *args, **kwargs: Shard())
    monkeypatch.setattr(
        index_module.zoekt_query, "repository_file_count", lambda *args, **kwargs: 484
    )
    monkeypatch.setattr(
        index_module.zoekt_query,
        "search_shards",
        lambda *args, **kwargs: [
            index_module.zoekt_query.ZoektMatch(
                repository=FIXTURE_REPO_FULL_NAME,
                branch="main",
                path=path,
                line_number=1,
                line=f'model = "{RETIRED_MODEL}"',
                matched_text=RETIRED_MODEL,
            )
            for path in ("src/image.ts", "README.md")
        ],
    )

    inventory = index(fixture_repo, changed_paths=["src/image.ts"])

    # The shard still holds the whole repository; a changed-paths inventory must
    # not report files the push did not touch.
    assert {usage.file_path for usage in inventory.usages} == {"src/image.ts"}
    assert inventory.scope == SCOPE_CHANGED_PATHS
    assert inventory.files_scanned == 1


def test_an_empty_corpus_falls_back_instead_of_reporting_clean(
    fixture_repo, monkeypatch, zoekt_backend, caplog
):
    """The silent false negative this component exists to prevent.

    A shard indexed under a name the `repo:` term does not match answers every
    query with zero hits and HTTP 200 — the same bytes a genuinely unaffected
    repository returns. Reading that as "clean" would hide a real usage behind a
    healthy-looking index, so a scope with no documents degrades to the walk.
    """

    class Shard:
        ref = index_module.zoekt_shard.ShardRef(FIXTURE_REPO_FULL_NAME, "main")

    monkeypatch.setattr(
        index_module.zoekt_shard, "index_repository", lambda *args, **kwargs: Shard()
    )
    monkeypatch.setattr(index_module.zoekt_query, "repository_file_count", lambda *a, **k: 0)

    def must_not_be_trusted(*args, **kwargs):
        return []

    monkeypatch.setattr(index_module.zoekt_query, "search_shards", must_not_be_trusted)

    with caplog.at_level(logging.WARNING, logger="patchapi_repo_indexer.index"):
        inventory = index(fixture_repo)

    assert RETIRED_MODEL in inventory.matched_identifiers
    assert any("falling back to literal scan" in r.getMessage() for r in caplog.records)


def test_query_failure_also_falls_back(fixture_repo, monkeypatch, zoekt_backend):
    """A reachable shard with an unreachable webserver degrades the same way."""

    class Shard:
        ref = index_module.zoekt_shard.ShardRef(FIXTURE_REPO_FULL_NAME, "main")

    monkeypatch.setattr(
        index_module.zoekt_shard, "index_repository", lambda *args, **kwargs: Shard()
    )

    def unreachable(*args, **kwargs):
        raise ZoektUnavailableError("zoekt-webserver is unreachable")

    monkeypatch.setattr(index_module.zoekt_query, "search_shards", unreachable)

    assert RETIRED_MODEL in index(fixture_repo).matched_identifiers
