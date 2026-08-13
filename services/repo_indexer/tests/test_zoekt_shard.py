"""Shard lifecycle: where a shard lives, and what an unreadable one means.

The naming and validation tests run everywhere. The tests that build a real
index skip when the Zoekt binaries are absent, which is also the condition
`test_fallback.py` covers from the other side.
"""

import json
import pathlib
import shutil
import subprocess

import pytest
from patchapi_repo_indexer.errors import ShardCorruptError, ZoektUnavailableError
from patchapi_repo_indexer.zoekt import shard as shard_module
from patchapi_repo_indexer.zoekt.shard import (
    MIN_SHARD_BYTES,
    SHARD_SUFFIX,
    ShardRef,
    binaries_available,
    delta_index,
    index_repository,
    shard_info,
    shard_path_for,
)

REPOSITORY = "patchapi-fixtures/repo-with-imagen"
BRANCH = "main"

needs_zoekt = pytest.mark.skipif(
    not binaries_available(), reason="zoekt-git-index / zoekt-index are not installed"
)
needs_no_zoekt = pytest.mark.skipif(
    binaries_available(), reason="zoekt binaries are installed, so absence cannot be observed"
)


@pytest.fixture
def index_dir(tmp_path, monkeypatch):
    directory = tmp_path / "shards"
    directory.mkdir()
    monkeypatch.setattr(shard_module, "ZOEKT_INDEX_DIR", str(directory))
    return directory


def write_shard(directory, name: str = "0", size: int = MIN_SHARD_BYTES) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}{SHARD_SUFFIX}").write_bytes(b"\0" * size)


def test_a_plain_tree_is_indexed_under_its_logical_name(fixture_repo, index_dir, monkeypatch):
    """`zoekt-index` must be told the repository name, not left to infer one.

    Left alone it names the repository after the directory it read, so a
    checkout in `/tmp/work` is indexed as `work` while queries ask for
    `repo:^owner/name$`. Nothing errors: the search just returns zero hits, and
    an affected repository reports clean.
    """
    captured: list[list[str]] = []
    monkeypatch.setattr(shard_module, "_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(shard_module, "_run", lambda command: captured.append(list(command)))
    monkeypatch.setattr(
        shard_module,
        "_validate_shard",
        lambda repository, branch, directory: shard_module.ShardInfo(
            repository, branch, directory, ("0.zoekt",), MIN_SHARD_BYTES
        ),
    )

    index_repository(fixture_repo, REPOSITORY, BRANCH)

    command = captured[0]
    assert "-meta" in command, "without -meta the shard is named after the directory"
    meta_path = pathlib.Path(command[command.index("-meta") + 1])
    assert json.loads(meta_path.read_text(encoding="utf-8"))["Name"] == REPOSITORY


def test_shard_path_is_stable_for_a_repository_and_branch(index_dir):
    assert shard_path_for(REPOSITORY, BRANCH) == shard_path_for(REPOSITORY, BRANCH)


def test_each_branch_gets_its_own_shard(index_dir):
    assert shard_path_for(REPOSITORY, "main") != shard_path_for(REPOSITORY, "release")


def test_two_projects_importing_one_repository_share_a_shard(index_dir):
    # The shard is keyed by (repository, branch) and nothing else, which is what
    # makes a repository imported by ten projects cost one index.
    assert shard_path_for(REPOSITORY, BRANCH) == shard_path_for(str(REPOSITORY), BRANCH)


def test_a_hostile_repository_name_cannot_escape_the_index_dir(index_dir):
    path = shard_path_for("../../etc", BRANCH)

    # The traversal survives as characters in a single directory name, never as
    # path segments, so the shard lands inside the index directory like any
    # other.
    assert path.parent == index_dir
    assert path.resolve().parent == index_dir.resolve()
    assert path.name not in (".", "..")


def test_missing_shard_is_unavailable_not_corrupt(index_dir):
    with pytest.raises(ZoektUnavailableError):
        shard_info(REPOSITORY, BRANCH)


def test_shard_dir_without_a_shard_file_is_corrupt(index_dir):
    shard_path_for(REPOSITORY, BRANCH).mkdir(parents=True)

    # Something indexed and left nothing readable behind. Returning an empty
    # result here would read as "this repository is not affected".
    with pytest.raises(ShardCorruptError):
        shard_info(REPOSITORY, BRANCH)


def test_truncated_shard_file_is_corrupt(index_dir):
    write_shard(shard_path_for(REPOSITORY, BRANCH), size=4)

    with pytest.raises(ShardCorruptError):
        shard_info(REPOSITORY, BRANCH)


def test_valid_shard_is_described(index_dir):
    write_shard(shard_path_for(REPOSITORY, BRANCH))

    info = shard_info(REPOSITORY, BRANCH)

    assert info.repository == REPOSITORY
    assert info.branch == BRANCH
    assert info.shard_files == (f"0{SHARD_SUFFIX}",)
    assert info.size_bytes >= MIN_SHARD_BYTES
    assert info.ref == ShardRef(REPOSITORY, BRANCH)


@needs_no_zoekt
def test_missing_binaries_are_unavailable_rather_than_a_crash(fixture_repo, index_dir):
    with pytest.raises(ZoektUnavailableError):
        index_repository(fixture_repo, REPOSITORY, BRANCH)


def test_indexing_a_file_is_refused(tmp_path, index_dir):
    target = tmp_path / "file.txt"
    target.write_text("imagen-4.0-generate-001\n", encoding="utf-8")

    with pytest.raises(ZoektUnavailableError):
        index_repository(target, REPOSITORY, BRANCH)


def test_a_failing_indexer_does_not_look_like_an_empty_repository(
    fixture_repo, index_dir, monkeypatch
):
    monkeypatch.setattr(shard_module, "_binary", lambda name: "/usr/bin/false")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "boom"),
    )

    with pytest.raises(ZoektUnavailableError, match="boom"):
        index_repository(fixture_repo, REPOSITORY, BRANCH)


def test_delta_of_only_deletions_keeps_the_existing_shard(tmp_path, index_dir):
    tree = tmp_path / "tree"
    tree.mkdir()
    write_shard(shard_path_for(REPOSITORY, BRANCH))

    info = delta_index(tree, REPOSITORY, BRANCH, ["src/gone.ts"])

    assert info.shard_files == (f"0{SHARD_SUFFIX}",)


@needs_zoekt
def test_full_index_builds_a_readable_shard(fixture_repo, index_dir):
    info = index_repository(fixture_repo, REPOSITORY, BRANCH)

    assert info.shard_files
    assert info.size_bytes > MIN_SHARD_BYTES
    assert shard_info(REPOSITORY, BRANCH) == info


@needs_zoekt
def test_delta_index_refreshes_an_existing_shard(tmp_path, index_dir):
    tree = tmp_path / "tree"
    (tree / "src").mkdir(parents=True)
    (tree / "src" / "image.ts").write_text(
        'export const MODEL = "imagen-4.0-generate-001";\n', encoding="utf-8"
    )
    index_repository(tree, REPOSITORY, BRANCH)

    (tree / "src" / "image.ts").write_text(
        'export const MODEL = "imagen-4.0-fast-generate-001";\n', encoding="utf-8"
    )
    info = delta_index(tree, REPOSITORY, BRANCH, ["src/image.ts"])

    assert info.shard_files


def test_binaries_available_agrees_with_the_path():
    assert binaries_available() == (
        shutil.which("zoekt-git-index") is not None and shutil.which("zoekt-index") is not None
    )
