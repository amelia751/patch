"""Deterministic inbox classification. No database."""

from packages.state.findings import aggregate_hits, classify, file_hit_kind, is_false_positive
from packages.state.watchlist import GOOGLE_WATCHLIST, watchlist_for


def test_watchlist_is_google_only_and_has_the_flagship_notes() -> None:
    notes = watchlist_for("google")
    ids = {note["external_id"] for note in notes}
    assert ids == {note["external_id"] for note in GOOGLE_WATCHLIST}
    assert "imagen4-retirement-2026-08-17" in ids
    assert "ui-vertex-prefix-leftover" in ids
    assert "adv-fal-ai-not-covered" in ids
    assert watchlist_for("acme") == ()


def test_runtime_hit_is_need_you() -> None:
    status, reason = classify(
        identifiers=["imagen-4.0-generate-001"],
        hits=[{"usage_kind": "runtime_source", "identifier": "imagen-4.0-generate-001"}],
        fail_closed=False,
        false_positive=False,
        change_kind="deprecation",
    )
    assert (status, reason) == ("needs_you", "runtime_hit")


def test_docs_only_stays_watching() -> None:
    status, reason = classify(
        identifiers=["imagen-4.0-generate-001"],
        hits=[{"usage_kind": "documentation_example", "identifier": "imagen-4.0-generate-001"}],
        fail_closed=False,
        false_positive=False,
        change_kind="deprecation",
    )
    assert (status, reason) == ("watching", "docs_only")


def test_no_usage_stays_watching() -> None:
    status, reason = classify(
        identifiers=["gemini-2.0-flash"],
        hits=[],
        fail_closed=False,
        false_positive=False,
        change_kind="deprecation",
    )
    assert (status, reason) == ("watching", "no_usage")


def test_vertex_prefix_fails_closed() -> None:
    status, reason = classify(
        identifiers=["vertex/imagen-4.0-generate-001"],
        hits=[{"usage_kind": "runtime_source", "identifier": "vertex/imagen-4.0-generate-001"}],
        fail_closed=True,
        false_positive=False,
        change_kind="breaking_change",
    )
    assert (status, reason) == ("needs_you", "fail_closed")


def test_fal_ai_is_dismissed() -> None:
    status, reason = classify(
        identifiers=["fal-ai/imagen4/preview"],
        hits=[{"usage_kind": "runtime_source", "identifier": "fal-ai/imagen4/preview"}],
        fail_closed=False,
        false_positive=True,
        change_kind="other",
    )
    assert (status, reason) == ("dismissed", "false_positive")
    assert is_false_positive("fal-ai/imagen4/preview")
    assert not is_false_positive("imagen-4.0-generate-001")


def test_empty_identifiers_are_not_an_api_id() -> None:
    status, reason = classify(
        identifiers=[],
        hits=[],
        fail_closed=False,
        false_positive=False,
        change_kind="other",
    )
    assert (status, reason) == ("watching", "not_an_identifier")


def test_changelog_path_is_not_runtime() -> None:
    assert file_hit_kind("cli/CHANGELOG.md", "runtime_source") == "changelog"
    assert file_hit_kind("cli/src/cli/generate.ts", "runtime_source") == "runtime"
    assert file_hit_kind("README.md", "documentation_example") == "documentation"


def test_aggregate_hits_groups_by_path() -> None:
    repos, file_hits, file_count, counts, files = aggregate_hits(
        [
            {
                "identifier": "imagen-4.0-generate-001",
                "repository": "amelia751/egaki",
                "file_path": "cli/src/cli/model-catalog.ts",
                "usage_kind": "runtime_source",
            },
            {
                "identifier": "imagen-4.0-generate-001",
                "repository": "amelia751/egaki",
                "file_path": "cli/src/cli/model-catalog.ts",
                "usage_kind": "runtime_source",
            },
            {
                "identifier": "imagen-4.0-generate-001",
                "repository": "amelia751/egaki",
                "file_path": "README.md",
                "usage_kind": "documentation_example",
            },
        ]
    )
    assert repos == ["amelia751/egaki"]
    assert file_hits == 3
    assert file_count == 2
    assert counts["imagen-4.0-generate-001"] == 3
    assert files[0] == {"path": "cli/src/cli/model-catalog.ts", "hits": 2, "kind": "runtime"}
