"""The command the verifier and an operator both run."""

import json

from patchapi_repo_indexer.__main__ import main

NULL_SHA = "0" * 40
FIXTURE_REPO_FULL_NAME = "patchapi-fixtures/repo-with-imagen"
RETIRED_MODEL = "imagen-4.0-generate-001"


def run(root, out, *extra):
    return main(
        [
            "--root",
            str(root),
            "--repository",
            FIXTURE_REPO_FULL_NAME,
            "--sha",
            NULL_SHA,
            "--out",
            str(out),
            *extra,
        ]
    )


def test_writes_an_inventory_naming_the_retired_model(fixture_repo, tmp_path):
    out = tmp_path / "inventory" / "usages.json"

    assert run(fixture_repo, out) == 0

    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["repository"] == FIXTURE_REPO_FULL_NAME
    assert document["observed_sha"] == NULL_SHA
    assert document["scope"] == "full_tree"
    identifiers = {usage["identifier"] for usage in document["usages"]}
    assert RETIRED_MODEL in identifiers
    runtime = [
        usage
        for usage in document["usages"]
        if usage["file_path"] == "src/image.ts" and usage["usage_kind"] == "runtime_source"
    ]
    assert len(runtime) == 1
    assert runtime[0]["detection_layer"] == "A_DETERMINISTIC"


def test_empty_tree_writes_an_empty_inventory_and_succeeds(empty_repo, tmp_path):
    out = tmp_path / "usages.json"

    assert run(empty_repo, out) == 0

    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["usages"] == []


def test_output_is_byte_identical_across_runs(fixture_repo, tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"

    assert run(fixture_repo, first) == 0
    assert run(fixture_repo, second) == 0

    assert first.read_bytes() == second.read_bytes()


def test_explicit_identifiers_are_honoured(fixture_repo, tmp_path):
    out = tmp_path / "usages.json"

    assert run(fixture_repo, out, "--identifier", "gemini-3.5-flash") == 0

    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["watched_identifiers"] == ["gemini-3.5-flash"]


def test_changed_paths_produce_a_partial_inventory(fixture_repo, tmp_path):
    out = tmp_path / "usages.json"

    assert run(fixture_repo, out, "--changed-path", "src/image.ts") == 0

    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["scope"] == "changed_paths"
    assert document["files_scanned"] == 1


def test_missing_root_exits_non_zero(tmp_path, capsys):
    assert run(tmp_path / "not-here", tmp_path / "usages.json") == 2
    assert "FAIL:" in capsys.readouterr().err


def test_malformed_sha_exits_non_zero(fixture_repo, tmp_path):
    out = tmp_path / "usages.json"

    exit_code = main(
        [
            "--root",
            str(fixture_repo),
            "--repository",
            FIXTURE_REPO_FULL_NAME,
            "--sha",
            "nope",
            "--out",
            str(out),
        ]
    )

    assert exit_code == 2
    assert not out.exists()


def test_unknown_provider_exits_non_zero(fixture_repo, tmp_path):
    assert run(fixture_repo, tmp_path / "usages.json", "--provider", "acme") == 2


def test_inventory_goes_to_stdout_without_out(fixture_repo, capsys):
    exit_code = main(
        [
            "--root",
            str(fixture_repo),
            "--repository",
            FIXTURE_REPO_FULL_NAME,
            "--sha",
            NULL_SHA,
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert RETIRED_MODEL in {usage["identifier"] for usage in document["usages"]}
