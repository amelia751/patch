"""Allocation guards, pinned checkout, and destruction that keeps evidence."""

import subprocess

import pytest

from sandbox.runner.config import Source
from sandbox.runner.workspace import (
    IsolationError,
    SourceError,
    allocate,
    destroy,
    new_run_id,
    populate,
    repository_root,
)


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def pinned_repo(tmp_path):
    """A two-commit local repository whose first commit is the pinned base."""

    repo = tmp_path / "origin"
    repo.mkdir()
    git("init", "--quiet", "--initial-branch=main", cwd=repo)
    git("config", "user.email", "runner@patchapi.invalid", cwd=repo)
    git("config", "user.name", "sandbox runner tests", cwd=repo)
    (repo / "model.txt").write_text("imagen-4.0-generate-001\n", encoding="utf-8")
    git("add", ".", cwd=repo)
    git("commit", "--quiet", "-m", "baseline", cwd=repo)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    (repo / "model.txt").write_text("drifted\n", encoding="utf-8")
    git("commit", "--quiet", "-am", "drift after the pin", cwd=repo)
    return repo, base


def test_allocation_refuses_a_sandbox_root_inside_the_checkout(repo_root, fixture_dir):
    with pytest.raises(IsolationError, match="inside the source repository"):
        allocate(sandbox_root=repo_root / "tmp", run_id=new_run_id(), source_path=fixture_dir)


def test_allocation_refuses_a_sandbox_root_containing_the_checkout(repo_root, fixture_dir):
    with pytest.raises(IsolationError, match="inside the sandbox root"):
        allocate(sandbox_root=repo_root.parent, run_id=new_run_id(), source_path=fixture_dir)


def test_allocation_refuses_a_reused_run_id(sandbox_root, fixture_dir):
    run_id = new_run_id()
    allocate(sandbox_root=sandbox_root, run_id=run_id, source_path=fixture_dir)
    with pytest.raises(IsolationError, match="unique"):
        allocate(sandbox_root=sandbox_root, run_id=run_id, source_path=fixture_dir)


def test_repository_root_finds_the_checkout(repo_root, fixture_dir):
    assert repository_root(fixture_dir) == repo_root


def test_copy_excludes_version_control_and_caches(sandbox_root, tmp_path):
    origin = tmp_path / "origin"
    (origin / ".git").mkdir(parents=True)
    (origin / ".git" / "config").write_text("secret remote\n", encoding="utf-8")
    (origin / "node_modules").mkdir()
    (origin / "keep.txt").write_text("kept\n", encoding="utf-8")
    space = allocate(sandbox_root=sandbox_root, run_id=new_run_id(), source_path=origin)

    populate(space, Source(kind="path", location="origin"), base_dir=tmp_path)

    assert (space.workspace / "keep.txt").read_text(encoding="utf-8") == "kept\n"
    assert not (space.workspace / ".git").exists()
    assert not (space.workspace / "node_modules").exists()


def test_git_source_checks_out_the_pinned_sha(sandbox_root, pinned_repo):
    repo, base = pinned_repo
    space = allocate(sandbox_root=sandbox_root, run_id=new_run_id(), source_path=None)

    resolved = populate(space, Source(kind="git", location=str(repo), sha=base), base_dir=repo)

    assert resolved == base
    pinned = (space.workspace / "model.txt").read_text(encoding="utf-8")
    assert pinned == "imagen-4.0-generate-001\n"


def test_unknown_sha_fails_closed(sandbox_root, pinned_repo):
    repo, _ = pinned_repo
    space = allocate(sandbox_root=sandbox_root, run_id=new_run_id(), source_path=None)
    absent = "0" * 40

    with pytest.raises(SourceError, match="pinned sha"):
        populate(space, Source(kind="git", location=str(repo), sha=absent), base_dir=repo)


def test_destroy_removes_the_workspace_and_keeps_the_evidence(sandbox_root, fixture_dir, repo_root):
    space = allocate(sandbox_root=sandbox_root, run_id=new_run_id(), source_path=fixture_dir)
    populate(
        space,
        Source(kind="path", location="sandbox/runner/testdata/image_service"),
        base_dir=repo_root,
    )
    (space.logs / "build.txt").write_text("log line\n", encoding="utf-8")

    destroy(space)

    assert not space.workspace.exists()
    assert (space.logs / "build.txt").read_text(encoding="utf-8") == "log line\n"
