"""Mirror, checkout and diff behaviour against real git repositories.

No network and no credentials: the "remote" is a temporary repository served
over `file://`, which exercises the same clone, fetch and worktree code paths
the GitHub URL takes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from patchapi_repo_indexer import config, git
from patchapi_repo_indexer.errors import UnsafePathError

REPOSITORY = "patchapi-fixtures/egaki"


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-c",
            "user.name=PatchAPI Test",
            "-c",
            "user.email=test@patchapi.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


@pytest.fixture(autouse=True)
def isolated_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the indexer at a throwaway workdir and remove every token from the env."""
    work = tmp_path / "workdir"
    monkeypatch.setattr(config, "INDEXER_WORKDIR", str(work))
    for name in git.TOKEN_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return work


@pytest.fixture
def source_repo(tmp_path: Path) -> dict[str, object]:
    """Two commits: the second edits one file, deletes another, and adds a third."""
    src = tmp_path / "source"
    src.mkdir()
    _git(src, "init", "--quiet", ".")

    (src / "src").mkdir()
    (src / "src" / "generate.ts").write_text(
        'export const MODEL = "imagen-4.0-generate-001";\n', encoding="utf-8"
    )
    (src / "legacy.ts").write_text('export const OLD = "imagen-4.0-ultra-generate-001";\n', "utf-8")
    (src / "README.md").write_text("# fixture\n", encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "--quiet", "-m", "first")
    base_sha = _git(src, "rev-parse", "HEAD")

    (src / "src" / "generate.ts").write_text(
        'export const MODEL = "gemini-3.1-flash-image";\n', encoding="utf-8"
    )
    (src / "legacy.ts").unlink()
    (src / "src" / "added.ts").write_text("export const ADDED = true;\n", encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "--quiet", "-m", "second")
    head_sha = _git(src, "rev-parse", "HEAD")

    return {"path": src, "url": src.as_uri(), "base": base_sha, "head": head_sha}


def test_changed_paths_lists_edits_additions_and_deletions(source_repo: dict[str, object]) -> None:
    paths = git.changed_paths(
        source_repo["path"], str(source_repo["base"]), str(source_repo["head"])
    )

    assert paths == ["legacy.ts", "src/added.ts", "src/generate.ts"]


def test_changed_paths_includes_a_deleted_file(source_repo: dict[str, object]) -> None:
    src = source_repo["path"]
    assert isinstance(src, Path)
    assert not (src / "legacy.ts").exists()

    paths = git.changed_paths(src, str(source_repo["base"]), str(source_repo["head"]))

    assert "legacy.ts" in paths


def test_changed_paths_reports_a_rename_as_delete_plus_add(source_repo: dict[str, object]) -> None:
    src = source_repo["path"]
    assert isinstance(src, Path)
    _git(src, "mv", "README.md", "docs.md")
    _git(src, "commit", "--quiet", "-m", "rename")
    renamed = _git(src, "rev-parse", "HEAD")

    paths = git.changed_paths(src, str(source_repo["head"]), renamed)

    assert paths == ["README.md", "docs.md"]


def test_changed_paths_is_sorted_and_unique(source_repo: dict[str, object]) -> None:
    paths = git.changed_paths(
        source_repo["path"], str(source_repo["base"]), str(source_repo["head"])
    )

    assert paths == sorted(paths)
    assert len(paths) == len(set(paths))
    assert all(not path.startswith("/") and "\\" not in path for path in paths)


def test_changed_paths_rejects_an_unknown_revision(source_repo: dict[str, object]) -> None:
    with pytest.raises(git.RevisionNotFoundError):
        git.changed_paths(source_repo["path"], "0" * 40, str(source_repo["head"]))


def test_changed_paths_rejects_a_non_sha_revision(source_repo: dict[str, object]) -> None:
    with pytest.raises(UnsafePathError):
        git.changed_paths(source_repo["path"], "HEAD~1", str(source_repo["head"]))


def test_ensure_checkout_materialises_the_requested_sha(source_repo: dict[str, object]) -> None:
    base = str(source_repo["base"])

    checkout = git.ensure_checkout(REPOSITORY, "main", base, remote_url=str(source_repo["url"]))

    # `legacy.ts` only exists at the first commit, so its presence proves the
    # checkout is the requested sha rather than the branch tip.
    assert (checkout / "legacy.ts").is_file()
    assert (checkout / "src" / "generate.ts").read_text(encoding="utf-8").count("imagen-4.0") == 1
    assert _git(checkout, "rev-parse", "HEAD") == base


def test_ensure_checkout_of_head_reflects_the_second_commit(source_repo: dict[str, object]) -> None:
    checkout = git.ensure_checkout(
        REPOSITORY, "main", str(source_repo["head"]), remote_url=str(source_repo["url"])
    )

    assert not (checkout / "legacy.ts").exists()
    assert (checkout / "src" / "added.ts").is_file()


def test_two_shas_of_one_repository_share_a_single_mirror(source_repo: dict[str, object]) -> None:
    url = str(source_repo["url"])
    first = git.ensure_checkout(REPOSITORY, "main", str(source_repo["base"]), remote_url=url)
    second = git.ensure_checkout(REPOSITORY, "main", str(source_repo["head"]), remote_url=url)

    assert first != second
    assert len(list(git.mirror_root().iterdir())) == 1


def test_ensure_checkout_is_idempotent(source_repo: dict[str, object]) -> None:
    url = str(source_repo["url"])
    first = git.ensure_checkout(REPOSITORY, "main", str(source_repo["head"]), remote_url=url)
    (first / "src" / "added.ts").unlink()
    second = git.ensure_checkout(REPOSITORY, "main", str(source_repo["head"]), remote_url=url)

    assert first == second
    # A surviving checkout is reused as-is; repairing it is `prune` + re-add, not
    # a silent re-materialisation of files a caller may have been reading.
    assert not (second / "src" / "added.ts").exists()


def test_ensure_checkout_rejects_an_unreachable_sha(source_repo: dict[str, object]) -> None:
    with pytest.raises(git.RevisionNotFoundError):
        git.ensure_checkout(REPOSITORY, "main", "0" * 40, remote_url=str(source_repo["url"]))


def test_checkout_stays_inside_the_workdir(
    source_repo: dict[str, object], isolated_workdir: Path
) -> None:
    checkout = git.ensure_checkout(
        REPOSITORY, "main", str(source_repo["head"]), remote_url=str(source_repo["url"])
    )

    assert checkout.resolve().is_relative_to(isolated_workdir.resolve())


@pytest.mark.parametrize(
    "repository",
    [
        "../../etc",
        "owner/../../etc",
        "owner/..",
        "/absolute/name",
        "owner/name/extra",
        "owner",
        "..",
        "-upload-pack/name",
        "owner/na me",
    ],
)
def test_ensure_checkout_refuses_path_escaping_repository_names(repository: str) -> None:
    with pytest.raises(UnsafePathError):
        git.ensure_checkout(repository, "main", "a" * 40)


def test_dot_prefixed_repository_names_are_accepted() -> None:
    # `owner/.github` is a real repository; the validator must not confuse a
    # leading dot with traversal.
    assert git.clone_url_for("remorses/.github").endswith("/remorses/.github.git")


@pytest.mark.parametrize("branch", ["--upload-pack=touch /tmp/pwn", "../main", "main..", "a b"])
def test_ensure_checkout_refuses_unsafe_branches(branch: str) -> None:
    with pytest.raises(UnsafePathError):
        git.ensure_checkout(REPOSITORY, branch, "a" * 40)


@pytest.mark.parametrize("sha", ["", "HEAD", "main", "../../etc/passwd", "zz" * 20])
def test_ensure_checkout_refuses_non_sha_revisions(sha: str) -> None:
    with pytest.raises(UnsafePathError):
        git.ensure_checkout(REPOSITORY, "main", sha)


def test_clone_url_is_derived_from_the_full_name() -> None:
    assert git.clone_url_for("remorses/egaki") == "https://github.com/remorses/egaki.git"


def test_no_credential_is_written_into_the_mirror_config(
    source_repo: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_fixture_token_value")
    git.ensure_checkout(
        REPOSITORY, "main", str(source_repo["head"]), remote_url=str(source_repo["url"])
    )

    mirror = git.mirror_root() / f"{git._slug(REPOSITORY)}.git"
    assert "ghs_fixture_token_value" not in (mirror / "config").read_text(encoding="utf-8")


def test_prune_checkouts_keeps_everything_under_the_limit(source_repo: dict[str, object]) -> None:
    checkout = git.ensure_checkout(
        REPOSITORY, "main", str(source_repo["head"]), remote_url=str(source_repo["url"])
    )

    git.prune_checkouts(1024 * 1024 * 1024)

    assert checkout.is_dir()
    assert list(git.mirror_root().iterdir())


def test_prune_checkouts_evicts_checkouts_before_mirrors(source_repo: dict[str, object]) -> None:
    url = str(source_repo["url"])
    old = git.ensure_checkout(REPOSITORY, "main", str(source_repo["base"]), remote_url=url)
    new = git.ensure_checkout(REPOSITORY, "main", str(source_repo["head"]), remote_url=url)
    os.utime(old, (1, 1))

    mirror_bytes = git._directory_size(git.mirror_root() / f"{git._slug(REPOSITORY)}.git")
    git.prune_checkouts(mirror_bytes + git._directory_size(new))

    assert not old.exists()
    assert new.is_dir()
    assert (git.mirror_root() / f"{git._slug(REPOSITORY)}.git").is_dir()


def test_prune_checkouts_drops_mirrors_when_checkouts_are_not_enough(
    source_repo: dict[str, object],
) -> None:
    checkout = git.ensure_checkout(
        REPOSITORY, "main", str(source_repo["head"]), remote_url=str(source_repo["url"])
    )

    git.prune_checkouts(0)

    assert not checkout.exists()
    assert not list(git.mirror_root().iterdir())


def test_prune_checkouts_on_an_empty_workdir_is_a_no_op() -> None:
    git.prune_checkouts(0)


def test_prune_checkouts_rejects_a_negative_budget() -> None:
    with pytest.raises(ValueError):
        git.prune_checkouts(-1)


def test_a_pruned_repository_can_be_checked_out_again(source_repo: dict[str, object]) -> None:
    url = str(source_repo["url"])
    git.ensure_checkout(REPOSITORY, "main", str(source_repo["head"]), remote_url=url)
    git.prune_checkouts(0)

    checkout = git.ensure_checkout(REPOSITORY, "main", str(source_repo["head"]), remote_url=url)

    assert (checkout / "src" / "added.ts").is_file()
