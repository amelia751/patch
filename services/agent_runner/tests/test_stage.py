"""Staging a checkout into a sandbox.

The property under test is a cost, which is unusual but it is the reason this
code changed. A remote sandbox charges a round-trip per call, and staging used to
make one per file: 20 small files measured 9s, the largest wait before the
agent's first action once the run itself stopped waiting for a container. So the
assertion is on the *number of calls*, not on the bytes — a test that only
checked the files arrived would pass just as well against the slow version.

Everything else here guards what the fast path must not lose: the excluded
directories stay out, a binary file goes in (the old per-file path could not
carry one and skipped it, leaving the sandbox holding a tree that was not the
commit), and a local session still gets the plain copy with no archive at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from patchapi_agent_runner.remediation import checkout as checkout_module
from patchapi_agent_runner.remediation.checkout import Checkout, CheckoutError, stage


class PodSession:
    """A remote session: no real directory, so staging must go over `write_tree`."""

    def __init__(self) -> None:
        self.tree_calls: list[list[str]] = []
        self.file_calls: list[str] = []
        self.staged: dict[str, bytes] = {}

    @property
    def working_dir(self) -> str:
        # Deliberately not a Path. That is what tells `stage` this is remote.
        return "/sandbox/workspace"

    def write_tree(self, tree: Path, relpaths: list[str]) -> None:
        self.tree_calls.append(list(relpaths))
        for relpath in relpaths:
            self.staged[relpath] = (tree / relpath).read_bytes()

    def write_file(self, relpath: str, content: str) -> None:
        self.file_calls.append(relpath)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "checkout"
    (root / "lib").mkdir(parents=True)
    (root / "public").mkdir()
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / ".git").mkdir()

    (root / "lib" / "gemini.ts").write_text('export const MODEL = "gemini-2.0-flash";\n')
    (root / "package.json").write_text('{"name":"storygen"}\n')
    (root / "public" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02\xff")
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports=0\n")
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    return root


def _checkout(tree: Path) -> Checkout:
    return Checkout(tree=tree, repository="amelia751/storygen", base_sha="e" * 40, files=3)


def test_a_remote_sandbox_is_staged_in_one_round_trip(tree: Path) -> None:
    """The whole point. One call, whatever the file count."""
    session = PodSession()

    staged = stage(session, _checkout(tree))

    assert len(session.tree_calls) == 1
    assert session.file_calls == []
    assert staged == 3


def test_the_excluded_directories_do_not_reach_the_sandbox(tree: Path) -> None:
    session = PodSession()

    stage(session, _checkout(tree))

    assert sorted(session.staged) == ["lib/gemini.ts", "package.json", "public/logo.png"]


def test_a_binary_file_is_staged_rather_than_skipped(tree: Path) -> None:
    """`write_file` was text-only and dropped these, so the tree was not the commit."""
    session = PodSession()

    stage(session, _checkout(tree))

    assert session.staged["public/logo.png"] == b"\x89PNG\r\n\x1a\n\x00\x01\x02\xff"


def test_a_local_sandbox_is_copied_without_an_archive(tree: Path, tmp_path: Path) -> None:
    """A directory on the same disk has no round-trip to save."""

    class Localish:
        def __init__(self, workspace: Path) -> None:
            self.working_dir = workspace

        def write_tree(self, tree: Path, relpaths: list[str]) -> None:
            raise AssertionError("a local session should not archive its own disk")

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    staged = stage(Localish(workspace), _checkout(tree))

    assert staged == 3
    assert (workspace / "lib" / "gemini.ts").exists()
    assert not (workspace / "node_modules").exists()


def test_an_oversized_tree_is_refused_before_anything_is_sent(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The limit is a sandbox boundary, so it must hold on the bulk path too."""
    monkeypatch.setattr(checkout_module, "MAX_STAGED_FILES", 2)
    session = PodSession()

    with pytest.raises(CheckoutError):
        stage(session, _checkout(tree))

    assert session.tree_calls == []
